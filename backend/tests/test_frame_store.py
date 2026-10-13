import asyncio
import unittest

from app.routes.monitoring import _mjpeg_frames
from app.services.frame_store import LatestFrameStore
from app.services.frame_store import frame_store


class LatestFrameStoreTests(unittest.TestCase):
    def test_store_keeps_only_latest_frame_for_each_camera_and_scopes_room(self):
        store = LatestFrameStore()
        first = store.publish(1, 10, b"first")
        second = store.publish(1, 10, b"second")

        self.assertEqual(store.latest(1, 10, first.sequence).sequence, second.sequence)
        current = store.latest(1, 10, first.sequence - 1)
        self.assertEqual(current.jpeg, b"second")
        self.assertIsNone(store.latest(1, 11))

    def test_store_rejects_empty_or_oversized_frames(self):
        store = LatestFrameStore()
        with self.assertRaises(ValueError):
            store.publish(1, 10, b"")
        with self.assertRaises(ValueError):
            store.publish(1, 10, b"x" * 2_000_001)

    def test_multiple_stream_consumers_read_the_same_latest_frame(self):
        async def read_first_frames():
            frame_store.clear()
            frame_store.publish(7, 70, b"shared-jpeg")
            first_stream = _mjpeg_frames(7, 70)
            second_stream = _mjpeg_frames(7, 70)
            first = await first_stream.__anext__()
            second = await second_stream.__anext__()
            await first_stream.aclose()
            await second_stream.aclose()
            return first, second

        first, second = asyncio.run(read_first_frames())
        self.assertEqual(first, second)
        self.assertIn(b"shared-jpeg", first)


if __name__ == "__main__":
    unittest.main()
