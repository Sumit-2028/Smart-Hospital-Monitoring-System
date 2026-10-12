from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import relationship

from app.database import Base


def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Department(Base):
    __tablename__ = "departments"
    __table_args__ = (UniqueConstraint("name", name="uq_department_name"),)

    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False, index=True)
    description = Column(String(500))
    active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)


class Room(Base):
    __tablename__ = "rooms"
    __table_args__ = (
        CheckConstraint("capacity > 0", name="ck_room_capacity_positive"),
        CheckConstraint("warning_percentage > 0 AND warning_percentage <= 100", name="ck_room_warning_percentage"),
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False, index=True)
    code = Column(String(80), unique=True, index=True)
    room_type = Column(String(40), nullable=False, default="WAITING_AREA")
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), index=True)
    capacity = Column(Integer, nullable=False, default=1)
    warning_percentage = Column(Integer, nullable=False, default=80)
    active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)


class Camera(Base):
    __tablename__ = "cameras"

    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    source_type = Column(String(20), nullable=False, default="WEBCAM")
    source = Column(String(500), nullable=False)
    room_id = Column(Integer, ForeignKey("rooms.id", ondelete="RESTRICT"), nullable=False, index=True)
    active = Column(Boolean, nullable=False, default=True, index=True)
    status = Column(String(20), nullable=False, default="STOPPED")
    last_frame_at = Column(DateTime, index=True)
    status_updated_at = Column(DateTime, index=True)
    processing_interval = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    room = relationship("Room", foreign_keys=[room_id])


class Doctor(Base):
    __tablename__ = "doctors"

    id = Column(Integer, primary_key=True)
    name = Column(String(160), nullable=False)
    specialty = Column(String(160), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), index=True)
    cabin_id = Column(Integer, ForeignKey("rooms.id", ondelete="SET NULL"), index=True)
    work_identifier = Column(String(120))
    available = Column(Boolean, nullable=False, default=True, index=True)
    active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)


class AdminUser(Base):
    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True)
    username = Column(String(120), nullable=False, unique=True, index=True)
    password_hash = Column(String(300), nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
