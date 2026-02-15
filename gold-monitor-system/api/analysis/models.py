"""ORM models for the fundamental analysis module.

Tables
------
- ``asset_prices_daily``   — daily OHLC for gold, DXY, S&P, yields, VIX, BTC, silver
- ``macro_indicators``     — FRED macro series (fed funds, CPI, real rates, etc.)
- ``etf_holdings``         — daily GLD/IAU total holdings in tonnes
- ``cot_data``             — weekly CFTC Commitment of Traders for gold futures
- ``market_events_analysis`` — auto-generated event feed from data changes
- ``correlation_cache``    — pre-computed 30-day rolling Pearson correlations
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from api.models import Base


class AssetPriceDaily(Base):
    """Daily closing prices for tracked assets."""

    __tablename__ = "asset_prices_daily"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol = Column(String(32), nullable=False)          # GC=F, DX-Y.NYB, ^GSPC, ^TNX, ^VIX, BTC-USD, SI=F
    trade_date = Column(Date, nullable=False)
    open = Column(Float, nullable=True)
    high = Column(Float, nullable=True)
    low = Column(Float, nullable=True)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=True)
    source = Column(String(32), nullable=False, default="yahoo")
    fetched_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("symbol", "trade_date", name="uq_asset_price_symbol_date"),
        Index("ix_asset_price_symbol", "symbol"),
        Index("ix_asset_price_date", "trade_date"),
    )


class MacroIndicator(Base):
    """FRED macro indicators — time series snapshots."""

    __tablename__ = "macro_indicators"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    series_id = Column(String(32), nullable=False)       # FEDFUNDS, CPIAUCSL, DFII10, DGS10, T10YIE
    observation_date = Column(Date, nullable=False)
    value = Column(Float, nullable=False)
    source = Column(String(32), nullable=False, default="fred")
    fetched_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("series_id", "observation_date", name="uq_macro_series_date"),
        Index("ix_macro_series", "series_id"),
        Index("ix_macro_date", "observation_date"),
    )


class EtfHolding(Base):
    """Daily ETF gold holdings (tonnes)."""

    __tablename__ = "etf_holdings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fund = Column(String(16), nullable=False)            # GLD, IAU
    holding_date = Column(Date, nullable=False)
    total_tonnes = Column(Float, nullable=False)
    change_tonnes = Column(Float, nullable=True)         # day-over-day change
    total_oz = Column(Float, nullable=True)
    total_value_usd = Column(Float, nullable=True)
    source = Column(String(64), nullable=False)
    source_url = Column(String(512), nullable=True)
    fetched_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("fund", "holding_date", name="uq_etf_fund_date"),
        Index("ix_etf_fund", "fund"),
        Index("ix_etf_date", "holding_date"),
    )


class CotData(Base):
    """Weekly CFTC Commitment of Traders data for gold futures."""

    __tablename__ = "cot_data"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_date = Column(Date, nullable=False)
    asset = Column(String(32), nullable=False, default="gold")
    commercial_long = Column(Float, nullable=True)
    commercial_short = Column(Float, nullable=True)
    non_commercial_long = Column(Float, nullable=True)
    non_commercial_short = Column(Float, nullable=True)
    non_commercial_net = Column(Float, nullable=True)    # longs - shorts
    open_interest = Column(Float, nullable=True)
    change_non_commercial_net = Column(Float, nullable=True)  # week-over-week
    source = Column(String(64), nullable=False, default="cftc")
    source_url = Column(String(512), nullable=True)
    fetched_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("asset", "report_date", name="uq_cot_asset_date"),
        Index("ix_cot_date", "report_date"),
    )


class MarketEventAnalysis(Base):
    """Auto-generated event feed from significant data changes."""

    __tablename__ = "market_events_analysis"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type = Column(String(64), nullable=False)      # etf_flow, cot_change, price_move, macro_release, correlation_shift
    title = Column(String(512), nullable=False)
    title_fa = Column(String(512), nullable=True)
    description = Column(Text, nullable=True)
    description_fa = Column(Text, nullable=True)
    impact = Column(String(16), nullable=False, default="neutral")  # bullish, bearish, neutral
    magnitude = Column(Float, nullable=True)             # 0-100 importance
    data_json = Column(Text, nullable=True)              # JSON payload with event-specific data
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_market_event_type", "event_type"),
        Index("ix_market_event_created", "created_at"),
    )


class CorrelationCache(Base):
    """Pre-computed 30-day rolling Pearson correlations between asset pairs."""

    __tablename__ = "correlation_cache"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pair_a = Column(String(32), nullable=False)          # e.g., GC=F
    pair_b = Column(String(32), nullable=False)          # e.g., DX-Y.NYB
    correlation = Column(Float, nullable=False)           # -1 to +1
    window_days = Column(Float, nullable=False, default=30)
    computed_date = Column(Date, nullable=False)
    computed_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("pair_a", "pair_b", "computed_date", name="uq_corr_pair_date"),
        Index("ix_corr_date", "computed_date"),
    )


class BacktestRun(Base):
    """Stores backtest run results and metadata."""

    __tablename__ = "backtest_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_type = Column(String(32), nullable=False)          # unified, regime, correlation, etc.
    started_at = Column(DateTime(timezone=True), nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(16), nullable=False, default="running")  # running, completed, failed
    date_range_start = Column(Date, nullable=True)
    date_range_end = Column(Date, nullable=True)
    total_benchmarks = Column(Integer, nullable=True)
    passed_benchmarks = Column(Integer, nullable=True)
    failed_benchmarks = Column(Integer, nullable=True)
    benchmark_results = Column(JSONB, nullable=True)
    summary = Column(JSONB, nullable=True)
    parameters = Column(JSONB, nullable=True)
    error_message = Column(Text, nullable=True)
    triggered_by = Column(String(64), nullable=True)       # admin email or "system"
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_backtest_runs_type", "run_type"),
        Index("ix_backtest_runs_created", "created_at"),
    )


class RegimeScore(Base):
    """Daily macro regime probabilities computed by the regime engine."""

    __tablename__ = "regime_scores"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ts = Column(Date, unique=True, nullable=False)
    liquidity_stress_index = Column(Float, nullable=True)
    usd_pressure_index = Column(Float, nullable=True)
    real_yield_pressure_index = Column(Float, nullable=True)
    # Raw softmax probabilities
    p_expansion = Column(Float, nullable=True)
    p_tightening = Column(Float, nullable=True)
    p_stress = Column(Float, nullable=True)
    p_recovery = Column(Float, nullable=True)
    # EWMA smoothed probabilities
    smoothed_p_expansion = Column(Float, nullable=True)
    smoothed_p_tightening = Column(Float, nullable=True)
    smoothed_p_stress = Column(Float, nullable=True)
    smoothed_p_recovery = Column(Float, nullable=True)
    chosen_regime = Column(String(16), nullable=True)
    chosen_regime_raw = Column(String(16), nullable=True)
    chosen_note_fa = Column(String(256), nullable=True)
    score_semantics = Column(String(64), nullable=True)
    lookahead_safe = Column("lookahead_safe", Integer, nullable=True, default=1)
    real_yield_source = Column(String(32), nullable=True)
    credit_proxy_source = Column(String(32), nullable=True)
    days_skipped = Column(Integer, default=0)
    metadata_ = Column("metadata", JSONB, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_regime_scores_ts", ts.desc()),
    )


class RegimeAuditLog(Base):
    """Audit log for regime engine computations — full provenance per day."""

    __tablename__ = "regime_audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    computed_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    ts = Column(Date, nullable=False)
    inputs_json = Column(JSONB, nullable=True)
    indices_json = Column(JSONB, nullable=True)
    scores_json = Column(JSONB, nullable=True)
    raw_probs = Column(JSONB, nullable=True)
    smoothed_probs = Column(JSONB, nullable=True)
    chosen_regime = Column(String(16), nullable=True)
    chosen_regime_raw = Column(String(16), nullable=True)
    chosen_note_fa = Column(String(256), nullable=True)
    sources = Column(JSONB, nullable=True)
    staleness = Column(JSONB, nullable=True)
    extra = Column(JSONB, nullable=True)

    __table_args__ = (
        Index("ix_regime_audit_ts", ts.desc()),
        Index("ix_regime_audit_computed", computed_at.desc()),
    )
