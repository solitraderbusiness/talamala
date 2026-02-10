"""Add economic_events table and sentiment_scores table

Revision ID: 002
Revises: 001
Create Date: 2026-02-10

These tables were previously created via checkfirst=True on startup.
This migration formalizes them in Alembic version history.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # sentiment_scores (may already exist via checkfirst startup)
    op.execute("""
        CREATE TABLE IF NOT EXISTS sentiment_scores (
            id UUID PRIMARY KEY,
            timeframe VARCHAR(10) NOT NULL,
            score INTEGER NOT NULL DEFAULT 50,
            sentiment VARCHAR(20) NOT NULL DEFAULT 'neutral',
            sentiment_label VARCHAR(50) NOT NULL DEFAULT '',
            alert_count INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_sentiment_timeframe_created
        ON sentiment_scores (timeframe, created_at)
    """)

    # economic_events
    op.execute("""
        CREATE TABLE IF NOT EXISTS economic_events (
            id UUID PRIMARY KEY,
            event_name VARCHAR(512) NOT NULL,
            event_name_fa VARCHAR(512) NOT NULL DEFAULT '',
            country VARCHAR(10) NOT NULL DEFAULT '',
            currency VARCHAR(10) NOT NULL DEFAULT '',
            category VARCHAR(50) NOT NULL DEFAULT '',
            datetime_utc TIMESTAMPTZ NOT NULL,
            impact VARCHAR(10) NOT NULL DEFAULT 'low',
            actual VARCHAR(100),
            forecast VARCHAR(100),
            previous VARCHAR(100),
            source VARCHAR(50) NOT NULL DEFAULT 'mql5',
            affected_assets JSONB NOT NULL DEFAULT '[]',
            gold_impact_note JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_econ_events_name_datetime
        ON economic_events (event_name, datetime_utc)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_econ_events_datetime
        ON economic_events (datetime_utc)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_econ_events_impact
        ON economic_events (impact)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_econ_events_currency
        ON economic_events (currency)
    """)

    # Add gold_impact_note column if table existed before this migration
    op.execute("""
        ALTER TABLE economic_events
        ADD COLUMN IF NOT EXISTS gold_impact_note JSONB
    """)


def downgrade() -> None:
    op.drop_table("economic_events")
    op.drop_table("sentiment_scores")
