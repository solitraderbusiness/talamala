"""Add regime_scores table for liquidity regime engine.

Revision ID: 014
Revises: 013
Create Date: 2026-02-13
"""

from alembic import op

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS regime_scores (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            ts DATE UNIQUE NOT NULL,
            liquidity_stress_index FLOAT,
            usd_pressure_index FLOAT,
            real_yield_pressure_index FLOAT,
            p_expansion FLOAT,
            p_tightening FLOAT,
            p_stress FLOAT,
            p_recovery FLOAT,
            smoothed_p_expansion FLOAT,
            smoothed_p_tightening FLOAT,
            smoothed_p_stress FLOAT,
            smoothed_p_recovery FLOAT,
            chosen_regime VARCHAR(16),
            real_yield_source VARCHAR(32),
            credit_proxy_source VARCHAR(32),
            days_skipped INTEGER DEFAULT 0,
            metadata JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_regime_scores_ts
        ON regime_scores (ts DESC)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS regime_scores")
