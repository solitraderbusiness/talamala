"""Add fundamental analysis tables.

Revision ID: 009
Revises: 008
Create Date: 2026-02-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # asset_prices_daily
    op.execute("""
        CREATE TABLE IF NOT EXISTS asset_prices_daily (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            symbol VARCHAR(32) NOT NULL,
            trade_date DATE NOT NULL,
            open FLOAT,
            high FLOAT,
            low FLOAT,
            close FLOAT NOT NULL,
            volume FLOAT,
            source VARCHAR(32) NOT NULL DEFAULT 'yahoo',
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_asset_price_symbol_date UNIQUE (symbol, trade_date)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_asset_price_symbol ON asset_prices_daily (symbol)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_asset_price_date ON asset_prices_daily (trade_date)")

    # macro_indicators
    op.execute("""
        CREATE TABLE IF NOT EXISTS macro_indicators (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            series_id VARCHAR(32) NOT NULL,
            observation_date DATE NOT NULL,
            value FLOAT NOT NULL,
            source VARCHAR(32) NOT NULL DEFAULT 'fred',
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_macro_series_date UNIQUE (series_id, observation_date)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_macro_series ON macro_indicators (series_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_macro_date ON macro_indicators (observation_date)")

    # etf_holdings
    op.execute("""
        CREATE TABLE IF NOT EXISTS etf_holdings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            fund VARCHAR(16) NOT NULL,
            holding_date DATE NOT NULL,
            total_tonnes FLOAT NOT NULL,
            change_tonnes FLOAT,
            total_oz FLOAT,
            total_value_usd FLOAT,
            source VARCHAR(64) NOT NULL,
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_etf_fund_date UNIQUE (fund, holding_date)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_etf_fund ON etf_holdings (fund)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_etf_date ON etf_holdings (holding_date)")

    # cot_data
    op.execute("""
        CREATE TABLE IF NOT EXISTS cot_data (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            report_date DATE NOT NULL,
            asset VARCHAR(32) NOT NULL DEFAULT 'gold',
            commercial_long FLOAT,
            commercial_short FLOAT,
            non_commercial_long FLOAT,
            non_commercial_short FLOAT,
            non_commercial_net FLOAT,
            open_interest FLOAT,
            change_non_commercial_net FLOAT,
            source VARCHAR(64) NOT NULL DEFAULT 'cftc',
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_cot_asset_date UNIQUE (asset, report_date)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_cot_date ON cot_data (report_date)")

    # market_events_analysis
    op.execute("""
        CREATE TABLE IF NOT EXISTS market_events_analysis (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            event_type VARCHAR(64) NOT NULL,
            title VARCHAR(512) NOT NULL,
            title_fa VARCHAR(512),
            description TEXT,
            description_fa TEXT,
            impact VARCHAR(16) NOT NULL DEFAULT 'neutral',
            magnitude FLOAT,
            data_json TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_market_event_type ON market_events_analysis (event_type)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_market_event_created ON market_events_analysis (created_at)")

    # correlation_cache
    op.execute("""
        CREATE TABLE IF NOT EXISTS correlation_cache (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            pair_a VARCHAR(32) NOT NULL,
            pair_b VARCHAR(32) NOT NULL,
            correlation FLOAT NOT NULL,
            window_days FLOAT NOT NULL DEFAULT 30,
            computed_date DATE NOT NULL,
            computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_corr_pair_date UNIQUE (pair_a, pair_b, computed_date)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_corr_date ON correlation_cache (computed_date)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS correlation_cache")
    op.execute("DROP TABLE IF EXISTS market_events_analysis")
    op.execute("DROP TABLE IF EXISTS cot_data")
    op.execute("DROP TABLE IF EXISTS etf_holdings")
    op.execute("DROP TABLE IF EXISTS macro_indicators")
    op.execute("DROP TABLE IF EXISTS asset_prices_daily")
