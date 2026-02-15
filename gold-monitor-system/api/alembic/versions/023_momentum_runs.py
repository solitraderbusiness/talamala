"""Create momentum_runs table for admin debugging and audit trail.

Revision ID: 023
Revises: 022
"""

from alembic import op

revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS momentum_runs (
            id              VARCHAR(64) PRIMARY KEY,
            computed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            as_of           TIMESTAMPTZ NOT NULL,
            raw_inputs      JSONB,
            driver_scores   JSONB,
            weights         JSONB,
            composite_score FLOAT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_momentum_runs_computed
        ON momentum_runs (computed_at DESC);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS momentum_runs;")
