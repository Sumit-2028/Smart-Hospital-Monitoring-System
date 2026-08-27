from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


UTC = timezone.utc
IST = ZoneInfo("Asia/Kolkata")


def utc_now_naive() -> datetime:
    """Return the current UTC instant in the database's naive-UTC format."""

    return datetime.now(UTC).replace(tzinfo=None)


def as_utc(value: datetime) -> datetime:
    """Normalize an aware or naive-UTC datetime to an aware UTC datetime."""

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)

    return value.astimezone(UTC)


def as_utc_naive(value: datetime) -> datetime:
    """Normalize a timestamp for the existing PostgreSQL naive-UTC columns."""

    return as_utc(value).replace(tzinfo=None)


def utc_to_ist(value: datetime | None) -> datetime | None:
    if value is None:
        return None

    return as_utc(value).astimezone(IST)


def serialize_utc(value: datetime | None) -> str | None:
    """Serialize database timestamps with an explicit UTC offset."""

    if value is None:
        return None

    return as_utc(value).isoformat()


def ist_day_bounds_utc_naive(target_date: date) -> tuple[datetime, datetime]:
    """Return the UTC-naive start/end bounds for one Indian calendar day."""

    start_ist = datetime.combine(target_date, time.min, tzinfo=IST)
    end_ist = start_ist + timedelta(days=1)

    return as_utc_naive(start_ist), as_utc_naive(end_ist)
