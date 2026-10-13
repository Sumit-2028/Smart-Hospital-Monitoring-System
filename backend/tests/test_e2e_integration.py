"""Isolated API/WebSocket integration coverage.

This suite never uses the configured PostgreSQL database. It overrides the
FastAPI database dependency with an in-memory SQLite database and uses
deterministic crowd readings as the documented test seam. It does not claim
that YOLO detected real people or that a physical camera was connected.
"""

import csv
import io
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.auth import hash_password, issue_token
from app.database import Base, get_db
from app.models.audit import AuditLog
from app.models.crowd import CongestionEvent, CrowdReading
from app.models.facility import AdminUser, Camera, Department, Room


class EndToEndIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_database_url = os.environ.get("DATABASE_URL")
        cls.original_agent_token = os.environ.get("CAMERA_AGENT_TOKEN")
        os.environ["ADMIN_TOKEN_SECRET"] = "isolated-e2e-admin-secret"
        os.environ["CAMERA_AGENT_TOKEN"] = "isolated-e2e-camera-token"

        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(cls.engine)
        cls.session_factory = sessionmaker(bind=cls.engine, expire_on_commit=False)

        cls.db = cls.session_factory()
        cls.department = Department(name="E2E Cardiology", description="isolated integration data")
        cls.room_one = Room(
            name="E2E Waiting Room",
            room_type="WAITING_AREA",
            capacity=10,
            warning_percentage=80,
        )
        cls.room_two = Room(
            name="E2E Doctor Cabin",
            room_type="DOCTOR_CABIN",
            capacity=4,
            warning_percentage=75,
        )
        cls.db.add_all([cls.department, cls.room_one, cls.room_two])
        cls.db.flush()
        cls.room_one.department_id = cls.department.id
        cls.room_two.department_id = cls.department.id
        cls.camera_one = Camera(
            name="E2E Camera One",
            source_type="WEBCAM",
            source="0",
            room_id=cls.room_one.id,
            status="STOPPED",
        )
        cls.camera_two = Camera(
            name="E2E Camera Two",
            source_type="WEBCAM",
            source="1",
            room_id=cls.room_two.id,
            status="STOPPED",
        )
        cls.admin = AdminUser(
            username="e2e-superadmin",
            password_hash=hash_password("isolated-e2e-password"),
            role="SUPERADMIN",
            active=True,
        )
        cls.db.add_all([cls.camera_one, cls.camera_two, cls.admin])
        cls.db.commit()
        cls.department_id = cls.department.id
        cls.room_one_id = cls.room_one.id
        cls.room_two_id = cls.room_two.id
        cls.camera_one_id = cls.camera_one.id
        cls.camera_two_id = cls.camera_two.id
        cls.db.close()

        cls.previous_overrides = dict(main.app.dependency_overrides)

        def override_db():
            session = cls.session_factory()
            try:
                yield session
            finally:
                session.close()

        main.app.dependency_overrides[get_db] = override_db
        cls.previous_engine = main.engine
        main.engine = cls.engine
        cls.client_context = TestClient(main.app, raise_server_exceptions=False)
        cls.client = cls.client_context.__enter__()

        login = cls.client.post(
            "/api/admin/login",
            json={"username": "e2e-superadmin", "password": "isolated-e2e-password"},
        )
        if login.status_code != 200:
            raise AssertionError(f"isolated admin login failed: {login.text}")
        cls.admin_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        cls.camera_headers = {"X-Camera-Agent-Token": "isolated-e2e-camera-token"}

    @classmethod
    def tearDownClass(cls):
        cls.client_context.__exit__(None, None, None)
        main.engine = cls.previous_engine
        main.app.dependency_overrides.clear()
        main.app.dependency_overrides.update(cls.previous_overrides)
        cls.engine.dispose()
        if cls.original_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = cls.original_database_url
        if cls.original_agent_token is None:
            os.environ.pop("CAMERA_AGENT_TOKEN", None)
        else:
            os.environ["CAMERA_AGENT_TOKEN"] = cls.original_agent_token

    def post_reading(self, camera_id, person_count):
        response = self.client.post(
            "/api/crowd/",
            headers=self.camera_headers,
            json={"camera_id": camera_id, "person_count": person_count},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_room_camera_mapping_event_lifecycle_websocket_reports_and_audit(self):
        rooms = self.client.get("/api/admin/rooms", headers=self.admin_headers)
        self.assertEqual(rooms.status_code, 200)
        room_ids = {room["id"] for room in rooms.json()}
        self.assertIn(self.room_one.id, room_ids)

        internal = self.client.get("/api/monitoring/internal/cameras", headers=self.camera_headers)
        self.assertEqual(internal.status_code, 200)
        internal_mapping = {item["id"]: item["room_id"] for item in internal.json()}
        self.assertEqual(internal_mapping[self.camera_one.id], self.room_one.id)
        self.assertEqual(internal_mapping[self.camera_two.id], self.room_two.id)

        below = self.post_reading(self.camera_one.id, 7)
        self.assertEqual(below["room_id"], self.room_one.id)
        self.assertEqual(below["camera_id"], self.camera_one.id)
        self.assertEqual(below["status"], "NORMAL")

        with self.client.websocket_connect("/ws") as websocket:
            above = self.post_reading(self.camera_one.id, 10)
            message = websocket.receive_json()
            self.assertEqual(message["event_type"], "crowd.reading")
            self.assertEqual(message["camera_id"], self.camera_one.id)
            self.assertEqual(message["room_id"], self.room_one.id)
            self.assertEqual(message["schema_version"], 1)
            self.assertEqual(above["event"], "STARTED")
            self.assertEqual(above["event_details"]["status"], "ACTIVE")

        ongoing = self.post_reading(self.camera_one.id, 12)
        self.assertEqual(ongoing["event"], "ONGOING")
        self.assertEqual(ongoing["event_details"]["peak_crowd"], 12)

        other_room_event = self.post_reading(self.camera_two.id, 4)
        self.assertEqual(other_room_event["room_id"], self.room_two.id)
        self.assertEqual(other_room_event["event_details"]["room_id"], self.room_two.id)

        resolved = self.post_reading(self.camera_one.id, 7)
        self.assertEqual(resolved["event"], "ENDED")
        self.assertEqual(resolved["event_details"]["status"], "RESOLVED")

        summary = self.client.get("/api/monitoring/summary")
        self.assertEqual(summary.status_code, 200)
        summary_payload = summary.json()
        self.assertEqual(summary_payload["total_count"], 11)
        self.assertEqual(summary_payload["complete_room_count"], 2)
        room_counts = {item["room_id"]: item["current_count"] for item in summary_payload["rooms"]}
        self.assertEqual(room_counts[self.room_one.id], 7)
        self.assertEqual(room_counts[self.room_two.id], 4)

        active = self.client.get("/api/crowd/alerts/active", params={"room_id": self.room_two.id})
        self.assertEqual(active.status_code, 200)
        self.assertEqual(active.json()["total"], 1)
        self.assertEqual(active.json()["items"][0]["room_id"], self.room_two.id)

        history = self.client.get("/api/crowd/events/history", params={"room_id": self.room_one.id, "status": "RESOLVED"})
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.json()["total"], 1)

        session = self.session_factory()
        readings = session.query(CrowdReading).filter(CrowdReading.camera_id == self.camera_one.id).all()
        events = session.query(CongestionEvent).filter(CongestionEvent.room_id == self.room_one.id).all()
        self.assertTrue(all(reading.room_id == self.room_one.id for reading in readings))
        self.assertEqual(len(events), 1)
        self.assertTrue(events[0].resolved)
        session.close()

        export = self.client.get(
            "/api/reports/crowd-readings.csv",
            headers=self.admin_headers,
            params={"room_id": self.room_one.id, "camera_id": self.camera_one.id},
        )
        self.assertEqual(export.status_code, 200)
        rows = list(csv.DictReader(io.StringIO(export.text)))
        self.assertGreaterEqual(len(rows), 4)
        self.assertTrue(all(int(row["room_id"]) == self.room_one.id for row in rows))
        self.assertTrue(all(int(row["camera_id"]) == self.camera_one.id for row in rows))

        audit = self.client.get("/api/admin/audit-logs", headers=self.admin_headers)
        self.assertEqual(audit.status_code, 200)
        actions = {item["action"] for item in audit.json()["items"]}
        self.assertIn("LOGIN", actions)
        self.assertIn("REPORT_EXPORTED", actions)
        self.assertNotIn("isolated-e2e-password", export.text)
        self.assertNotIn("isolated-e2e-camera-token", export.text)

    def test_camera_disconnect_does_not_resolve_event_and_reconnect_is_fresh(self):
        self.post_reading(self.camera_two.id, 4)
        now = datetime.now(timezone.utc).isoformat()
        disconnected = self.client.post(
            "/api/monitoring/internal/heartbeat",
            headers=self.camera_headers,
            json={"camera_id": self.camera_two.id, "status": "DISCONNECTED"},
        )
        self.assertEqual(disconnected.status_code, 200)

        rooms = self.client.get("/api/monitoring/rooms")
        self.assertEqual(rooms.status_code, 200)
        room = next(item for item in rooms.json() if item["room_id"] == self.room_two.id)
        self.assertEqual(room["camera"]["status"], "DISCONNECTED")

        session = self.session_factory()
        event_before = session.query(CongestionEvent).filter(
            CongestionEvent.room_id == self.room_two.id,
            CongestionEvent.resolved.is_(False),
        ).one()
        session.close()
        self.assertIsNone(event_before.ended_at)

        reconnected = self.client.post(
            "/api/monitoring/internal/heartbeat",
            headers=self.camera_headers,
            json={"camera_id": self.camera_two.id, "status": "CONNECTED", "last_frame_at": now},
        )
        self.assertEqual(reconnected.status_code, 200)
        rooms = self.client.get("/api/monitoring/rooms")
        room = next(item for item in rooms.json() if item["room_id"] == self.room_two.id)
        self.assertEqual(room["camera"]["status"], "CONNECTED")

    def test_room_detail_and_today_summary_are_room_scoped(self):
        detail = self.client.get(f"/api/monitoring/rooms/{self.room_one.id}")
        self.assertEqual(detail.status_code, 200)
        payload = detail.json()
        self.assertEqual(payload["room_id"], self.room_one.id)
        self.assertEqual(payload["cameras"][0]["id"], self.camera_one.id)
        self.assertNotIn("source", payload["cameras"][0])

        summary = self.client.get("/api/crowd/today", params={"room_id": self.room_one.id})
        self.assertEqual(summary.status_code, 200)
        self.assertIn("average_crowd", summary.json())
        self.assertIn("peak_crowd", summary.json())

        missing = self.client.get("/api/monitoring/rooms/999999")
        self.assertEqual(missing.status_code, 404)

    def test_camera_frame_ingestion_is_authenticated_and_room_bound(self):
        frame = b"\xff\xd8test-jpeg\xff\xd9"
        accepted = self.client.post(
            f"/api/monitoring/internal/cameras/{self.camera_one.id}/frame",
            headers={**self.camera_headers, "Content-Type": "image/jpeg"},
            content=frame,
        )
        self.assertEqual(accepted.status_code, 202, accepted.text)
        self.assertEqual(accepted.json()["room_id"], self.room_one.id)

        unauthorized = self.client.get(
            f"/api/monitoring/rooms/{self.room_one.id}/cameras/{self.camera_one.id}/stream",
            headers={"Origin": "http://localhost:5173"},
        )
        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(unauthorized.headers.get("access-control-allow-origin"), "http://localhost:5173")

        wrong_room = self.client.get(
            f"/api/monitoring/rooms/{self.room_two.id}/cameras/{self.camera_one.id}/stream",
            headers=self.admin_headers,
        )
        self.assertEqual(wrong_room.status_code, 404)

    def test_expired_admin_token_cannot_open_camera_stream(self):
        # Build the token without printing or persisting its value.  This
        # exercises the same expiry validation used by the live stream route.
        with patch("app.auth.time.time", return_value=1000):
            expired = issue_token("e2e-superadmin")
        with patch("app.auth.time.time", return_value=1000 + 8 * 3600 + 1):
            response = self.client.get(
                f"/api/monitoring/rooms/{self.room_one.id}/cameras/{self.camera_one.id}/stream",
                headers={"Authorization": f"Bearer {expired}"},
            )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Invalid or expired admin token")

    def test_invalid_camera_and_authentication_are_rejected_without_data_changes(self):
        before = self.client.get("/api/crowd/rooms/999999/latest")
        self.assertEqual(before.status_code, 200)
        invalid_camera = self.client.post(
            "/api/crowd/",
            headers=self.camera_headers,
            json={"camera_id": 999999, "person_count": 2},
        )
        self.assertEqual(invalid_camera.status_code, 422)
        no_auth = self.client.get("/api/reports/crowd-readings.csv")
        self.assertEqual(no_auth.status_code, 401)


if __name__ == "__main__":
    unittest.main()
