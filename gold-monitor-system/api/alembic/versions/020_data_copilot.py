"""Create Data Copilot tables: metric_registry, calc_runs, data_freshness.

Revision ID: 020
Revises: 019
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── metric_registry ──────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS metric_registry (
            key              VARCHAR(64) PRIMARY KEY,
            label_fa         TEXT NOT NULL,
            label_en         VARCHAR(128),
            unit             VARCHAR(32) NOT NULL,
            frequency        VARCHAR(20) NOT NULL,
            source_name      VARCHAR(100) NOT NULL,
            source_id        VARCHAR(100),
            direction_for_gold VARCHAR(30),
            description_fa   TEXT,
            precision        INTEGER DEFAULT 2,
            source_table     VARCHAR(64),
            source_column    VARCHAR(64),
            source_filter    JSONB,
            ts_column        VARCHAR(64),
            staleness_hours  DOUBLE PRECISION DEFAULT 96,
            created_at       TIMESTAMPTZ DEFAULT NOW(),
            updated_at       TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    # ── calc_runs ────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS calc_runs (
            run_id           UUID PRIMARY KEY,
            run_type         VARCHAR(50) NOT NULL,
            asset            VARCHAR(20) DEFAULT 'XAUUSD',
            ts               TIMESTAMPTZ NOT NULL,
            inputs           JSONB,
            intermediates    JSONB,
            outputs          JSONB,
            warnings         JSONB,
            created_at       TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_calc_runs_type_ts
        ON calc_runs (run_type, ts DESC)
    """)

    # ── data_freshness ───────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS data_freshness (
            key                  VARCHAR(64) PRIMARY KEY,
            expected_frequency   VARCHAR(20),
            max_age_seconds      INTEGER,
            last_seen_ts         TIMESTAMPTZ,
            is_stale             BOOLEAN DEFAULT FALSE,
            updated_at           TIMESTAMPTZ DEFAULT NOW()
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS data_freshness")
    op.execute("DROP INDEX IF EXISTS ix_calc_runs_type_ts")
    op.execute("DROP TABLE IF EXISTS calc_runs")
    op.execute("DROP TABLE IF EXISTS metric_registry")
