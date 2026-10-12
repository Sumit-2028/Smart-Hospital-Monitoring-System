import logging
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.auth import require_admin
from app.database import get_db
from app.models.facility import AdminUser, Camera, Room
from app.services.audit_service import add_audit
from app.services.report_service import (
    CROWD_READING_HEADERS,
    EVENT_HEADERS,
    SUMMARY_HEADERS,
    csv_stream,
    iter_crowd_reading_rows,
    iter_daily_summary_rows,
    iter_event_rows,
)
from app.time_utils import utc_to_ist

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/reports", tags=["Reports"])


def _validate_filters(db, start_date, end_date, room_id, camera_id):
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must not be after end_date")
    if room_id is not None and not db.get(Room, room_id):
        raise HTTPException(status_code=404, detail="Room not found")
    if camera_id is not None:
        camera = db.get(Camera, camera_id)
        if not camera:
            raise HTTPException(status_code=404, detail="Camera not found")
        if room_id is not None and camera.room_id != room_id:
            raise HTTPException(status_code=422, detail="Camera is not assigned to the selected room")


def _filename(report_name, start_date, end_date):
    date_part = "all-dates" if not start_date and not end_date else f"{start_date or 'start'}-to-{end_date or 'end'}"
    return f"{report_name}-{date_part}.csv"


def _csv_response(report_name, headers, rows, start_date, end_date):
    filename = _filename(report_name, start_date, end_date)
    return StreamingResponse(
        csv_stream(headers, rows),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _record_export(db, actor, report_name, start_date, end_date, room_id, camera_id, status=None):
    try:
        add_audit(
            db,
            actor=actor,
            action="REPORT_EXPORTED",
            outcome="SUCCESS",
            resource_type="REPORT",
            resource_id=report_name,
            context={
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None,
                "room_id": room_id,
                "camera_id": camera_id,
                "status": status,
            },
        )
        db.commit()
    except SQLAlchemyError as error:
        db.rollback()
        logger.exception("report export audit could not be persisted", extra={"actor_id": actor.id, "report": report_name})
        raise HTTPException(status_code=503, detail="Report export could not be recorded.") from error


@router.get("/crowd-readings.csv")
def export_crowd_readings(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    room_id: int | None = Query(default=None, ge=1),
    camera_id: int | None = Query(default=None, ge=1),
    actor: AdminUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _validate_filters(db, start_date, end_date, room_id, camera_id)
    _record_export(db, actor, "crowd-readings", start_date, end_date, room_id, camera_id)
    return _csv_response("crowd-readings", CROWD_READING_HEADERS, iter_crowd_reading_rows(db, start_date, end_date, room_id, camera_id), start_date, end_date)


@router.get("/congestion-events.csv")
def export_congestion_events(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    room_id: int | None = Query(default=None, ge=1),
    camera_id: int | None = Query(default=None, ge=1),
    status: str = Query(default="ALL"),
    actor: AdminUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    normalized_status = status.upper()
    if normalized_status not in {"ALL", "ACTIVE", "RESOLVED"}:
        raise HTTPException(status_code=422, detail="status must be ALL, ACTIVE, or RESOLVED")
    _validate_filters(db, start_date, end_date, room_id, camera_id)
    _record_export(db, actor, "congestion-events", start_date, end_date, room_id, camera_id, normalized_status)
    return _csv_response("congestion-events", EVENT_HEADERS, iter_event_rows(db, start_date, end_date, room_id, camera_id, normalized_status), start_date, end_date)


@router.get("/daily-summary.csv")
def export_daily_summary(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    room_id: int | None = Query(default=None, ge=1),
    camera_id: int | None = Query(default=None, ge=1),
    actor: AdminUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if start_date is None and end_date is None:
        today = utc_to_ist(datetime.now(timezone.utc)).date()
        start_date = today
        end_date = today
    elif start_date is None:
        start_date = end_date
    elif end_date is None:
        end_date = start_date
    _validate_filters(db, start_date, end_date, room_id, camera_id)
    _record_export(db, actor, "daily-summary", start_date, end_date, room_id, camera_id)
    return _csv_response("daily-summary", SUMMARY_HEADERS, iter_daily_summary_rows(db, start_date, end_date, room_id, camera_id), start_date, end_date)
