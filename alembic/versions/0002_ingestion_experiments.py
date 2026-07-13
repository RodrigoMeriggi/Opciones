"""Migración: ingesta histórica, experimentos y estado autónomo."""

from __future__ import annotations

revision = "0002_ingestion_experiments"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.create_table(
        "import_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("source", sa.String(128), nullable=False),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("imported_at", sa.DateTime(), nullable=False),
        sa.Column("schema_version", sa.String(16), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("period_start", sa.DateTime(), nullable=True),
        sa.Column("period_end", sa.DateTime(), nullable=True),
        sa.Column("initiated_by", sa.String(128), nullable=False),
        sa.Column("allow_duplicate", sa.Boolean(), server_default=sa.text("false")),
    )
    op.create_table(
        "historical_bars",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("open", sa.Numeric(18, 6), nullable=True),
        sa.Column("high", sa.Numeric(18, 6), nullable=True),
        sa.Column("low", sa.Numeric(18, 6), nullable=True),
        sa.Column("close", sa.Numeric(18, 6), nullable=True),
        sa.Column("volume", sa.Integer(), nullable=True),
        sa.Column("bid", sa.Numeric(18, 6), nullable=True),
        sa.Column("ask", sa.Numeric(18, 6), nullable=True),
        sa.Column("bid_size", sa.Integer(), nullable=True),
        sa.Column("ask_size", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(64), nullable=True),
        sa.Column("import_id", sa.Uuid(), nullable=True),
        sa.Column("classification", sa.String(16), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
    )
    op.create_index("ix_hist_bars_symbol_ts", "historical_bars", ["symbol", "timestamp"])
    op.create_table(
        "historical_option_quotes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(64), nullable=False),
        sa.Column("underlying_symbol", sa.String(32), nullable=False),
        sa.Column("option_type", sa.String(8), nullable=False),
        sa.Column("strike", sa.Numeric(18, 6), nullable=False),
        sa.Column("expiration_date", sa.Date(), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("bid", sa.Numeric(18, 6), nullable=True),
        sa.Column("ask", sa.Numeric(18, 6), nullable=True),
        sa.Column("last_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("volume", sa.Integer(), nullable=True),
        sa.Column("open_interest", sa.Integer(), nullable=True),
        sa.Column("contract_size", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(8), nullable=True),
        sa.Column("source", sa.String(64), nullable=True),
        sa.Column("import_id", sa.Uuid(), nullable=True),
        sa.Column("classification", sa.String(16), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_hist_opt_und_ts", "historical_option_quotes", ["underlying_symbol", "timestamp"]
    )
    op.create_index(
        "ix_hist_opt_exp_strike_type",
        "historical_option_quotes",
        ["expiration_date", "strike", "option_type"],
    )
    op.create_table(
        "experiments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("period", sa.JSON(), nullable=False),
        sa.Column("train_metrics", sa.JSON(), nullable=True),
        sa.Column("validation_metrics", sa.JSON(), nullable=True),
        sa.Column("test_metrics", sa.JSON(), nullable=True),
        sa.Column("walk_forward_metrics", sa.JSON(), nullable=True),
        sa.Column("objective_score", sa.Numeric(18, 8), nullable=True),
        sa.Column("robustness_score", sa.Numeric(18, 8), nullable=True),
        sa.Column("fragile", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("approved_for_live", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("code_version", sa.String(32), nullable=True),
        sa.Column("data_version", sa.String(64), nullable=True),
    )
    op.create_table(
        "application_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("application_state")
    op.drop_table("experiments")
    op.drop_table("historical_option_quotes")
    op.drop_table("historical_bars")
    op.drop_table("import_versions")
