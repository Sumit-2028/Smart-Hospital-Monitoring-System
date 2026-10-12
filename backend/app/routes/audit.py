import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.auth import require_superadmin
from app.database import get_db
from app.models.audit import AuditLog
from app.models.facility import AdminUser
from app.services.audit_service import add_audit, serialize_audit
from app.time_utils import ist_day_bounds_utc_naive

router = APIRouter(prefix="/api/admin/audit-logs", tags=["Audit Logs"])
logger = logging.getLogger(__name__)


@router.get("")
def list_audit_logs(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    actor_id: int | None = Query(default=None, ge=1),
    actor_username: str | None = Query(default=None, min_length=1, max_length=120),
    action: str | None = Query(default=None, min_length=1, max_length=80),
    resource_type: str | None = Query(default=None, min_length=1, max_length=80),
    outcome: str | None = Query(default=None, min_length=1, max_length=20),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
    actor: AdminUser = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must not be after end_date")
    normalized_outcome = outcome.upper() if outcome else None
    if normalized_outcome and normalized_outcome not in {"SUCCESS", "FAILURE"}:
        raise HTTPException(status_code=422, detail="outcome must be SUCCESS or FAILURE")

    query = db.query(AuditLog)
    if start_date:
        start, _ = ist_day_bounds_utc_naive(start_date)
        query = query.filter(AuditLog.timestamp >= start)
    if end_date:
        _, end = ist_day_bounds_utc_naive(end_date)
        query = query.filter(AuditLog.timestamp < end)
    if actor_id is not None:
        query = query.filter(AuditLog.actor_admin_id == actor_id)
    if actor_username:
        query = query.filter(func.lower(AuditLog.actor_username) == actor_username.strip().lower())
    if action:
        query = query.filter(func.lower(AuditLog.action) == action.lower())
    if resource_type:
        query = query.filter(func.lower(AuditLog.resource_type) == resource_type.lower())
    if normalized_outcome:
        query = query.filter(AuditLog.outcome == normalized_outcome)

    total = query.with_entities(func.count(AuditLog.id)).scalar() or 0
    items = query.order_by(AuditLog.timestamp.desc(), AuditLog.id.desc()).offset(offset).limit(limit).all()
    try:
        add_audit(
            db,
            actor=actor,
            action="AUDIT_LOG_VIEWED",
            outcome="SUCCESS",
            resource_type="AUDIT_LOG",
            context={"offset": offset, "limit": limit},
        )
        db.commit()
    except SQLAlchemyError as error:
        db.rollback()
        logger.exception("audit-log access could not be persisted", extra={"actor_id": actor.id})
        raise HTTPException(status_code=503, detail="Audit log query could not be recorded.") from error
    return {"items": [serialize_audit(item) for item in items], "total": total, "offset": offset, "limit": limit}
