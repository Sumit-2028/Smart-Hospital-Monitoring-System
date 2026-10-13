from datetime import date, datetime, timezone
import logging

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
)

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.database import get_db

from app.models.crowd import (
    CrowdReading,
    CongestionEvent
)
from app.models.facility import Camera, Room

from app.schemas.crowd import (
    CrowdReadingCreate
)

from app.websocket.manager import manager

from app.services.congestion_service import (
    update_congestion_event
)

from app.services.crowd_service import (
    get_latest_reading,
    get_today_summary,
    get_daily_history,
    get_hourly_history
)
from app.time_utils import ist_day_bounds_utc_naive, serialize_utc


router = APIRouter(
    prefix="/api/crowd",
    tags=["Crowd Monitoring"]
)
logger = logging.getLogger(__name__)


def _event_payload(event, room_name=None, current_count=None, now=None):
    current_time = now or datetime.now(timezone.utc)
    started_at = event.started_at
    ended_at = event.ended_at
    end_for_duration = ended_at or current_time.replace(tzinfo=None)
    if started_at.tzinfo is None and end_for_duration.tzinfo is not None:
        end_for_duration = end_for_duration.replace(tzinfo=None)
    duration_seconds = max(0, int((end_for_duration - started_at).total_seconds()))
    return {
        "id": event.id,
        "room_id": event.room_id,
        "room_name": room_name,
        "camera_id": event.camera_id,
        "peak_crowd": event.peak_crowd,
        "current_count": current_count,
        "threshold": event.threshold,
        "started_at": serialize_utc(started_at),
        "ended_at": serialize_utc(ended_at),
        "duration_seconds": duration_seconds,
        "duration_minutes": round(duration_seconds / 60, 1),
        "resolved": event.resolved,
        "status": "RESOLVED" if event.resolved else "ACTIVE",
    }


def _event_rows(db, room_id=None, status=None, start_date=None, end_date=None, offset=0, limit=20):
    if status and status.upper() not in {"ACTIVE", "RESOLVED", "ALL"}:
        raise HTTPException(status_code=422, detail="status must be ACTIVE, RESOLVED, or ALL")
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must not be after end_date")

    query = db.query(CongestionEvent, Room.name.label("room_name")).outerjoin(
        Room, Room.id == CongestionEvent.room_id
    )
    if room_id is not None:
        query = query.filter(CongestionEvent.room_id == room_id)
    if status and status.upper() != "ALL":
        query = query.filter(CongestionEvent.resolved.is_(status.upper() == "RESOLVED"))
    if start_date:
        start, _ = ist_day_bounds_utc_naive(start_date)
        query = query.filter(CongestionEvent.started_at >= start)
    if end_date:
        _, end = ist_day_bounds_utc_naive(end_date)
        query = query.filter(CongestionEvent.started_at < end)

    total = query.with_entities(func.count(CongestionEvent.id)).scalar() or 0
    rows = query.order_by(CongestionEvent.started_at.desc(), CongestionEvent.id.desc()).offset(offset).limit(limit).all()
    return total, rows


def _active_event_rows(db, room_id=None, limit=100):
    latest_reading = db.query(
        CrowdReading.room_id.label("latest_room_id"),
        CrowdReading.camera_id.label("latest_camera_id"),
        func.max(CrowdReading.timestamp).label("latest_timestamp"),
    ).group_by(CrowdReading.room_id, CrowdReading.camera_id).subquery()
    query = db.query(
        CongestionEvent,
        Room.name.label("room_name"),
        CrowdReading.person_count.label("current_count"),
        CrowdReading.timestamp.label("current_reading_timestamp"),
    ).outerjoin(Room, Room.id == CongestionEvent.room_id).outerjoin(
        latest_reading,
        or_(
            and_(
                latest_reading.c.latest_room_id == CongestionEvent.room_id,
                latest_reading.c.latest_camera_id == CongestionEvent.camera_id,
            ),
            and_(
                latest_reading.c.latest_room_id.is_(None),
                latest_reading.c.latest_camera_id.is_(None),
                CongestionEvent.room_id.is_(None),
                CongestionEvent.camera_id.is_(None),
            ),
        ),
    ).outerjoin(
        CrowdReading,
        and_(
            CrowdReading.timestamp == latest_reading.c.latest_timestamp,
            or_(
                and_(
                    CrowdReading.room_id == latest_reading.c.latest_room_id,
                    CrowdReading.camera_id == latest_reading.c.latest_camera_id,
                ),
                and_(
                    CrowdReading.room_id.is_(None),
                    CrowdReading.camera_id.is_(None),
                    latest_reading.c.latest_room_id.is_(None),
                    latest_reading.c.latest_camera_id.is_(None),
                ),
            ),
        ),
    ).filter(CongestionEvent.resolved.is_(False), CongestionEvent.ended_at.is_(None))
    if room_id is not None:
        query = query.filter(CongestionEvent.room_id == room_id)
    total = query.with_entities(func.count(CongestionEvent.id)).scalar() or 0
    rows = query.order_by(CongestionEvent.started_at.desc(), CongestionEvent.id.desc()).all()
    unique_rows = []
    seen_scopes = set()
    for row in rows:
        event = row[0]
        scope = (event.room_id, event.camera_id) if event.room_id is not None else (None, None)
        if scope in seen_scopes:
            continue
        seen_scopes.add(scope)
        unique_rows.append(row)
        if len(unique_rows) >= limit:
            break
    return len(unique_rows), unique_rows


