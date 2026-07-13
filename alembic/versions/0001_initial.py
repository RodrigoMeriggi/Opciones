"""Initial schema for opciones platform."""

from __future__ import annotations

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.create_table(
        "underlying_assets",
        sa.Column("symbol", sa.String(32), primary_key=True),
        sa.Column("description", sa.String(256), server_default=""),
        sa.Column("currency", sa.String(8), server_default="ARS"),
        sa.Column("market", sa.String(16), server_default="BYMA"),
        sa.Column("last_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("bid", sa.Numeric(18, 6), nullable=True),
        sa.Column("ask", sa.Numeric(18, 6), nullable=True),
        sa.Column("volume", sa.Integer(), nullable=True),
        sa.Column("timestamp", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "option_contracts",
        sa.Column("symbol", sa.String(64), primary_key=True),
        sa.Column("underlying_symbol", sa.String(32), nullable=False),
        sa.Column("option_type", sa.String(8), nullable=False),
        sa.Column("strike", sa.Numeric(18, 6), nullable=False),
        sa.Column("expiration_date", sa.Date(), nullable=False),
        sa.Column("contract_size", sa.Integer(), server_default="1"),
        sa.Column("currency", sa.String(8), server_default="ARS"),
        sa.Column("bid", sa.Numeric(18, 6), nullable=True),
        sa.Column("ask", sa.Numeric(18, 6), nullable=True),
        sa.Column("last_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("volume", sa.Integer(), nullable=True),
        sa.Column("open_interest", sa.Integer(), nullable=True),
        sa.Column("implied_volatility", sa.Numeric(18, 8), nullable=True),
        sa.Column("intrinsic_value", sa.Numeric(18, 6), nullable=True),
        sa.Column("extrinsic_value", sa.Numeric(18, 6), nullable=True),
        sa.Column("days_to_expiration", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(16), server_default="ACTIVE"),
        sa.Column("moneyness", sa.String(8), nullable=True),
        sa.Column("timestamp", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_option_contracts_underlying", "option_contracts", ["underlying_symbol"])
    op.create_index("ix_option_contracts_expiration", "option_contracts", ["expiration_date"])

    op.create_table(
        "orders",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("symbol", sa.String(64), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("order_type", sa.String(16), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("limit_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("stop_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("filled_quantity", sa.Integer(), server_default="0"),
        sa.Column("average_fill_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("commission", sa.Numeric(18, 6), server_default="0"),
        sa.Column("slippage", sa.Numeric(18, 6), server_default="0"),
        sa.Column("rejection_code", sa.String(64), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("validation_notes", sa.JSON(), nullable=True),
        sa.Column("quote_used", sa.JSON(), nullable=True),
        sa.Column("fills", sa.JSON(), nullable=True),
        sa.Column("strategy_id", sa.String(64), nullable=True),
        sa.Column("correlation_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_orders_symbol", "orders", ["symbol"])
    op.create_index("ix_orders_status", "orders", ["status"])

    op.create_table(
        "positions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("symbol", sa.String(64), nullable=False, unique=True),
        sa.Column("underlying_symbol", sa.String(32), nullable=False),
        sa.Column("option_type", sa.String(8), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("average_price", sa.Numeric(18, 6), nullable=False),
        sa.Column("current_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("expiration_date", sa.Date(), nullable=False),
        sa.Column("opened_at", sa.DateTime(), nullable=False),
        sa.Column("strategy_id", sa.String(64), nullable=True),
        sa.Column("correlation_id", sa.String(64), nullable=True),
        sa.Column("is_open", sa.Boolean(), server_default=sa.text("true")),
    )

    op.create_table(
        "portfolio_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("cash", sa.Numeric(18, 6), nullable=False),
        sa.Column("reserved_cash", sa.Numeric(18, 6), server_default="0"),
        sa.Column("equity", sa.Numeric(18, 6), nullable=False),
        sa.Column("open_positions", sa.Integer(), server_default="0"),
        sa.Column("total_premium", sa.Numeric(18, 6), server_default="0"),
        sa.Column("realized_pnl", sa.Numeric(18, 6), server_default="0"),
        sa.Column("unrealized_pnl", sa.Numeric(18, 6), server_default="0"),
        sa.Column("daily_pnl", sa.Numeric(18, 6), server_default="0"),
        sa.Column("weekly_pnl", sa.Numeric(18, 6), server_default="0"),
        sa.Column("peak_equity", sa.Numeric(18, 6), server_default="0"),
        sa.Column("consecutive_losses", sa.Integer(), server_default="0"),
        sa.Column("trades_today", sa.Integer(), server_default="0"),
        sa.Column("positions_by_underlying", sa.JSON(), nullable=True),
        sa.Column("as_of", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "decision_records",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("strategy_id", sa.String(64), nullable=False),
        sa.Column("contract_symbol", sa.String(64), nullable=True),
        sa.Column("underlying_symbol", sa.String(32), nullable=True),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("indicators", sa.JSON(), nullable=True),
        sa.Column("score", sa.Numeric(18, 6), nullable=True),
        sa.Column("score_components", sa.JSON(), nullable=True),
        sa.Column("rules_passed", sa.JSON(), nullable=True),
        sa.Column("rules_failed", sa.JSON(), nullable=True),
        sa.Column("entry_reason", sa.Text(), nullable=True),
        sa.Column("discard_reason", sa.Text(), nullable=True),
        sa.Column("exit_reason", sa.Text(), nullable=True),
        sa.Column("estimated_risk", sa.Numeric(18, 6), nullable=True),
        sa.Column("expected_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("executed_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("correlation_id", sa.String(64), nullable=True),
    )

    op.create_table(
        "risk_audit",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("symbol", sa.String(64), nullable=True),
        sa.Column("side", sa.String(8), nullable=True),
        sa.Column("approved", sa.Boolean(), nullable=False),
        sa.Column("codes", sa.JSON(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("risk_audit")
    op.drop_table("decision_records")
    op.drop_table("portfolio_snapshots")
    op.drop_table("positions")
    op.drop_table("orders")
    op.drop_table("option_contracts")
    op.drop_table("underlying_assets")
