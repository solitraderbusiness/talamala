"""Create risk_radar_runs table for admin debugging and audit trail.

Revision ID: 022
Revises: 021
"""

from alembic import op

revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS risk_radar_runs (
            id              VARCHAR(64) PRIMARY KEY,
            computed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            as_of           TIMESTAMPTZ NOT NULL,
            raw_inputs      JSONB,
            component_scores JSONB,
            weights         JSONB,
            confidences     JSONB,
            final_score     FLOAT,
            label           VARCHAR(20),
            warnings        JSONB,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_risk_radar_runs_computed
        ON risk_radar_runs (computed_at DESC);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS risk_radar_runs;")
