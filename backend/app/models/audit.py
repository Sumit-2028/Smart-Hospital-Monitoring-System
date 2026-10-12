from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, JSON, String

from app.database import Base
from app.time_utils import utc_now_naive


class AuditLog(Base):
    """Append-only security and administration history."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_timestamp", "timestamp"),
        Index("ix_audit_logs_actor", "actor_admin_id"),
        Index("ix_audit_logs_action", "action"),
        Index("ix_audit_logs_resource", "resource_type", "resource_id"),
        Index("ix_audit_logs_outcome", "outcome"),
    )

    id = Column(Integer, primary_key=True, index=True)
    actor_admin_id = Column(Integer, ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True)
    actor_username = Column(String(120), nullable=True)
    action = Column(String(80), nullable=False)
    outcome = Column(String(20), nullable=False)
    resource_type = Column(String(80), nullable=True)
    resource_id = Column(String(120), nullable=True)
    timestamp = Column(DateTime(timezone=False), nullable=False, default=utc_now_naive)
    context = Column("metadata", JSON, nullable=True)
