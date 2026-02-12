"""Market snapshot capture — records full market context at alert time.

Called as a fire-and-forget task after ``_store_alert()`` in the worker.
Captures prices, technicals, sentiment, alert context, and quality info.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import desc, func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from api.database import AsyncSessionLocal
from api.analysis.models import AssetPriceDaily
from api.data_collection.indicators import compute_atr, compute_rsi, compute_sma
from api.data_collection.models import AlertMarketSnapshot, AlertOutcome

logger = logging.getLogger("gold_monitor.snapshot")

# Symbol mapping for asset_prices_daily → snapshot fields
_ASSET_SYMBOL_MAP = {
    "DX-Y.NYB": "dxy",
    "^GSPC": "spx",
    "^TNX": "us10y",
    "^VIX": "vix",
    "BTC-USD": "btcusd",
    "SI=F": "xagusd",
}


async def capture_market_snapshot(
    alert_id: str,
    alert_dict: dict,
    price_snapshot: dict,
) -> None:
    """Build and persist a market snapshot for a newly created alert.

    All sections are wrapped in try/except so partial data is always saved.
    """
    t0 = time.monotonic()
    missing: list[str] = []
    data: dict = {
        "id": uuid.uuid4(),
        "alert_id": alert_id,
    }

    async with AsyncSessionLocal() as session:
        # ── 1. Prices from price_snapshot (already fetched by worker) ──
        try:
            data["xauusd"] = price_snapshot.get("xauusd")
            data["usdirr"] = price_snapshot.get("usdirr")
            data["coin"] = price_snapshot.get("coin")
            data["gold_18k"] = price_snapshot.get("gold_18k")

            # Fill remaining from asset_prices_daily (latest row per symbol)
            for symbol, field in _ASSET_SYMBOL_MAP.items():
                row = await session.execute(
                    select(AssetPriceDaily)
                    .where(AssetPriceDaily.symbol == symbol)
                    .order_by(desc(AssetPriceDaily.trade_date))
                    .limit(1)
                )
                r = row.scalar_one_or_none()
                if r:
                    data[field] = r.close
                else:
                    missing.append(field)

            # WTI from yahoo data (CL=F not tracked — skip gracefully)
            if data.get("xauusd") is None:
                missing.append("xauusd")
        except Exception:
            logger.debug("Snapshot prices partial", exc_info=True)
            missing.append("prices_section")

        # ── 2. Technicals from GC=F daily closes ──────────────────────
        try:
            gold_q = await session.execute(
                select(AssetPriceDaily)
                .where(AssetPriceDaily.symbol == "GC=F")
                .order_by(desc(AssetPriceDaily.trade_date))
                .limit(260)
            )
            gold_rows = list(reversed(gold_q.scalars().all()))
            closes = [r.close for r in gold_rows if r.close]
            highs = [r.high for r in gold_rows if r.high is not None]
            lows = [r.low for r in gold_rows if r.low is not None]

            if closes:
                data["gold_rsi_14"] = compute_rsi(closes, 14)
                data["gold_ma50"] = compute_sma(closes, 50)
                data["gold_ma200"] = compute_sma(closes, 200)
                data["gold_atr_14"] = compute_atr(highs, lows, closes, 14)

                current = closes[-1]
                if data.get("gold_ma50"):
                    data["gold_price_vs_ma50_pct"] = (
                        (current - data["gold_ma50"]) / data["gold_ma50"] * 100
                    )
                if data.get("gold_ma200"):
                    data["gold_price_vs_ma200_pct"] = (
                        (current - data["gold_ma200"]) / data["gold_ma200"] * 100
                    )
                if len(closes) >= 6:
                    data["gold_5d_return_pct"] = (
                        (closes[-1] - closes[-6]) / closes[-6] * 100
                    )
                if len(closes) >= 11:
                    data["gold_10d_return_pct"] = (
                        (closes[-1] - closes[-11]) / closes[-11] * 100
                    )

            # DXY 5-day change
            dxy_q = await session.execute(
                select(AssetPriceDaily)
                .where(AssetPriceDaily.symbol == "DX-Y.NYB")
                .order_by(desc(AssetPriceDaily.trade_date))
                .limit(6)
            )
            dxy_rows = dxy_q.scalars().all()
            if len(dxy_rows) >= 2:
                data["dxy_5d_change"] = dxy_rows[0].close - dxy_rows[-1].close

            if not closes:
                missing.append("technicals")
        except Exception:
            logger.debug("Snapshot technicals partial", exc_info=True)
            missing.append("technicals_section")

        # ── 3. Sentiment ──────────────────────────────────────────────
        try:
            from api.data_collection.sentiment_calculator import compute_sentiment
            sent = await compute_sentiment(session)
            data["sentiment_composite"] = sent.get("composite_score")
            data["sentiment_direction"] = sent.get("label")
            data["sentiment_sub_scores"] = sent.get("components")
        except Exception:
            logger.debug("Snapshot sentiment partial", exc_info=True)
            missing.append("sentiment")

        # ── 4. Alert context ──────────────────────────────────────────
        try:
            now = datetime.now(timezone.utc)
            for hours, field in [(1, "alerts_1h_count"), (4, "alerts_4h_count"), (24, "alerts_24h_count")]:
                since = now - timedelta(hours=hours)
                cnt = await session.execute(
                    text("SELECT COUNT(*) FROM alerts WHERE timestamp_utc >= :since"),
                    {"since": since},
                )
                data[field] = cnt.scalar() or 0

            # Bullish/bearish in 24h (from match_evidence → direction)
            alerts_24h = await session.execute(
                text(
                    "SELECT match_evidence->>'direction' AS dir "
                    "FROM alerts WHERE timestamp_utc >= :since"
                ),
                {"since": now - timedelta(hours=24)},
            )
            dirs = [r[0] for r in alerts_24h if r[0]]
            data["alerts_bullish_24h"] = sum(1 for d in dirs if d == "bullish")
            data["alerts_bearish_24h"] = sum(1 for d in dirs if d == "bearish")
            if data["alerts_bullish_24h"] > data["alerts_bearish_24h"]:
                data["dominant_sentiment_24h"] = "bullish"
            elif data["alerts_bearish_24h"] > data["alerts_bullish_24h"]:
                data["dominant_sentiment_24h"] = "bearish"
            else:
                data["dominant_sentiment_24h"] = "neutral"

            # Previous high-severity alert
            prev_high = await session.execute(
                text(
                    "SELECT id, timestamp_utc, event_category, "
                    "match_evidence->>'direction' AS direction "
                    "FROM alerts WHERE severity = 'high' AND id != :aid "
                    "ORDER BY timestamp_utc DESC LIMIT 1"
                ),
                {"aid": alert_id},
            )
            prev = prev_high.first()
            if prev:
                data["prev_high_alert_id"] = prev[0]
                data["prev_high_alert_hours_ago"] = (
                    (now - prev[1]).total_seconds() / 3600 if prev[1] else None
                )
                data["prev_high_alert_category"] = prev[2]
                data["prev_high_alert_direction"] = prev[3]
        except Exception:
            logger.debug("Snapshot alert context partial", exc_info=True)
            missing.append("alert_context")

        # ── 5. Price changes before alert ─────────────────────────────
        try:
            xau_price = data.get("xauusd")
            if xau_price:
                # Try signal_price_ticks for intraday data
                for hours, field in [(1, "price_change_1h_before"), (4, "price_change_4h_before"), (24, "price_change_24h_before")]:
                    since = datetime.now(timezone.utc) - timedelta(hours=hours)
                    tick_q = await session.execute(
                        text(
                            "SELECT price FROM signal_price_ticks "
                            "WHERE checked_at <= :since "
                            "ORDER BY checked_at DESC LIMIT 1"
                        ),
                        {"since": since},
                    )
                    old_price = tick_q.scalar()
                    if old_price and old_price > 0:
                        data[field] = (xau_price - old_price) / old_price * 100
        except Exception:
            logger.debug("Snapshot price changes partial", exc_info=True)
            missing.append("price_changes_before")

        # ── 6. Quality check ──────────────────────────────────────────
        essential = ["xauusd", "gold_rsi_14", "sentiment_composite", "alerts_24h_count"]
        data["snapshot_complete"] = all(data.get(f) is not None for f in essential)
        data["missing_fields"] = missing if missing else None
        data["fetch_duration_ms"] = int((time.monotonic() - t0) * 1000)

        # ── Persist snapshot ──────────────────────────────────────────
        try:
            snapshot = AlertMarketSnapshot(**data)
            session.add(snapshot)
            await session.flush()

            # Also create the alert_outcomes row
            direction = alert_dict.get("match_evidence", {}).get("direction")
            outcome = AlertOutcome(
                alert_id=alert_id,
                alert_direction=direction,
                alert_severity=alert_dict.get("severity"),
                price_at_alert=data.get("xauusd"),
                alert_created_at=alert_dict.get("timestamp_utc") or datetime.now(timezone.utc),
                status="pending_30min",
            )
            session.add(outcome)

            await session.commit()
            logger.info(
                "Snapshot saved for alert %s (complete=%s, %dms)",
                str(alert_id)[:8], data["snapshot_complete"], data["fetch_duration_ms"],
            )
        except Exception:
            await session.rollback()
            logger.warning("Failed to persist snapshot for alert %s", alert_id, exc_info=True)
