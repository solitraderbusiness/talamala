"""Add data reliability & provenance tables.

Revision ID: 013
Revises: 012
Create Date: 2026-02-13
"""

from alembic import op

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. metric_definitions
    op.execute("""
        CREATE TABLE IF NOT EXISTS metric_definitions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            metric_id VARCHAR(64) UNIQUE NOT NULL,
            display_name VARCHAR(128) NOT NULL,
            description TEXT,
            unit VARCHAR(32),
            timezone VARCHAR(32) DEFAULT 'UTC',
            update_frequency_minutes INTEGER,
            formula_version VARCHAR(16) DEFAULT 'v1',
            raw_sources JSONB,
            formula_steps JSONB,
            dependencies JSONB,
            expected_range JSONB,
            sanity_rules JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    # 2. metric_runs
    op.execute("""
        CREATE TABLE IF NOT EXISTS metric_runs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            metric_id VARCHAR(64) NOT NULL REFERENCES metric_definitions(metric_id),
            started_at TIMESTAMPTZ NOT NULL,
            finished_at TIMESTAMPTZ,
            duration_ms INTEGER,
            status VARCHAR(16) DEFAULT 'running',
            qa_result VARCHAR(16),
            qa_reasons JSONB,
            final_value JSONB,
            data_timestamp TIMESTAMPTZ,
            formula_version VARCHAR(16),
            fallback_used BOOLEAN DEFAULT FALSE,
            error_message TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_metric_runs_metric_time
        ON metric_runs (metric_id, started_at DESC)
    """)

    # 3. raw_ingests
    op.execute("""
        CREATE TABLE IF NOT EXISTS raw_ingests (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            run_id UUID REFERENCES metric_runs(id) ON DELETE CASCADE,
            source_id VARCHAR(64) NOT NULL,
            request_url TEXT,
            request_params JSONB,
            response_status INTEGER,
            response_size_bytes INTEGER,
            payload_hash VARCHAR(64),
            payload_sample JSONB,
            data_timestamp_in_payload TIMESTAMPTZ,
            retrieved_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            latency_ms INTEGER
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_raw_ingests_run
        ON raw_ingests (run_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_raw_ingests_source_time
        ON raw_ingests (source_id, retrieved_at DESC)
    """)

    # 4. transform_steps
    op.execute("""
        CREATE TABLE IF NOT EXISTS transform_steps (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            run_id UUID NOT NULL REFERENCES metric_runs(id) ON DELETE CASCADE,
            step_order INTEGER NOT NULL,
            step_name VARCHAR(64) NOT NULL,
            input_refs JSONB,
            output_value JSONB,
            normalization_method VARCHAR(32),
            normalization_params JSONB,
            notes TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_transform_steps_run
        ON transform_steps (run_id, step_order)
    """)

    # 5. validation_results
    op.execute("""
        CREATE TABLE IF NOT EXISTS validation_results (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            run_id UUID NOT NULL REFERENCES metric_runs(id) ON DELETE CASCADE,
            check_name VARCHAR(64) NOT NULL,
            result VARCHAR(16) NOT NULL,
            reason TEXT,
            details JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_validation_results_run
        ON validation_results (run_id)
    """)

    # 6. metric_alerts
    op.execute("""
        CREATE TABLE IF NOT EXISTS metric_alerts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            metric_id VARCHAR(64) NOT NULL,
            alert_type VARCHAR(32) NOT NULL,
            severity VARCHAR(16) NOT NULL,
            message TEXT,
            resolved_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_metric_alerts_metric
        ON metric_alerts (metric_id, created_at DESC)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_metric_alerts_unresolved
        ON metric_alerts (resolved_at) WHERE resolved_at IS NULL
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS metric_alerts")
    op.execute("DROP TABLE IF EXISTS validation_results")
    op.execute("DROP TABLE IF EXISTS transform_steps")
    op.execute("DROP TABLE IF EXISTS raw_ingests")
    op.execute("DROP TABLE IF EXISTS metric_runs")
    op.execute("DROP TABLE IF EXISTS metric_definitions")
