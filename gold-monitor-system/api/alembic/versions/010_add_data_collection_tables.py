"""Add data collection & outcome tracking tables.

Revision ID: 010
Revises: 009
Create Date: 2026-02-12
"""

from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. alert_market_snapshots
    op.execute("""
        CREATE TABLE IF NOT EXISTS alert_market_snapshots (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            alert_id UUID NOT NULL UNIQUE REFERENCES alerts(id) ON DELETE CASCADE,

            -- Prices
            xauusd FLOAT,
            xagusd FLOAT,
            dxy FLOAT,
            usdirr FLOAT,
            wti FLOAT,
            btcusd FLOAT,
            spx FLOAT,
            us10y FLOAT,
            vix FLOAT,
            coin FLOAT,
            gold_18k FLOAT,

            -- Technicals
            gold_rsi_14 FLOAT,
            gold_ma50 FLOAT,
            gold_ma200 FLOAT,
            gold_atr_14 FLOAT,
            gold_price_vs_ma50_pct FLOAT,
            gold_price_vs_ma200_pct FLOAT,
            gold_5d_return_pct FLOAT,
            gold_10d_return_pct FLOAT,
            dxy_5d_change FLOAT,

            -- Sentiment
            sentiment_composite INTEGER,
            sentiment_direction VARCHAR(20),
            sentiment_sub_scores JSONB,

            -- Alert context
            alerts_1h_count INTEGER,
            alerts_4h_count INTEGER,
            alerts_24h_count INTEGER,
            alerts_bullish_24h INTEGER,
            alerts_bearish_24h INTEGER,
            dominant_sentiment_24h VARCHAR(20),

            -- Previous high alert
            prev_high_alert_id UUID,
            prev_high_alert_hours_ago FLOAT,
            prev_high_alert_category VARCHAR(50),
            prev_high_alert_direction VARCHAR(20),

            -- Price momentum before
            price_change_1h_before FLOAT,
            price_change_4h_before FLOAT,
            price_change_24h_before FLOAT,

            -- Quality
            snapshot_complete BOOLEAN NOT NULL DEFAULT FALSE,
            missing_fields JSONB,
            fetch_duration_ms INTEGER,

            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_snapshot_created_at
        ON alert_market_snapshots (created_at)
    """)

    # 2. alert_outcomes
    op.execute("""
        CREATE TABLE IF NOT EXISTS alert_outcomes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            alert_id UUID NOT NULL UNIQUE REFERENCES alerts(id) ON DELETE CASCADE,

            -- Alert context
            alert_direction VARCHAR(20),
            alert_severity VARCHAR(10),
            price_at_alert FLOAT,
            alert_created_at TIMESTAMPTZ,

            -- 30 min
            price_30min FLOAT,
            change_pct_30min FLOAT,
            direction_correct_30min BOOLEAN,
            checked_at_30min TIMESTAMPTZ,

            -- 1 hour
            price_1h FLOAT,
            change_pct_1h FLOAT,
            direction_correct_1h BOOLEAN,
            checked_at_1h TIMESTAMPTZ,

            -- 4 hours
            price_4h FLOAT,
            change_pct_4h FLOAT,
            direction_correct_4h BOOLEAN,
            checked_at_4h TIMESTAMPTZ,

            -- 24 hours
            price_24h FLOAT,
            change_pct_24h FLOAT,
            direction_correct_24h BOOLEAN,
            checked_at_24h TIMESTAMPTZ,

            -- 48 hours
            price_48h FLOAT,
            change_pct_48h FLOAT,
            direction_correct_48h BOOLEAN,
            checked_at_48h TIMESTAMPTZ,

            -- 7 days
            price_7d FLOAT,
            change_pct_7d FLOAT,
            direction_correct_7d BOOLEAN,
            checked_at_7d TIMESTAMPTZ,

            -- Magnitude
            max_favorable_move_pct FLOAT,
            max_adverse_move_pct FLOAT,
            time_to_max_favorable_hours FLOAT,

            -- Reversion
            reverted_within_4h BOOLEAN,
            reverted_within_24h BOOLEAN,

            -- Status
            status VARCHAR(20) NOT NULL DEFAULT 'pending_30min',
            errors JSONB,

            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_outcome_status
        ON alert_outcomes (status)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_outcome_created_at
        ON alert_outcomes (created_at)
    """)

    # 3. sentiment_timeline
    op.execute("""
        CREATE TABLE IF NOT EXISTS sentiment_timeline (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            recorded_at TIMESTAMPTZ NOT NULL UNIQUE,
            composite_score INTEGER,
            direction VARCHAR(20),
            sub_scores JSONB,
            gold_price FLOAT,
            gold_change_1h_pct FLOAT,
            alerts_active_1h INTEGER,
            alerts_active_4h INTEGER,
            alerts_active_24h INTEGER
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_sentiment_tl_recorded_at
        ON sentiment_timeline (recorded_at)
    """)

    # 4. price_history
    op.execute("""
        CREATE TABLE IF NOT EXISTS price_history (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            symbol VARCHAR(32) NOT NULL,
            timeframe VARCHAR(10) NOT NULL,
            datetime_utc TIMESTAMPTZ NOT NULL,
            open FLOAT,
            high FLOAT,
            low FLOAT,
            close FLOAT,
            volume FLOAT,
            source VARCHAR(32),
            UNIQUE (symbol, timeframe, datetime_utc)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_price_history_symbol_tf
        ON price_history (symbol, timeframe)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_price_history_symbol_tf_dt_desc
        ON price_history (symbol, timeframe, datetime_utc DESC)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS price_history")
    op.execute("DROP TABLE IF EXISTS sentiment_timeline")
    op.execute("DROP TABLE IF EXISTS alert_outcomes")
    op.execute("DROP TABLE IF EXISTS alert_market_snapshots")
