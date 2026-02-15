"""ORM models for the Data Copilot module.

Tables
------
- ``metric_registry``   — catalog of all metrics the chatbot can query
- ``calc_runs``         — audit trail for computed metrics (sentiment, risk_radar)
- ``data_freshness``    — staleness tracking for all registered metrics
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from api.models import Base

# ── Import source table ORM models for safe resolution ────────────────
from api.analysis.models import (
    AssetPriceDaily,
    CotData,
    CorrelationCache,
    EtfHolding,
    MacroIndicator,
)

# Compile-time allowlist: source_table string → ORM model.
# No raw SQL — all dynamic queries resolve through this map.
TABLE_MODEL_MAP: dict[str, type] = {
    "asset_prices_daily": AssetPriceDaily,
    "macro_indicators": MacroIndicator,
    "etf_holdings": EtfHolding,
    "cot_data": CotData,
    "correlation_cache": CorrelationCache,
}


class MetricRegistry(Base):
    """Catalog of all metrics the chatbot can query."""

    __tablename__ = "metric_registry"

    key = Column(String(64), primary_key=True)
    label_fa = Column(Text, nullable=False)
    label_en = Column(String(128))
    unit = Column(String(32), nullable=False)
    frequency = Column(String(20), nullable=False)
    source_name = Column(String(100), nullable=False)
    source_id = Column(String(100))
    direction_for_gold = Column(String(30))
    description_fa = Column(Text)
    precision = Column(Integer, default=2)
    # Source mapping for dynamic querying
    source_table = Column(String(64))
    source_column = Column(String(64))
    source_filter = Column(JSONB)
    ts_column = Column(String(64))
    staleness_hours = Column(Float, default=96)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class CalcRun(Base):
    """Audit trail for computed metrics (sentiment, risk_radar)."""

    __tablename__ = "calc_runs"

    run_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_type = Column(String(50), nullable=False, index=True)
    asset = Column(String(20), default="XAUUSD")
    ts = Column(DateTime(timezone=True), nullable=False)
    inputs = Column(JSONB)
    intermediates = Column(JSONB)
    outputs = Column(JSONB)
    warnings = Column(JSONB)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_calc_runs_type_ts", "run_type", ts.desc()),
    )


class DataFreshness(Base):
    """Staleness tracking for all registered metrics."""

    __tablename__ = "data_freshness"

    key = Column(String(64), primary_key=True)
    expected_frequency = Column(String(20))
    max_age_seconds = Column(Integer)
    last_seen_ts = Column(DateTime(timezone=True))
    is_stale = Column(Boolean, default=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
