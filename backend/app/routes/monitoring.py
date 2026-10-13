from datetime import datetime, timezone
import os

import asyncio
import logging
import time

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import require_admin
from app.models.crowd import CongestionEvent, CrowdReading
from app.models.facility import Camera, Department, Doctor, Room
from app.time_utils import as_utc_naive, serialize_utc
from app.websocket.manager import manager
from app.services.frame_store import MAX_FRAME_BYTES, frame_store

router = APIRouter(prefix="/api/monitoring", tags=["Monitoring"])
logger = logging.getLogger(__name__)
FRAME_STREAM_INTERVAL_SECONDS = max(0.05, float(os.getenv("FRAME_STREAM_INTERVAL_SECONDS", "0.15")))
FRAME_STREAM_IDLE_TIMEOUT_SECONDS = max(5, int(os.getenv("FRAME_STREAM_IDLE_TIMEOUT_SECONDS", "30")))

CAMERA_STALE_AFTER_SECONDS = max(5, int(os.getenv("CAMERA_STALE_AFTER_SECONDS", "15")))
CROWD_READING_STALE_AFTER_SECONDS = max(5, int(os.getenv("CROWD_READING_STALE_AFTER_SECONDS", "30")))
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


def _crowd_status(room: Room, count: int) -> str:
    warning_threshold = max(1, round(room.capacity * room.warning_percentage / 100))
    if count >= room.capacity:
        return "CONGESTED"
    if count >= warning_threshold:
        return "WARNING"
    return "NORMAL"


