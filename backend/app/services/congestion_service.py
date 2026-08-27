from datetime import datetime

from sqlalchemy.orm import Session

from app.models.crowd import CongestionEvent




def update_congestion_event(
    db: Session,
    person_count: int,
    threshold: int
):

    is_congested = person_count >= threshold

    active_event = (
        db.query(CongestionEvent)
        .filter(
            CongestionEvent.resolved == False
        )
        .order_by(
            CongestionEvent.started_at.desc()
        )
        .first()
    )

    # Start a new congestion event
    if is_congested and active_event is None:

        event = CongestionEvent(
            started_at=datetime.utcnow(),
            peak_crowd=person_count,
            threshold=threshold,
            resolved=False
        )

        db.add(event)
        db.commit()

        return "STARTED"

    # Update existing event
    if is_congested and active_event:

        if person_count > active_event.peak_crowd:

            active_event.peak_crowd = person_count

            db.commit()

        return "ONGOING"

    # End existing event
    if not is_congested and active_event:

        active_event.ended_at = datetime.utcnow()

        active_event.resolved = True

        db.commit()

        return "ENDED"

    return "NONE"