"""SQLAlchemy ORM models for the Signal Aggregator module.

All tables use UUID primary keys and UTC timestamps, matching the
existing Talamala conventions.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.database import Base


# ── Helpers ─────────────────────────────────────────────────────────────

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_uuid() -> uuid.UUID:
    return uuid.uuid4()


# ── Enums ───────────────────────────────────────────────────────────────

class SignalSourceType(str, enum.Enum):
    telegram = "telegram"
    tradingview = "tradingview"
    website = "website"
    forum = "forum"


class SignalDirection(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"


class SignalTimeframe(str, enum.Enum):
    m5 = "5min"
    m15 = "15min"
    m30 = "30min"
    h1 = "1h"
    h4 = "4h"
    daily = "daily"
    weekly = "weekly"


class TimeframeConfidence(str, enum.Enum):
    explicit = "explicit"
    inferred = "inferred"


class AnalysisType(str, enum.Enum):
    technical = "technical"
    fundamental = "fundamental"
    sentiment = "sentiment"
    mixed = "mixed"


class SignalStatus(str, enum.Enum):
    active = "active"
    tp1_hit = "tp1_hit"
    tp2_hit = "tp2_hit"
    tp3_hit = "tp3_hit"
    sl_hit = "sl_hit"
    expired = "expired"
    cancelled = "cancelled"


class ConsensusView(str, enum.Enum):
    scalp = "scalp"
    intraday = "intraday"
    swing = "swing"
    position = "position"


class ConsensusDirection(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"
    NEUTRAL = "NEUTRAL"


# ── Signal Sources ──────────────────────────────────────────────────────

class SignalSource(Base):
    __tablename__ = "signal_sources"
    __table_args__ = (
        Index("ix_signal_sources_type", "type"),
        Index("ix_signal_sources_active", "active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_new_uuid,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    telegram_channel_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    telegram_channel_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default="now()",
    )

    # Confidence tracking
    total_signals: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    correct_signals: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    wrong_signals: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    expired_signals: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    accuracy_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_profit_pips: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_loss_pips: Mapped[float | None] = mapped_column(Float, nullable=True)
    profit_factor: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_weight: Mapped[float] = mapped_column(Float, default=0.5, server_default="0.5")
    last_signal_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # Relationships
    raw_posts: Mapped[list[RawPost]] = relationship(
        "RawPost", back_populates="source", lazy="noload",
    )
    parsed_signals: Mapped[list[ParsedSignal]] = relationship(
        "ParsedSignal", back_populates="source", lazy="noload",
    )

    def __repr__(self) -> str:
        return f"<SignalSource {self.name!r} ({self.type})>"


# ── Raw Posts ───────────────────────────────────────────────────────────

class RawPost(Base):
    __tablename__ = "raw_posts"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_raw_posts_source_external"),
        Index("ix_raw_posts_source_id", "source_id"),
        Index("ix_raw_posts_parsed", "parsed"),
        Index("ix_raw_posts_captured_at", "captured_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_new_uuid,
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("signal_sources.id", ondelete="CASCADE"),
        nullable=False,
    )
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    media_urls: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    posted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default="now()",
    )
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    parsed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    parse_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    # Relationships
    source: Mapped[SignalSource] = relationship("SignalSource", back_populates="raw_posts")
    parsed_signal: Mapped[ParsedSignal | None] = relationship(
        "ParsedSignal", back_populates="raw_post", uselist=False,
    )

    def __repr__(self) -> str:
        return f"<RawPost {self.external_id} src={self.source_id}>"


# ── Parsed Signals ──────────────────────────────────────────────────────

class ParsedSignal(Base):
    __tablename__ = "parsed_signals"
    __table_args__ = (
        Index("ix_parsed_signals_source_id", "source_id"),
        Index("ix_parsed_signals_status", "status"),
        Index("ix_parsed_signals_asset_timeframe", "asset", "timeframe"),
        Index("ix_parsed_signals_valid_until", "valid_until"),
        Index("ix_parsed_signals_parsed_at", "parsed_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_new_uuid,
    )
    raw_post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("raw_posts.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("signal_sources.id", ondelete="CASCADE"),
        nullable=False,
    )
    asset: Mapped[str] = mapped_column(String(20), default="XAUUSD", server_default="XAUUSD")
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    entry_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit_1: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit_2: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit_3: Mapped[float | None] = mapped_column(Float, nullable=True)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)
    timeframe_confidence: Mapped[str] = mapped_column(
        String(10), default="inferred", server_default="inferred",
    )
    analysis_type: Mapped[str] = mapped_column(
        String(20), default="mixed", server_default="mixed",
    )
    confidence_raw: Mapped[int] = mapped_column(Integer, default=5, server_default="5")
    key_reasons: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    parsed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default="now()",
    )
    valid_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # Outcome tracking
    status: Mapped[str] = mapped_column(
        String(20), default="active", server_default="active",
    )
    outcome_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    outcome_pips: Mapped[float | None] = mapped_column(Float, nullable=True)
    outcome_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # Relationships
    raw_post: Mapped[RawPost] = relationship("RawPost", back_populates="parsed_signal")
    source: Mapped[SignalSource] = relationship("SignalSource", back_populates="parsed_signals")

    def __repr__(self) -> str:
        return f"<ParsedSignal {self.direction} {self.asset} {self.timeframe}>"


# ── Consensus Snapshots ─────────────────────────────────────────────────

class ConsensusSnapshot(Base):
    __tablename__ = "consensus_snapshots"
    __table_args__ = (
        Index("ix_consensus_generated_at", "generated_at"),
        Index("ix_consensus_view", "consensus_view"),
        Index("ix_consensus_asset_view", "asset", "consensus_view"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_new_uuid,
    )
    asset: Mapped[str] = mapped_column(String(20), default="XAUUSD", server_default="XAUUSD")
    consensus_view: Mapped[str] = mapped_column(String(20), nullable=False)
    timeframes_included: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default="now()",
    )
    signals_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    buy_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    sell_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    weighted_buy_score: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    weighted_sell_score: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    consensus_direction: Mapped[str] = mapped_column(
        String(10), default="NEUTRAL", server_default="NEUTRAL",
    )
    consensus_strength: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    avg_entry_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    median_entry_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_take_profit: Mapped[float | None] = mapped_column(Float, nullable=True)
    dominant_timeframe: Mapped[str | None] = mapped_column(String(10), nullable=True)
    dominant_reasons: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    timeframe_alignment: Mapped[Any | None] = mapped_column(JSONB, nullable=True)

    def __repr__(self) -> str:
        return f"<ConsensusSnapshot {self.consensus_view} {self.consensus_direction}>"


# ── Price Ticks ─────────────────────────────────────────────────────────

class SignalPriceTick(Base):
    __tablename__ = "signal_price_ticks"
    __table_args__ = (
        Index("ix_signal_price_ticks_checked_at", "checked_at"),
        Index("ix_signal_price_ticks_asset", "asset"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_new_uuid,
    )
    asset: Mapped[str] = mapped_column(String(20), default="XAUUSD", server_default="XAUUSD")
    price: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default="now()",
    )

    def __repr__(self) -> str:
        return f"<SignalPriceTick {self.asset} {self.price}>"


# ── Daily Performance ───────────────────────────────────────────────────

class DailyPerformance(Base):
    __tablename__ = "signal_daily_performance"
    __table_args__ = (
        UniqueConstraint("date", "asset", name="uq_daily_perf_date_asset"),
        Index("ix_daily_perf_date", "date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_new_uuid,
    )
    date: Mapped[datetime] = mapped_column(Date, nullable=False)
    asset: Mapped[str] = mapped_column(String(20), default="XAUUSD", server_default="XAUUSD")
    total_signals: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    closed_signals: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    winning_signals: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    losing_signals: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    expired_signals: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    win_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_profit_pips: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    total_loss_pips: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    net_pips: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    cumulative_pips: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    best_signal_pips: Mapped[float | None] = mapped_column(Float, nullable=True)
    worst_signal_pips: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_signal_pips: Mapped[float | None] = mapped_column(Float, nullable=True)
    consensus_accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Breakdown by timeframe view
    scalp_signals: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    scalp_win_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    intraday_signals: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    intraday_win_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    swing_signals: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    swing_win_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    position_signals: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    position_win_rate: Mapped[float | None] = mapped_column(Float, nullable=True)

    def __repr__(self) -> str:
        return f"<DailyPerformance {self.date} net={self.net_pips}>"


# ── Monthly Performance ─────────────────────────────────────────────────

class MonthlyPerformance(Base):
    __tablename__ = "signal_monthly_performance"
    __table_args__ = (
        UniqueConstraint("year", "month", "asset", name="uq_monthly_perf_ym_asset"),
        Index("ix_monthly_perf_year_month", "year", "month"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_new_uuid,
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    asset: Mapped[str] = mapped_column(String(20), default="XAUUSD", server_default="XAUUSD")
    total_signals: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    closed_signals: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    win_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    net_pips: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    cumulative_pips: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    best_day_pips: Mapped[float | None] = mapped_column(Float, nullable=True)
    worst_day_pips: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_daily_pips: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_drawdown_pips: Mapped[float | None] = mapped_column(Float, nullable=True)
    profit_factor: Mapped[float | None] = mapped_column(Float, nullable=True)
    sharpe_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_consensus_calls: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    consensus_accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    active_sources: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    def __repr__(self) -> str:
        return f"<MonthlyPerformance {self.year}-{self.month:02d} net={self.net_pips}>"
