from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from app.database import Base


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)

    alert_type = Column(String, nullable=False)

    message = Column(String, nullable=False)

    severity = Column(String, nullable=False)

    resolved = Column(Boolean, default=False)

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )