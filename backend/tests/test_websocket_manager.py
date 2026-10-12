import asyncio
import unittest

from app.websocket.manager import ConnectionManager


class FakeSocket:
    def __init__(self, should_fail=False):
        self.should_fail = should_fail
        self.messages = []

    async def send_json(self, data):
        if self.should_fail:
            raise RuntimeError("test socket failure")
        self.messages.append(data)


class WebSocketManagerTests(unittest.IsolatedAsyncioTestCase):
    async def test_broadcast_removes_failed_client_and_preserves_payload(self):
        manager = ConnectionManager()
        healthy = FakeSocket()
        failed = FakeSocket(should_fail=True)
        manager.active_connections.extend([healthy, failed])

        payload = {"event_type": "camera.status", "schema_version": 1, "room_id": 4, "camera_id": 7}
        await manager.broadcast(payload)

        self.assertEqual(healthy.messages, [payload])
        self.assertEqual(manager.active_connections, [healthy])


if __name__ == "__main__":
    unittest.main()
