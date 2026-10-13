import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app import camera_manager
from app.camera_manager import parse_camera_source


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

    def set(self, _property, _value):
        return True


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

    def test_local_and_network_source_values_are_parsed_for_opencv(self):
        self.assertEqual(parse_camera_source("WEBCAM", "0"), 0)
        self.assertEqual(parse_camera_source("WEBCAM", " 1 "), 1)
        self.assertEqual(parse_camera_source("IP_STREAM", "http://192.168.1.20:8080/video"), "http://192.168.1.20:8080/video")
        self.assertEqual(parse_camera_source("IP_STREAM", "rtsp://example.test/live"), "rtsp://example.test/live")

        for source_type, source in (("WEBCAM", "-1"), ("WEBCAM", "camera"), ("IP_STREAM", "not-a-url"), ("UNKNOWN", "0")):
            with self.assertRaises(ValueError):
                parse_camera_source(source_type, source)
        self.assertFalse(camera_manager.is_valid_frame(SimpleNamespace(shape=(0, 0, 3), size=0)))
        self.assertTrue(camera_manager.is_valid_frame(self.frame))

    def test_unreachable_network_camera_is_bounded_and_releases_capture(self):
        captures = [FakeCapture(opened=False), FakeCapture(opened=False)]
        statuses = []

        def fake_heartbeat(_worker, status, **_kwargs):
            statuses.append(status)

        config = {**camera_config(), "source_type": "IP_STREAM", "source": "http://192.0.2.1:8080/video"}
        with patch.object(camera_manager, "CAMERA_RECONNECT_ATTEMPTS", 2), \
             patch.object(camera_manager, "CAMERA_RECONNECT_DELAY", 0.001), \
             patch.object(camera_manager.cv2, "VideoCapture", side_effect=captures), \
             patch.object(camera_manager, "PersonDetector", return_value=FakeDetector()), \
             patch.object(camera_manager.CameraWorker, "heartbeat", new=fake_heartbeat):
            worker = camera_manager.CameraWorker(config, threading.Event())
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

    def test_processing_interval_records_skipped_frames_and_closes_session(self):
        stop_event = threading.Event()
        capture = FakeCapture(reads=[(True, self.frame)] * 4)

        class StoppingDetector(FakeDetector):
            calls = 0

            def track(self, frame):
                self.calls += 1
                if self.calls == 2:
                    stop_event.set()
                return super().track(frame)

        class FakeSession:
            def __init__(self):
                self.closed = False

            def close(self):
                self.closed = True

        session = FakeSession()
        config = {**camera_config(), "processing_interval": 2}
        with patch.object(camera_manager.requests, "Session", return_value=session), \
             patch.object(camera_manager.cv2, "VideoCapture", return_value=capture), \
             patch.object(camera_manager, "PersonDetector", return_value=StoppingDetector()), \
             patch.object(camera_manager.CameraWorker, "heartbeat"), \
             patch.object(camera_manager.CameraWorker, "post_count"):
            worker = camera_manager.CameraWorker(config, stop_event)
            worker.run()

        metrics = worker.metrics_snapshot()
        self.assertEqual(metrics["frames_read"], 4)
        self.assertEqual(metrics["frames_processed"], 2)
        self.assertEqual(metrics["frames_skipped"], 2)
        self.assertEqual(metrics["processing_interval"], 2)
        self.assertTrue(session.closed)
        self.assertTrue(capture.released)

    def test_duplicate_worker_start_is_ignored(self):
        class FakeWorker:
            instances = []

            def __init__(self, config, _stop_event):
                self.config = config
                self.alive = False
                self.__class__.instances.append(self)

            def start(self):
                self.alive = True

            def is_alive(self):
                return self.alive

            def stop(self):
                self.alive = False

            def join(self, timeout):
                return None

        config = camera_config()
        with patch.object(camera_manager, "CameraWorker", FakeWorker):
            manager = camera_manager.CameraProcessingManager([config])
            self.assertFalse(manager._start_worker(config))
            self.assertEqual(len(FakeWorker.instances), 1)

    def test_frame_relay_uses_worker_http_session_without_opening_another_capture(self):
        class FakeSession:
            def __init__(self):
                self.calls = []

            def post(self, url, **kwargs):
                self.calls.append((url, kwargs))
                return FakeResponse()

        session = FakeSession()
        encoded = SimpleNamespace(tobytes=lambda: b"jpeg-bytes")
        worker = camera_manager.CameraWorker(camera_config(), threading.Event())
        worker.http = session
        with patch.object(camera_manager.cv2, "imencode", return_value=(True, encoded)):
            worker.post_frame(object())

        self.assertEqual(len(session.calls), 1)
        url, kwargs = session.calls[0]
        self.assertIn("/api/monitoring/internal/cameras/1/frame", url)
        self.assertEqual(kwargs["data"], b"jpeg-bytes")
        self.assertEqual(kwargs["headers"]["Content-Type"], "image/jpeg")

    def test_one_worker_start_failure_does_not_block_other_cameras(self):
        class PartiallyFailingWorker:
            def __init__(self, config, _stop_event):
                self.config = config
                self.alive = False

            def start(self):
                if self.config["id"] == 1:
                    raise RuntimeError("simulated start failure")
                self.alive = True

            def is_alive(self):
                return self.alive

            def stop(self):
                self.alive = False

            def join(self, timeout):
                return None

        with patch.object(camera_manager, "CameraWorker", PartiallyFailingWorker):
            manager = camera_manager.CameraProcessingManager([camera_config(1), camera_config(2)])

        self.assertNotIn(1, manager.workers)
        self.assertIn(2, manager.workers)

    def test_dead_camera_restart_keeps_other_worker_running(self):
        class IndependentWorker:
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

        with patch.object(camera_manager, "CameraWorker", IndependentWorker), \
             patch.object(camera_manager, "CAMERA_RESTART_DELAY", 0):
            manager = camera_manager.CameraProcessingManager([camera_config(1), camera_config(2)])
            other_worker = manager.workers[2]
            manager.workers[1].alive = False
            manager.sync_configs([camera_config(1), camera_config(2)])

            self.assertIs(manager.workers[2], other_worker)
            self.assertTrue(manager.workers[2].is_alive())
            manager.stop()

    def test_local_and_network_workers_coexist_without_duplicate_starts(self):
        class FakeWorker:
            instances = []

            def __init__(self, config, _stop_event):
                self.config = config
                self.alive = False
                self.__class__.instances.append(self)

            def start(self):
                self.alive = True

            def is_alive(self):
                return self.alive

            def stop(self):
                self.alive = False

            def join(self, timeout):
                return None

        local = camera_config(1)
        network = {**camera_config(2), "source_type": "IP_STREAM", "source": "http://192.168.1.20:8080/video"}
        with patch.object(camera_manager, "CameraWorker", FakeWorker):
            manager = camera_manager.CameraProcessingManager([local, network])
            manager.sync_configs([local, network])
            self.assertEqual(len(FakeWorker.instances), 2)
            self.assertEqual(manager.workers[1].config["source_type"], "WEBCAM")
            self.assertEqual(manager.workers[2].config["source_type"], "IP_STREAM")
            manager.stop()


if __name__ == "__main__":
    unittest.main()
