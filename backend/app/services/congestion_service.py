from datetime import datetime

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models.crowd import CongestionEvent
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
    """

    is_congested = person_count >= threshold

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
