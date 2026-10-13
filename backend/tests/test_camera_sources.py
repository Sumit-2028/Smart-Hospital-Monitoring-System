import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import hash_password
from app.database import Base
from app.models.facility import AdminUser, Camera, Room
from app.routes.admin import _validate_camera_source, camera_edit_details, create_camera, update_camera
from app.schemas.facility import CameraIn, CameraUpdate


class CameraSourceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self.admin = AdminUser(username="camera-admin", password_hash=hash_password("camera-password"))
        self.room = Room(name="Source Test Room", room_type="WAITING_AREA", capacity=10, warning_percentage=80)
        self.session.add_all([self.admin, self.room])
        self.session.commit()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_local_and_network_sources_are_validated_and_normalized(self):
        self.assertEqual(_validate_camera_source("WEBCAM", " 01 "), "1")
        self.assertEqual(
            _validate_camera_source("IP_STREAM", " http://192.168.1.20:8080/video "),
            "http://192.168.1.20:8080/video",
        )
        self.assertEqual(_validate_camera_source("IP_STREAM", "rtsp://user:pass@example.test/live"), "rtsp://user:pass@example.test/live")

        for source_type, source in (
            ("WEBCAM", "-1"),
            ("WEBCAM", "laptop"),
            ("IP_STREAM", "192.168.1.20:8080/video"),
            ("IP_STREAM", "http:///video"),
            ("IP_STREAM", "ftp://example.test/video"),
        ):
            with self.assertRaises(HTTPException):
                _validate_camera_source(source_type, source)

    def test_edit_response_hides_source_and_blank_update_preserves_it(self):
        camera = create_camera(
            CameraIn(
                name="Phone camera",
                source_type="IP_STREAM",
                source="http://192.168.1.20:8080/video",
                room_id=self.room.id,
            ),
            self.admin,
            self.session,
        )
        stored = self.session.query(Camera).filter_by(id=camera["id"]).one()
        details = camera_edit_details(stored.id, self.admin, self.session)
        self.assertNotIn("source", details)
        self.assertTrue(details["source_configured"])

        update_camera(
            stored.id,
            CameraUpdate(
                name="Renamed phone camera",
                source_type=None,
                source=None,
                room_id=self.room.id,
            ),
            self.admin,
            self.session,
        )
        self.session.refresh(stored)
        self.assertEqual(stored.source, "http://192.168.1.20:8080/video")


if __name__ == "__main__":
    unittest.main()
