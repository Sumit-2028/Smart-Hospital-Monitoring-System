import unittest
from datetime import datetime, timedelta, timezone

from app.models.facility import Camera
from app.routes.monitoring import _effective_camera_status


class MonitoringStatusTests(unittest.TestCase):
    def make_camera(self, status="CONNECTED", last_frame_at=None):
        camera = Camera(name="test", source_type="WEBCAM", source="0", room_id=1)
        camera.status = status
        camera.last_frame_at = last_frame_at
        return camera

    def test_connected_without_a_frame_is_stale(self):
        self.assertEqual(_effective_camera_status(self.make_camera()), "STALE")

    def test_old_frame_is_stale(self):
        old_frame = datetime.now(timezone.utc) - timedelta(seconds=60)
        self.assertEqual(_effective_camera_status(self.make_camera(last_frame_at=old_frame)), "STALE")

    def test_fresh_frame_remains_connected(self):
        fresh_frame = datetime.now(timezone.utc) - timedelta(seconds=1)
        self.assertEqual(_effective_camera_status(self.make_camera(last_frame_at=fresh_frame)), "CONNECTED")

    def test_non_connected_status_is_preserved(self):
        self.assertEqual(_effective_camera_status(self.make_camera(status="STOPPED")), "STOPPED")


if __name__ == "__main__":
    unittest.main()
