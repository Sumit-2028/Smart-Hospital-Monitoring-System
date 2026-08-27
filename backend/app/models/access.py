from sqlalchemy import Column, DateTime, Integer, String

from app.database import Base
from app.time_utils import utc_now_naive


class AccessLog(Base):
    __tablename__ = "access_logs"

    id = Column(Integer, primary_key=True, index=True)

    rfid_uid = Column(String, nullable=False)

    status = Column(String, nullable=False)

    timestamp = Column(
        DateTime(timezone=False),
        default=utc_now_naive,
        nullable=False
    )
