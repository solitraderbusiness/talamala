"""Create analysis_audit_logs table for indicator computation provenance.

Stores one row per indicator per computation with full metadata:
indicator_id, score, percentile, raw_value, transformed_value,
smoothed_value, direction, zscore, source_name, source_url, etc.

Revision ID: 024
Revises: 023
"""

from alembic import op

revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS analysis_audit_logs (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            run_id          VARCHAR(64) NOT NULL,
            computed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            indicator_id    VARCHAR(64) NOT NULL,
            score           INTEGER,
            percentile      FLOAT,
            raw_value       FLOAT,
            transformed_value FLOAT,
            smoothed_value  FLOAT,
            direction       VARCHAR(32),
            window_size     INTEGER,
            crowded         BOOLEAN DEFAULT FALSE,
            stale           BOOLEAN DEFAULT FALSE,
            fallback_used   BOOLEAN DEFAULT FALSE,
            last_updated_at VARCHAR(32),
            source_name     VARCHAR(128),
            source_url      VARCHAR(512),
            winsorize_bounds JSONB,
            smoothing_applied BOOLEAN DEFAULT FALSE,
            scoring_method  VARCHAR(32),
            zscore          FLOAT,
            context         VARCHAR(32),
            extra           JSONB
        );

        CREATE INDEX IF NOT EXISTS idx_analysis_audit_logs_run_id ON analysis_audit_logs(run_id);
        CREATE INDEX IF NOT EXISTS idx_analysis_audit_logs_indicator ON analysis_audit_logs(indicator_id);
        CREATE INDEX IF NOT EXISTS idx_analysis_audit_logs_computed ON analysis_audit_logs(computed_at DESC);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS analysis_audit_logs")
