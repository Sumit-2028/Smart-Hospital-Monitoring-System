from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from app.database import Base


class CrowdReading(Base):
    __tablename__ = "crowd_readings"

    id = Column(Integer, primary_key=True, index=True)

    person_count = Column(Integer, nullable=False)

    threshold = Column(Integer, nullable=False)

    status = Column(String, nullable=False)

    timestamp = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )