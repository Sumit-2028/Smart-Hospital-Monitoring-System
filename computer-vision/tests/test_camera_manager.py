import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app import camera_manager


def camera_config(camera_id=1):
    return {
        "id": camera_id,
        "room_id": camera_id,
        "source_type": "WEBCAM",
        "source": "0",
        "agent_token": "test-token",
    }


class FakeResponse:
    def raise_for_status(self):
        return None


class FakeCapture:
    def __init__(self, opened=True, reads=None):
        self.opened = opened
        self.reads = iter(reads or [])
        self.released = False

    def isOpened(self):
        return self.opened

    def read(self):
        try:
            return next(self.reads)
        except StopIteration:
            return False, None

    def release(self):
        self.released = True


class FakeDetector:
    def track(self, _frame):
        return SimpleNamespace(boxes=None)


class CameraManagerTests(unittest.TestCase):
    def setUp(self):
        self.frame = SimpleNamespace(shape=(100, 100, 3))

    def test_open_failure_is_reported_and_capture_is_retried_with_bound(self):
        captures = [FakeCapture(opened=False), FakeCapture(opened=False)]
        statuses = []

        def fake_heartbeat(_worker, status, **_kwargs):
            statuses.append(status)

        with patch.object(camera_manager, "CAMERA_RECONNECT_ATTEMPTS", 2), \
             patch.object(camera_manager, "CAMERA_RECONNECT_DELAY", 0.001), \
             patch.object(camera_manager.cv2, "VideoCapture", side_effect=captures), \
             patch.object(camera_manager, "PersonDetector", return_value=FakeDetector()), \
             patch.object(camera_manager.CameraWorker, "heartbeat", new=fake_heartbeat):
            worker = camera_manager.CameraWorker(camera_config(), threading.Event())
            worker.run()

        self.assertIn("ERROR", statuses)
        self.assertTrue(all(c.released for c in captures))

    def test_missing_frames_reconnect_and_recover(self):
        recovered = threading.Event()
        captures = [
            FakeCapture(reads=[(False, None)]),
            FakeCapture(reads=[(True, self.frame)]),
        ]
        statuses = []

        def fake_heartbeat(worker, status, **_kwargs):
            statuses.append(status)
            if status == "CONNECTED":
                recovered.set()
                worker.stop_event.set()

        with patch.object(camera_manager, "CAMERA_RECONNECT_ATTEMPTS", 3), \
             patch.object(camera_manager, "CAMERA_RECONNECT_DELAY", 0.001), \
             patch.object(camera_manager.cv2, "VideoCapture", side_effect=captures), \
             patch.object(camera_manager, "PersonDetector", return_value=FakeDetector()), \
             patch.object(camera_manager.CameraWorker, "heartbeat", new=fake_heartbeat), \
             patch.object(camera_manager.CameraWorker, "post_count"):
            worker = camera_manager.CameraWorker(camera_config(), threading.Event())
            worker.run()

        self.assertTrue(recovered.is_set())
        self.assertIn("DISCONNECTED", statuses)
        self.assertIn("CONNECTED", statuses)
        self.assertTrue(all(c.released for c in captures))

    def test_dead_worker_is_restarted_and_shutdown_calls_stop(self):
        class FakeWorker:
            instances = []

            def __init__(self, config, _stop_event):
                self.config = config
                self.alive = False
                self.stopped = False
                self.__class__.instances.append(self)

            def start(self):
                self.alive = True

            def is_alive(self):
                return self.alive

            def stop(self):
                self.stopped = True
                self.alive = False

            def join(self, timeout):
                return None

        config = camera_config()
        with patch.object(camera_manager, "CameraWorker", FakeWorker), \
             patch.object(camera_manager, "CAMERA_RESTART_DELAY", 0):
            manager = camera_manager.CameraProcessingManager([config])
            first = manager.workers[1]
            first.alive = False
            manager.sync_configs([config])
            self.assertEqual(len(FakeWorker.instances), 2)
            self.assertIsNot(manager.workers[1], first)
            manager.stop()
            self.assertTrue(manager.workers[1].stopped)


if __name__ == "__main__":
    unittest.main()
