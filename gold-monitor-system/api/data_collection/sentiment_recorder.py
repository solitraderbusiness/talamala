"""Sentiment timeline recorder — captures sentiment + price every 5 minutes.

Runs as a periodic task in the analysis-worker process.
Stores records in the ``sentiment_timeline`` table.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, text

from api.database import AsyncSessionLocal
from api.data_collection.models import SentimentTimeline
from api.data_collection.sentiment_calculator import compute_sentiment
from api.price_snapshot import get_price_snapshot

logger = logging.getLogger("analysis.sentiment_recorder")

RETENTION_DAYS = 90


async def run() -> dict:
    """Record a sentiment timeline datapoint.

    Deduplicates by rounding recorded_at to the nearest 5-minute bucket.
    """
    now = datetime.now(timezone.utc)
    # Round to 5-min bucket
    bucket = now.replace(second=0, microsecond=0)
    bucket = bucket.replace(minute=(bucket.minute // 5) * 5)

    async with AsyncSessionLocal() as session:
        # Check if already recorded for this bucket
        existing = await session.execute(
            select(SentimentTimeline).where(
                SentimentTimeline.recorded_at == bucket
            )
        )
        if existing.scalar_one_or_none() is not None:
            return {"status": "skipped", "reason": "already_recorded"}

        # Compute sentiment
        try:
            sent = await compute_sentiment(session)
        except Exception:
            logger.warning("Could not compute sentiment", exc_info=True)
            sent = {}

        # Get gold price
        try:
            prices = await get_price_snapshot()
            gold_price = prices.get("xauusd")
        except Exception:
            gold_price = None

        # Get gold 1h change from signal_price_ticks
        gold_change_1h = None
        if gold_price:
            try:
                one_hour_ago = now - timedelta(hours=1)
                tick_q = await session.execute(
                    text(
                        "SELECT price FROM signal_price_ticks "
                        "WHERE checked_at <= :since "
                        "ORDER BY checked_at DESC LIMIT 1"
                    ),
                    {"since": one_hour_ago},
                )
                old_price = tick_q.scalar()
                if old_price and old_price > 0:
                    gold_change_1h = (gold_price - old_price) / old_price * 100
            except Exception:
                pass

        # Count active alerts
        alert_counts = {}
        for hours, field in [(1, "alerts_active_1h"), (4, "alerts_active_4h"), (24, "alerts_active_24h")]:
            try:
                since = now - timedelta(hours=hours)
                cnt = await session.execute(
                    text("SELECT COUNT(*) FROM alerts WHERE timestamp_utc >= :since"),
                    {"since": since},
                )
                alert_counts[field] = cnt.scalar() or 0
            except Exception:
                alert_counts[field] = None

        # Insert record
        record = SentimentTimeline(
            recorded_at=bucket,
            composite_score=sent.get("composite_score"),
            direction=sent.get("label"),
            sub_scores=sent.get("components"),
            gold_price=gold_price,
            gold_change_1h_pct=round(gold_change_1h, 4) if gold_change_1h is not None else None,
            alerts_active_1h=alert_counts.get("alerts_active_1h"),
            alerts_active_4h=alert_counts.get("alerts_active_4h"),
            alerts_active_24h=alert_counts.get("alerts_active_24h"),
        )
        session.add(record)

        # Cleanup old records
        cutoff = now - timedelta(days=RETENTION_DAYS)
        await session.execute(
            delete(SentimentTimeline).where(
                SentimentTimeline.recorded_at < cutoff
            )
        )

        await session.commit()

    logger.info(
        "Sentiment recorded: score=%s price=%s",
        sent.get("composite_score"), gold_price,
    )
    return {
        "status": "ok",
        "composite_score": sent.get("composite_score"),
        "gold_price": gold_price,
    }
