from datetime import datetime, timedelta, timezone
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.crowd import CrowdReading
from app.models.facility import Camera, Department, Room
from app.routes.monitoring import _hospital_summary


class HospitalSummaryTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self.department = Department(name="Summary Department")
        self.room_one = Room(name="Summary Room One", room_type="WAITING_AREA", capacity=10, warning_percentage=80)
        self.room_two = Room(name="Summary Room Two", room_type="DOCTOR_CABIN", capacity=5, warning_percentage=60)
        self.room_three = Room(name="Summary Room Three", room_type="OPD", capacity=8, warning_percentage=75)
        self.session.add_all([self.department, self.room_one, self.room_two, self.room_three])
        self.session.flush()
        self.room_one.department_id = self.department.id
        self.camera_one = Camera(name="Summary Camera One", source_type="WEBCAM", source="0", room_id=self.room_one.id, status="CONNECTED")
        self.camera_two = Camera(name="Summary Camera Two", source_type="IP_STREAM", source="http://example.test/video", room_id=self.room_one.id, status="CONNECTED")
        self.camera_three = Camera(name="Summary Camera Three", source_type="WEBCAM", source="1", room_id=self.room_two.id, status="DISCONNECTED")
        self.session.add_all([self.camera_one, self.camera_two, self.camera_three])
        self.session.commit()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_latest_valid_reading_per_room_and_no_double_counting(self):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        self.session.add_all([
            CrowdReading(person_count=9, threshold=8, camera_id=self.camera_one.id, room_id=self.room_one.id, status="CONGESTED", timestamp=now - timedelta(seconds=5)),
            CrowdReading(person_count=4, threshold=8, camera_id=self.camera_two.id, room_id=self.room_one.id, status="NORMAL", timestamp=now - timedelta(seconds=1)),
            CrowdReading(person_count=3, threshold=3, camera_id=self.camera_three.id, room_id=self.room_two.id, status="CONGESTED", timestamp=now - timedelta(seconds=2)),
        ])
        self.session.commit()

        summary = _hospital_summary(self.session, now.replace(tzinfo=timezone.utc))
        rooms = {item["room_id"]: item for item in summary["rooms"]}

        self.assertEqual(summary["total_count"], 7)
        self.assertEqual(summary["complete_room_count"], 2)
        self.assertEqual(summary["incomplete_room_count"], 1)
        self.assertFalse(summary["is_complete"])
        self.assertEqual(rooms[self.room_one.id]["current_count"], 4)
        self.assertEqual(rooms[self.room_one.id]["reading_camera_id"], self.camera_two.id)
        self.assertEqual(rooms[self.room_two.id]["current_count"], 3)
        self.assertEqual(rooms[self.room_three.id]["monitoring_status"], "UNAVAILABLE")

    def test_stale_reading_is_excluded_and_capacity_is_read_from_room(self):
        now = datetime.now(timezone.utc)
        old_timestamp = (now - timedelta(seconds=31)).replace(tzinfo=None)
        self.session.add(CrowdReading(
            person_count=7,
            threshold=8,
            camera_id=self.camera_one.id,
            room_id=self.room_one.id,
            status="WARNING",
            timestamp=old_timestamp,
        ))
        self.session.commit()

        summary = _hospital_summary(self.session, now)
        room = next(item for item in summary["rooms"] if item["room_id"] == self.room_one.id)
        self.assertIsNone(room["current_count"])
        self.assertEqual(room["monitoring_status"], "STALE")
        self.assertEqual(room["capacity"], 10)
        self.assertEqual(summary["total_count"], 0)

    def test_empty_configuration_is_a_zero_complete_snapshot(self):
        self.session.query(Camera).delete()
        self.session.query(Room).delete()
        self.session.commit()

        summary = _hospital_summary(self.session)
        self.assertEqual(summary["total_count"], 0)
        self.assertEqual(summary["rooms"], [])
        self.assertTrue(summary["is_complete"])


if __name__ == "__main__":
    unittest.main()
