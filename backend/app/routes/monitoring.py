from datetime import datetime, timezone
import os

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.crowd import CrowdReading
from app.models.facility import Camera, Department, Room
from app.time_utils import as_utc_naive, serialize_utc
from app.websocket.manager import manager

router = APIRouter(prefix="/api/monitoring", tags=["Monitoring"])

CAMERA_STALE_AFTER_SECONDS = max(5, int(os.getenv("CAMERA_STALE_AFTER_SECONDS", "15")))
CAMERA_STATUSES = {"STARTING", "CONNECTED", "RECONNECTING", "DISCONNECTED", "ERROR", "STOPPED"}


class CameraHeartbeat(BaseModel):
    camera_id: int
    status: str = Field(min_length=3, max_length=20)
    last_frame_at: datetime | None = None
    message: str | None = Field(default=None, max_length=500)


def _effective_camera_status(camera: Camera, now: datetime | None = None) -> str:
    """Return the feed status that is safe to show to a dashboard user."""
    if camera.status == "CONNECTED":
        current_time = now or datetime.now(timezone.utc)
        if camera.last_frame_at is None:
            return "STALE"
        last_frame = camera.last_frame_at.replace(tzinfo=timezone.utc) if camera.last_frame_at.tzinfo is None else camera.last_frame_at
        if (current_time - last_frame).total_seconds() > CAMERA_STALE_AFTER_SECONDS:
            return "STALE"
    return camera.status


def _camera_payload(camera: Camera, now: datetime | None = None):
    return {
        "id": camera.id,
        "name": camera.name,
        "status": _effective_camera_status(camera, now),
        "raw_status": camera.status,
        "last_frame_at": serialize_utc(camera.last_frame_at),
        "status_updated_at": serialize_utc(camera.status_updated_at),
        "stale_after_seconds": CAMERA_STALE_AFTER_SECONDS,
    }


@router.get("/rooms")
def active_rooms(db: Session = Depends(get_db)):
    result = []
    now = datetime.now(timezone.utc)
    for room in db.query(Room).filter(Room.active.is_(True)).order_by(Room.name).all():
        camera = db.query(Camera).filter(Camera.room_id == room.id, Camera.active.is_(True)).first()
        department = db.get(Department, room.department_id) if room.department_id else None
        reading = db.query(CrowdReading).filter(CrowdReading.room_id == room.id).order_by(CrowdReading.timestamp.desc()).first()
        count = reading.person_count if reading else 0
        warning_threshold = max(1, round(room.capacity * room.warning_percentage / 100))
        status = "CONGESTED" if count >= room.capacity else "WARNING" if count >= warning_threshold else "NORMAL"
        result.append({"room_id": room.id, "room_name": room.name, "room_type": room.room_type,
                       "department_id": room.department_id, "department_name": department.name if department else None, "capacity": room.capacity,
                       "warning_percentage": room.warning_percentage, "current_count": count,
                       "status": status, "camera": _camera_payload(camera, now) if camera else None,
                       "last_update": serialize_utc(reading.timestamp) if reading else None})
    return result


@router.get("/cameras")
def camera_statuses(db: Session = Depends(get_db)):
    """Public status-only view; source URLs are intentionally excluded."""
    now = datetime.now(timezone.utc)
    return [{"id": c.id, "room_id": c.room_id, "active": c.active, **_camera_payload(c, now)}
            for c in db.query(Camera).order_by(Camera.name).all()]


@router.get("/internal/cameras")
def internal_camera_config(agent_token: str | None = Header(default=None, alias="X-Camera-Agent-Token"), db: Session = Depends(get_db)):
    expected = os.getenv("CAMERA_AGENT_TOKEN")
    if not expected or agent_token != expected:
        raise HTTPException(status_code=401, detail="Camera agent authentication required")
    return [{"id": c.id, "name": c.name, "source_type": c.source_type, "source": c.source,
             "room_id": c.room_id, "room_name": c.room.name if hasattr(c, "room") else None,
             "processing_interval": c.processing_interval}
            for c in db.query(Camera).filter(Camera.active.is_(True)).order_by(Camera.id).all()]


@router.post("/internal/heartbeat")
async def camera_heartbeat(data: CameraHeartbeat, agent_token: str | None = Header(default=None, alias="X-Camera-Agent-Token"), db: Session = Depends(get_db)):
    expected = os.getenv("CAMERA_AGENT_TOKEN")
    if not expected or agent_token != expected:
        raise HTTPException(status_code=401, detail="Camera agent authentication required")
    camera = db.get(Camera, data.camera_id)
    if not camera or not camera.active:
        raise HTTPException(status_code=404, detail="Camera not found")
    if data.status not in CAMERA_STATUSES:
        raise HTTPException(status_code=422, detail="Unsupported camera status")
    camera.status = data.status
    camera.status_updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    if data.last_frame_at is not None:
        camera.last_frame_at = as_utc_naive(data.last_frame_at)
    db.commit()
    room = db.get(Room, camera.room_id)
    payload = {
        "event_type": "camera.status",
        "schema_version": 1,
        "camera_id": camera.id,
        "room_id": camera.room_id,
        "room_name": room.name if room else None,
        "camera_status": _effective_camera_status(camera),
        "raw_camera_status": camera.status,
        "last_frame_at": serialize_utc(camera.last_frame_at),
        "timestamp": serialize_utc(camera.status_updated_at),
    }
    await manager.broadcast(payload)
    return {"ok": True, "camera": _camera_payload(camera)}