def _hospital_summary(db: Session, now: datetime | None = None):
    """Build one deterministic, room-scoped snapshot for the dashboard.

    If a room has multiple active cameras, the newest valid reading from any
    assigned active camera is used. Counts are never summed across views of the
    same room because cross-camera identity deduplication is not available.
    """
    current_time = now or datetime.now(timezone.utc)
    rooms = db.query(Room).filter(Room.active.is_(True)).order_by(Room.name, Room.id).all()
    room_items = []
    total_count = 0
    complete_room_count = 0
    monitored_room_count = 0
    normal_room_count = 0
    congested_room_count = 0
    connected_camera_count = 0
    disconnected_camera_count = 0
    latest_timestamp = None

    for room in rooms:
        cameras = db.query(Camera).filter(
            Camera.room_id == room.id,
            Camera.active.is_(True),
        ).order_by(Camera.id).all()
        camera_by_id = {camera.id: camera for camera in cameras}
        camera_statuses = [_effective_camera_status(camera, current_time) for camera in cameras]
        connected_camera_count += sum(status == "CONNECTED" for status in camera_statuses)
        disconnected_camera_count += sum(status != "CONNECTED" for status in camera_statuses)
        if cameras:
            monitored_room_count += 1

        reading = None
        if camera_by_id:
            reading = db.query(CrowdReading).filter(
                CrowdReading.room_id == room.id,
                CrowdReading.camera_id.in_(camera_by_id),
                CrowdReading.person_count >= 0,
            ).order_by(CrowdReading.timestamp.desc(), CrowdReading.id.desc()).first()

        age_seconds = None
        fresh = False
        if reading and reading.timestamp:
            reading_time = reading.timestamp.replace(tzinfo=timezone.utc) if reading.timestamp.tzinfo is None else reading.timestamp
            age_seconds = max(0, (current_time - reading_time).total_seconds())
            fresh = age_seconds <= CROWD_READING_STALE_AFTER_SECONDS
            latest_timestamp = max(latest_timestamp, reading.timestamp) if latest_timestamp else reading.timestamp

        count = reading.person_count if fresh else None
        crowd_status = _crowd_status(room, count) if count is not None else None
        if fresh:
            complete_room_count += 1
            total_count += count
            if crowd_status == "NORMAL":
                normal_room_count += 1
            elif crowd_status == "CONGESTED":
                congested_room_count += 1

        selected_camera = camera_by_id.get(reading.camera_id) if reading else None
        room_items.append({
            "room_id": room.id,
            "room_name": room.name,
            "room_type": room.room_type,
            "department_id": room.department_id,
            "department_name": None,
            "capacity": room.capacity,
            "warning_percentage": room.warning_percentage,
            "warning_threshold": max(1, round(room.capacity * room.warning_percentage / 100)),
            "current_count": count,
            "occupancy_percentage": round((count / room.capacity) * 100, 1) if count is not None else None,
            "crowd_status": crowd_status,
            "monitoring_status": crowd_status or ("STALE" if reading else "UNAVAILABLE"),
            "camera_status": "UNAVAILABLE" if not cameras else ("CONNECTED" if "CONNECTED" in camera_statuses else camera_statuses[0]),
            "camera_count": len(cameras),
            "connected_camera_count": sum(status == "CONNECTED" for status in camera_statuses),
            "last_reading_at": serialize_utc(reading.timestamp) if reading else None,
            "last_successful_reading_at": serialize_utc(reading.timestamp) if reading else None,
            "reading_camera_id": selected_camera.id if selected_camera else None,
            "has_fresh_reading": fresh,
            "reading_age_seconds": round(age_seconds, 1) if age_seconds is not None else None,
            "active_alert_count": db.query(CongestionEvent).filter(
                CongestionEvent.room_id == room.id,
                CongestionEvent.resolved.is_(False),
                CongestionEvent.ended_at.is_(None),
            ).count(),
        })

    for item in room_items:
        department = db.get(Department, item["department_id"]) if item["department_id"] else None
        item["department_name"] = department.name if department else None

    incomplete_room_count = len(room_items) - complete_room_count
    return {
        "total_count": total_count,
        "configured_room_count": len(room_items),
        "monitored_room_count": monitored_room_count,
        "complete_room_count": complete_room_count,
        "incomplete_room_count": incomplete_room_count,
        "normal_room_count": normal_room_count,
        "congested_room_count": congested_room_count,
        "connected_camera_count": connected_camera_count,
        "disconnected_camera_count": disconnected_camera_count,
        "is_complete": incomplete_room_count == 0,
        "freshness_policy": {
            "stale_after_seconds": CROWD_READING_STALE_AFTER_SECONDS,
            "unavailable_rooms_are_excluded_from_total": True,
            "multiple_cameras_per_room": "newest_valid_reading_only",
        },
        "latest_reading_at": serialize_utc(latest_timestamp),
        "rooms": room_items,
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


@router.get("/summary")
def hospital_summary(db: Session = Depends(get_db)):
    """Return the current hospital-wide room-scoped crowd snapshot."""
    try:
        return _hospital_summary(db)
    except Exception:
        logger.exception("hospital crowd summary failed", extra={"operation": "hospital_summary"})
        raise HTTPException(status_code=503, detail="Hospital crowd summary is temporarily unavailable.")


@router.get("/rooms/{room_id}")
def room_detail(room_id: int, db: Session = Depends(get_db)):
    """Return the safe, room-scoped monitoring view used by the public dashboard."""
    room = db.query(Room).filter(Room.id == room_id, Room.active.is_(True)).first()
    if not room:
        raise HTTPException(status_code=404, detail="Active monitoring room not found")

    now = datetime.now(timezone.utc)
    department = db.get(Department, room.department_id) if room.department_id else None
    reading = db.query(CrowdReading).filter(
        CrowdReading.room_id == room.id,
    ).order_by(CrowdReading.timestamp.desc()).first()
    warning_threshold = max(1, round(room.capacity * room.warning_percentage / 100))
    count = reading.person_count if reading else 0
    status = "CONGESTED" if count >= room.capacity else "WARNING" if count >= warning_threshold else "NORMAL"
    cameras = db.query(Camera).filter(
        Camera.room_id == room.id,
        Camera.active.is_(True),
    ).order_by(Camera.name).all()
    doctor = db.query(Doctor).filter(
        Doctor.cabin_id == room.id,
        Doctor.active.is_(True),
    ).order_by(Doctor.name).first()

    return {
        "room_id": room.id,
        "room_name": room.name,
        "room_type": room.room_type,
        "department_id": room.department_id,
        "department_name": department.name if department else None,
        "capacity": room.capacity,
        "warning_percentage": room.warning_percentage,
        "warning_threshold": warning_threshold,
        "current_count": count,
        "status": status,
        "last_update": serialize_utc(reading.timestamp) if reading else None,
        "doctor": {
            "id": doctor.id,
            "name": doctor.name,
            "specialty": doctor.specialty,
            "available": doctor.available,
        } if doctor else None,
        "cameras": [_camera_payload(camera, now) for camera in cameras],
    }


@router.post("/internal/cameras/{camera_id}/frame", status_code=202)
def ingest_camera_frame(
    camera_id: int,
    request: Request,
    frame: bytes = Body(...),
    agent_token: str | None = Header(default=None, alias="X-Camera-Agent-Token"),
    db: Session = Depends(get_db),
):
    """Receive one encoded frame from the existing authenticated camera worker."""
    expected = os.getenv("CAMERA_AGENT_TOKEN")
    if not expected or agent_token != expected:
        raise HTTPException(status_code=401, detail="Camera agent authentication required")
    if request.headers.get("content-type", "").split(";", 1)[0].lower() != "image/jpeg":
        raise HTTPException(status_code=415, detail="Camera frames must be JPEG images")
    if len(frame) == 0 or len(frame) > MAX_FRAME_BYTES:
        raise HTTPException(status_code=413, detail="Camera frame is empty or too large")

    camera = db.query(Camera).filter(Camera.id == camera_id, Camera.active.is_(True)).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    room = db.query(Room).filter(Room.id == camera.room_id, Room.active.is_(True)).first()
    if not room:
        raise HTTPException(status_code=422, detail="Camera is not assigned to an active room")
    try:
        stored = frame_store.publish(camera.id, room.id, frame)
    except ValueError as error:
        raise HTTPException(status_code=413, detail=str(error)) from error
    logger.debug("camera frame accepted", extra={"camera_id": camera.id, "room_id": room.id, "frame_bytes": len(frame), "sequence": stored.sequence})
    return {"accepted": True, "camera_id": camera.id, "room_id": room.id, "sequence": stored.sequence}


async def _mjpeg_frames(camera_id: int, room_id: int):
    last_sequence = 0
    last_frame_at = time.monotonic()
    try:
        while True:
            frame = frame_store.latest(camera_id, room_id, last_sequence)
            if frame is not None:
                last_sequence = frame.sequence
                last_frame_at = time.monotonic()
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    + f"Content-Length: {len(frame.jpeg)}\r\n".encode("ascii")
                    + f"X-Frame-Sequence: {frame.sequence}\r\n".encode("ascii")
                    + f"X-Frame-Received-At: {frame.received_at.isoformat()}\r\n\r\n".encode("ascii")
                    + frame.jpeg
                    + b"\r\n"
                )
            elif time.monotonic() - last_frame_at > FRAME_STREAM_IDLE_TIMEOUT_SECONDS:
                logger.warning("camera stream idle; closing preview", extra={"camera_id": camera_id, "room_id": room_id})
                return
            await asyncio.sleep(FRAME_STREAM_INTERVAL_SECONDS)
    except asyncio.CancelledError:
        logger.debug("camera stream client disconnected", extra={"camera_id": camera_id, "room_id": room_id})
        raise
    except Exception:
        logger.exception("camera stream failed", extra={"camera_id": camera_id, "room_id": room_id})
        raise


@router.get("/rooms/{room_id}/cameras/{camera_id}/stream")
async def camera_stream(
    room_id: int,
    camera_id: int,
    _: object = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Stream frames from the worker-owned capture to an authorized browser viewer."""
    camera = db.query(Camera).filter(
        Camera.id == camera_id,
        Camera.room_id == room_id,
        Camera.active.is_(True),
    ).first()
    room = db.query(Room).filter(Room.id == room_id, Room.active.is_(True)).first()
    if not room or not camera:
        raise HTTPException(status_code=404, detail="Active room camera not found")
    return StreamingResponse(
        _mjpeg_frames(camera.id, room.id),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


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