def _active_alert_payload(event, room_name, current_count, current_reading_timestamp):
    """Serialize an active event without presenting an old reading as current."""
    has_current_reading = (
        current_reading_timestamp is not None
        and current_reading_timestamp >= event.started_at
    )
    payload = _event_payload(
        event,
        room_name,
        current_count if has_current_reading else None,
    )
    payload["current_reading_timestamp"] = serialize_utc(current_reading_timestamp)
    payload["current_reading_is_stale"] = not has_current_reading
    return payload


# ==================================================
# CREATE CROWD READING
# ==================================================

@router.post("/")
async def create_crowd_reading(
    data: CrowdReadingCreate,
    db: Session = Depends(get_db)
):

    camera = None
    room = None
    if data.camera_id is not None:
        camera = db.query(Camera).filter(Camera.id == data.camera_id, Camera.active.is_(True)).first()
        if not camera:
            raise HTTPException(status_code=422, detail="Camera is not registered or active")
        room = db.query(Room).filter(Room.id == camera.room_id, Room.active.is_(True)).first()
        if not room:
            raise HTTPException(status_code=422, detail="Camera is not assigned to an active room")
        threshold = max(1, round(room.capacity * room.warning_percentage / 100))
        congestion_threshold = room.capacity
        status = "CONGESTED" if data.person_count >= congestion_threshold else "WARNING" if data.person_count >= threshold else "NORMAL"
    else:
        if data.threshold is None:
            raise HTTPException(status_code=422, detail="threshold is required for legacy readings")
        threshold = data.threshold
        status = "CONGESTED" if data.person_count >= threshold else "NORMAL"

    reading = CrowdReading(
        person_count=data.person_count,
        threshold=threshold,
        camera_id=camera.id if camera else None,
        room_id=room.id if room else None,
        status=status
    )

    try:
        # Flush gives the event the same timestamp as its triggering reading.
        # The reading and event transition are committed atomically.
        db.add(reading)
        db.flush()

        event_status = update_congestion_event(
            db,
            data.person_count,
            congestion_threshold if room else threshold,
            now=reading.timestamp,
            commit=False,
            room_id=room.id if room else None,
            camera_id=camera.id if camera else None,
        )
        db.commit()
        db.refresh(reading)
    except SQLAlchemyError as error:
        db.rollback()
        logger.exception(
            "crowd reading transaction failed",
            extra={"camera_id": data.camera_id, "room_id": room.id if room else None},
        )
        raise HTTPException(
            status_code=503,
            detail="Crowd reading could not be stored.",
        ) from error

    timestamp = reading.timestamp
    logger.info(
        "crowd reading persisted",
        extra={
            "camera_id": reading.camera_id,
            "room_id": reading.room_id,
            "person_count": reading.person_count,
            "event_transition": event_status,
        },
    )

    # ----------------------------------------
    # Response
    # ----------------------------------------

    event_query = db.query(CongestionEvent).filter(CongestionEvent.room_id == (room.id if room else None))
    if event_status == "ENDED":
        event = event_query.filter(CongestionEvent.ended_at == reading.timestamp).order_by(CongestionEvent.id.desc()).first()
    else:
        event = event_query.filter(CongestionEvent.resolved.is_(False), CongestionEvent.ended_at.is_(None)).order_by(CongestionEvent.started_at.desc()).first()
    event_details = _event_payload(event, room.name if room else None, data.person_count) if event else None

    response = {

        "id":
            reading.id,

        "person_count":
            reading.person_count,

        "threshold":
            reading.threshold,

        "camera_id": reading.camera_id,
        "room_id": reading.room_id,

        "status":
            reading.status,

        "event":
            event_status,

        "event_id": event.id if event else None,

        "event_details": event_details,

        "timestamp":
            serialize_utc(timestamp)
    }

    response.update({
        "event_type": "crowd.reading",
        "schema_version": 1,
        "room_name": room.name if room else None,
        "capacity": room.capacity if room else None,
        "warning_percentage": room.warning_percentage if room else None,
        "camera_status": camera.status if camera else None,
    })

    # ----------------------------------------
    # WebSocket broadcast
    # ----------------------------------------

    await manager.broadcast(
        response
    )

    if event_details:
        lifecycle_type = {
            "STARTED": "congestion.started",
            "ONGOING": "congestion.updated",
            "ENDED": "congestion.resolved",
        }.get(event_status)
        if lifecycle_type:
            await manager.broadcast({
                "event_type": lifecycle_type,
                "schema_version": 1,
                "timestamp": serialize_utc(timestamp),
                "current_count": data.person_count,
                "event": event_details,
            })

    return response


