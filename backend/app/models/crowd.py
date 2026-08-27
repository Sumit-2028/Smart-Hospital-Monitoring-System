from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    String
)

from app.database import Base


class CrowdReading(Base):

    __tablename__ = "crowd_readings"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    person_count = Column(
        Integer,
        nullable=False
    )

    threshold = Column(
        Integer,
        nullable=False
    )

    status = Column(
        String,
        nullable=False
    )

    timestamp = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True
    )


class CongestionEvent(Base):

    __tablename__ = "congestion_events"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    started_at = Column(
        DateTime,
        nullable=False
    )

    ended_at = Column(
        DateTime,
        nullable=True
    )

    peak_crowd = Column(
        Integer,
        nullable=False
    )

    threshold = Column(
        Integer,
        nullable=False
    )

    resolved = Column(
        Boolean,
        default=False,
        nullable=False
    )