"""
SQLAlchemy ORM models for the Gold Monitor system.

All tables use UUID primary keys and UTC timestamps.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
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

class SourceType(str, enum.Enum):
    rss = "rss"
    html = "html"
    json_api = "json_api"
    websocket = "websocket"
    file = "file"
    custom = "custom"


class Severity(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"


class TimeHorizon(str, enum.Enum):
    immediate = "immediate"
    short = "short"
    medium = "medium"
    long = "long"


# ── Sources ─────────────────────────────────────────────────────────────

class Source(Base):
    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_new_uuid,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(
        String(20), nullable=False,
    )
    base_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    endpoints: Mapped[Any] = mapped_column(JSONB, default=list, server_default="[]")
    method: Mapped[str] = mapped_column(String(10), default="GET", server_default="GET")
    headers: Mapped[Any] = mapped_column(JSONB, default=dict, server_default="{}")
    auth_config: Mapped[Any] = mapped_column(JSONB, default=dict, server_default="{}")
    parser: Mapped[str] = mapped_column(String(255), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    poll_interval_seconds: Mapped[int] = mapped_column(
        Integer, default=60, server_default="60",
    )
    categories: Mapped[Any] = mapped_column(JSONB, default=list, server_default="[]")
    rule_bindings: Mapped[Any] = mapped_column(JSONB, default=list, server_default="[]")
    reliability_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Fetch tracking
    last_fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    last_success_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default="now()",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, server_default="now()",
    )

    # Relationships (lazy="noload" — load explicitly when needed)
    raw_items: Mapped[list[RawItem]] = relationship(
        "RawItem", back_populates="source", lazy="noload",
    )
    fetch_logs: Mapped[list[FetchLog]] = relationship(
        "FetchLog", back_populates="source", lazy="noload",
    )

    def __repr__(self) -> str:
        return f"<Source {self.name!r} ({self.type})>"


# ── Raw Items ───────────────────────────────────────────────────────────

class RawItem(Base):
    __tablename__ = "raw_items"
    __table_args__ = (
        Index("ix_raw_items_content_hash", "content_hash"),
        Index("ix_raw_items_source_id", "source_id"),
        Index("ix_raw_items_fetched_at", "fetched_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_new_uuid,
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False,
    )
    content_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_: Mapped[Any] = mapped_column(
        "metadata_", JSONB, default=dict, server_default="{}",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default="now()",
    )

    # Relationships
    source: Mapped[Source] = relationship("Source", back_populates="raw_items")
    alert: Mapped[Alert | None] = relationship(
        "Alert", back_populates="raw_item", uselist=False,
    )

    def __repr__(self) -> str:
        return f"<RawItem {self.title[:40]!r}>"


# ── Alerts ──────────────────────────────────────────────────────────────

class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_alerts_dedupe_key"),
        Index("ix_alerts_dedupe_key", "dedupe_key"),
        Index("ix_alerts_severity", "severity"),
        Index("ix_alerts_timestamp_utc", "timestamp_utc"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_new_uuid,
    )
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    timestamp_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False,
    )
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    matched_rule_ids: Mapped[Any] = mapped_column(
        JSONB, default=list, server_default="[]",
    )
    summary_fa: Mapped[str] = mapped_column(Text, nullable=False, default="")
    why_important_fa: Mapped[str] = mapped_column(Text, nullable=False, default="")
    expected_impact: Mapped[Any] = mapped_column(
        JSONB, default=dict, server_default="{}",
    )
    severity: Mapped[str] = mapped_column(
        String(10), nullable=False, default="medium",
    )
    time_horizon: Mapped[str] = mapped_column(
        String(20), nullable=False, default="short",
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    follow_up_questions: Mapped[Any] = mapped_column(
        JSONB, default=list, server_default="[]",
    )
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False)
    raw_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("raw_items.id", ondelete="SET NULL"),
        nullable=True,
    )
    match_evidence: Mapped[Any] = mapped_column(
        JSONB, default=dict, server_default="{}",
    )

    # ── Price snapshot at alert creation time ─────────────────────────
    price_xauusd_at_alert: Mapped[float | None] = mapped_column(
        Float, nullable=True, default=None,
    )
    price_usdirr_at_alert: Mapped[float | None] = mapped_column(
        Float, nullable=True, default=None,
    )
    price_coin_at_alert: Mapped[float | None] = mapped_column(
        Float, nullable=True, default=None,
    )
    price_18k_at_alert: Mapped[float | None] = mapped_column(
        Float, nullable=True, default=None,
    )

    # ── Classification metadata ───────────────────────────────────────
    news_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True, default=None,
    )
    event_category: Mapped[str | None] = mapped_column(
        String(50), nullable=True, default=None,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default="now()",
    )

    # Relationships
    raw_item: Mapped[RawItem | None] = relationship(
        "RawItem", back_populates="alert",
    )
    price_outcomes: Mapped[list[AlertPriceOutcome]] = relationship(
        "AlertPriceOutcome", back_populates="alert", lazy="noload",
    )

    def __repr__(self) -> str:
        return f"<Alert {self.severity} {self.title[:40]!r}>"


# ── Alert Price Outcomes ───────────────────────────────────────────────

class AlertPriceOutcome(Base):
    """Tracks what happened to prices 1h, 4h, and 24h after an alert.

    Populated by a background job that looks back at alerts and records
    the actual price changes, enabling accuracy scoring.
    """
    __tablename__ = "alert_price_outcomes"
    __table_args__ = (
        UniqueConstraint("alert_id", "check_interval", name="uq_outcome_alert_interval"),
        Index("ix_outcome_alert_id", "alert_id"),
        Index("ix_outcome_checked_at", "checked_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_new_uuid,
    )
    alert_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("alerts.id", ondelete="CASCADE"),
        nullable=False,
    )
    check_interval: Mapped[str] = mapped_column(
        String(10), nullable=False,  # '1h', '4h', '24h'
    )

    # Prices at the check time
    price_xauusd: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_usdirr: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_coin: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_18k: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Change percentages from alert time
    change_pct_xauusd: Mapped[float | None] = mapped_column(Float, nullable=True)
    change_pct_usdirr: Mapped[float | None] = mapped_column(Float, nullable=True)
    change_pct_coin: Mapped[float | None] = mapped_column(Float, nullable=True)
    change_pct_18k: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Was the alert's predicted direction correct? (null if neutral)
    direction_correct: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True,
    )

    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default="now()",
    )

    # Relationships
    alert: Mapped[Alert] = relationship("Alert", back_populates="price_outcomes")

    def __repr__(self) -> str:
        return f"<AlertPriceOutcome {self.check_interval} alert={self.alert_id}>"


# ── Fetch Logs ──────────────────────────────────────────────────────────

class FetchLog(Base):
    __tablename__ = "fetch_logs"
    __table_args__ = (
        Index("ix_fetch_logs_source_id", "source_id"),
        Index("ix_fetch_logs_started_at", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_new_uuid,
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="success",
    )
    items_fetched_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0",
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Relationships
    source: Mapped[Source] = relationship("Source", back_populates="fetch_logs")

    def __repr__(self) -> str:
        return f"<FetchLog {self.status} src={self.source_id}>"


# ── Settings (key-value store) ──────────────────────────────────────────

class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, server_default="now()",
    )

    def __repr__(self) -> str:
        return f"<Setting {self.key!r}>"


# ── Admin Users ─────────────────────────────────────────────────────────

class AdminUser(Base):
    __tablename__ = "admin_users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_admin_users_email"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_new_uuid,
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        String(50), default="admin", server_default="admin",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default="now()",
    )

    def __repr__(self) -> str:
        return f"<AdminUser {self.email!r}>"


# ── Rules Snapshot ──────────────────────────────────────────────────────

class SentimentScore(Base):
    """Persisted sentiment scores for historical tracking and charting."""
    __tablename__ = "sentiment_scores"
    __table_args__ = (
        Index("ix_sentiment_scores_timeframe_created", "timeframe", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_new_uuid,
    )
    timeframe: Mapped[str] = mapped_column(
        String(10), nullable=False,  # "1h", "4h", "24h"
    )
    score: Mapped[int] = mapped_column(
        Integer, nullable=False,  # 0-100
    )
    sentiment: Mapped[str] = mapped_column(
        String(20), nullable=False,  # very_bullish, bullish, neutral, bearish, very_bearish
    )
    sentiment_label: Mapped[str] = mapped_column(
        String(50), nullable=False,  # Persian label
    )
    alert_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default="now()",
    )

    def __repr__(self) -> str:
        return f"<SentimentScore {self.timeframe} score={self.score} {self.sentiment}>"


# ── Economic Events (Calendar) ─────────────────────────────────────────

class EconomicEvent(Base):
    """Cached economic calendar events from JBlanked / Finnhub APIs."""
    __tablename__ = "economic_events"
    __table_args__ = (
        Index("ix_econ_events_datetime", "datetime_utc"),
        Index("ix_econ_events_impact", "impact"),
        Index("ix_econ_events_currency", "currency"),
        UniqueConstraint("event_name", "datetime_utc", name="uq_econ_events_name_datetime"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_new_uuid,
    )
    event_name: Mapped[str] = mapped_column(String(512), nullable=False)
    event_name_fa: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    country: Mapped[str] = mapped_column(String(10), nullable=False, default="")
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="")
    category: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    datetime_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    impact: Mapped[str] = mapped_column(
        String(10), nullable=False, default="low",
    )
    actual: Mapped[str | None] = mapped_column(String(100), nullable=True)
    forecast: Mapped[str | None] = mapped_column(String(100), nullable=True)
    previous: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source: Mapped[str] = mapped_column(
        String(50), nullable=False, default="mql5",
    )
    affected_assets: Mapped[Any] = mapped_column(
        JSONB, default=list, server_default="[]",
    )
    gold_impact_note: Mapped[Any] = mapped_column(
        JSONB, nullable=True, default=None,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default="now()",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, server_default="now()",
    )

    def __repr__(self) -> str:
        return f"<EconomicEvent {self.event_name!r} {self.datetime_utc}>"


class RulesSnapshot(Base):
    __tablename__ = "rules_snapshot"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_new_uuid,
    )
    version: Mapped[str] = mapped_column(String(100), nullable=False)
    yaml_content: Mapped[str] = mapped_column(Text, nullable=False)
    loaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False,
    )

    def __repr__(self) -> str:
        return f"<RulesSnapshot v{self.version!r}>"
