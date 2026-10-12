import unittest
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from app.auth import hash_password, require_superadmin, verify_password
from app.database import Base
from app.models.audit import AuditLog
from app.models.facility import AdminUser, Room
from app.routes.admin import create_admin, create_room, login, set_admin_active, update_admin
from app.routes.audit import list_audit_logs
from app.schemas.facility import AdminCreate, AdminLogin, AdminUpdate, RoomIn


class AdminSecurityTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self.superadmin = AdminUser(username="root", password_hash=hash_password("root-password"), role="SUPERADMIN")
        self.admin = AdminUser(username="operator", password_hash=hash_password("operator-password"), role="ADMIN")
        self.session.add_all([self.superadmin, self.admin])
        self.session.commit()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_admin_create_update_and_password_is_not_exposed(self):
        result = create_admin(AdminCreate(username="New Operator", password="new-password", role="ADMIN"), self.superadmin, self.session)
        self.assertEqual(result["username"], "new operator")
        self.assertNotIn("password_hash", result)
        created = self.session.query(AdminUser).filter_by(username="new operator").one()
        self.assertTrue(verify_password("new-password", created.password_hash))
        self.assertNotEqual(created.password_hash, "new-password")

        updated = update_admin(created.id, AdminUpdate(username="new operator", password="changed-password", role="ADMIN", active=True), self.superadmin, self.session)
        self.assertNotIn("password_hash", updated)
        self.assertTrue(verify_password("changed-password", self.session.get(AdminUser, created.id).password_hash))

    def test_duplicate_admin_and_failed_login_are_audited(self):
        with self.assertRaises(HTTPException) as duplicate:
            create_admin(AdminCreate(username=" ROOT ", password="another-password", role="ADMIN"), self.superadmin, self.session)
        self.assertEqual(duplicate.exception.status_code, 409)
        self.assertEqual(self.session.query(AuditLog).filter_by(action="ADMIN_CREATED", outcome="FAILURE").count(), 1)

        with self.assertRaises(HTTPException) as invalid_login:
            login(AdminLogin(username="operator", password="wrong-password"), self.session)
        self.assertEqual(invalid_login.exception.status_code, 401)
        failure = self.session.query(AuditLog).filter_by(action="LOGIN", outcome="FAILURE").one()
        self.assertEqual(failure.actor_username, "operator")
        self.assertNotIn("password", str(failure.context or {}))

    def test_role_authorization_and_self_deactivation_are_enforced(self):
        with self.assertRaises(HTTPException) as forbidden:
            require_superadmin(self.admin)
        self.assertEqual(forbidden.exception.status_code, 403)

        with self.assertRaises(HTTPException) as self_deactivate:
            set_admin_active(self.superadmin.id, False, self.superadmin, self.session)
        self.assertEqual(self_deactivate.exception.status_code, 409)
        self.assertTrue(self.session.get(AdminUser, self.superadmin.id).active)

        with self.assertRaises(HTTPException) as last_superadmin:
            update_admin(self.superadmin.id, AdminUpdate(username="root", password=None, role="ADMIN", active=True), self.superadmin, self.session)
        self.assertEqual(last_superadmin.exception.status_code, 409)

    def test_configuration_changes_are_audited_without_sensitive_values(self):
        room = create_room(RoomIn(name="Audit Room", room_type="WAITING_AREA", capacity=10, warning_percentage=80), self.admin, self.session)
        self.assertEqual(room["warning_percentage"], 80)
        row = self.session.query(AuditLog).filter_by(action="ROOM_CREATED", outcome="SUCCESS").one()
        self.assertEqual(row.actor_username, "operator")
        self.assertEqual(row.context, {"capacity": 10, "warning_percentage": 80})

    def test_audit_query_filters_and_paginates(self):
        for index in range(3):
            self.session.add(AuditLog(actor_admin_id=self.superadmin.id, actor_username="root", action="ROOM_UPDATED", outcome="SUCCESS", resource_type="ROOM", resource_id=str(index), context={"index": index}))
        self.session.commit()
        result = list_audit_logs(start_date=None, end_date=None, actor_id=None, actor_username=None, action="ROOM_UPDATED", resource_type="ROOM", outcome="SUCCESS", offset=1, limit=1, actor=self.superadmin, db=self.session)
        self.assertEqual(result["total"], 3)
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["offset"], 1)
        self.assertNotIn("password_hash", str(result))

    def test_audit_failure_rolls_back_business_transaction(self):
        with patch("app.routes.admin.add_audit", side_effect=SQLAlchemyError("audit unavailable")):
            with self.assertRaises(HTTPException) as failure:
                create_room(RoomIn(name="Should Roll Back", room_type="WAITING_AREA", capacity=10, warning_percentage=80), self.admin, self.session)
        self.assertEqual(failure.exception.status_code, 503)
        self.assertIsNone(self.session.query(Room).filter_by(name="Should Roll Back").first())


if __name__ == "__main__":
    unittest.main()
