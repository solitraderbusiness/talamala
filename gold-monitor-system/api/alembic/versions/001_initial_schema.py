"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-02-08
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Sources table
    op.create_table(
        "sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("type", sa.String(50), nullable=False, server_default="rss"),
        sa.Column("base_url", sa.String(1024), nullable=False),
        sa.Column("endpoints", postgresql.JSONB, server_default="[]"),
        sa.Column("method", sa.String(10), server_default="GET"),
        sa.Column("headers", postgresql.JSONB, server_default="{}"),
        sa.Column("auth_config", postgresql.JSONB, server_default="{}"),
        sa.Column("parser", sa.String(50), server_default="rss_parser"),
        sa.Column("enabled", sa.Boolean, server_default="true"),
        sa.Column("poll_interval_seconds", sa.Integer, server_default="60"),
        sa.Column("categories", postgresql.JSONB, server_default="[]"),
        sa.Column("rule_bindings", postgresql.JSONB, server_default="[]"),
        sa.Column("reliability_score", sa.Float, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("last_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Raw items table
    op.create_table(
        "raw_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(1024), nullable=False),
        sa.Column("url", sa.String(2048), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("content_text", sa.Text, nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("metadata_", postgresql.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_raw_items_content_hash", "raw_items", ["content_hash"])
    op.create_index("ix_raw_items_source_id", "raw_items", ["source_id"])
    op.create_index("ix_raw_items_fetched_at", "raw_items", ["fetched_at"])

    # Alerts table
    op.create_table(
        "alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(1024), nullable=False),
        sa.Column("timestamp_utc", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("source_name", sa.String(255), nullable=True),
        sa.Column("source_url", sa.String(2048), nullable=True),
        sa.Column("matched_rule_ids", postgresql.JSONB, server_default="[]"),
        sa.Column("summary_fa", sa.Text, nullable=True),
        sa.Column("why_important_fa", sa.Text, nullable=True),
        sa.Column("expected_impact", postgresql.JSONB, server_default="[]"),
        sa.Column("severity", sa.String(10), nullable=False, server_default="medium"),
        sa.Column("time_horizon", sa.String(20), nullable=False, server_default="short"),
        sa.Column("confidence", sa.Float, server_default="0.5"),
        sa.Column("follow_up_questions", postgresql.JSONB, server_default="[]"),
        sa.Column("dedupe_key", sa.String(128), nullable=False),
        sa.Column("raw_item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("raw_items.id", ondelete="SET NULL"), nullable=True),
        sa.Column("match_evidence", postgresql.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_alerts_dedupe_key", "alerts", ["dedupe_key"], unique=True)
    op.create_index("ix_alerts_severity", "alerts", ["severity"])
    op.create_index("ix_alerts_created_at", "alerts", ["created_at"])
    op.create_index("ix_alerts_time_horizon", "alerts", ["time_horizon"])

    # Fetch logs table
    op.create_table(
        "fetch_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="success"),
        sa.Column("items_fetched_count", sa.Integer, server_default="0"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
    )
    op.create_index("ix_fetch_logs_source_id", "fetch_logs", ["source_id"])
    op.create_index("ix_fetch_logs_started_at", "fetch_logs", ["started_at"])

    # Settings table
    op.create_table(
        "settings",
        sa.Column("key", sa.String(255), primary_key=True),
        sa.Column("value", postgresql.JSONB, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Admin users table
    op.create_table(
        "admin_users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), server_default="admin"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Rules snapshot table
    op.create_table(
        "rules_snapshot",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("yaml_content", sa.Text, nullable=False),
        sa.Column("loaded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Seed default settings
    op.execute("""
        INSERT INTO settings (key, value) VALUES
        ('openrouter_model', '"anthropic/claude-sonnet-4"'),
        ('temperature', '0.3'),
        ('max_tokens', '1000'),
        ('enable_llm', 'false'),
        ('dedupe_window_hours', '6')
        ON CONFLICT (key) DO NOTHING;
    """)


def downgrade() -> None:
    op.drop_table("rules_snapshot")
    op.drop_table("admin_users")
    op.drop_table("settings")
    op.drop_table("fetch_logs")
    op.drop_table("alerts")
    op.drop_table("raw_items")
    op.drop_table("sources")
