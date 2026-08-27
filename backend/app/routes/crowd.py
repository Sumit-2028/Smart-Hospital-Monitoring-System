from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.crowd import CrowdReading
from app.schemas.crowd import CrowdReadingCreate
from app.websocket.manager import manager

from app.services.congestion_service import (
    update_congestion_event
)

from app.services.crowd_service import (
    get_today_summary,
    get_daily_history,
    get_hourly_history
)

from app.models.crowd import (
    CrowdReading,
    CongestionEvent
)


router = APIRouter(
    prefix="/api/crowd",
    tags=["Crowd Monitoring"]
)


@router.post("/")
async def create_crowd_reading(
    data: CrowdReadingCreate,
    db: Session = Depends(get_db)
):

    # Determine status
    if data.person_count >= data.threshold:
        status = "CONGESTED"
    else:
        status = "NORMAL"

    # Save crowd reading
    reading = CrowdReading(
        person_count=data.person_count,
        threshold=data.threshold,
        status=status
    )

    db.add(reading)
    db.commit()
    db.refresh(reading)

    # Update congestion event
    event_status = update_congestion_event(
        db,
        data.person_count,
        data.threshold
    )

    # Response
    response = {
        "id": reading.id,
        "person_count": reading.person_count,
        "threshold": reading.threshold,
        "status": reading.status,
        "event": event_status,
        "timestamp": reading.timestamp.isoformat()
    }

    # Send live update to React
    await manager.broadcast(response)

    return response


@router.get("/today")
def today_summary(
    db: Session = Depends(get_db)
):

    return get_today_summary(db)


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


@router.get("/history/{selected_date}")
def hourly_history(
    selected_date: str,
    db: Session = Depends(get_db)
):

    return get_hourly_history(
        db,
        selected_date
    )



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

    return [
        {
            "id": event.id,
            "started_at": event.started_at.isoformat(),
            "ended_at": (
                event.ended_at.isoformat()
                if event.ended_at
                else None
            ),
            "peak_crowd": event.peak_crowd,
            "threshold": event.threshold,
            "resolved": event.resolved
        }
        for event in events
    ]