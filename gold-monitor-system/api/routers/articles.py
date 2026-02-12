"""Gold articles API — list, detail, and daily digest endpoints.

All endpoints return graceful empty responses when no data exists.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query
from sqlalchemy import and_, desc, func, select

from api.articles.config import (
    ASSET_LABELS_FA,
    OUTLOOK_LABELS_FA,
    TIME_HORIZON_LABELS_FA,
    TOPIC_LABELS_FA,
)
from api.articles.models import GoldArticle
from api.database import AsyncSessionLocal

router = APIRouter(tags=["articles"])
logger = logging.getLogger("gold_monitor.articles")


def _article_to_dict(article: GoldArticle) -> dict:
    """Convert a GoldArticle ORM instance to a response dict."""
    # Find source_name_fa from config
    from api.articles.config import ARTICLE_SOURCES
    source_name_fa = article.source_name
    for src in ARTICLE_SOURCES:
        if src["name"] == article.source_name:
            source_name_fa = src["name_fa"]
            break

    return {
        "id": article.id,
        "title_fa": article.title_fa,
        "title_original": article.title_original,
        "source_name": article.source_name,
        "source_name_fa": source_name_fa,
        "source_url": article.source_url,
        "source_logo": article.source_logo,
        "author": article.author,
        "published_at": article.published_at.isoformat() if article.published_at else None,
        "summary_fa": article.summary_fa,
        "key_takeaways_fa": article.key_takeaways_fa or [],
        "gold_outlook": article.gold_outlook,
        "gold_outlook_fa": OUTLOOK_LABELS_FA.get(article.gold_outlook or "", ""),
        "time_horizon": article.time_horizon,
        "time_horizon_fa": TIME_HORIZON_LABELS_FA.get(article.time_horizon or "", ""),
        "topics": article.topics or [],
        "topics_fa": [TOPIC_LABELS_FA.get(t, t) for t in (article.topics or [])],
        "affected_assets": article.affected_assets or [],
        "affected_assets_fa": [ASSET_LABELS_FA.get(a, a) for a in (article.affected_assets or [])],
        "importance_score": article.importance_score,
        "is_featured": article.is_featured,
        "is_published": article.is_published,
        "original_language": article.original_language,
        "created_at": article.created_at.isoformat() if article.created_at else None,
    }


# ══════════════════════════════════════════════════════════════════════════
#  1. GET /articles — paginated list with filters
# ══════════════════════════════════════════════════════════════════════════

@router.get("/articles")
async def list_articles(
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=50),
    topic: str | None = Query(None),
    outlook: str | None = Query(None),
    asset: str | None = Query(None),
    source: str | None = Query(None),
    featured: bool | None = Query(None),
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
):
    """Paginated list of published gold articles with filters."""
    async with AsyncSessionLocal() as session:
        # Base query — only published articles
        q = select(GoldArticle).where(GoldArticle.is_published.is_(True))

        # Apply filters
        if topic:
            # JSON contains filter for topics array
            q = q.where(GoldArticle.topics.op("@>")(f'["{topic}"]'))

        if outlook and outlook in ("bullish", "bearish", "neutral", "mixed"):
            q = q.where(GoldArticle.gold_outlook == outlook)

        if asset:
            q = q.where(GoldArticle.affected_assets.op("@>")(f'["{asset}"]'))

        if source:
            q = q.where(GoldArticle.source_name == source)

        if featured is True:
            q = q.where(GoldArticle.is_featured.is_(True))

        if from_date:
            try:
                from_dt = datetime.fromisoformat(from_date)
                q = q.where(GoldArticle.published_at >= from_dt)
            except ValueError:
                pass

        if to_date:
            try:
                to_dt = datetime.fromisoformat(to_date)
                q = q.where(GoldArticle.published_at <= to_dt)
            except ValueError:
                pass

        # Count total
        count_q = select(func.count()).select_from(q.subquery())
        total_result = await session.execute(count_q)
        total = total_result.scalar() or 0

        # Paginate and order
        offset = (page - 1) * per_page
        q = q.order_by(desc(GoldArticle.published_at)).offset(offset).limit(per_page)
        result = await session.execute(q)
        articles = result.scalars().all()

        # Today's outlook summary
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        today_q = await session.execute(
            select(
                GoldArticle.gold_outlook,
                func.count().label("count"),
            )
            .where(
                GoldArticle.is_published.is_(True),
                GoldArticle.created_at >= today_start,
            )
            .group_by(GoldArticle.gold_outlook)
        )
        outlook_counts = {row[0]: row[1] for row in today_q.all()}

        today_count_q = await session.execute(
            select(func.count())
            .where(
                GoldArticle.is_published.is_(True),
                GoldArticle.created_at >= today_start,
            )
        )
        today_count = today_count_q.scalar() or 0

        return {
            "articles": [_article_to_dict(a) for a in articles],
            "total": total,
            "page": page,
            "per_page": per_page,
            "today_count": today_count,
            "today_outlook_summary": {
                "bullish": outlook_counts.get("bullish", 0),
                "bearish": outlook_counts.get("bearish", 0),
                "neutral": outlook_counts.get("neutral", 0),
                "mixed": outlook_counts.get("mixed", 0),
            },
        }


# ══════════════════════════════════════════════════════════════════════════
#  2. GET /articles/daily-digest — today's featured + all published
# ══════════════════════════════════════════════════════════════════════════

@router.get("/articles/daily-digest")
async def daily_digest():
    """Today's featured article + all published, grouped by topic."""
    async with AsyncSessionLocal() as session:
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        # Featured article
        featured_q = await session.execute(
            select(GoldArticle)
            .where(
                GoldArticle.is_published.is_(True),
                GoldArticle.is_featured.is_(True),
            )
            .order_by(desc(GoldArticle.created_at))
            .limit(1)
        )
        featured = featured_q.scalar_one_or_none()

        # Today's articles
        today_q = await session.execute(
            select(GoldArticle)
            .where(
                GoldArticle.is_published.is_(True),
                GoldArticle.created_at >= today_start,
            )
            .order_by(desc(GoldArticle.importance_score))
        )
        today_articles = today_q.scalars().all()

        # Group by first topic
        by_topic: dict[str, list] = {}
        for article in today_articles:
            topics = article.topics or []
            primary_topic = topics[0] if topics else "other"
            by_topic.setdefault(primary_topic, []).append(_article_to_dict(article))

        return {
            "featured": _article_to_dict(featured) if featured else None,
            "today_articles": [_article_to_dict(a) for a in today_articles],
            "by_topic": by_topic,
            "today_count": len(today_articles),
        }


