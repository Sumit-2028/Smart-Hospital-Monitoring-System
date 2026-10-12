import os
import unittest
from unittest.mock import patch

os.environ["DATABASE_URL"] = "sqlite:///./test_auth_api.db"
os.environ["ADMIN_TOKEN_SECRET"] = "test-only-auth-secret"

from fastapi.testclient import TestClient

from app.auth import issue_token
from app.database import SessionLocal
from app.main import app
from app.models.facility import AdminUser


class AdminAuthApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client_context = TestClient(app, raise_server_exceptions=False)
        cls.client_context.__enter__()
        db = SessionLocal()
        if not db.query(AdminUser).filter(AdminUser.username == "test-admin").first():
            from app.auth import hash_password
            db.add(AdminUser(username="test-admin", password_hash=hash_password("correct-password")))
            db.commit()
        db.close()

    @classmethod
    def tearDownClass(cls):
        cls.client_context.__exit__(None, None, None)

    def test_successful_login_returns_bearer_token_and_cors(self):
        response = self.client_context.post(
            "/api/admin/login",
            json={"username": "test-admin", "password": "correct-password"},
            headers={"Origin": "http://localhost:5173"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["token_type"], "bearer")
        self.assertTrue(response.json()["access_token"])
        self.assertEqual(response.headers["access-control-allow-origin"], "http://localhost:5173")

    def test_invalid_credentials_are_401(self):
        for credentials in (
            {"username": "test-admin", "password": "wrong-password"},
            {"username": "unknown", "password": "correct-password"},
        ):
            response = self.client_context.post("/api/admin/login", json=credentials, headers={"Origin": "http://127.0.0.1:5173"})
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.headers["access-control-allow-origin"], "http://127.0.0.1:5173")

    def test_invalid_input_and_missing_token_are_rejected(self):
        self.assertEqual(self.client_context.post("/api/admin/login", json={"username": "x"}).status_code, 422)
        response = self.client_context.get("/api/admin/rooms", headers={"Origin": "http://localhost:5173"})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers["access-control-allow-origin"], "http://localhost:5173")

    def test_preflight_allows_frontend_origins_and_auth_headers(self):
        for origin in ("http://localhost:5173", "http://127.0.0.1:5173"):
            response = self.client_context.options("/api/admin/login", headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type,authorization",
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["access-control-allow-origin"], origin)
            self.assertIn("authorization", response.headers["access-control-allow-headers"].lower())

    def test_valid_token_access_and_malformed_or_expired_tokens(self):
        login = self.client_context.post("/api/admin/login", json={"username": "test-admin", "password": "correct-password"})
        valid_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        self.assertEqual(self.client_context.get("/api/admin/rooms", headers=valid_headers).status_code, 200)
        self.assertEqual(self.client_context.get("/api/admin/rooms", headers={"Authorization": "Bearer malformed"}).status_code, 401)
        with patch("app.auth.time.time", return_value=1000):
            expired = issue_token("test-admin")
        with patch("app.auth.time.time", return_value=1001 + 8 * 3600):
            response = self.client_context.get("/api/admin/rooms", headers={"Authorization": f"Bearer {expired}"})
        self.assertEqual(response.status_code, 401)

    def test_multiple_active_doctor_cabins_are_available_for_assignment(self):
        login = self.client_context.post("/api/admin/login", json={"username": "test-admin", "password": "correct-password"})
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        for name in ("Test Cabin A", "Test Cabin B"):
            response = self.client_context.post("/api/admin/rooms", headers=headers, json={
                "name": name, "room_type": "DOCTOR_CABIN", "capacity": 1, "warning_percentage": 80,
            })
            self.assertEqual(response.status_code, 200)
        cabins = self.client_context.get("/api/admin/cabins", headers=headers)
        self.assertEqual(cabins.status_code, 200)
        names = {cabin["name"] for cabin in cabins.json()}
        self.assertTrue({"Test Cabin A", "Test Cabin B"}.issubset(names))

    def test_missing_secret_is_actionable(self):
        with patch.dict(os.environ, {"ADMIN_TOKEN_SECRET": ""}):
            response = self.client_context.post("/api/admin/login", json={"username": "test-admin", "password": "correct-password"})
        self.assertEqual(response.status_code, 503)
        self.assertIn("ADMIN_TOKEN_SECRET", response.json()["detail"])

    def test_unexpected_login_failure_is_sanitized_and_cors_enabled(self):
        with patch("app.routes.admin.issue_token", side_effect=ValueError("internal test failure")):
            response = self.client_context.post(
                "/api/admin/login",
                json={"username": "test-admin", "password": "correct-password"},
                headers={"Origin": "http://localhost:5173"},
            )
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["detail"], "Internal server error.")
        self.assertEqual(response.headers["access-control-allow-origin"], "http://localhost:5173")


if __name__ == "__main__":
    unittest.main()
