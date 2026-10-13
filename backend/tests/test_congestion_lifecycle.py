import unittest
from datetime import date, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.facility import Camera, Room
from app.models.crowd import CongestionEvent, CrowdReading
from app.routes.crowd import _active_alert_payload, _active_event_rows, _event_rows
from app.services.congestion_service import update_congestion_event


class CongestionLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self.room_one = Room(name="Room One", room_type="WAITING_AREA", capacity=10, warning_percentage=80)
        self.room_two = Room(name="Room Two", room_type="WAITING_AREA", capacity=10, warning_percentage=80)
        self.session.add_all([self.room_one, self.room_two])
        self.session.flush()
        self.camera = Camera(name="Camera One", source_type="WEBCAM", source="0", room_id=self.room_one.id)
        self.session.add(self.camera)
        self.session.commit()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_below_threshold_creates_no_event(self):
        result = update_congestion_event(self.session, 9, 10, room_id=self.room_one.id)
        self.session.commit()
        self.assertEqual(result, "NONE")
        self.assertEqual(self.session.query(CongestionEvent).count(), 0)

    def test_start_update_and_resolve_preserves_one_event(self):
        start = datetime(2026, 1, 1, 10, 0)
        self.assertEqual(update_congestion_event(self.session, 10, 10, start, False, self.room_one.id, self.camera.id), "STARTED")
        event = self.session.query(CongestionEvent).one()
        self.assertEqual(event.room_id, self.room_one.id)
        self.assertEqual(event.camera_id, self.camera.id)

        self.assertEqual(update_congestion_event(self.session, 12, 10, datetime(2026, 1, 1, 10, 1), False, self.room_one.id, self.camera.id), "ONGOING")
        self.assertEqual(self.session.query(CongestionEvent).count(), 1)
        self.assertEqual(self.session.query(CongestionEvent).one().peak_crowd, 12)

        end = datetime(2026, 1, 1, 10, 5)
        self.assertEqual(update_congestion_event(self.session, 9, 10, end, False, self.room_one.id, self.camera.id), "ENDED")
        event = self.session.query(CongestionEvent).one()
        self.assertTrue(event.resolved)
        self.assertEqual(event.ended_at, end)

    def test_rooms_have_independent_event_lifecycles(self):
        self.assertEqual(update_congestion_event(self.session, 10, 10, room_id=self.room_one.id, commit=False), "STARTED")
        self.assertEqual(update_congestion_event(self.session, 10, 10, room_id=self.room_two.id, commit=False), "STARTED")
        self.assertEqual(self.session.query(CongestionEvent).count(), 2)
        self.assertEqual(update_congestion_event(self.session, 0, 10, room_id=self.room_one.id, commit=False), "ENDED")
        self.assertEqual(self.session.query(CongestionEvent).filter(CongestionEvent.resolved.is_(False)).count(), 1)
        self.assertEqual(self.session.query(CongestionEvent).filter(CongestionEvent.resolved.is_(False)).one().room_id, self.room_two.id)

    def test_invalid_values_are_rejected(self):
        with self.assertRaises(ValueError):
            update_congestion_event(self.session, -1, 10, room_id=self.room_one.id)
        with self.assertRaises(ValueError):
            update_congestion_event(self.session, 1, 0, room_id=self.room_one.id)

    def test_stale_or_missing_camera_input_does_not_resolve_existing_event(self):
        update_congestion_event(self.session, 10, 10, room_id=self.room_one.id, commit=False)
        self.session.commit()
        # No heartbeat/disconnect operation calls this service, so the event
        # remains active until a below-threshold crowd reading arrives.
        active = self.session.query(CongestionEvent).filter(CongestionEvent.resolved.is_(False)).one()
        self.assertIsNone(active.ended_at)

    def test_history_filters_apply_in_the_database_query(self):
        update_congestion_event(self.session, 10, 10, datetime(2026, 2, 1, 5, 0), False, self.room_one.id, self.camera.id)
        update_congestion_event(self.session, 0, 10, datetime(2026, 2, 1, 5, 5), False, self.room_one.id, self.camera.id)
        update_congestion_event(self.session, 10, 10, datetime(2026, 2, 2, 5, 0), False, self.room_two.id)
        self.session.commit()

        total, rows = _event_rows(self.session, room_id=self.room_one.id, status="RESOLVED", start_date=date(2026, 2, 1), end_date=date(2026, 2, 1))
        self.assertEqual(total, 1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0].room_id, self.room_one.id)

    def test_active_alert_snapshot_deduplicates_legacy_records(self):
        self.session.add_all([
            CongestionEvent(started_at=datetime(2026, 2, 1, 5, 0), peak_crowd=10, threshold=10),
            CongestionEvent(started_at=datetime(2026, 2, 1, 5, 1), peak_crowd=11, threshold=10),
        ])
        self.session.add(CrowdReading(person_count=11, threshold=10, status="CONGESTED"))
        self.session.commit()
        total, rows = _active_event_rows(self.session)
        self.assertEqual(total, 1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][2], 11)

    def test_legacy_active_alert_does_not_report_pre_event_reading_as_current(self):
        reading_time = datetime(2026, 2, 1, 4, 0)
        event_time = datetime(2026, 2, 1, 5, 0)
        self.session.add(CrowdReading(
            person_count=0,
            threshold=1,
            status="NORMAL",
            timestamp=reading_time,
        ))
        self.session.add(CongestionEvent(
            started_at=event_time,
            peak_crowd=1,
            threshold=1,
        ))
        self.session.commit()

        total, rows = _active_event_rows(self.session)
        self.assertEqual(total, 1)
        payload = _active_alert_payload(
            rows[0][0], rows[0][1], rows[0][2], rows[0][3]
        )
        self.assertIsNone(payload["room_name"])
        self.assertIsNone(payload["current_count"])
        self.assertTrue(payload["current_reading_is_stale"])
        self.assertEqual(payload["current_reading_timestamp"], "2026-02-01T04:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
