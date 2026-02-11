"""Add price tracking columns to alerts and create outcome table.

Revision ID: 003
Revises: 002
Create Date: 2026-02-11
"""

from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Add price snapshot columns to alerts ───────────────────────────
    for col, col_type in [
        ("price_xauusd_at_alert", "DOUBLE PRECISION"),
        ("price_usdirr_at_alert", "DOUBLE PRECISION"),
        ("price_coin_at_alert", "DOUBLE PRECISION"),
        ("price_18k_at_alert", "DOUBLE PRECISION"),
        ("news_type", "VARCHAR(50)"),
        ("event_category", "VARCHAR(50)"),
    ]:
        op.execute(
            f"ALTER TABLE alerts ADD COLUMN IF NOT EXISTS {col} {col_type}"
        )

    # ── Create alert_price_outcomes table ──────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS alert_price_outcomes (
            id UUID PRIMARY KEY,
            alert_id UUID NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
            check_interval VARCHAR(10) NOT NULL,
            price_xauusd DOUBLE PRECISION,
            price_usdirr DOUBLE PRECISION,
            price_coin DOUBLE PRECISION,
            price_18k DOUBLE PRECISION,
            change_pct_xauusd DOUBLE PRECISION,
            change_pct_usdirr DOUBLE PRECISION,
            change_pct_coin DOUBLE PRECISION,
            change_pct_18k DOUBLE PRECISION,
            direction_correct BOOLEAN,
            checked_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_outcome_alert_interval UNIQUE (alert_id, check_interval)
        )
    """)

    # Indexes
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_outcome_alert_id "
        "ON alert_price_outcomes (alert_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_outcome_checked_at "
        "ON alert_price_outcomes (checked_at)"
    )

    # Index on alerts for the tracker query (find alerts needing outcomes)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_alerts_price_tracking "
        "ON alerts (timestamp_utc) "
        "WHERE price_xauusd_at_alert IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS alert_price_outcomes")
    op.execute("DROP INDEX IF EXISTS ix_alerts_price_tracking")
    for col in [
        "price_xauusd_at_alert", "price_usdirr_at_alert",
        "price_coin_at_alert", "price_18k_at_alert",
        "news_type", "event_category",
    ]:
        op.execute(f"ALTER TABLE alerts DROP COLUMN IF EXISTS {col}")
