from sqlalchemy import Boolean, Column, DateTime, Integer, String

from app.database import Base
from app.time_utils import utc_now_naive


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)

    alert_type = Column(String, nullable=False)

    message = Column(String, nullable=False)

    severity = Column(String, nullable=False)

    resolved = Column(Boolean, default=False)

    created_at = Column(
        DateTime(timezone=False),
        default=utc_now_naive,
        nullable=False
    )
