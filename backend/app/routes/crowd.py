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

    status = "CONGESTED" if data.person_count >= data.threshold else "NORMAL"

    reading = CrowdReading(
        person_count=data.person_count,
        threshold=data.threshold,
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
            data.threshold,
            now=reading.timestamp,
            commit=False,
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

        "status":
            reading.status,

        "event":
            event_status,

        "timestamp":
            serialize_utc(timestamp)
    }

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
    db: Session = Depends(get_db)
):

    return get_daily_history(
        db,
        days
    )


# ==================================================
# HOURLY HISTORY
# ==================================================

@router.get(
    "/history/{selected_date}"
)
def hourly_history(
    selected_date: date,
    db: Session = Depends(get_db)
):

    return get_hourly_history(
        db,
        selected_date
    )


# ==================================================
# CONGESTION EVENTS
# ==================================================

@router.get("/events")
def congestion_events(
    db: Session = Depends(get_db)
):

    events = (
        db.query(CongestionEvent)
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
                event.resolved
        })

    return result
