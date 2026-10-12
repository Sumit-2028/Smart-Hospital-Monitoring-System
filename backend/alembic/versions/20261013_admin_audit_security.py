"""Add administrator roles and append-only audit history.

This migration is additive. Existing administrator rows are assigned
SUPERADMIN so the current installation is not locked out; review those rows
after migration and reduce roles through the protected admin API as needed.
"""

from alembic import op
import sqlalchemy as sa


revision = "20261013_admin_audit_security"
down_revision = "20261012_cam_status_ts"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "admin_users" in tables:
        columns = {column["name"] for column in inspector.get_columns("admin_users")}
        if "role" not in columns:
            op.add_column("admin_users", sa.Column("role", sa.String(20), nullable=True))
            op.execute(sa.text("UPDATE admin_users SET role = 'SUPERADMIN' WHERE role IS NULL"))
            op.alter_column("admin_users", "role", existing_type=sa.String(20), nullable=False)
            op.create_index("ix_admin_users_role", "admin_users", ["role"])

    if "audit_logs" not in tables:
        op.create_table(
            "audit_logs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("actor_admin_id", sa.Integer(), sa.ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("actor_username", sa.String(120), nullable=True),
            sa.Column("action", sa.String(80), nullable=False),
            sa.Column("outcome", sa.String(20), nullable=False),
            sa.Column("resource_type", sa.String(80), nullable=True),
            sa.Column("resource_id", sa.String(120), nullable=True),
            sa.Column("timestamp", sa.DateTime(), nullable=False),
            sa.Column("metadata", sa.JSON(), nullable=True),
        )
        op.create_index("ix_audit_logs_id", "audit_logs", ["id"])
        op.create_index("ix_audit_logs_timestamp", "audit_logs", ["timestamp"])
        op.create_index("ix_audit_logs_actor", "audit_logs", ["actor_admin_id"])
        op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
        op.create_index("ix_audit_logs_resource", "audit_logs", ["resource_type", "resource_id"])
        op.create_index("ix_audit_logs_outcome", "audit_logs", ["outcome"])


def downgrade():
    raise RuntimeError("This security migration is intentionally not destructive; restore from a backup for rollback")
