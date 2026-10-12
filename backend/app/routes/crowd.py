from datetime import date

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
)

from sqlalchemy.exc import SQLAlchemyError
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
from app.time_utils import serialize_utc


router = APIRouter(
    prefix="/api/crowd",
    tags=["Crowd Monitoring"]
)


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
        raise HTTPException(
            status_code=503,
            detail="Crowd reading could not be stored.",
        ) from error

    timestamp = reading.timestamp

    # ----------------------------------------
    # Response
    # ----------------------------------------

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
    db: Session = Depends(get_db)
):

    return get_today_summary(
        db
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
    db: Session = Depends(get_db)
):

    query = db.query(CongestionEvent)
    if room_id is not None:
        query = query.filter(CongestionEvent.room_id == room_id)
    events = (
        query
        .order_by(
            CongestionEvent.started_at.desc()
        )
        .limit(20)
        .all()
    )

    result = []

    for event in events:

        started_at = event.started_at
        ended_at = event.ended_at

        result.append({

            "id":
                event.id,

            "started_at":
                serialize_utc(started_at),

            "ended_at":
                serialize_utc(ended_at),

            "peak_crowd":
                event.peak_crowd,

            "threshold":
                event.threshold,

            "resolved":
                event.resolved,
            "camera_id": event.camera_id,
            "room_id": event.room_id,
        })

    return result


@router.get("/rooms/{room_id}/latest")
def room_latest_reading(room_id: int, db: Session = Depends(get_db)):
    reading = db.query(CrowdReading).filter(CrowdReading.room_id == room_id).order_by(CrowdReading.timestamp.desc()).first()
    if not reading:
        return None
    return {"id": reading.id, "person_count": reading.person_count, "threshold": reading.threshold,
            "status": reading.status, "camera_id": reading.camera_id, "room_id": reading.room_id,
            "timestamp": serialize_utc(reading.timestamp)}
