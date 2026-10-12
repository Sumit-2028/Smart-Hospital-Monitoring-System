from datetime import date, datetime, timedelta

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.crowd import (
    CrowdReading,
    CongestionEvent
)
from app.time_utils import (
    IST,
    as_utc_naive,
    ist_day_bounds_utc_naive,
    serialize_utc,
    utc_now_naive,
    utc_to_ist,
)


def get_latest_reading(db: Session):
    reading = (
        db.query(CrowdReading)
        .order_by(CrowdReading.timestamp.desc())
        .first()
    )

    if reading is None:
        return None

    return {
        "id": reading.id,
        "person_count": reading.person_count,
        "threshold": reading.threshold,
        "status": reading.status,
        "timestamp": serialize_utc(reading.timestamp),
    }


# ==================================================
# TODAY START
# ==================================================

def get_today_start():
    """
    Return today's midnight in UTC-naive format,
    based on the current Indian date.
    """

    return ist_day_bounds_utc_naive(datetime.now(IST).date())[0]


# ==================================================
# TODAY SUMMARY
# ==================================================

def get_today_summary(
    db: Session
):

    start = get_today_start()
    now = utc_now_naive()

    readings = (
        db.query(CrowdReading)
        .filter(
            CrowdReading.timestamp >= start,
            CrowdReading.timestamp <= now
        )
        .order_by(CrowdReading.timestamp)
        .all()
    )

    # ----------------------------------------
    # No readings
    # ----------------------------------------

    if not readings:

        return {
            "average_crowd": 0,
            "peak_crowd": 0,
            "peak_time": None,
            "minimum_crowd": 0,
            "congestion_events": 0,
            "congestion_minutes": 0,
            "busiest_hour": None,
            "threshold": None,
            "current_count": 0,
            "current_status": "NORMAL",
            "last_update": None
        }

    # ----------------------------------------
    # Average crowd
    # ----------------------------------------

    average_crowd = (
        sum(
            reading.person_count
            for reading in readings
        )
        / len(readings)
    )

    # ----------------------------------------
    # Peak crowd
    # ----------------------------------------

    peak_reading = max(
        readings,
        key=lambda reading:
            reading.person_count
    )

    # ----------------------------------------
    # Minimum crowd
    # ----------------------------------------

    minimum_crowd = min(
        reading.person_count
        for reading in readings
    )

    # ----------------------------------------
    # Busiest hour - IST
    # ----------------------------------------

    hourly_totals = {}

    for reading in readings:

        ist_time = utc_to_ist(
            reading.timestamp
        )

        hour = ist_time.hour

        if hour not in hourly_totals:

            hourly_totals[hour] = []

        hourly_totals[hour].append(
            reading.person_count
        )

    hourly_averages = {

        hour:
            sum(values) / len(values)

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
            CongestionEvent.started_at <= now,
            or_(
                CongestionEvent.ended_at.is_(None),
                CongestionEvent.ended_at >= start,
            )
        )
        .all()
    )

    congestion_minutes = 0

    for event in events:
        started_at = max(as_utc_naive(event.started_at), start)
        ended_at = as_utc_naive(event.ended_at) if event.ended_at else now
        ended_at = min(ended_at, now)
        congestion_minutes += max(
            0,
            (ended_at - started_at).total_seconds() / 60,
        )

    # ----------------------------------------
    # Peak time → IST
    # ----------------------------------------

    peak_time_ist = utc_to_ist(
        peak_reading.timestamp
    )

    # ----------------------------------------
    # Return summary
    # ----------------------------------------

    return {

        "average_crowd":
            round(
                average_crowd,
                2
            ),

        "peak_crowd":
            peak_reading.person_count,

        "peak_time":
            peak_time_ist.isoformat(),

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
            busiest_hour,

        "threshold":
            readings[-1].threshold,

        "current_count":
            readings[-1].person_count,

        "current_status":
            readings[-1].status,

        "last_update":
            utc_to_ist(readings[-1].timestamp).isoformat()
    }


# ==================================================
# DAILY HISTORY
# ==================================================

def get_daily_history(
    db: Session,
    days: int = 7,
    room_id: int | None = None,
):

    # ----------------------------------------
    # Current Indian date
    # ----------------------------------------

    now_ist = datetime.now(IST)

    start_date_ist = (
        now_ist.date()
        - timedelta(
            days=days - 1
        )
    )

    # ----------------------------------------
    # Indian midnight
    # ----------------------------------------

    start_utc, _ = ist_day_bounds_utc_naive(start_date_ist)

    # ----------------------------------------
    # Get readings
    # ----------------------------------------

    query = db.query(CrowdReading).filter(
            CrowdReading.timestamp >= start_utc,
            CrowdReading.timestamp <= utc_now_naive()
        )
    if room_id is not None:
        query = query.filter(CrowdReading.room_id == room_id)
    readings = (
        query
        .order_by(
            CrowdReading.timestamp
        )
        .all()
    )

    # ----------------------------------------
    # Group by IST date
    # ----------------------------------------

    daily_data = {}

    for reading in readings:

        ist_time = utc_to_ist(
            reading.timestamp
        )

        date_key = ist_time.date()

        if date_key not in daily_data:

            daily_data[date_key] = []

        daily_data[date_key].append(
            reading.person_count
        )

    # ----------------------------------------
    # Build result
    # ----------------------------------------

    result = []

    for date_key in sorted(
        daily_data.keys()
    ):

        values = daily_data[date_key]

        result.append({

            "date":
                str(date_key),

            "average_crowd":
                round(
                    sum(values) / len(values),
                    2
                ),

            "peak_crowd":
                max(values),

            "minimum_crowd":
                min(values),

            "reading_count":
                len(values)
        })

    return result


# ==================================================
# HOURLY HISTORY
# ==================================================

def get_hourly_history(
    db: Session,
    selected_date: date | str,
    room_id: int | None = None,
):

    # ----------------------------------------
    # Parse requested date
    # ----------------------------------------

    if isinstance(selected_date, str):
        target_date = datetime.strptime(selected_date, "%Y-%m-%d").date()
    else:
        target_date = selected_date

    start_utc, end_utc = ist_day_bounds_utc_naive(target_date)

    # ----------------------------------------
    # Get readings
    # ----------------------------------------

    query = db.query(CrowdReading).filter(
            CrowdReading.timestamp >= start_utc,
            CrowdReading.timestamp < end_utc,
            CrowdReading.timestamp <= utc_now_naive()
        )
    if room_id is not None:
        query = query.filter(CrowdReading.room_id == room_id)
    readings = (
        query
        .order_by(
            CrowdReading.timestamp
        )
        .all()
    )

    # ----------------------------------------
    # Group by IST hour
    # ----------------------------------------

    hourly_data = {}

    for reading in readings:

        ist_time = utc_to_ist(
            reading.timestamp
        )

        hour = ist_time.hour

        if hour not in hourly_data:

            hourly_data[hour] = []

        hourly_data[hour].append(
            reading.person_count
        )

    # ----------------------------------------
    # Build result
    # ----------------------------------------

    result = []

    for hour in sorted(
        hourly_data.keys()
    ):

        values = hourly_data[hour]

        result.append({

            "hour":
                hour,

            "average_crowd":
                round(
                    sum(values) / len(values),
                    2
                ),

            "peak_crowd":
                max(values),

            "reading_count":
                len(values)
        })

    return result
