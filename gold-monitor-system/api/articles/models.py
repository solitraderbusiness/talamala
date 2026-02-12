"""ORM model for the gold articles module.

Tables
------
- ``gold_articles`` — curated expert gold analysis articles with Persian summaries
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
from sqlalchemy.dialects.postgresql import JSON, UUID

from api.models import Base


class GoldArticle(Base):
    """Curated gold market analysis article with LLM-generated Persian summary."""

    __tablename__ = "gold_articles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title_original = Column(String(1024), nullable=False)
    title_fa = Column(String(1024), nullable=True)
    source_name = Column(String(256), nullable=False)
    source_url = Column(String(2048), nullable=False)
    source_logo = Column(String(512), nullable=True)
    author = Column(String(256), nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    fetched_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    summary_fa = Column(Text, nullable=True)
    key_takeaways_fa = Column(JSON, nullable=True)      # list of strings
    gold_outlook = Column(String(16), nullable=True)     # bullish/bearish/neutral/mixed
    time_horizon = Column(String(16), nullable=True)     # short_term/medium_term/long_term
    topics = Column(JSON, nullable=True)                 # list of topic slugs
    affected_assets = Column(JSON, nullable=True)        # list of asset slugs
    importance_score = Column(Float, nullable=True)      # 0-100
    is_published = Column(Boolean, nullable=False, default=False)
    is_featured = Column(Boolean, nullable=False, default=False)
    original_language = Column(String(8), nullable=True, default="en")
    word_count_original = Column(Integer, nullable=True)
    dedupe_hash = Column(String(64), nullable=False, unique=True)
    partial_content = Column(Boolean, nullable=False, default=False)
    raw_importance_score = Column(Float, nullable=True)  # before source boost
    source_boost = Column(Float, nullable=True, default=0)
    llm_processed = Column(Boolean, nullable=False, default=False)
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
        Index("ix_gold_articles_published_at", "published_at"),
        Index("ix_gold_articles_importance", "importance_score"),
        Index("ix_gold_articles_is_published", "is_published"),
        Index("ix_gold_articles_source_name", "source_name"),
        Index("ix_gold_articles_created_at", "created_at"),
    )
