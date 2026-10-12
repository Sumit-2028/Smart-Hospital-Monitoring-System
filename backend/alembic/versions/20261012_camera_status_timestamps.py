"""Track camera heartbeat/status timestamps for stale-feed detection."""

from alembic import op
import sqlalchemy as sa


revision = "20261012_cam_status_ts"
down_revision = "20261009_room_camera_foundation"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    if "cameras" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("cameras")}
        if "status_updated_at" not in columns:
            op.add_column("cameras", sa.Column("status_updated_at", sa.DateTime(), nullable=True))
            op.create_index("ix_cameras_status_updated_at", "cameras", ["status_updated_at"])


def downgrade():
    inspector = sa.inspect(op.get_bind())
    if "cameras" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("cameras")}
        if "status_updated_at" in columns:
            op.drop_index("ix_cameras_status_updated_at", table_name="cameras")
            op.drop_column("cameras", "status_updated_at")
