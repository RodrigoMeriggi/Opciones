"""Migración seguridad / auditoría / lifecycle."""

from __future__ import annotations

revision = "0003_security_observability"
down_revision = "0002_ingestion_experiments"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("username", sa.String(64), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(256), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("refresh_token_hash", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("resource", sa.String(256), nullable=False),
        sa.Column("result", sa.String(32), nullable=False),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("session_id", sa.String(64), nullable=True),
        sa.Column("correlation_id", sa.String(64), nullable=True),
        sa.Column("before", sa.JSON(), nullable=True),
        sa.Column("after", sa.JSON(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("prev_hash", sa.String(64), nullable=False),
        sa.Column("event_hash", sa.String(64), nullable=False),
    )
    # Sin UPDATE/DELETE grants a nivel app: la app solo inserta
    op.create_table(
        "approval_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("requester", sa.String(128), nullable=False),
        sa.Column("approver", sa.String(128), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("before", sa.JSON(), nullable=True),
        sa.Column("after", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "strategy_lifecycle",
        sa.Column("strategy_id", sa.String(64), primary_key=True),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("git_commit", sa.String(64), nullable=False),
        sa.Column("environment", sa.String(32), nullable=False),
        sa.Column("params", sa.JSON(), nullable=True),
        sa.Column("limits", sa.JSON(), nullable=True),
        sa.Column("approvers", sa.JSON(), nullable=True),
        sa.Column("checklist", sa.JSON(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("activation_expires_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("strategy_lifecycle")
    op.drop_table("approval_requests")
    op.drop_table("audit_events")
    op.drop_table("sessions")
    op.drop_table("users")
