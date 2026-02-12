"""ORM models for the data collection & outcome tracking system.

Tables
------
- ``alert_market_snapshots``  — full market context at alert creation time
- ``alert_outcomes``          — price outcome tracking at 6 intervals
- ``sentiment_timeline``      — 5-min sentiment + price recording
- ``price_history``           — multi-timeframe OHLCV candles
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
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy import ForeignKey

from api.models import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ══════════════════════════════════════════════════════════════════════════
#  1. Alert Market Snapshots
# ══════════════════════════════════════════════════════════════════════════

class AlertMarketSnapshot(Base):
    """Full market context captured at alert creation time."""

    __tablename__ = "alert_market_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    alert_id = Column(
        UUID(as_uuid=True),
        ForeignKey("alerts.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    # ── Prices ────────────────────────────────────────────────────────
    xauusd = Column(Float, nullable=True)
    xagusd = Column(Float, nullable=True)
    dxy = Column(Float, nullable=True)
    usdirr = Column(Float, nullable=True)
    wti = Column(Float, nullable=True)
    btcusd = Column(Float, nullable=True)
    spx = Column(Float, nullable=True)
    us10y = Column(Float, nullable=True)
    vix = Column(Float, nullable=True)
    coin = Column(Float, nullable=True)
    gold_18k = Column(Float, nullable=True)

    # ── Technicals ────────────────────────────────────────────────────
    gold_rsi_14 = Column(Float, nullable=True)
    gold_ma50 = Column(Float, nullable=True)
    gold_ma200 = Column(Float, nullable=True)
    gold_atr_14 = Column(Float, nullable=True)
    gold_price_vs_ma50_pct = Column(Float, nullable=True)
    gold_price_vs_ma200_pct = Column(Float, nullable=True)
    gold_5d_return_pct = Column(Float, nullable=True)
    gold_10d_return_pct = Column(Float, nullable=True)
    dxy_5d_change = Column(Float, nullable=True)

    # ── Sentiment ─────────────────────────────────────────────────────
    sentiment_composite = Column(Integer, nullable=True)
    sentiment_direction = Column(String(20), nullable=True)
    sentiment_sub_scores = Column(JSONB, nullable=True)

    # ── Alert context ─────────────────────────────────────────────────
    alerts_1h_count = Column(Integer, nullable=True)
    alerts_4h_count = Column(Integer, nullable=True)
    alerts_24h_count = Column(Integer, nullable=True)
    alerts_bullish_24h = Column(Integer, nullable=True)
    alerts_bearish_24h = Column(Integer, nullable=True)
    dominant_sentiment_24h = Column(String(20), nullable=True)

    # ── Previous high alert ───────────────────────────────────────────
    prev_high_alert_id = Column(UUID(as_uuid=True), nullable=True)
    prev_high_alert_hours_ago = Column(Float, nullable=True)
    prev_high_alert_category = Column(String(50), nullable=True)
    prev_high_alert_direction = Column(String(20), nullable=True)

    # ── Price momentum before alert ───────────────────────────────────
    price_change_1h_before = Column(Float, nullable=True)
    price_change_4h_before = Column(Float, nullable=True)
    price_change_24h_before = Column(Float, nullable=True)

    # ── Quality ───────────────────────────────────────────────────────
    snapshot_complete = Column(Boolean, nullable=False, default=False)
    missing_fields = Column(JSONB, nullable=True)
    fetch_duration_ms = Column(Integer, nullable=True)

    created_at = Column(
        DateTime(timezone=True), nullable=False, default=_utcnow,
    )

    __table_args__ = (
        Index("ix_snapshot_alert_id", "alert_id", unique=True),
        Index("ix_snapshot_created_at", "created_at"),
    )


# ══════════════════════════════════════════════════════════════════════════
#  2. Alert Outcomes
# ══════════════════════════════════════════════════════════════════════════

class AlertOutcome(Base):
    """Price outcome tracking at 6 intervals (30min → 7d)."""

    __tablename__ = "alert_outcomes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    alert_id = Column(
        UUID(as_uuid=True),
        ForeignKey("alerts.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    # ── Alert context ─────────────────────────────────────────────────
    alert_direction = Column(String(20), nullable=True)
    alert_severity = Column(String(10), nullable=True)
    price_at_alert = Column(Float, nullable=True)
    alert_created_at = Column(DateTime(timezone=True), nullable=True)

    # ── 30 min ────────────────────────────────────────────────────────
    price_30min = Column(Float, nullable=True)
    change_pct_30min = Column(Float, nullable=True)
    direction_correct_30min = Column(Boolean, nullable=True)
    checked_at_30min = Column(DateTime(timezone=True), nullable=True)

    # ── 1 hour ────────────────────────────────────────────────────────
    price_1h = Column(Float, nullable=True)
    change_pct_1h = Column(Float, nullable=True)
    direction_correct_1h = Column(Boolean, nullable=True)
    checked_at_1h = Column(DateTime(timezone=True), nullable=True)

    # ── 4 hours ───────────────────────────────────────────────────────
    price_4h = Column(Float, nullable=True)
    change_pct_4h = Column(Float, nullable=True)
    direction_correct_4h = Column(Boolean, nullable=True)
    checked_at_4h = Column(DateTime(timezone=True), nullable=True)

    # ── 24 hours ──────────────────────────────────────────────────────
    price_24h = Column(Float, nullable=True)
    change_pct_24h = Column(Float, nullable=True)
    direction_correct_24h = Column(Boolean, nullable=True)
    checked_at_24h = Column(DateTime(timezone=True), nullable=True)

    # ── 48 hours ──────────────────────────────────────────────────────
    price_48h = Column(Float, nullable=True)
    change_pct_48h = Column(Float, nullable=True)
    direction_correct_48h = Column(Boolean, nullable=True)
    checked_at_48h = Column(DateTime(timezone=True), nullable=True)

    # ── 7 days ────────────────────────────────────────────────────────
    price_7d = Column(Float, nullable=True)
    change_pct_7d = Column(Float, nullable=True)
    direction_correct_7d = Column(Boolean, nullable=True)
    checked_at_7d = Column(DateTime(timezone=True), nullable=True)

    # ── Magnitude ─────────────────────────────────────────────────────
    max_favorable_move_pct = Column(Float, nullable=True)
    max_adverse_move_pct = Column(Float, nullable=True)
    time_to_max_favorable_hours = Column(Float, nullable=True)

    # ── Reversion ─────────────────────────────────────────────────────
    reverted_within_4h = Column(Boolean, nullable=True)
    reverted_within_24h = Column(Boolean, nullable=True)

    # ── Status ────────────────────────────────────────────────────────
    status = Column(
        String(20), nullable=False, default="pending_30min",
    )
    errors = Column(JSONB, nullable=True)

    created_at = Column(
        DateTime(timezone=True), nullable=False, default=_utcnow,
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False, default=_utcnow,
        onupdate=_utcnow,
    )

    __table_args__ = (
        Index("ix_outcome_alert_id_uniq", "alert_id", unique=True),
        Index("ix_outcome_status", "status"),
        Index("ix_outcome_created_at", "created_at"),
    )


# ══════════════════════════════════════════════════════════════════════════
#  3. Sentiment Timeline
# ══════════════════════════════════════════════════════════════════════════

class SentimentTimeline(Base):
    """5-minute sentiment + price recordings for trend analysis."""

    __tablename__ = "sentiment_timeline"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recorded_at = Column(
        DateTime(timezone=True), nullable=False, unique=True,
    )
    composite_score = Column(Integer, nullable=True)
    direction = Column(String(20), nullable=True)
    sub_scores = Column(JSONB, nullable=True)

    gold_price = Column(Float, nullable=True)
    gold_change_1h_pct = Column(Float, nullable=True)

    alerts_active_1h = Column(Integer, nullable=True)
    alerts_active_4h = Column(Integer, nullable=True)
    alerts_active_24h = Column(Integer, nullable=True)

    __table_args__ = (
        Index("ix_sentiment_tl_recorded_at", "recorded_at"),
    )


# ══════════════════════════════════════════════════════════════════════════
#  4. Price History
# ══════════════════════════════════════════════════════════════════════════

class PriceHistory(Base):
    """Multi-timeframe OHLCV candles from various sources."""

    __tablename__ = "price_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol = Column(String(32), nullable=False)
    timeframe = Column(String(10), nullable=False)  # 5min, 1h, 1d
    datetime_utc = Column(DateTime(timezone=True), nullable=False)
    open = Column(Float, nullable=True)
    high = Column(Float, nullable=True)
    low = Column(Float, nullable=True)
    close = Column(Float, nullable=True)
    volume = Column(Float, nullable=True)
    source = Column(String(32), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "symbol", "timeframe", "datetime_utc",
            name="uq_price_history_symbol_tf_dt",
        ),
        Index("ix_price_history_symbol_tf", "symbol", "timeframe"),
        Index(
            "ix_price_history_symbol_tf_dt_desc",
            "symbol", "timeframe", datetime_utc.desc(),
        ),
    )
