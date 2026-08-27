from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from app.database import Base


class AccessLog(Base):
    __tablename__ = "access_logs"

    id = Column(Integer, primary_key=True, index=True)

    rfid_uid = Column(String, nullable=False)

    status = Column(String, nullable=False)

    timestamp = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )