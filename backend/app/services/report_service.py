import csv
import io
import logging
from datetime import date, datetime, timedelta

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models.crowd import CongestionEvent, CrowdReading
from app.models.facility import Camera, Room
from app.time_utils import as_utc_naive, ist_day_bounds_utc_naive, serialize_utc, utc_now_naive, utc_to_ist

logger = logging.getLogger(__name__)

CROWD_READING_HEADERS = [
    "reading_id", "timestamp", "room_id", "room_name", "camera_id", "camera_name",
    "person_count", "threshold", "status",
]
EVENT_HEADERS = [
    "event_id", "room_id", "room_name", "camera_id", "camera_name", "started_at",
    "ended_at", "peak_crowd", "threshold", "status", "duration_seconds", "duration_minutes",
]
SUMMARY_HEADERS = [
    "date", "room_id", "room_name", "reading_count", "average_crowd", "peak_crowd",
    "minimum_crowd", "congestion_event_count", "total_congestion_duration_seconds",
    "total_congestion_duration_minutes",
]

TEXT_COLUMNS = {
    "room_name", "camera_name", "status", "date",
}


def csv_value(value, column):
    """Convert a value to CSV-safe text without changing the database value."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return serialize_utc(value)
    if isinstance(value, float):
        return f"{value:.2f}"
    text = str(value)
    if column in TEXT_COLUMNS and text[:1] in {"=", "+", "-", "@"}:
        return f"'{text}"
    return text


def csv_stream(headers, rows):
    """Yield CSV chunks incrementally so exports do not require one large buffer."""
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(headers)
    yield buffer.getvalue()
    for row in rows:
        buffer.seek(0)
        buffer.truncate(0)
        writer.writerow([csv_value(row.get(column), column) for column in headers])
        yield buffer.getvalue()


def iter_crowd_reading_rows(db: Session, start_date=None, end_date=None, room_id=None, camera_id=None):
    query = db.query(CrowdReading, Room.name.label("room_name"), Camera.name.label("camera_name")).outerjoin(
        Room, Room.id == CrowdReading.room_id
    ).outerjoin(Camera, Camera.id == CrowdReading.camera_id)
    if start_date:
        start, _ = ist_day_bounds_utc_naive(start_date)
        query = query.filter(CrowdReading.timestamp >= start)
    if end_date:
        _, end = ist_day_bounds_utc_naive(end_date)
        query = query.filter(CrowdReading.timestamp < end)
    if room_id is not None:
        query = query.filter(CrowdReading.room_id == room_id)
    if camera_id is not None:
        query = query.filter(CrowdReading.camera_id == camera_id)
    query = query.order_by(CrowdReading.timestamp, CrowdReading.id).yield_per(1000)
    for reading, room_name, camera_name in query:
        yield {
            "reading_id": reading.id,
            "timestamp": reading.timestamp,
            "room_id": reading.room_id,
            "room_name": room_name,
            "camera_id": reading.camera_id,
            "camera_name": camera_name,
            "person_count": reading.person_count,
            "threshold": reading.threshold,
            "status": reading.status,
        }


def iter_event_rows(db: Session, start_date=None, end_date=None, room_id=None, camera_id=None, status="ALL"):
    query = db.query(CongestionEvent, Room.name.label("room_name"), Camera.name.label("camera_name")).outerjoin(
        Room, Room.id == CongestionEvent.room_id
    ).outerjoin(Camera, Camera.id == CongestionEvent.camera_id)
    if start_date:
        start, _ = ist_day_bounds_utc_naive(start_date)
        query = query.filter(CongestionEvent.started_at >= start)
    if end_date:
        _, end = ist_day_bounds_utc_naive(end_date)
        query = query.filter(CongestionEvent.started_at < end)
    if room_id is not None:
        query = query.filter(CongestionEvent.room_id == room_id)
    if camera_id is not None:
        query = query.filter(CongestionEvent.camera_id == camera_id)
    if status != "ALL":
        query = query.filter(CongestionEvent.resolved.is_(status == "RESOLVED"))
    now = utc_now_naive()
    for event, room_name, camera_name in query.order_by(CongestionEvent.started_at, CongestionEvent.id).yield_per(1000):
        ended_at = event.ended_at or now
        duration_seconds = max(0, int((ended_at - event.started_at).total_seconds()))
        yield {
            "event_id": event.id,
            "room_id": event.room_id,
            "room_name": room_name,
            "camera_id": event.camera_id,
            "camera_name": camera_name,
            "started_at": event.started_at,
            "ended_at": event.ended_at,
            "peak_crowd": event.peak_crowd,
            "threshold": event.threshold,
            "status": "RESOLVED" if event.resolved else "ACTIVE",
            "duration_seconds": duration_seconds,
            "duration_minutes": round(duration_seconds / 60, 2),
        }


def iter_daily_summary_rows(db: Session, start_date: date, end_date: date, room_id=None, camera_id=None):
    start_utc, _ = ist_day_bounds_utc_naive(start_date)
    _, end_utc = ist_day_bounds_utc_naive(end_date)
    summary = {}
    readings = db.query(CrowdReading, Room.name.label("room_name")).outerjoin(
        Room, Room.id == CrowdReading.room_id
    ).filter(
        CrowdReading.timestamp >= start_utc,
        CrowdReading.timestamp < end_utc,
    )
    if room_id is not None:
        readings = readings.filter(CrowdReading.room_id == room_id)
    if camera_id is not None:
        readings = readings.filter(CrowdReading.camera_id == camera_id)
    for reading, room_name in readings.order_by(CrowdReading.timestamp, CrowdReading.id).yield_per(1000):
        day = utc_to_ist(reading.timestamp).date()
        key = (day, reading.room_id, room_name)
        values = summary.setdefault(key, {"counts": [], "event_count": 0, "duration_seconds": 0})
        values["counts"].append(reading.person_count)

    events = db.query(CongestionEvent, Room.name.label("room_name")).outerjoin(
        Room, Room.id == CongestionEvent.room_id
    ).filter(
        CongestionEvent.started_at < end_utc,
        or_(CongestionEvent.ended_at.is_(None), CongestionEvent.ended_at > start_utc),
    )
    if room_id is not None:
        events = events.filter(CongestionEvent.room_id == room_id)
    if camera_id is not None:
        events = events.filter(CongestionEvent.camera_id == camera_id)
    now = utc_now_naive()
    cursor = start_date
    days = []
    while cursor <= end_date:
        days.append(cursor)
        cursor += timedelta(days=1)
    for event, room_name in events.order_by(CongestionEvent.started_at, CongestionEvent.id).yield_per(1000):
        event_end = event.ended_at or now
        event_start_ist = utc_to_ist(event.started_at).date()
        for day in days:
            day_start, day_end = ist_day_bounds_utc_naive(day)
            overlap_start = max(event.started_at, day_start)
            overlap_end = min(event_end, day_end)
            if overlap_end <= overlap_start:
                continue
            key = (day, event.room_id, room_name)
            values = summary.setdefault(key, {"counts": [], "event_count": 0, "duration_seconds": 0})
            values["duration_seconds"] += int((overlap_end - overlap_start).total_seconds())
            if event_start_ist == day:
                values["event_count"] += 1

    for (day, current_room_id, room_name), values in sorted(summary.items()):
        counts = values["counts"]
        yield {
            "date": day.isoformat(),
            "room_id": current_room_id,
            "room_name": room_name,
            "reading_count": len(counts),
            "average_crowd": round(sum(counts) / len(counts), 2) if counts else None,
            "peak_crowd": max(counts) if counts else None,
            "minimum_crowd": min(counts) if counts else None,
            "congestion_event_count": values["event_count"],
            "total_congestion_duration_seconds": values["duration_seconds"],
            "total_congestion_duration_minutes": round(values["duration_seconds"] / 60, 2),
        }
