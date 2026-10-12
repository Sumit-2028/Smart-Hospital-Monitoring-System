from datetime import datetime

from sqlalchemy import and_, text
from sqlalchemy.orm import Session

from app.models.crowd import CongestionEvent
from app.models.facility import Room
from app.time_utils import as_utc_naive, utc_now_naive


def update_congestion_event(
    db: Session,
    person_count: int,
    threshold: int,
    now: datetime | None = None,
    commit: bool = True,
    room_id: int | None = None,
    camera_id: int | None = None,
):
    """
    Start, update, or end a congestion event.

    Room-row locking serializes event transitions for one room on PostgreSQL.
    This prevents two simultaneous readings from both creating an active event.
    A camera disconnect never calls this function, so it cannot resolve an
    event merely because a feed stopped reporting.
    """

    if person_count < 0:
        raise ValueError("person_count must be non-negative")
    if threshold <= 0:
        raise ValueError("threshold must be greater than zero")

    is_congested = person_count >= threshold

    if room_id is not None:
        # Lock the parent room before reading the active event. PostgreSQL
        # transactions that process the same room therefore serialize here.
        db.query(Room.id).filter(Room.id == room_id).with_for_update().one_or_none()
    elif db.bind is not None and db.bind.dialect.name == "postgresql":
        # Legacy readings have no room row to lock. Use one transaction-scoped
        # advisory lock for that single compatibility stream instead.
        db.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": 918273645})

    # Find currently active congestion event
    active_event = (
        db.query(CongestionEvent)
        .filter(
            and_(
                CongestionEvent.resolved.is_(False),
                CongestionEvent.ended_at.is_(None),
                CongestionEvent.room_id == room_id,
            )
        )
        .order_by(
            CongestionEvent.started_at.desc()
        )
        .first()
    )

    # ----------------------------------------
    # START NEW CONGESTION EVENT
    # ----------------------------------------

    if is_congested and active_event is None:

        event_time = as_utc_naive(now) if now else utc_now_naive()

        event = CongestionEvent(
            started_at=event_time,
            peak_crowd=person_count,
            threshold=threshold,
            room_id=room_id,
            camera_id=camera_id,
            resolved=False
        )

        db.add(event)
        if commit:
            db.commit()

        return "STARTED"

    # ----------------------------------------
    # UPDATE EXISTING CONGESTION EVENT
    # ----------------------------------------

    if is_congested and active_event:

        if person_count > active_event.peak_crowd:

            active_event.peak_crowd = person_count

            if commit:
                db.commit()

        return "ONGOING"

    # ----------------------------------------
    # END EXISTING CONGESTION EVENT
    # ----------------------------------------

    if not is_congested and active_event:

        event_time = as_utc_naive(now) if now else utc_now_naive()

        active_event.ended_at = event_time
        active_event.resolved = True

        if commit:
            db.commit()

        return "ENDED"

    # ----------------------------------------
    # NO EVENT
    # ----------------------------------------

    return "NONE"
