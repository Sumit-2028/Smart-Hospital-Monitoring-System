from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String

from app.database import Base


class SensorReading(Base):
    __tablename__ = "sensor_readings"

    id = Column(Integer, primary_key=True, index=True)

    sensor_type = Column(String, nullable=False)

    value = Column(Float, nullable=False)

    status = Column(String, nullable=False)

    timestamp = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )