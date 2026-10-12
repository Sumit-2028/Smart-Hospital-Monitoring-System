"""Add facility entities and nullable crowd scope columns.

This migration is additive and preserves existing crowd data.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261009_room_camera_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())
    if "departments" not in existing:
        op.create_table("departments", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(120), nullable=False), sa.Column("description", sa.String(500)), sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False), sa.UniqueConstraint("name", name="uq_department_name"))
    if "rooms" not in existing:
        op.create_table("rooms", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(120), nullable=False), sa.Column("code", sa.String(80)), sa.Column("room_type", sa.String(40), nullable=False), sa.Column("department_id", sa.Integer(), sa.ForeignKey("departments.id", ondelete="SET NULL")), sa.Column("capacity", sa.Integer(), nullable=False), sa.Column("warning_percentage", sa.Integer(), nullable=False), sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False), sa.UniqueConstraint("code"), sa.CheckConstraint("capacity > 0", name="ck_room_capacity_positive"), sa.CheckConstraint("warning_percentage > 0 AND warning_percentage <= 100", name="ck_room_warning_percentage"))
    if "cameras" not in existing:
        op.create_table("cameras", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(120), nullable=False), sa.Column("source_type", sa.String(20), nullable=False), sa.Column("source", sa.String(500), nullable=False), sa.Column("room_id", sa.Integer(), sa.ForeignKey("rooms.id", ondelete="RESTRICT"), nullable=False), sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("status", sa.String(20), nullable=False), sa.Column("last_frame_at", sa.DateTime()), sa.Column("processing_interval", sa.Integer(), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False))
    if "doctors" not in existing:
        op.create_table("doctors", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(160), nullable=False), sa.Column("specialty", sa.String(160), nullable=False), sa.Column("department_id", sa.Integer(), sa.ForeignKey("departments.id", ondelete="SET NULL")), sa.Column("cabin_id", sa.Integer(), sa.ForeignKey("rooms.id", ondelete="SET NULL")), sa.Column("work_identifier", sa.String(120)), sa.Column("available", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False))
    if "admin_users" not in existing:
        op.create_table("admin_users", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("username", sa.String(120), nullable=False), sa.Column("password_hash", sa.String(300), nullable=False), sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("created_at", sa.DateTime(), nullable=False), sa.UniqueConstraint("username"))
    for table in ("crowd_readings", "congestion_events"):
        if table not in existing:
            continue
        columns = {column["name"] for column in inspector.get_columns(table)}
        if "camera_id" not in columns:
            op.add_column(table, sa.Column("camera_id", sa.Integer(), sa.ForeignKey("cameras.id", ondelete="SET NULL"), nullable=True))
        if "room_id" not in columns:
            op.add_column(table, sa.Column("room_id", sa.Integer(), sa.ForeignKey("rooms.id", ondelete="SET NULL"), nullable=True))


def downgrade():
    raise RuntimeError("This additive migration has no automatic destructive downgrade")
