import logging
import threading
import time
from datetime import datetime, timezone

import cv2
import requests

from app.config import (
    BACKEND_URL,
    CAMERA_HEARTBEAT_INTERVAL,
    CAMERA_RECONNECT_ATTEMPTS,
    CAMERA_RECONNECT_DELAY,
    CAMERA_RESTART_DELAY,
    CROWD_THRESHOLD,
    UPDATE_INTERVAL,
)
from app.detector import PersonDetector
from app.tracker import CrowdTracker

logger = logging.getLogger(__name__)


def _utc_now():
    return datetime.now(timezone.utc)


class CameraWorker(threading.Thread):
    """One isolated capture, detector and tracker state per registered camera."""

    def __init__(self, config, stop_event):
        super().__init__(name=f"camera-{config['id']}", daemon=True)
        self.config = config
        self.stop_event = stop_event
        self.local_stop = threading.Event()
        self.camera = None

    @property
    def context(self):
        return {"camera_id": self.config.get("id"), "room_id": self.config.get("room_id")}

    def stop(self):
        self.local_stop.set()

    def _stopping(self):
        return self.stop_event.is_set() or self.local_stop.is_set()

    def _wait_for_retry(self, attempt):
        delay = min(CAMERA_RECONNECT_DELAY * (2 ** max(0, attempt - 1)), 30)
        logger.info("camera retry scheduled", extra={**self.context, "retry_attempt": attempt, "retry_delay_seconds": delay})
        return self.stop_event.wait(delay) or self.local_stop.wait(0)

    def heartbeat(self, status, last_frame_at=None, message=None):
        if self.config.get("legacy"):
            return
        payload = {"camera_id": self.config["id"], "status": status}
        if last_frame_at is not None:
            payload["last_frame_at"] = last_frame_at.isoformat()
        if message:
            payload["message"] = message[:500]
        try:
            response = requests.post(
                f"{BACKEND_URL}/api/monitoring/internal/heartbeat",
                json=payload,
                headers={"X-Camera-Agent-Token": self.config.get("agent_token", "")},
                timeout=2,
            )
            response.raise_for_status()
        except requests.RequestException:
            logger.warning("camera heartbeat request failed", extra={**self.context, "camera_status": status}, exc_info=True)

    def post_count(self, count):
        payload = {"person_count": count, "threshold": CROWD_THRESHOLD} if self.config.get("legacy") else {"person_count": count, "camera_id": self.config["id"]}
        response = requests.post(
            f"{BACKEND_URL}/api/crowd/",
            json=payload,
            headers={"X-Camera-Agent-Token": self.config.get("agent_token", "")},
            timeout=2,
        )
        response.raise_for_status()

    def _open_capture(self, source):
        try:
            capture = cv2.VideoCapture(source)
            if not capture.isOpened():
                capture.release()
                return None
            return capture
        except (TypeError, ValueError):
            logger.error("invalid camera source configuration", extra=self.context, exc_info=True)
            return None

    def run(self):
        tracker = CrowdTracker()
        try:
            source = int(self.config["source"]) if self.config["source_type"] == "WEBCAM" else self.config["source"]
            self.heartbeat("STARTING")
            detector = PersonDetector()
            reconnect_attempt = 0
            last_update = 0.0
            last_heartbeat = 0.0
            roi = None

            while not self._stopping():
                self.heartbeat("RECONNECTING" if reconnect_attempt else "STARTING")
                self.camera = self._open_capture(source)
                if self.camera is None:
                    reconnect_attempt += 1
                    logger.error("camera could not be opened", extra={**self.context, "retry_attempt": reconnect_attempt})
                    if reconnect_attempt >= CAMERA_RECONNECT_ATTEMPTS:
                        self.heartbeat("ERROR", message="camera could not be opened after bounded retries")
                        return
                    if self._wait_for_retry(reconnect_attempt):
                        return
                    continue

                while not self._stopping():
                    success, frame = self.camera.read()
                    if not success or frame is None:
                        logger.warning("camera frame read failed", extra={**self.context, "retry_attempt": reconnect_attempt + 1})
                        self.heartbeat("DISCONNECTED")
                        break

                    reconnect_attempt = 0
                    frame_time = _utc_now()
                    height, width = frame.shape[:2]
                    roi = roi or (int(width * .10), int(height * .15), int(width * .90), int(height * .90))
                    result = detector.track(frame)
                    tracker.update(result, roi)
                    now = time.monotonic()

                    if now - last_update >= UPDATE_INTERVAL:
                        try:
                            self.post_count(tracker.count())
                        except requests.RequestException:
                            logger.warning("crowd reading request failed; camera processing continues", extra=self.context, exc_info=True)
                        last_update = now

                    if now - last_heartbeat >= CAMERA_HEARTBEAT_INTERVAL or last_heartbeat == 0:
                        self.heartbeat("CONNECTED", last_frame_at=frame_time)
                        last_heartbeat = now

                if self.camera is not None:
                    self.camera.release()
                    self.camera = None
                if self._stopping():
                    return

                reconnect_attempt += 1
                if reconnect_attempt >= CAMERA_RECONNECT_ATTEMPTS:
                    self.heartbeat("ERROR", message="camera stopped returning frames after bounded retries")
                    return
                self.heartbeat("RECONNECTING")
                if self._wait_for_retry(reconnect_attempt):
                    return
        except requests.RequestException:
            logger.warning("backend request failed", extra=self.context, exc_info=True)
            self.heartbeat("ERROR", message="backend request failed")
        except Exception:
            logger.exception("camera worker failed", extra=self.context)
            self.heartbeat("ERROR", message="unexpected camera worker failure")
        finally:
            if self.camera is not None:
                try:
                    self.camera.release()
                except Exception:
                    logger.exception("camera cleanup failed", extra=self.context)
                self.camera = None
            if self._stopping():
                self.heartbeat("STOPPED")
            logger.info("camera worker exited", extra=self.context)


