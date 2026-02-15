"""ORM models for the gold videos module.

Tables
------
- ``curated_videos`` — curated YouTube videos with Persian summaries
- ``live_stream_channels`` — live stream channel references
- ``monitored_youtube_channels`` — channels scanned for new videos
- ``video_chat_logs`` — per-video chat Q&A logs
"""

from __future__ import annotations

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
from sqlalchemy.dialects.postgresql import JSON

from api.database import Base


class CuratedVideo(Base):
    """Curated YouTube video with LLM-generated Persian summary."""

    __tablename__ = "curated_videos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    youtube_id = Column(String(20), nullable=False, unique=True)
    title_original = Column(String(1024), nullable=True)
    title_fa = Column(String(1024), nullable=True)
    channel_name = Column(String(256), nullable=True)
    channel_id = Column(String(64), nullable=True)
    thumbnail_url = Column(String(512), nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    view_count = Column(Integer, nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    fetched_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    transcript = Column(Text, nullable=True)
    summary_fa = Column(Text, nullable=True)
    key_points_fa = Column(JSON, nullable=True)        # list of strings
    topics = Column(JSON, nullable=True)                # list of topic slugs
    category = Column(String(32), nullable=True)        # analysis/news/education/interview/documentary
    gold_outlook = Column(String(16), nullable=True)    # bullish/bearish/neutral/mixed
    relevance_score = Column(Float, nullable=True)      # 0-100
    is_published = Column(Boolean, nullable=False, default=False)
    is_featured = Column(Boolean, nullable=False, default=False)
    llm_processed = Column(Boolean, nullable=False, default=False)
    metadata_errors = Column(Integer, nullable=False, default=0)
    added_by = Column(String(16), nullable=True, default="auto")  # auto/admin
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_curated_videos_published_at", "published_at"),
        Index("ix_curated_videos_is_published", "is_published"),
        Index("ix_curated_videos_category", "category"),
        Index("ix_curated_videos_relevance", "relevance_score"),
        Index("ix_curated_videos_created_at", "created_at"),
    )


class LiveStreamChannel(Base):
    """Live stream channel reference for embedding."""

    __tablename__ = "live_stream_channels"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(256), nullable=False)
    name_fa = Column(String(256), nullable=True)
    youtube_channel_id = Column(String(64), nullable=False, unique=True)
    thumbnail_url = Column(String(512), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class MonitoredYoutubeChannel(Base):
    """YouTube channel monitored for auto-discovery of new videos."""

    __tablename__ = "monitored_youtube_channels"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(256), nullable=False)
    youtube_channel_id = Column(String(64), nullable=False, unique=True)
    rss_url = Column(String(512), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    auto_publish = Column(Boolean, nullable=False, default=False)
    always_relevant = Column(Boolean, nullable=False, default=False)
    min_duration_seconds = Column(Integer, nullable=True, default=120)
    max_age_days = Column(Integer, nullable=True, default=14)
    last_checked_at = Column(DateTime(timezone=True), nullable=True)
    last_video_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class VideoChatLog(Base):
    """Per-video chat Q&A log entry."""

    __tablename__ = "video_chat_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    video_id = Column(Integer, nullable=False)
    ip_address = Column(String(45), nullable=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=True)
    tokens_used = Column(Integer, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_video_chat_logs_video_id", "video_id"),
        Index("ix_video_chat_logs_created_at", "created_at"),
    )
