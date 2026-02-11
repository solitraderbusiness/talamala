"""Add system_jobs and job_runs tables for operations monitoring

Revision ID: 004
Revises: 003
Create Date: 2026-02-11

Note: Originally 002 but conflicted with 002_add_economic_events.
Tables are also created via checkfirst=True on startup as a safety net.
"""
from typing import Sequence, Union
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # system_jobs — registry of all background jobs
    op.execute("""
        CREATE TABLE IF NOT EXISTS system_jobs (
            id UUID PRIMARY KEY,
            job_name VARCHAR(255) NOT NULL UNIQUE,
            job_label_fa VARCHAR(512),
            job_category VARCHAR(50) NOT NULL DEFAULT 'general',
            schedule VARCHAR(255),
            last_run_at TIMESTAMPTZ,
            last_success_at TIMESTAMPTZ,
            last_failure_at TIMESTAMPTZ,
            last_error TEXT,
            last_duration_ms INTEGER,
            items_processed INTEGER DEFAULT 0,
            status VARCHAR(20) NOT NULL DEFAULT 'healthy',
            expected_interval_minutes INTEGER NOT NULL DEFAULT 5,
            enabled BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_system_jobs_job_name "
        "ON system_jobs (job_name)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_system_jobs_status "
        "ON system_jobs (status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_system_jobs_job_category "
        "ON system_jobs (job_category)"
    )

    # job_runs — execution history for each job
    op.execute("""
        CREATE TABLE IF NOT EXISTS job_runs (
            id UUID PRIMARY KEY,
            job_id UUID NOT NULL REFERENCES system_jobs(id) ON DELETE CASCADE,
            started_at TIMESTAMPTZ NOT NULL,
            finished_at TIMESTAMPTZ,
            status VARCHAR(20) NOT NULL DEFAULT 'success',
            items_processed INTEGER DEFAULT 0,
            error_message TEXT,
            duration_ms INTEGER,
            metadata_ JSONB DEFAULT '{}'
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_job_runs_job_id "
        "ON job_runs (job_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_job_runs_started_at "
        "ON job_runs (started_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_job_runs_status "
        "ON job_runs (status)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS job_runs")
    op.execute("DROP TABLE IF EXISTS system_jobs")
