"""Add backtest_runs table for unified backtest framework.

Revision ID: 015
Revises: 014
Create Date: 2026-02-13
"""

from alembic import op

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS backtest_runs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            run_type VARCHAR(32) NOT NULL,
            started_at TIMESTAMPTZ NOT NULL,
            finished_at TIMESTAMPTZ,
            status VARCHAR(16) NOT NULL DEFAULT 'running',
            date_range_start DATE,
            date_range_end DATE,
            total_benchmarks INTEGER,
            passed_benchmarks INTEGER,
            failed_benchmarks INTEGER,
            benchmark_results JSONB,
            summary JSONB,
            parameters JSONB,
            error_message TEXT,
            triggered_by VARCHAR(64),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_backtest_runs_type
        ON backtest_runs (run_type)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_backtest_runs_created
        ON backtest_runs (created_at)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS backtest_runs")
