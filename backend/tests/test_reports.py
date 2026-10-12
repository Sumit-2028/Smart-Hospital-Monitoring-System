import csv
import io
import unittest
from datetime import date, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.crowd import CongestionEvent, CrowdReading
from app.models.facility import Camera, Room
from app.services.report_service import (
    CROWD_READING_HEADERS,
    EVENT_HEADERS,
    SUMMARY_HEADERS,
    csv_stream,
    iter_crowd_reading_rows,
    iter_daily_summary_rows,
    iter_event_rows,
)


class ReportServiceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self.room = Room(name="Waiting Area", room_type="WAITING_AREA", capacity=10, warning_percentage=80)
        self.camera = Camera(name="Laptop Camera", source_type="WEBCAM", source="0", room_id=1)
        self.session.add(self.room)
        self.session.flush()
        self.camera.room_id = self.room.id
        self.session.add(self.camera)
        self.session.flush()
        self.session.add_all([
            CrowdReading(person_count=4, threshold=8, status="NORMAL", room_id=self.room.id, camera_id=self.camera.id, timestamp=datetime(2026, 1, 10, 5, 0)),
            CrowdReading(person_count=9, threshold=8, status="CONGESTED", room_id=self.room.id, camera_id=self.camera.id, timestamp=datetime(2026, 1, 10, 6, 0)),
            CrowdReading(person_count=2, threshold=8, status="NORMAL", room_id=self.room.id, camera_id=self.camera.id, timestamp=datetime(2026, 1, 11, 5, 0)),
        ])
        self.session.add(CongestionEvent(
            started_at=datetime(2026, 1, 10, 5, 30),
            ended_at=datetime(2026, 1, 10, 6, 0),
            peak_crowd=9,
            threshold=8,
            resolved=True,
            room_id=self.room.id,
            camera_id=self.camera.id,
        ))
        self.session.commit()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_csv_has_stable_headers_and_formula_safe_text(self):
        chunks = list(csv_stream(["room_name", "status"], [{"room_name": "=HYPERLINK(\"x\")", "status": "+ACTIVE"}]))
        rows = list(csv.reader(io.StringIO("".join(chunks))))
        self.assertEqual(rows[0], ["room_name", "status"])
        self.assertEqual(rows[1], ["'=HYPERLINK(\"x\")", "'+ACTIVE"])

    def test_empty_export_still_returns_header(self):
        rows = list(iter_crowd_reading_rows(self.session, date(2026, 2, 1), date(2026, 2, 1)))
        csv_rows = list(csv.reader(io.StringIO("".join(csv_stream(CROWD_READING_HEADERS, rows)))))
        self.assertEqual(len(csv_rows), 1)
        self.assertEqual(csv_rows[0], CROWD_READING_HEADERS)

    def test_reading_filters_use_ist_date_and_camera(self):
        rows = list(iter_crowd_reading_rows(self.session, date(2026, 1, 10), date(2026, 1, 10), room_id=self.room.id, camera_id=self.camera.id))
        self.assertEqual([row["person_count"] for row in rows], [4, 9])
        self.assertEqual(rows[0]["room_name"], "Waiting Area")

    def test_event_status_and_duration_are_exported(self):
        rows = list(iter_event_rows(self.session, date(2026, 1, 10), date(2026, 1, 10), status="RESOLVED"))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "RESOLVED")
        self.assertEqual(rows[0]["duration_seconds"], 1800)
        self.assertEqual(rows[0]["duration_minutes"], 30.0)

    def test_daily_summary_contains_reading_and_event_metrics(self):
        rows = list(iter_daily_summary_rows(self.session, date(2026, 1, 10), date(2026, 1, 10), room_id=self.room.id, camera_id=self.camera.id))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["date"], "2026-01-10")
        self.assertEqual(rows[0]["reading_count"], 2)
        self.assertEqual(rows[0]["average_crowd"], 6.5)
        self.assertEqual(rows[0]["peak_crowd"], 9)
        self.assertEqual(rows[0]["minimum_crowd"], 4)
        self.assertEqual(rows[0]["congestion_event_count"], 1)
        self.assertEqual(rows[0]["total_congestion_duration_seconds"], 1800)

    def test_headers_match_contract(self):
        self.assertEqual(EVENT_HEADERS[-2:], ["duration_seconds", "duration_minutes"])
        self.assertEqual(SUMMARY_HEADERS[:4], ["date", "room_id", "room_name", "reading_count"])


if __name__ == "__main__":
    unittest.main()
