"""Add signal aggregator tables.

Revision ID: 007
Revises: 006
Create Date: 2026-02-11
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── signal_sources ──────────────────────────────────────────────────
    op.create_table(
        "signal_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("telegram_channel_id", sa.String(100), nullable=True),
        sa.Column("telegram_channel_name", sa.String(255), nullable=True),
        sa.Column("url", sa.String(2048), nullable=True),
        sa.Column("active", sa.Boolean, server_default="true"),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("total_signals", sa.Integer, server_default="0"),
        sa.Column("correct_signals", sa.Integer, server_default="0"),
        sa.Column("wrong_signals", sa.Integer, server_default="0"),
        sa.Column("expired_signals", sa.Integer, server_default="0"),
        sa.Column("accuracy_rate", sa.Float, nullable=True),
        sa.Column("avg_profit_pips", sa.Float, nullable=True),
        sa.Column("avg_loss_pips", sa.Float, nullable=True),
        sa.Column("profit_factor", sa.Float, nullable=True),
        sa.Column("current_weight", sa.Float, server_default="0.5"),
        sa.Column("last_signal_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_signal_sources_type", "signal_sources", ["type"])
    op.create_index("ix_signal_sources_active", "signal_sources", ["active"])

    # ── raw_posts ───────────────────────────────────────────────────────
    op.create_table(
        "raw_posts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("signal_sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("raw_text", sa.Text, nullable=False),
        sa.Column("media_urls", postgresql.JSONB, nullable=True),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("parsed", sa.Boolean, server_default="false"),
        sa.Column("parse_attempts", sa.Integer, server_default="0"),
        sa.UniqueConstraint("source_id", "external_id", name="uq_raw_posts_source_external"),
    )
    op.create_index("ix_raw_posts_source_id", "raw_posts", ["source_id"])
    op.create_index("ix_raw_posts_parsed", "raw_posts", ["parsed"])
    op.create_index("ix_raw_posts_captured_at", "raw_posts", ["captured_at"])

    # ── parsed_signals ──────────────────────────────────────────────────
    op.create_table(
        "parsed_signals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "raw_post_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("raw_posts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("signal_sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("asset", sa.String(20), server_default="XAUUSD"),
        sa.Column("direction", sa.String(10), nullable=False),
        sa.Column("entry_price", sa.Float, nullable=True),
        sa.Column("stop_loss", sa.Float, nullable=True),
        sa.Column("take_profit_1", sa.Float, nullable=True),
        sa.Column("take_profit_2", sa.Float, nullable=True),
        sa.Column("take_profit_3", sa.Float, nullable=True),
        sa.Column("timeframe", sa.String(10), nullable=False),
        sa.Column("timeframe_confidence", sa.String(10), server_default="inferred"),
        sa.Column("analysis_type", sa.String(20), server_default="mixed"),
        sa.Column("confidence_raw", sa.Integer, server_default="5"),
        sa.Column("key_reasons", postgresql.JSONB, nullable=True),
        sa.Column("parsed_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), server_default="active"),
        sa.Column("outcome_price", sa.Float, nullable=True),
        sa.Column("outcome_pips", sa.Float, nullable=True),
        sa.Column("outcome_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_parsed_signals_source_id", "parsed_signals", ["source_id"])
    op.create_index("ix_parsed_signals_status", "parsed_signals", ["status"])
    op.create_index(
        "ix_parsed_signals_asset_timeframe", "parsed_signals", ["asset", "timeframe"]
    )
    op.create_index("ix_parsed_signals_valid_until", "parsed_signals", ["valid_until"])
    op.create_index("ix_parsed_signals_parsed_at", "parsed_signals", ["parsed_at"])

    # ── consensus_snapshots ─────────────────────────────────────────────
    op.create_table(
        "consensus_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("asset", sa.String(20), server_default="XAUUSD"),
        sa.Column("consensus_view", sa.String(20), nullable=False),
        sa.Column("timeframes_included", postgresql.JSONB, nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("signals_count", sa.Integer, server_default="0"),
        sa.Column("buy_count", sa.Integer, server_default="0"),
        sa.Column("sell_count", sa.Integer, server_default="0"),
        sa.Column("weighted_buy_score", sa.Float, server_default="0"),
        sa.Column("weighted_sell_score", sa.Float, server_default="0"),
        sa.Column("consensus_direction", sa.String(10), server_default="NEUTRAL"),
        sa.Column("consensus_strength", sa.Integer, server_default="0"),
        sa.Column("avg_entry_price", sa.Float, nullable=True),
        sa.Column("median_entry_price", sa.Float, nullable=True),
        sa.Column("avg_stop_loss", sa.Float, nullable=True),
        sa.Column("avg_take_profit", sa.Float, nullable=True),
        sa.Column("dominant_timeframe", sa.String(10), nullable=True),
        sa.Column("dominant_reasons", postgresql.JSONB, nullable=True),
        sa.Column("timeframe_alignment", postgresql.JSONB, nullable=True),
    )
    op.create_index("ix_consensus_generated_at", "consensus_snapshots", ["generated_at"])
    op.create_index("ix_consensus_view", "consensus_snapshots", ["consensus_view"])
    op.create_index(
        "ix_consensus_asset_view", "consensus_snapshots", ["asset", "consensus_view"]
    )

    # ── signal_price_ticks ──────────────────────────────────────────────
    op.create_table(
        "signal_price_ticks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("asset", sa.String(20), server_default="XAUUSD"),
        sa.Column("price", sa.Float, nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_signal_price_ticks_checked_at", "signal_price_ticks", ["checked_at"])
    op.create_index("ix_signal_price_ticks_asset", "signal_price_ticks", ["asset"])

    # ── signal_daily_performance ────────────────────────────────────────
    op.create_table(
        "signal_daily_performance",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("asset", sa.String(20), server_default="XAUUSD"),
        sa.Column("total_signals", sa.Integer, server_default="0"),
        sa.Column("closed_signals", sa.Integer, server_default="0"),
        sa.Column("winning_signals", sa.Integer, server_default="0"),
        sa.Column("losing_signals", sa.Integer, server_default="0"),
        sa.Column("expired_signals", sa.Integer, server_default="0"),
        sa.Column("win_rate", sa.Float, nullable=True),
        sa.Column("total_profit_pips", sa.Float, server_default="0"),
        sa.Column("total_loss_pips", sa.Float, server_default="0"),
        sa.Column("net_pips", sa.Float, server_default="0"),
        sa.Column("cumulative_pips", sa.Float, server_default="0"),
        sa.Column("best_signal_pips", sa.Float, nullable=True),
        sa.Column("worst_signal_pips", sa.Float, nullable=True),
        sa.Column("avg_signal_pips", sa.Float, nullable=True),
        sa.Column("consensus_accuracy", sa.Float, nullable=True),
        sa.Column("scalp_signals", sa.Integer, server_default="0"),
        sa.Column("scalp_win_rate", sa.Float, nullable=True),
        sa.Column("intraday_signals", sa.Integer, server_default="0"),
        sa.Column("intraday_win_rate", sa.Float, nullable=True),
        sa.Column("swing_signals", sa.Integer, server_default="0"),
        sa.Column("swing_win_rate", sa.Float, nullable=True),
        sa.Column("position_signals", sa.Integer, server_default="0"),
        sa.Column("position_win_rate", sa.Float, nullable=True),
        sa.UniqueConstraint("date", "asset", name="uq_daily_perf_date_asset"),
    )
    op.create_index("ix_daily_perf_date", "signal_daily_performance", ["date"])

    # ── signal_monthly_performance ──────────────────────────────────────
    op.create_table(
        "signal_monthly_performance",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("month", sa.Integer, nullable=False),
        sa.Column("asset", sa.String(20), server_default="XAUUSD"),
        sa.Column("total_signals", sa.Integer, server_default="0"),
        sa.Column("closed_signals", sa.Integer, server_default="0"),
        sa.Column("win_rate", sa.Float, nullable=True),
        sa.Column("net_pips", sa.Float, server_default="0"),
        sa.Column("cumulative_pips", sa.Float, server_default="0"),
        sa.Column("best_day_pips", sa.Float, nullable=True),
        sa.Column("worst_day_pips", sa.Float, nullable=True),
        sa.Column("avg_daily_pips", sa.Float, nullable=True),
        sa.Column("max_drawdown_pips", sa.Float, nullable=True),
        sa.Column("profit_factor", sa.Float, nullable=True),
        sa.Column("sharpe_ratio", sa.Float, nullable=True),
        sa.Column("total_consensus_calls", sa.Integer, server_default="0"),
        sa.Column("consensus_accuracy", sa.Float, nullable=True),
        sa.Column("active_sources", sa.Integer, server_default="0"),
        sa.UniqueConstraint("year", "month", "asset", name="uq_monthly_perf_ym_asset"),
    )
    op.create_index(
        "ix_monthly_perf_year_month", "signal_monthly_performance", ["year", "month"]
    )


def downgrade() -> None:
    op.drop_table("signal_monthly_performance")
    op.drop_table("signal_daily_performance")
    op.drop_table("signal_price_ticks")
    op.drop_table("consensus_snapshots")
    op.drop_table("parsed_signals")
    op.drop_table("raw_posts")
    op.drop_table("signal_sources")
