from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.crowd import CrowdReading
from app.schemas.crowd import CrowdReadingCreate
from app.websocket.manager import manager


router = APIRouter(
    prefix="/api/crowd",
    tags=["Crowd Monitoring"]
)


@router.post("/")
async def create_crowd_reading(
    data: CrowdReadingCreate,
    db: Session = Depends(get_db)
):

    if data.person_count >= data.threshold:
        status = "CONGESTED"
    else:
        status = "NORMAL"

    reading = CrowdReading(
        person_count=data.person_count,
        threshold=data.threshold,
        status=status
    )

    db.add(reading)
    db.commit()
    db.refresh(reading)

    response = {
        "id": reading.id,
        "person_count": reading.person_count,
        "threshold": reading.threshold,
        "status": reading.status,
        "timestamp": reading.timestamp.isoformat()
    }

    await manager.broadcast(response)

    return response