"""Add indexes declared by the facility and crowd models.

This migration is additive and preserves the existing unique constraints and
all historical rows. It is safe to run on an installation that partially
created any of these indexes.
"""

from alembic import op
import sqlalchemy as sa


revision = "20261014_performance_indexes"
down_revision = "20261013_admin_audit_security"
branch_labels = None
depends_on = None


INDEXES = {
    "departments": [("ix_departments_name", ["name"]), ("ix_departments_active", ["active"])],
    "rooms": [
        ("ix_rooms_name", ["name"]),
        ("ix_rooms_department_id", ["department_id"]),
        ("ix_rooms_active", ["active"]),
    ],
    "cameras": [
        ("ix_cameras_room_id", ["room_id"]),
        ("ix_cameras_active", ["active"]),
        ("ix_cameras_last_frame_at", ["last_frame_at"]),
        ("ix_cameras_status_updated_at", ["status_updated_at"]),
    ],
    "doctors": [
        ("ix_doctors_department_id", ["department_id"]),
        ("ix_doctors_cabin_id", ["cabin_id"]),
        ("ix_doctors_available", ["available"]),
        ("ix_doctors_active", ["active"]),
    ],
    "admin_users": [("ix_admin_users_role", ["role"])],
    "crowd_readings": [
        ("ix_crowd_readings_camera_id", ["camera_id"]),
        ("ix_crowd_readings_room_id", ["room_id"]),
        ("ix_crowd_readings_timestamp", ["timestamp"]),
    ],
    "congestion_events": [
        ("ix_congestion_events_started_at", ["started_at"]),
        ("ix_congestion_events_resolved", ["resolved"]),
        ("ix_congestion_events_camera_id", ["camera_id"]),
        ("ix_congestion_events_room_id", ["room_id"]),
    ],
}


def upgrade():
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    for table, indexes in INDEXES.items():
        if table not in tables:
            continue
        existing = {index["name"] for index in inspector.get_indexes(table)}
        for name, columns in indexes:
            if name not in existing:
                op.create_index(name, table, columns)


def downgrade():
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    for table, indexes in reversed(list(INDEXES.items())):
        if table not in tables:
            continue
        existing = {index["name"] for index in inspector.get_indexes(table)}
        for name, _columns in reversed(indexes):
            if name in existing:
                op.drop_index(name, table_name=table)
