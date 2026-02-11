"""Add system_jobs and job_runs tables for operations monitoring

Revision ID: 002
Revises: 001
Create Date: 2026-02-11
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
    # system_jobs — registry of all background jobs
    op.create_table(
        "system_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_name", sa.String(255), nullable=False, unique=True),
        sa.Column("job_label_fa", sa.String(512), nullable=True),
        sa.Column(
            "job_category",
            sa.String(50),
            nullable=False,
            server_default="general",
        ),
        sa.Column("schedule", sa.String(255), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("last_duration_ms", sa.Integer, nullable=True),
        sa.Column("items_processed", sa.Integer, nullable=True, server_default="0"),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="healthy",
        ),
        sa.Column("expected_interval_minutes", sa.Integer, nullable=False, server_default="5"),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index("ix_system_jobs_job_name", "system_jobs", ["job_name"], unique=True)
    op.create_index("ix_system_jobs_status", "system_jobs", ["status"])
    op.create_index("ix_system_jobs_job_category", "system_jobs", ["job_category"])

    # job_runs — execution history for each job
    op.create_table(
        "job_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("system_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="success",
        ),
        sa.Column("items_processed", sa.Integer, nullable=True, server_default="0"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("metadata_", postgresql.JSONB, server_default="{}"),
    )
    op.create_index("ix_job_runs_job_id", "job_runs", ["job_id"])
    op.create_index("ix_job_runs_started_at", "job_runs", ["started_at"])
    op.create_index("ix_job_runs_status", "job_runs", ["status"])


def downgrade() -> None:
    op.drop_table("job_runs")
    op.drop_table("system_jobs")
