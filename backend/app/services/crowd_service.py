from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.crowd import (
    CrowdReading,
    CongestionEvent
)


def get_today_start():

    now = datetime.utcnow()

    return datetime(
        now.year,
        now.month,
        now.day
    )


def get_today_summary(db: Session):

    start = get_today_start()

    readings = (
        db.query(CrowdReading)
        .filter(
            CrowdReading.timestamp >= start
        )
        .all()
    )

    if not readings:

        return {
            "average_crowd": 0,
            "peak_crowd": 0,
            "peak_time": None,
            "minimum_crowd": 0,
            "congestion_events": 0,
            "congestion_minutes": 0,
            "busiest_hour": None
        }

    average_crowd = sum(
        reading.person_count
        for reading in readings
    ) / len(readings)

    peak_reading = max(
        readings,
        key=lambda reading: reading.person_count
    )

    minimum_crowd = min(
        reading.person_count
        for reading in readings
    )

    # ----------------------------------------
    # Calculate busiest hour
    # ----------------------------------------

    hourly_totals = {}

    for reading in readings:

        hour = reading.timestamp.hour

        if hour not in hourly_totals:
            hourly_totals[hour] = []

        hourly_totals[hour].append(
            reading.person_count
        )

    hourly_averages = {
        hour: sum(values) / len(values)
        for hour, values
        in hourly_totals.items()
    }

    busiest_hour = None

    if hourly_averages:

        busiest_hour = max(
            hourly_averages,
            key=hourly_averages.get
        )

    # ----------------------------------------
    # Congestion events
    # ----------------------------------------

    events = (
        db.query(CongestionEvent)
        .filter(
            CongestionEvent.started_at >= start
        )
        .all()
    )

    congestion_minutes = 0

    for event in events:

        end = (
            event.ended_at
            if event.ended_at
            else datetime.utcnow()
        )

        congestion_minutes += (
            end - event.started_at
        ).total_seconds() / 60

    return {

        "average_crowd": round(
            average_crowd,
            2
        ),

        "peak_crowd":
            peak_reading.person_count,

        "peak_time":
            peak_reading.timestamp.isoformat(),

        "minimum_crowd":
            minimum_crowd,

        "congestion_events":
            len(events),

        "congestion_minutes":
            round(
                congestion_minutes,
                2
            ),

        "busiest_hour":
            busiest_hour

    }


def get_daily_history(
    db: Session,
    days: int = 7
):

    start = (
        datetime.utcnow()
        - timedelta(days=days - 1)
    )

    start = datetime(
        start.year,
        start.month,
        start.day
    )

    rows = (
        db.query(
            func.date(
                CrowdReading.timestamp
            ).label("date"),

            func.avg(
                CrowdReading.person_count
            ).label("average_crowd"),

            func.max(
                CrowdReading.person_count
            ).label("peak_crowd"),

            func.min(
                CrowdReading.person_count
            ).label("minimum_crowd"),

            func.count(
                CrowdReading.id
            ).label("reading_count")
        )
        .filter(
            CrowdReading.timestamp >= start
        )
        .group_by(
            func.date(
                CrowdReading.timestamp
            )
        )
        .order_by(
            func.date(
                CrowdReading.timestamp
            )
        )
        .all()
    )

    return [
        {
            "date": str(row.date),
            "average_crowd": round(
                float(row.average_crowd),
                2
            ),
            "peak_crowd": row.peak_crowd,
            "minimum_crowd": row.minimum_crowd,
            "reading_count": row.reading_count
        }
        for row in rows
    ]


def get_hourly_history(
    db: Session,
    selected_date: str
):

    from datetime import datetime

    target_date = datetime.strptime(
        selected_date,
        "%Y-%m-%d"
    ).date()

    rows = (
        db.query(
            func.extract(
                "hour",
                CrowdReading.timestamp
            ).label("hour"),

            func.avg(
                CrowdReading.person_count
            ).label("average_crowd"),

            func.max(
                CrowdReading.person_count
            ).label("peak_crowd")
        )
        .filter(
            func.date(
                CrowdReading.timestamp
            ) == target_date
        )
        .group_by(
            func.extract(
                "hour",
                CrowdReading.timestamp
            )
        )
        .order_by(
            func.extract(
                "hour",
                CrowdReading.timestamp
            )
        )
        .all()
    )

    return [
        {
            "hour": int(row.hour),

            "average_crowd": round(
                float(row.average_crowd),
                2
            ),

            "peak_crowd": row.peak_crowd
        }
        for row in rows
    ]