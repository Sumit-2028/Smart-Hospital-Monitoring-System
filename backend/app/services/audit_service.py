import logging

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.audit import AuditLog

logger = logging.getLogger(__name__)


def add_audit(
    db: Session,
    *,
    actor=None,
    actor_username=None,
    action,
    outcome,
    resource_type=None,
    resource_id=None,
    context=None,
):
    """Add an audit row to the caller's transaction.

    The caller must commit it with the business operation. If this flush fails,
    the caller receives the database exception and must roll back the operation.
    """
    row = AuditLog(
        actor_admin_id=getattr(actor, "id", None),
        actor_username=actor_username or getattr(actor, "username", None),
        action=action,
        outcome=outcome,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        context=context or None,
    )
    db.add(row)
    db.flush()
    return row


def record_failed_audit(
    db: Session,
    *,
    action,
    actor=None,
    actor_username=None,
    resource_type=None,
    resource_id=None,
    context=None,
):
    """Best-effort persistence for an already-failed operation.

    The original failure is never replaced with an audit failure. A traceback is
    logged if the audit database write also fails, and callers must not claim the
    event was persisted.
    """
    try:
        db.rollback()
        add_audit(
            db,
            actor=actor,
            actor_username=actor_username,
            action=action,
            outcome="FAILURE",
            resource_type=resource_type,
            resource_id=resource_id,
            context=context,
        )
        db.commit()
        return True
    except SQLAlchemyError:
        db.rollback()
        logger.exception(
            "audit persistence failed after operation failure",
            extra={"action": action, "resource_type": resource_type, "resource_id": resource_id},
        )
        return False


def serialize_audit(row):
    return {
        "id": row.id,
        "actor_admin_id": row.actor_admin_id,
        "actor_username": row.actor_username,
        "action": row.action,
        "outcome": row.outcome,
        "resource_type": row.resource_type,
        "resource_id": row.resource_id,
        "timestamp": row.timestamp.isoformat() + "+00:00" if row.timestamp else None,
        "metadata": row.context,
    }
