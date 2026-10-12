import logging
import signal
import threading

import requests

from app.camera_manager import CameraProcessingManager
from app.config import BACKEND_URL, CAMERA_AGENT_TOKEN, CAMERA_INDEX

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def load_cameras():
    if not CAMERA_AGENT_TOKEN:
        logger.warning("CAMERA_AGENT_TOKEN is not configured; using legacy laptop webcam only. Registered admin cameras will not be started.")
        return [{"id": "legacy-webcam", "name": "Legacy webcam", "source_type": "WEBCAM", "source": str(CAMERA_INDEX), "legacy": True}]
    response = requests.get(
        f"{BACKEND_URL}/api/monitoring/internal/cameras",
        headers={"X-Camera-Agent-Token": CAMERA_AGENT_TOKEN},
        timeout=5,
    )
    response.raise_for_status()
    configs = response.json()
    for config in configs:
        config["agent_token"] = CAMERA_AGENT_TOKEN
    return configs


def main():
    configs = load_cameras()
    if not configs:
        logger.warning("No active cameras are configured")
        return
    manager = CameraProcessingManager(configs)
    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    logger.info("Started %s isolated camera workers", len(configs))
    try:
        while not stop.wait(10):
            try:
                manager.sync_configs(load_cameras())
            except requests.RequestException:
                logger.warning("camera configuration refresh failed; keeping existing workers", exc_info=True)
    finally:
        manager.stop()


if __name__ == "__main__":
    main()