@router.get("/latest")
def latest_crowd_reading(db: Session = Depends(get_db)):
    """Return the latest persisted reading for dashboard hydration."""

    return get_latest_reading(db)


# ==================================================
# TODAY SUMMARY
# ==================================================

@router.get("/today")
def today_summary(
    room_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db)
):

    return get_today_summary(
        db,
        room_id=room_id,
    )


# ==================================================
# DAILY HISTORY
# ==================================================

@router.get("/history")
def crowd_history(
    days: int = Query(
        default=7,
        ge=1,
        le=90
    ),
    room_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db)
):

    return get_daily_history(
        db,
        days,
        room_id=room_id,
    )


# ==================================================
# HOURLY HISTORY
# ==================================================

@router.get(
    "/history/{selected_date}"
)
def hourly_history(
    selected_date: date,
    room_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db)
):

    return get_hourly_history(
        db,
        selected_date,
        room_id=room_id,
    )


# ==================================================
# CONGESTION EVENTS
# ==================================================

@router.get("/events")
def congestion_events(
    room_id: int | None = Query(default=None, ge=1),
    status: str | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    _, rows = _event_rows(db, room_id, status, start_date, end_date, limit=limit)
    return [_event_payload(event, room_name) for event, room_name in rows]


@router.get("/alerts/active")
def active_congestion_alerts(
    room_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=100, ge=1, le=100),
    db: Session = Depends(get_db),
):
    total, rows = _active_event_rows(db, room_id=room_id, limit=limit)
    return {
        "items": [
            _active_alert_payload(event, room_name, current_count, current_reading_timestamp)
            for event, room_name, current_count, current_reading_timestamp in rows
        ],
        "total": total,
    }


@router.get("/events/history")
def congestion_event_history(
    room_id: int | None = Query(default=None, ge=1),
    status: str | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    total, rows = _event_rows(db, room_id, status, start_date, end_date, offset, limit)
    return {
        "items": [_event_payload(event, room_name) for event, room_name in rows],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/events/{event_id}")
def congestion_event_detail(event_id: int, db: Session = Depends(get_db)):
    row = db.query(CongestionEvent, Room.name.label("room_name")).outerjoin(
        Room, Room.id == CongestionEvent.room_id
    ).filter(CongestionEvent.id == event_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Congestion event not found")
    return _event_payload(row[0], row[1])


@router.get("/rooms/{room_id}/latest")
def room_latest_reading(room_id: int, db: Session = Depends(get_db)):
    reading = db.query(CrowdReading).filter(CrowdReading.room_id == room_id).order_by(CrowdReading.timestamp.desc()).first()
    if not reading:
        return None
    return {"id": reading.id, "person_count": reading.person_count, "threshold": reading.threshold,
            "status": reading.status, "camera_id": reading.camera_id, "room_id": reading.room_id,
            "timestamp": serialize_utc(reading.timestamp)}
