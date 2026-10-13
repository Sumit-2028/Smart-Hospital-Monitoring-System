"""Bounded in-memory latest-frame storage for camera preview delivery."""

from dataclasses import dataclass
from datetime import datetime, timezone
import threading


MAX_FRAME_BYTES = 2_000_000


@dataclass(frozen=True)
class StoredFrame:
    camera_id: int
    room_id: int
    sequence: int
    jpeg: bytes
    received_at: datetime


class LatestFrameStore:
    """Keep exactly one encoded frame per camera; never queue unbounded frames."""

    def __init__(self):
        self._lock = threading.Lock()
        self._frames: dict[int, StoredFrame] = {}
        self._sequence = 0

    def publish(self, camera_id: int, room_id: int, jpeg: bytes, received_at: datetime | None = None):
        if not jpeg:
            raise ValueError("frame is empty")
        if len(jpeg) > MAX_FRAME_BYTES:
            raise ValueError("frame is too large")
        with self._lock:
            self._sequence += 1
            frame = StoredFrame(
                camera_id=camera_id,
                room_id=room_id,
                sequence=self._sequence,
                jpeg=bytes(jpeg),
                received_at=received_at or datetime.now(timezone.utc),
            )
            self._frames[camera_id] = frame
            return frame

    def latest(self, camera_id: int, room_id: int, after_sequence: int = 0):
        with self._lock:
            frame = self._frames.get(camera_id)
            if not frame or frame.room_id != room_id or frame.sequence <= after_sequence:
                return None
            return frame

    def clear(self, camera_id: int | None = None):
        with self._lock:
            if camera_id is None:
                self._frames.clear()
            else:
                self._frames.pop(camera_id, None)


frame_store = LatestFrameStore()