# ══════════════════════════════════════════════════════════════════════════
#  3. GET /articles/{article_id} — full article detail
# ══════════════════════════════════════════════════════════════════════════

@router.get("/articles/{article_id}")
async def get_article(article_id: int):
    """Full article detail with related articles."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(GoldArticle).where(GoldArticle.id == article_id)
        )
        article = result.scalar_one_or_none()

        if not article:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Article not found")

        article_dict = _article_to_dict(article)

        # Find related articles (overlapping topics, recent)
        related = []
        if article.topics:
            for topic in article.topics[:2]:
                related_q = await session.execute(
                    select(GoldArticle)
                    .where(
                        GoldArticle.id != article.id,
                        GoldArticle.is_published.is_(True),
                        GoldArticle.topics.op("@>")(f'["{topic}"]'),
                    )
                    .order_by(desc(GoldArticle.created_at))
                    .limit(3)
                )
                for r in related_q.scalars().all():
                    if r.id not in [x["id"] for x in related]:
                        related.append(_article_to_dict(r))
                        if len(related) >= 3:
                            break
                if len(related) >= 3:
                    break

        # Check for related alerts (cross-link dedup)
        related_alert = None
        try:
            from api.models import Alert
            alert_q = await session.execute(
                select(Alert)
                .where(
                    Alert.source_url == article.source_url,
                    Alert.created_at >= datetime.now(timezone.utc) - timedelta(hours=48),
                )
                .limit(1)
            )
            alert = alert_q.scalar_one_or_none()
            if alert:
                related_alert = {"id": str(alert.id), "title": alert.title}
        except Exception:
            pass

        article_dict["related_articles"] = related[:3]
        article_dict["related_alert"] = related_alert

        return article_dict