class CameraProcessingManager:
    def __init__(self, configs):
        self.stop_event = threading.Event()
        self.workers = {}
        self._next_restart_at = {}
        self._restart_attempts = {}
        self.sync_configs(configs)

    def _stop_worker(self, camera_id, worker):
        worker.stop()
        worker.join(timeout=5)
        if worker.is_alive():
            logger.error("camera worker did not stop within timeout", extra={"camera_id": camera_id})
            return False
        return True

    def _start_worker(self, config):
        camera_id = config["id"]
        worker = CameraWorker(config, self.stop_event)
        self.workers[camera_id] = worker
        self._next_restart_at.pop(camera_id, None)
        worker.start()
        logger.info("camera worker started", extra={"camera_id": camera_id, "room_id": config.get("room_id")})

    def sync_configs(self, configs):
        desired = {config["id"]: config for config in configs}
        for camera_id in set(self.workers) - set(desired):
            worker = self.workers[camera_id]
            if self._stop_worker(camera_id, worker):
                del self.workers[camera_id]
                self._next_restart_at.pop(camera_id, None)
                self._restart_attempts.pop(camera_id, None)

        for camera_id, config in desired.items():
            worker = self.workers.get(camera_id)
            if worker is None:
                self._start_worker(config)
                continue
            if worker.config != config:
                if self._stop_worker(camera_id, worker):
                    del self.workers[camera_id]
                    self._restart_attempts.pop(camera_id, None)
                    self._start_worker(config)
                continue
            if worker.is_alive():
                self._restart_attempts.pop(camera_id, None)
            elif time.monotonic() >= self._next_restart_at.get(camera_id, 0):
                attempts = self._restart_attempts.get(camera_id, 0) + 1
                if attempts > CAMERA_RECONNECT_ATTEMPTS:
                    logger.error("camera worker restart limit reached; waiting for configuration change", extra={"camera_id": camera_id, "room_id": config.get("room_id")})
                    continue
                logger.warning("dead camera worker detected; restarting", extra={"camera_id": camera_id, "room_id": config.get("room_id")})
                self._restart_attempts[camera_id] = attempts
                self._next_restart_at[camera_id] = time.monotonic() + CAMERA_RESTART_DELAY
                self._start_worker(config)

    def stop(self):
        self.stop_event.set()
        for camera_id, worker in list(self.workers.items()):
            self._stop_worker(camera_id, worker)
