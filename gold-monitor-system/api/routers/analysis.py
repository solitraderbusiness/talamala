"""Fundamental analysis API — macro overview, money flow, real rates,
correlations, sentiment gauge, Shanghai premium, market activity.

All endpoints return graceful empty/pending responses when no data exists.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import desc, func, select, text

from api.database import AsyncSessionLocal
from api.analysis.models import (
    AssetPriceDaily,
    CorrelationCache,
    CotData,
    EtfHolding,
    MacroIndicator,
    MarketEventAnalysis,
    RegimeScore,
)
from api.data_collection.models import SentimentTimeline, PriceHistory
from api.models import EconomicEvent
from api.data_collection.indicators import compute_rsi

router = APIRouter(tags=["analysis"])
logger = logging.getLogger("gold_monitor.analysis")

# ── Symbol display names (Persian) ──────────────────────────────────────

SYMBOL_LABELS = {
    "GC=F": {"en": "Gold (XAU)", "fa": "طلا (اونس)"},
    "DX-Y.NYB": {"en": "US Dollar Index", "fa": "شاخص دلار (DXY)"},
    "^GSPC": {"en": "S&P 500", "fa": "S&P 500"},
    "^TNX": {"en": "US 10Y Yield", "fa": "بازده ۱۰ ساله آمریکا"},
    "^VIX": {"en": "VIX (Fear Index)", "fa": "شاخص ترس (VIX)"},
    "BTC-USD": {"en": "Bitcoin", "fa": "بیت‌کوین"},
    "SI=F": {"en": "Silver", "fa": "نقره"},
}

FRED_LABELS = {
    "FEDFUNDS": {"en": "Fed Funds Rate", "fa": "نرخ بهره فدرال", "unit": "%"},
    "CPIAUCSL": {"en": "CPI (All Urban)", "fa": "شاخص تورم مصرف‌کننده", "unit": "index"},
    "DFII10": {"en": "10Y Real Rate (TIPS)", "fa": "نرخ بهره واقعی ۱۰ ساله", "unit": "%"},
    "DGS10": {"en": "10Y Treasury Yield", "fa": "بازده ۱۰ ساله خزانه‌داری", "unit": "%"},
    "T10YIE": {"en": "10Y Breakeven Inflation", "fa": "انتظارات تورمی ۱۰ ساله", "unit": "%"},
}


# ── Helper: safe JSON parse ─────────────────────────────────────────────

def _safe_json(raw: str | None) -> dict | list | None:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


# ══════════════════════════════════════════════════════════════════════════
#  1. GET /macro-overview — 4 summary cards
# ══════════════════════════════════════════════════════════════════════════

@router.get("/macro-overview")
async def macro_overview():
    """Return 4 high-level summary cards: Money Flow, Real Rates, Dollar, Risk."""
    async with AsyncSessionLocal() as session:
        today = date.today()
        week_ago = today - timedelta(days=7)

        # Latest ETF holdings
        etf_q = await session.execute(
            select(EtfHolding)
            .where(EtfHolding.fund == "GLD")
            .order_by(desc(EtfHolding.holding_date))
            .limit(2)
        )
        gld_rows = etf_q.scalars().all()
        gld_latest = gld_rows[0] if gld_rows else None
        gld_prev = gld_rows[1] if len(gld_rows) > 1 else None

        # Latest COT net position
        cot_q = await session.execute(
            select(CotData)
            .where(CotData.asset == "gold")
            .order_by(desc(CotData.report_date))
            .limit(1)
        )
        cot_latest = cot_q.scalar_one_or_none()

        # Latest real rate
        real_rate_q = await session.execute(
            select(MacroIndicator)
            .where(MacroIndicator.series_id == "DFII10")
            .order_by(desc(MacroIndicator.observation_date))
            .limit(1)
        )
        real_rate = real_rate_q.scalar_one_or_none()

        # Latest DXY
        dxy_q = await session.execute(
            select(AssetPriceDaily)
            .where(AssetPriceDaily.symbol == "DX-Y.NYB")
            .order_by(desc(AssetPriceDaily.trade_date))
            .limit(2)
        )
        dxy_rows = dxy_q.scalars().all()
        dxy_latest = dxy_rows[0] if dxy_rows else None
        dxy_prev = dxy_rows[1] if len(dxy_rows) > 1 else None

        # Latest VIX
        vix_q = await session.execute(
            select(AssetPriceDaily)
            .where(AssetPriceDaily.symbol == "^VIX")
            .order_by(desc(AssetPriceDaily.trade_date))
            .limit(1)
        )
        vix_latest = vix_q.scalar_one_or_none()

        # Build cards
        def _money_flow_card():
            if not gld_latest and not cot_latest:
                return {"id": "money_flow", "title_fa": "جریان پول", "status": "pending", "data": None}
            data: dict = {}
            if gld_latest:
                data["gld_tonnes"] = gld_latest.total_tonnes
                data["gld_change"] = gld_latest.change_tonnes
                data["gld_unit"] = "tonnes"
                data["source"] = "SPDR/GLD"
                data["source_date"] = str(gld_latest.holding_date)
                data["frequency"] = "daily"
            if cot_latest:
                data["cot_net"] = cot_latest.non_commercial_net
                data["cot_change"] = cot_latest.change_non_commercial_net
                data["cot_unit"] = "contracts"
            # Determine impact
            impact = "neutral"
            if gld_latest and gld_latest.change_tonnes and gld_latest.change_tonnes > 0:
                impact = "bullish"
            elif cot_latest and cot_latest.change_non_commercial_net and cot_latest.change_non_commercial_net > 0:
                impact = "bullish"
            elif gld_latest and gld_latest.change_tonnes and gld_latest.change_tonnes < 0:
                impact = "bearish"
            return {"id": "money_flow", "title_fa": "جریان پول", "status": "ready", "impact": impact, "data": data}

        def _real_rates_card():
            if not real_rate:
                return {"id": "real_rates", "title_fa": "نرخ بهره واقعی", "status": "pending", "data": None}
            impact = "bearish" if real_rate.value > 0 else "bullish"
            return {
                "id": "real_rates", "title_fa": "نرخ بهره واقعی", "status": "ready",
                "impact": impact,
                "data": {
                    "real_rate": real_rate.value,
                    "date": str(real_rate.observation_date),
                    "unit": "%",
                    "source": "FRED/DFII10",
                    "source_date": str(real_rate.observation_date),
                    "frequency": "daily",
                },
            }

        def _dollar_card():
            if not dxy_latest:
                return {"id": "dollar", "title_fa": "شاخص دلار", "status": "pending", "data": None}
            change = None
            if dxy_prev:
                change = round(dxy_latest.close - dxy_prev.close, 2)
            impact = "bearish" if change and change > 0 else "bullish" if change and change < 0 else "neutral"
            return {
                "id": "dollar", "title_fa": "شاخص دلار", "status": "ready",
                "impact": impact,
                "data": {
                    "dxy": dxy_latest.close,
                    "change": change,
                    "date": str(dxy_latest.trade_date),
                    "unit": "index",
                    "source": "Yahoo/DX-Y.NYB",
                    "source_date": str(dxy_latest.trade_date),
                    "frequency": "daily",
                },
            }

        def _risk_card():
            if not vix_latest:
                return {"id": "risk", "title_fa": "شاخص ترس (VIX)", "status": "pending", "data": None}
            impact = "bullish" if vix_latest.close > 25 else "bearish" if vix_latest.close < 15 else "neutral"
            return {
                "id": "risk", "title_fa": "شاخص ترس (VIX)", "status": "ready",
                "impact": impact,
                "data": {
                    "vix": vix_latest.close,
                    "date": str(vix_latest.trade_date),
                    "unit": "index",
                    "source": "Yahoo/^VIX",
                    "source_date": str(vix_latest.trade_date),
                    "frequency": "daily",
                    "direction_note_fa": "VIX بالاتر = ترس بیشتر = حمایت از طلا",
                },
            }

        return {
            "cards": [_money_flow_card(), _real_rates_card(), _dollar_card(), _risk_card()],
        }


# ══════════════════════════════════════════════════════════════════════════
#  2. GET /money-flow — ETF + COT + central bank detail
# ══════════════════════════════════════════════════════════════════════════

@router.get("/money-flow")
async def money_flow(days: int = Query(90, ge=7, le=365)):
    """Detailed money flow: ETF holdings history, COT positions."""
    async with AsyncSessionLocal() as session:
        since = date.today() - timedelta(days=days)

        # ETF history
        etf_q = await session.execute(
            select(EtfHolding)
            .where(EtfHolding.holding_date >= since)
            .order_by(EtfHolding.fund, EtfHolding.holding_date)
        )
        etf_rows = etf_q.scalars().all()

        etf_by_fund: dict[str, list] = {}
        for row in etf_rows:
            etf_by_fund.setdefault(row.fund, []).append({
                "date": str(row.holding_date),
                "total_tonnes": row.total_tonnes,
                "change_tonnes": row.change_tonnes,
                "unit": "tonnes",
            })

        # COT history
        cot_q = await session.execute(
            select(CotData)
            .where(CotData.report_date >= since, CotData.asset == "gold")
            .order_by(CotData.report_date)
        )
        cot_rows = cot_q.scalars().all()
        cot_history = [
            {
                "date": str(r.report_date),
                "non_commercial_net": r.non_commercial_net,
                "open_interest": r.open_interest,
                "change": r.change_non_commercial_net,
                "unit": "contracts",
            }
            for r in cot_rows
        ]

        # Derived stats (z-score, percentiles, combined signal)
        derived = None
        meta = None
        try:
            from api.analysis.money_flow_service import get_money_flow_derived

            derived_data = await get_money_flow_derived(session)
            derived = derived_data

            # Build meta with source attribution and freshness
            etf_info = derived_data.get("etf", {})
            cot_info = derived_data.get("cot", {})
            meta = {
                "etf_source": {
                    "name": "SPDR Gold Trust Archive",
                    "url": etf_info.get("source_url"),
                    "frequency": "daily",
                    "last_date": etf_info.get("latest_date"),
                },
                "cot_source": {
                    "name": "CFTC Commitment of Traders",
                    "url": cot_info.get("source_url"),
                    "frequency": "weekly",
                    "last_date": cot_info.get("latest_date"),
                },
            }
        except Exception:
            logger.debug("Money flow derived stats failed", exc_info=True)

        result = {
            "etf_holdings": etf_by_fund,
            "cot_positions": cot_history,
            "period_days": days,
        }
        if derived is not None:
            result["derived"] = derived
        if meta is not None:
            result["meta"] = meta

        return result


# ══════════════════════════════════════════════════════════════════════════
#  3. GET /real-rates — FRED indicators + 90-day history
# ══════════════════════════════════════════════════════════════════════════

@router.get("/real-rates")
async def real_rates(days: int = Query(90, ge=7, le=365)):
    """FRED macro indicators with history."""
    async with AsyncSessionLocal() as session:
        since = date.today() - timedelta(days=days)

        q = await session.execute(
            select(MacroIndicator)
            .where(MacroIndicator.observation_date >= since)
            .order_by(MacroIndicator.series_id, MacroIndicator.observation_date)
        )
        rows = q.scalars().all()

        by_series: dict[str, list] = {}
        latest_by_series: dict[str, dict] = {}
        for row in rows:
            entry = {"date": str(row.observation_date), "value": row.value}
            by_series.setdefault(row.series_id, []).append(entry)
            latest_by_series[row.series_id] = entry

        indicators = []
        freq_map = {"CPIAUCSL": "monthly", "FEDFUNDS": "daily"}
        for series_id, label_info in FRED_LABELS.items():
            latest = latest_by_series.get(series_id)
            indicators.append({
                "series_id": series_id,
                "label_en": label_info["en"],
                "label_fa": label_info["fa"],
                "unit": label_info.get("unit", "%"),
                "frequency": freq_map.get(series_id, "daily"),
                "latest_value": latest["value"] if latest else None,
                "latest_date": latest["date"] if latest else None,
                "history": by_series.get(series_id, []),
            })

        return {"indicators": indicators, "period_days": days}


# ══════════════════════════════════════════════════════════════════════════
#  4. GET /correlations — 30-day Pearson pairs
# ══════════════════════════════════════════════════════════════════════════

@router.get("/correlations")
async def correlations():
    """Latest 30-day correlations between gold and other assets."""
    async with AsyncSessionLocal() as session:
        # Get the most recent computed_date
        latest_date_q = await session.execute(
            select(func.max(CorrelationCache.computed_date))
        )
        latest_date = latest_date_q.scalar()

        if not latest_date:
            return {"pairs": [], "computed_date": None}

        q = await session.execute(
            select(CorrelationCache)
            .where(CorrelationCache.computed_date == latest_date)
            .order_by(CorrelationCache.pair_b)
        )
        rows = q.scalars().all()

        pairs = []
        for row in rows:
            label_info = SYMBOL_LABELS.get(row.pair_b, {"en": row.pair_b, "fa": row.pair_b})
            # Determine gold impact interpretation
            if row.pair_b in ("DX-Y.NYB",):
                # Negative correlation with gold is normal; strong negative = bearish for gold when DXY up
                impact = "bearish" if row.correlation < -0.3 else "bullish" if row.correlation > 0.3 else "neutral"
            elif row.pair_b in ("^VIX",):
                impact = "bullish" if row.correlation > 0.3 else "neutral"
            else:
                impact = "neutral"

            pairs.append({
                "pair_a": row.pair_a,
                "pair_b": row.pair_b,
                "label_fa": label_info["fa"],
                "correlation": round(row.correlation, 3),
                "unit": "coefficient",
                "impact": impact,
                "window_days": row.window_days,
            })

        return {
            "pairs": pairs,
            "computed_date": str(latest_date),
            "method": "pearson_log_returns",
            "frequency": "daily",
        }


# ══════════════════════════════════════════════════════════════════════════
#  5. GET /sentiment-gauge — 0-100 composite score
# ══════════════════════════════════════════════════════════════════════════

@router.get("/sentiment-gauge")
async def sentiment_gauge():
    """Composite 0-100 sentiment score from 6 components."""
    from api.data_collection.sentiment_calculator import compute_sentiment

    async with AsyncSessionLocal() as session:
        return await compute_sentiment(session)


# ══════════════════════════════════════════════════════════════════════════
#  6. GET /shanghai-premium — SGE vs LBMA spread
# ══════════════════════════════════════════════════════════════════════════

@router.get("/shanghai-premium")
async def shanghai_premium():
    """Shanghai Gold Exchange premium over LBMA.

    This requires a dedicated data source (not yet implemented).
    Returns pending status for now.
    """
    return {
        "status": "pending",
        "premium_usd": None,
        "premium_pct": None,
        "message_fa": "داده‌های بورس طلای شانگهای به زودی اضافه خواهند شد",
    }


# ══════════════════════════════════════════════════════════════════════════
#  7. GET /market-activity — auto-generated event feed (last 48h)
# ══════════════════════════════════════════════════════════════════════════

@router.get("/market-activity")
async def market_activity(
    hours: int = Query(48, ge=1, le=168),
    event_type: str | None = Query(None),
):
    """Chronological event feed from data changes."""
    async with AsyncSessionLocal() as session:
        since = datetime.now(timezone.utc) - timedelta(hours=hours)

        q = select(MarketEventAnalysis).where(
            MarketEventAnalysis.created_at >= since
        )
        if event_type:
            q = q.where(MarketEventAnalysis.event_type == event_type)
        q = q.order_by(desc(MarketEventAnalysis.created_at)).limit(100)

        result = await session.execute(q)
        rows = result.scalars().all()

        events = []
        for row in rows:
            events.append({
                "id": str(row.id),
                "event_type": row.event_type,
                "title": row.title,
                "title_fa": row.title_fa,
                "description": row.description,
                "description_fa": row.description_fa,
                "impact": row.impact,
                "magnitude": row.magnitude,
                "data": _safe_json(row.data_json),
                "created_at": row.created_at.isoformat() if row.created_at else None,
            })

        return {
            "events": events,
            "total": len(events),
            "period_hours": hours,
        }


# ── Helper: pure-Python Pearson correlation ───────────────────────────

def _pearson(xs: list[float], ys: list[float]) -> float | None:
    """Compute Pearson correlation coefficient without numpy."""
    n = len(xs)
    if n < 3 or len(ys) != n:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    dx = [x - mx for x in xs]
    dy = [y - my for y in ys]
    num = sum(a * b for a, b in zip(dx, dy))
    den_x = sum(a * a for a in dx)
    den_y = sum(b * b for b in dy)
    if den_x == 0 or den_y == 0:
        return None
    return num / (den_x * den_y) ** 0.5


# ══════════════════════════════════════════════════════════════════════════
#  8. GET /sentiment-price-correlation — sentiment vs gold price lag analysis
# ══════════════════════════════════════════════════════════════════════════

@router.get("/sentiment-price-correlation")
async def sentiment_price_correlation():
    """Compute Pearson correlation between sentiment score and gold price
    change at various lags (5min, 15min, 1h, 4h)."""
    try:
        async with AsyncSessionLocal() as session:
            since = datetime.now(timezone.utc) - timedelta(days=7)
            q = await session.execute(
                select(SentimentTimeline)
                .where(SentimentTimeline.recorded_at >= since)
                .order_by(SentimentTimeline.recorded_at)
            )
            rows = q.scalars().all()

            # Filter rows that have both score and price
            data = [
                (r.composite_score, r.gold_price)
                for r in rows
                if r.composite_score is not None and r.gold_price is not None
            ]
            if len(data) < 10:
                return {"lags": [], "data_points": len(data)}

            scores = [d[0] for d in data]
            prices = [d[1] for d in data]

            lags_config = [
                {"label": "5min", "rows": 1},
                {"label": "15min", "rows": 3},
                {"label": "1h", "rows": 12},
                {"label": "4h", "rows": 48},
            ]

            lags_result = []
            for cfg in lags_config:
                lag = cfg["rows"]
                if len(data) <= lag + 2:
                    lags_result.append({
                        "lag": cfg["label"],
                        "lag_rows": lag,
                        "correlation": None,
                    })
                    continue
                # Sentiment values up to -lag, price changes starting at +lag
                sent_slice = scores[:-lag]
                price_changes = [
                    prices[i + lag] - prices[i]
                    for i in range(len(prices) - lag)
                ]
                corr = _pearson(sent_slice, price_changes)
                lags_result.append({
                    "lag": cfg["label"],
                    "lag_rows": lag,
                    "correlation": round(corr, 4) if corr is not None else None,
                })

            return {"lags": lags_result, "data_points": len(data)}
    except Exception as exc:
        logger.exception("sentiment-price-correlation error: %s", exc)
        return {"lags": [], "data_points": 0}


# ══════════════════════════════════════════════════════════════════════════
#  9. GET /sentiment-extremes — price reaction to sentiment extremes
# ══════════════════════════════════════════════════════════════════════════

@router.get("/sentiment-extremes")
async def sentiment_extremes():
    """Find sentiment extremes (>80 bullish, <20 bearish) and measure
    subsequent gold price changes at 1h, 4h, 24h."""
    try:
        async with AsyncSessionLocal() as session:
            q = await session.execute(
                select(SentimentTimeline)
                .where(SentimentTimeline.composite_score.is_not(None))
                .where(SentimentTimeline.gold_price.is_not(None))
                .order_by(SentimentTimeline.recorded_at)
            )
            rows = q.scalars().all()

            if not rows:
                return {
                    "bullish_extreme": {"count": 0, "avg_change_1h": None, "avg_change_4h": None, "avg_change_24h": None},
                    "bearish_extreme": {"count": 0, "avg_change_1h": None, "avg_change_4h": None, "avg_change_24h": None},
                }

            # Build time-indexed list for lookups
            timed = [(r.recorded_at, r.composite_score, r.gold_price) for r in rows]

            def _find_closest_price(after_dt: datetime, target_delta: timedelta) -> float | None:
                """Find the gold price closest to after_dt + target_delta."""
                target = after_dt + target_delta
                best = None
                best_diff = None
                for dt, _score, price in timed:
                    diff = abs((dt - target).total_seconds())
                    # Only consider within 50% tolerance of the target delta
                    max_tolerance = target_delta.total_seconds() * 0.5
                    if diff <= max_tolerance and (best_diff is None or diff < best_diff):
                        best = price
                        best_diff = diff
                return best

            bullish_changes: dict[str, list[float]] = {"1h": [], "4h": [], "24h": []}
            bearish_changes: dict[str, list[float]] = {"1h": [], "4h": [], "24h": []}

            deltas = {
                "1h": timedelta(hours=1),
                "4h": timedelta(hours=4),
                "24h": timedelta(hours=24),
            }

            for dt, score, price in timed:
                if score > 80:
                    target = bullish_changes
                elif score < 20:
                    target = bearish_changes
                else:
                    continue

                for key, delta in deltas.items():
                    future_price = _find_closest_price(dt, delta)
                    if future_price is not None and price > 0:
                        change_pct = ((future_price - price) / price) * 100
                        target[key].append(change_pct)

            def _avg(lst: list[float]) -> float | None:
                return round(sum(lst) / len(lst), 4) if lst else None

            return {
                "bullish_extreme": {
                    "count": len(bullish_changes["1h"]) if bullish_changes["1h"] else 0,
                    "avg_change_1h": _avg(bullish_changes["1h"]),
                    "avg_change_4h": _avg(bullish_changes["4h"]),
                    "avg_change_24h": _avg(bullish_changes["24h"]),
                },
                "bearish_extreme": {
                    "count": len(bearish_changes["1h"]) if bearish_changes["1h"] else 0,
                    "avg_change_1h": _avg(bearish_changes["1h"]),
                    "avg_change_4h": _avg(bearish_changes["4h"]),
                    "avg_change_24h": _avg(bearish_changes["24h"]),
                },
            }
    except Exception as exc:
        logger.exception("sentiment-extremes error: %s", exc)
        return {
            "bullish_extreme": {"count": 0, "avg_change_1h": None, "avg_change_4h": None, "avg_change_24h": None},
            "bearish_extreme": {"count": 0, "avg_change_1h": None, "avg_change_4h": None, "avg_change_24h": None},
        }


# ══════════════════════════════════════════════════════════════════════════
# 10. GET /event-impact — economic event impact on gold price
# ══════════════════════════════════════════════════════════════════════════

@router.get("/event-impact")
async def event_impact(event_type: str | None = Query(None)):
    """Measure gold price movement after economic events, grouped by category."""
    try:
        async with AsyncSessionLocal() as session:
            now = datetime.now(timezone.utc)
            q = select(EconomicEvent).where(
                EconomicEvent.datetime_utc < now,
                EconomicEvent.actual.is_not(None),
            )
            if event_type:
                q = q.where(EconomicEvent.category == event_type)
            q = q.order_by(desc(EconomicEvent.datetime_utc)).limit(500)

            result = await session.execute(q)
            events = result.scalars().all()

            if not events:
                return {"event_types": []}

            # For each event, find gold price at event time and 1h/4h/24h after
            category_moves: dict[str, dict] = {}

            for ev in events:
                cat = ev.category or "unknown"
                if cat not in category_moves:
                    category_moves[cat] = {"moves_1h": [], "moves_4h": [], "count": 0}

                # Find price candle closest to event time
                base_q = await session.execute(
                    select(PriceHistory)
                    .where(
                        PriceHistory.symbol == "XAUUSD",
                        PriceHistory.timeframe == "5min",
                        PriceHistory.datetime_utc >= ev.datetime_utc - timedelta(minutes=10),
                        PriceHistory.datetime_utc <= ev.datetime_utc + timedelta(minutes=10),
                    )
                    .order_by(PriceHistory.datetime_utc)
                    .limit(1)
                )
                base_candle = base_q.scalar_one_or_none()
                if not base_candle or not base_candle.close:
                    continue

                base_price = base_candle.close
                category_moves[cat]["count"] += 1

                # 1h after
                h1_q = await session.execute(
                    select(PriceHistory)
                    .where(
                        PriceHistory.symbol == "XAUUSD",
                        PriceHistory.timeframe == "5min",
                        PriceHistory.datetime_utc >= ev.datetime_utc + timedelta(minutes=50),
                        PriceHistory.datetime_utc <= ev.datetime_utc + timedelta(minutes=70),
                    )
                    .order_by(PriceHistory.datetime_utc)
                    .limit(1)
                )
                h1_candle = h1_q.scalar_one_or_none()
                if h1_candle and h1_candle.close:
                    category_moves[cat]["moves_1h"].append(
                        abs((h1_candle.close - base_price) / base_price * 100)
                    )

                # 4h after
                h4_q = await session.execute(
                    select(PriceHistory)
                    .where(
                        PriceHistory.symbol == "XAUUSD",
                        PriceHistory.timeframe == "5min",
                        PriceHistory.datetime_utc >= ev.datetime_utc + timedelta(hours=3, minutes=50),
                        PriceHistory.datetime_utc <= ev.datetime_utc + timedelta(hours=4, minutes=10),
                    )
                    .order_by(PriceHistory.datetime_utc)
                    .limit(1)
                )
                h4_candle = h4_q.scalar_one_or_none()
                if h4_candle and h4_candle.close:
                    category_moves[cat]["moves_4h"].append(
                        abs((h4_candle.close - base_price) / base_price * 100)
                    )

            event_types = []
            for cat, data in category_moves.items():
                m1 = data["moves_1h"]
                m4 = data["moves_4h"]
                event_types.append({
                    "category": cat,
                    "event_count": data["count"],
                    "avg_abs_move_1h": round(sum(m1) / len(m1), 4) if m1 else None,
                    "avg_abs_move_4h": round(sum(m4) / len(m4), 4) if m4 else None,
                    "max_move_4h": round(max(m4), 4) if m4 else None,
                })

            return {"event_types": event_types}
    except Exception as exc:
        logger.exception("event-impact error: %s", exc)
        return {"event_types": []}


# ══════════════════════════════════════════════════════════════════════════
# 11. GET /event-impact/rankings — events ranked by gold impact
# ══════════════════════════════════════════════════════════════════════════

@router.get("/event-impact/rankings")
async def event_impact_rankings():
    """Return economic events ranked by average absolute gold price move at 4h."""
    try:
        async with AsyncSessionLocal() as session:
            now = datetime.now(timezone.utc)
            result = await session.execute(
                select(EconomicEvent)
                .where(EconomicEvent.datetime_utc < now, EconomicEvent.actual.is_not(None))
                .order_by(desc(EconomicEvent.datetime_utc))
                .limit(500)
            )
            events = result.scalars().all()

            if not events:
                return {"rankings": [], "total_events": 0}

            # Group by (category, event_name) and measure 4h move
            group_moves: dict[tuple[str, str], list[float]] = {}

            for ev in events:
                cat = ev.category or "unknown"
                name = ev.event_name or "unknown"
                key = (cat, name)

                base_q = await session.execute(
                    select(PriceHistory)
                    .where(
                        PriceHistory.symbol == "XAUUSD",
                        PriceHistory.timeframe == "5min",
                        PriceHistory.datetime_utc >= ev.datetime_utc - timedelta(minutes=10),
                        PriceHistory.datetime_utc <= ev.datetime_utc + timedelta(minutes=10),
                    )
                    .order_by(PriceHistory.datetime_utc)
                    .limit(1)
                )
                base_candle = base_q.scalar_one_or_none()
                if not base_candle or not base_candle.close:
                    continue

                h4_q = await session.execute(
                    select(PriceHistory)
                    .where(
                        PriceHistory.symbol == "XAUUSD",
                        PriceHistory.timeframe == "5min",
                        PriceHistory.datetime_utc >= ev.datetime_utc + timedelta(hours=3, minutes=50),
                        PriceHistory.datetime_utc <= ev.datetime_utc + timedelta(hours=4, minutes=10),
                    )
                    .order_by(PriceHistory.datetime_utc)
                    .limit(1)
                )
                h4_candle = h4_q.scalar_one_or_none()
                if h4_candle and h4_candle.close:
                    move = abs((h4_candle.close - base_candle.close) / base_candle.close * 100)
                    group_moves.setdefault(key, []).append(move)

            rankings = []
            for (cat, name), moves in group_moves.items():
                rankings.append({
                    "category": cat,
                    "event_name": name,
                    "avg_abs_move_4h": round(sum(moves) / len(moves), 4),
                    "count": len(moves),
                })

            rankings.sort(key=lambda x: x["avg_abs_move_4h"], reverse=True)

            return {"rankings": rankings, "total_events": len(events)}
    except Exception as exc:
        logger.exception("event-impact-rankings error: %s", exc)
        return {"rankings": [], "total_events": 0}


# ══════════════════════════════════════════════════════════════════════════
# 12. GET /etf-momentum — GLD inflow/outflow streak
# ══════════════════════════════════════════════════════════════════════════

@router.get("/etf-momentum")
async def etf_momentum():
    """Calculate current GLD ETF inflow/outflow streak."""
    try:
        async with AsyncSessionLocal() as session:
            q = await session.execute(
                select(EtfHolding)
                .where(EtfHolding.fund == "GLD")
                .order_by(desc(EtfHolding.holding_date))
                .limit(90)
            )
            rows = q.scalars().all()

            if not rows:
                return {
                    "fund": "GLD",
                    "streak_days": 0,
                    "streak_direction": None,
                    "streak_total_tonnes": 0,
                    "last_date": None,
                }

            # Rows are newest-first; walk from newest to find consecutive streak
            streak_days = 0
            streak_total = 0.0
            streak_dir = None

            for row in rows:
                change = row.change_tonnes
                if change is None or change == 0:
                    break

                current_sign = "inflow" if change > 0 else "outflow"
                if streak_dir is None:
                    streak_dir = current_sign
                elif current_sign != streak_dir:
                    break

                streak_days += 1
                streak_total += change

            return {
                "fund": "GLD",
                "streak_days": streak_days,
                "streak_direction": streak_dir,
                "streak_total_tonnes": round(streak_total, 2),
                "last_date": str(rows[0].holding_date) if rows else None,
            }
    except Exception as exc:
        logger.exception("etf-momentum error: %s", exc)
        return {
            "fund": "GLD",
            "streak_days": 0,
            "streak_direction": None,
            "streak_total_tonnes": 0,
            "last_date": None,
        }


# ══════════════════════════════════════════════════════════════════════════
# 13. GET /cot-percentile — COT net position percentile rank
# ══════════════════════════════════════════════════════════════════════════

@router.get("/cot-percentile")
async def cot_percentile():
    """Calculate where current COT net position sits vs 1yr and 3yr history."""
    try:
        async with AsyncSessionLocal() as session:
            q = await session.execute(
                select(CotData)
                .where(CotData.asset == "gold")
                .order_by(desc(CotData.report_date))
            )
            rows = q.scalars().all()

            if not rows or rows[0].non_commercial_net is None:
                return {
                    "current_net": None,
                    "percentile_1yr": None,
                    "percentile_3yr": None,
                    "total_records": 0,
                    "latest_date": None,
                }

            current_net = rows[0].non_commercial_net
            latest_date = rows[0].report_date

            all_nets = [
                r.non_commercial_net for r in rows
                if r.non_commercial_net is not None
            ]

            today = date.today()
            yr1_nets = [
                r.non_commercial_net for r in rows
                if r.non_commercial_net is not None
                and r.report_date >= today - timedelta(days=365)
            ]
            yr3_nets = [
                r.non_commercial_net for r in rows
                if r.non_commercial_net is not None
                and r.report_date >= today - timedelta(days=365 * 3)
            ]

            def _percentile_rank(value: float, population: list[float], min_window: int = 10) -> float | None:
                if len(population) < min_window:
                    return None
                below = sum(1 for v in population if v < value)
                equal = sum(1 for v in population if v == value)
                return round((below + 0.5 * equal) / len(population) * 100, 1)

            p1 = _percentile_rank(current_net, yr1_nets)
            p3 = _percentile_rank(current_net, yr3_nets)

            return {
                "current_net": current_net,
                "percentile_1yr": p1,
                "percentile_3yr": p3,
                "window_used_1yr": len(yr1_nets),
                "window_used_3yr": len(yr3_nets),
                "min_required": 10,
                "crowding_warning": (
                    (p1 is not None and len(yr1_nets) >= 26 and (p1 > 90 or p1 < 10))
                    or (p3 is not None and len(yr3_nets) >= 26 and (p3 > 90 or p3 < 10))
                ),
                "total_records": len(all_nets),
                "latest_date": str(latest_date),
                "frequency": "weekly",
            }
    except Exception as exc:
        logger.exception("cot-percentile error: %s", exc)
        return {
            "current_net": None,
            "percentile_1yr": None,
            "percentile_3yr": None,
            "total_records": 0,
            "latest_date": None,
        }


# ══════════════════════════════════════════════════════════════════════════
# 14. GET /expert-consensus — article + video outlook aggregation
# ══════════════════════════════════════════════════════════════════════════

@router.get("/expert-consensus")
async def expert_consensus():
    """Aggregate gold outlook from published articles and videos over 7d and 30d."""
    try:
        from api.articles.models import GoldArticle
        from api.videos.models import CuratedVideo

        async with AsyncSessionLocal() as session:
            now = datetime.now(timezone.utc)
            d7 = now - timedelta(days=7)
            d30 = now - timedelta(days=30)

            # Articles (last 30 days, published only)
            art_q = await session.execute(
                select(GoldArticle)
                .where(
                    GoldArticle.is_published.is_(True),
                    GoldArticle.published_at >= d30,
                )
            )
            articles = art_q.scalars().all()

            # Videos (last 30 days, published only)
            vid_q = await session.execute(
                select(CuratedVideo)
                .where(
                    CuratedVideo.is_published.is_(True),
                    CuratedVideo.published_at >= d30,
                )
            )
            videos = vid_q.scalars().all()

            def _count_outlooks(items: list, since: datetime) -> dict:
                counts = {"bullish": 0, "bearish": 0, "neutral": 0, "mixed": 0, "total": 0}
                for item in items:
                    pub = item.published_at
                    if pub is None or pub < since:
                        continue
                    outlook = item.gold_outlook
                    if outlook in counts:
                        counts[outlook] += 1
                    counts["total"] += 1
                return counts

            all_items = list(articles) + list(videos)

            return {
                "period_7d": _count_outlooks(all_items, d7),
                "period_30d": _count_outlooks(all_items, d30),
            }
    except Exception as exc:
        logger.exception("expert-consensus error: %s", exc)
        return {
            "period_7d": {"bullish": 0, "bearish": 0, "neutral": 0, "mixed": 0, "total": 0},
            "period_30d": {"bullish": 0, "bearish": 0, "neutral": 0, "mixed": 0, "total": 0},
        }


# ══════════════════════════════════════════════════════════════════════════
# 15. GET /time-of-day — hourly and session gold price patterns
# ══════════════════════════════════════════════════════════════════════════

@router.get("/time-of-day")
async def time_of_day_analysis():
    """Analyze gold price patterns by weekday and estimate session ranges.

    Uses AssetPriceDaily(GC=F) daily OHLC data (not 5min candles).
    Session breakdowns are estimated from known gold market proportions:
    Asia ~20%, London ~40%, New York ~40% of daily range.
    """
    try:
        async with AsyncSessionLocal() as session:
            since = date.today() - timedelta(days=90)
            q = await session.execute(
                select(AssetPriceDaily)
                .where(
                    AssetPriceDaily.symbol == "GC=F",
                    AssetPriceDaily.trade_date >= since,
                )
                .order_by(AssetPriceDaily.trade_date)
            )
            rows = q.scalars().all()

            # Filter valid rows
            valid = [
                r for r in rows
                if r.open is not None and r.close is not None
                and r.high is not None and r.low is not None
                and r.open > 0
            ]

            if len(valid) < 20:
                return {"weekdays": [], "sessions": [], "data_days": len(valid)}

            # Group by weekday (0=Mon ... 4=Fri)
            DOW_NAMES_FA = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"]
            DOW_NAMES_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
            weekday_data: dict[int, dict] = {d: {"ranges": [], "returns": []} for d in range(5)}

            for r in valid:
                dow = r.trade_date.weekday()
                if dow > 4:
                    continue
                rng = r.high - r.low
                ret = (r.close / r.open - 1) * 100
                weekday_data[dow]["ranges"].append(rng)
                weekday_data[dow]["returns"].append(ret)

            weekdays_result = []
            for d in range(5):
                wd = weekday_data[d]
                n = len(wd["ranges"])
                weekdays_result.append({
                    "day": d,
                    "day_fa": DOW_NAMES_FA[d],
                    "day_en": DOW_NAMES_EN[d],
                    "avg_range_usd": round(sum(wd["ranges"]) / n, 2) if n > 0 else 0,
                    "avg_return_pct": round(sum(wd["returns"]) / n, 4) if n > 0 else 0,
                    "count": n,
                })

            # Overall average daily range
            all_ranges = [r.high - r.low for r in valid]
            all_returns = [(r.close / r.open - 1) * 100 for r in valid]
            daily_avg_range = sum(all_ranges) / len(all_ranges) if all_ranges else 0
            daily_avg_return = sum(all_returns) / len(all_returns) if all_returns else 0

            # Estimated session ranges using industry proportions
            # Gold market: Asia ~20%, London ~40%, NY ~40% of daily range
            sessions_result = [
                {
                    "name": "asia",
                    "name_fa": "آسیا",
                    "avg_range_usd": round(daily_avg_range * 0.20, 2),
                    "avg_return_pct": round(daily_avg_return * 0.15, 4),
                    "share_pct": 20,
                    "note": "تخمین از داده روزانه",
                },
                {
                    "name": "london",
                    "name_fa": "لندن",
                    "avg_range_usd": round(daily_avg_range * 0.40, 2),
                    "avg_return_pct": round(daily_avg_return * 0.45, 4),
                    "share_pct": 40,
                    "note": "تخمین از داده روزانه",
                },
                {
                    "name": "new_york",
                    "name_fa": "نیویورک",
                    "avg_range_usd": round(daily_avg_range * 0.40, 2),
                    "avg_return_pct": round(daily_avg_return * 0.40, 4),
                    "share_pct": 40,
                    "note": "تخمین از داده روزانه",
                },
            ]

            return {
                "weekdays": weekdays_result,
                "sessions": sessions_result,
                "daily_avg_range_usd": round(daily_avg_range, 2),
                "daily_avg_return_pct": round(daily_avg_return, 4),
                "data_days": len(valid),
                "note": "محاسبات از داده‌های روزانه GC=F. تفکیک جلسات تخمینی از نسبت‌های شناخته‌شده بازار طلا.",
            }
    except Exception as exc:
        logger.exception("time-of-day error: %s", exc)
        return {"weekdays": [], "sessions": [], "data_days": 0}


# ══════════════════════════════════════════════════════════════════════════
# 16. GET /momentum — macro momentum dashboard (6 fundamental drivers)
# ══════════════════════════════════════════════════════════════════════════


@router.get("/momentum")
async def momentum():
    """Macro momentum dashboard — 6 fundamental drivers + composite score.

    Uses the v2 momentum engine with rolling percentile/z-score normalization
    and confidence-based dynamic weighting.
    """
    try:
        from api.services.analysis.momentum_engine import compute_momentum

        async with AsyncSessionLocal() as session:
            return await compute_momentum(session)
    except Exception as exc:
        logger.exception("momentum error: %s", exc)
        return {
            "composite_score": None,
            "composite_direction": "pending",
            "composite_direction_fa": "در انتظار داده",
            "alignment": {
                "aligned": False,
                "bullish_count": 0,
                "bearish_count": 0,
                "neutral_count": 0,
                "divergence_warning": False,
                "divergence_note_fa": "",
            },
            "drivers": [],
            "technical_context": {
                "gold_rsi_14": None,
                "gold_rsi_zone": "unknown",
                "gold_daily_change_pct": None,
                "gold_5d_return_pct": None,
            },
        }


@router.get("/momentum/runs")
async def momentum_runs(limit: int = Query(50, ge=1, le=200)):
    """Admin: list recent momentum run logs for debugging."""
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("""
                    SELECT id, computed_at, as_of, raw_inputs, driver_scores,
                           weights, composite_score
                    FROM momentum_runs
                    ORDER BY computed_at DESC
                    LIMIT :limit
                """),
                {"limit": limit},
            )
            rows = result.mappings().all()
            return {
                "runs": [dict(r) for r in rows],
                "count": len(rows),
            }
    except Exception as exc:
        logger.debug("momentum runs error: %s", exc)
        return {"runs": [], "count": 0, "error": str(exc)}


# ══════════════════════════════════════════════════════════════════════════
# 17. GET /risk-radar — composite risk score from 6 components
# ══════════════════════════════════════════════════════════════════════════

@router.get("/risk-radar")
async def risk_radar():
    """Compute composite risk score from 6 components using the v2 engine.

    Returns backward-compatible response (composite_score, label, components,
    computed_at) plus new fields (components_detailed, meta, weights,
    confidences, warnings) that old frontends safely ignore.
    """
    try:
        from api.services.analysis.risk_radar_engine import compute_risk_radar

        async with AsyncSessionLocal() as session:
            return await compute_risk_radar(session)
    except Exception as exc:
        logger.exception("risk-radar error: %s", exc)
        return {
            "composite_score": None,
            "label": None,
            "components": [],
            "computed_at": datetime.now(timezone.utc).isoformat(),
        }


@router.get("/risk-radar/runs")
async def risk_radar_runs(limit: int = Query(50, ge=1, le=200)):
    """Admin: list recent risk radar run logs for debugging."""
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("""
                    SELECT id, computed_at, as_of, raw_inputs, component_scores,
                           weights, confidences, final_score, label, warnings
                    FROM risk_radar_runs
                    ORDER BY computed_at DESC
                    LIMIT :limit
                """),
                {"limit": limit},
            )
            rows = result.mappings().all()
            return {
                "runs": [dict(r) for r in rows],
                "count": len(rows),
            }
    except Exception as exc:
        logger.debug("risk-radar runs error: %s", exc)
        return {"runs": [], "count": 0, "error": str(exc)}


@router.post("/risk-radar/backtest")
async def risk_radar_backtest(start: str = Query("2020-01-01")):
    """Run historical backtest for the risk radar engine (admin, ~30-60s).

    Uses a 3-component proxy (VIX/GVZ, realized gold vol, gold-DXY corr)
    since full engine requires DB data (sentiment, COT, ETF).
    Compares risk scores against future 20-day realized gold volatility.
    """
    try:
        from api.analysis.scripts.backtest_risk_radar import run_backtest

        result = run_backtest(start=start)
        return result
    except Exception as exc:
        logger.exception("risk-radar backtest error: %s", exc)
        return {"error": str(exc)}


# ══════════════════════════════════════════════════════════════════════════
# 18. GET /correlation-by-regime — correlations grouped by macro regime
# ══════════════════════════════════════════════════════════════════════════

@router.get("/correlation-by-regime")
async def correlation_by_regime():
    """Group asset correlations by macro regime to show how relationships
    change across market regimes."""
    try:
        async with AsyncSessionLocal() as session:
            # Fetch all correlations
            corr_q = await session.execute(
                select(CorrelationCache).order_by(CorrelationCache.computed_date)
            )
            corr_rows = corr_q.scalars().all()

            # Fetch all regime scores
            regime_q = await session.execute(
                select(RegimeScore)
                .where(RegimeScore.chosen_regime.is_not(None))
                .order_by(RegimeScore.ts)
            )
            regime_rows = regime_q.scalars().all()

            if not corr_rows or not regime_rows:
                return {"regimes": []}

            # Build a date -> regime mapping
            regime_by_date: dict[date, str] = {}
            for r in regime_rows:
                regime_by_date[r.ts] = r.chosen_regime

            # For each correlation, find the closest regime date
            # Group: regime -> pair_b -> list of correlations
            regime_corrs: dict[str, dict[str, list[float]]] = {}

            for c in corr_rows:
                cd = c.computed_date
                # Find closest regime date (exact match or within 3 days)
                regime = regime_by_date.get(cd)
                if regime is None:
                    # Try nearby dates
                    for delta in range(1, 4):
                        regime = regime_by_date.get(cd - timedelta(days=delta))
                        if regime:
                            break
                        regime = regime_by_date.get(cd + timedelta(days=delta))
                        if regime:
                            break
                if regime is None:
                    continue

                if regime not in regime_corrs:
                    regime_corrs[regime] = {}
                regime_corrs[regime].setdefault(c.pair_b, []).append(c.correlation)

            # Build response
            regimes_result = []
            for regime_name, pairs_dict in regime_corrs.items():
                pairs_list = []
                for pair_b, values in pairs_dict.items():
                    label_info = SYMBOL_LABELS.get(pair_b, {"fa": pair_b})
                    pairs_list.append({
                        "pair_b": pair_b,
                        "label_fa": label_info["fa"],
                        "avg_correlation": round(sum(values) / len(values), 3),
                        "sample_count": len(values),
                    })
                regimes_result.append({
                    "regime": regime_name,
                    "pairs": pairs_list,
                })

            return {"regimes": regimes_result}
    except Exception as exc:
        logger.exception("correlation-by-regime error: %s", exc)
        return {"regimes": []}


# ══════════════════════════════════════════════════════════════════════════
# 19. GET /action-summary — bias, story, stance, triggers, range, levels
# ══════════════════════════════════════════════════════════════════════════

@router.get("/action-summary")
async def action_summary():
    """Compute actionable trading summary from existing DB data.

    Returns bias score, narrative story, stance suggestion, triggers,
    ATR-based expected range, and key support/resistance levels.
    """
    try:
        from api.data_collection.sentiment_calculator import compute_sentiment

        async with AsyncSessionLocal() as session:
            # 1. Sentiment composite → bias
            sent_result = await compute_sentiment(session)
            bias_score = sent_result.get("composite_score")
            components = sent_result.get("components", [])
            component_count = sent_result.get("component_count", 0)
            max_components = sent_result.get("max_components", 6)

            if bias_score is None:
                return {
                    "bias_score": None,
                    "bias_label_fa": "در انتظار داده",
                    "story_fa": None,
                    "stance_fa": None,
                    "triggers": [],
                    "confidence": "low",
                    "confidence_reasons": ["داده کافی نیست"],
                    "expected_range_1d_usd": None,
                    "expected_range_1d_pct": None,
                    "key_levels": None,
                }

            # Bias label
            if bias_score >= 70:
                bias_label = "صعودی قوی"
            elif bias_score >= 60:
                bias_label = "کمی صعودی"
            elif bias_score >= 40:
                bias_label = "خنثی"
            elif bias_score >= 30:
                bias_label = "کمی نزولی"
            else:
                bias_label = "نزولی قوی"

            # 2. Build story from momentum drivers
            bullish_drivers = []
            bearish_drivers = []
            for comp in components:
                score = comp.get("score", 50)
                label = comp.get("label_fa", "")
                if score > 60:
                    bullish_drivers.append(label)
                elif score < 40:
                    bearish_drivers.append(label)

            parts = []
            if bullish_drivers:
                parts.append(f"حمایت: {' + '.join(bullish_drivers[:2])}")
            if bearish_drivers:
                parts.append(f"مقاومت: {' + '.join(bearish_drivers[:1])}")
            story = " | ".join(parts) if parts else "عوامل بنیادی متعادل"

            # 3. Stance from bias×confidence
            stale_count = sum(1 for c in components if c.get("stale"))
            fresh_count = component_count - stale_count

            if fresh_count >= 4 and component_count >= 4:
                confidence = "high"
            elif fresh_count >= 2:
                confidence = "medium"
            else:
                confidence = "low"

            confidence_reasons = []
            if fresh_count > 0:
                confidence_reasons.append(f"{fresh_count} جزء تازه")
            if stale_count > 0:
                confidence_reasons.append(f"{stale_count} جزء قدیمی")

            # Map bias + confidence → stance
            if confidence == "low":
                stance = "صبر — داده کافی نیست"
            elif bias_score >= 65:
                stance = "لانگ روی پولبک / عدم تعقیب شکست"
            elif bias_score >= 55:
                stance = "لانگ با حد ضرر تنگ"
            elif bias_score <= 35:
                stance = "شورت روی رالی / عدم خرید"
            elif bias_score <= 45:
                stance = "شورت با حد ضرر تنگ"
            else:
                stance = "بدون موقعیت / معامله محدوده‌ای"

            # 4. ATR(14) from GC=F daily
            gold_q = await session.execute(
                select(AssetPriceDaily)
                .where(AssetPriceDaily.symbol == "GC=F")
                .order_by(desc(AssetPriceDaily.trade_date))
                .limit(20)
            )
            gold_rows = gold_q.scalars().all()

            atr_usd = None
            atr_pct = None
            key_levels = None

            if len(gold_rows) >= 14:
                # Calculate ATR(14)
                trs = []
                rows_asc = list(reversed(gold_rows))
                for i in range(1, min(15, len(rows_asc))):
                    r = rows_asc[i]
                    prev_c = rows_asc[i - 1].close
                    if r.high and r.low and prev_c:
                        tr = max(r.high - r.low, abs(r.high - prev_c), abs(r.low - prev_c))
                        trs.append(tr)
                if trs:
                    atr_usd = round(sum(trs) / len(trs), 2)
                    current_price = gold_rows[0].close
                    if current_price and current_price > 0:
                        atr_pct = round(atr_usd / current_price * 100, 2)

                        # Key levels from recent swing high/low + ATR bands
                        recent_30 = gold_rows[:min(30, len(gold_rows))]
                        highs = [r.high for r in recent_30 if r.high]
                        lows = [r.low for r in recent_30 if r.low]

                        if highs and lows:
                            recent_high = max(highs)
                            recent_low = min(lows)
                            key_levels = {
                                "supports": sorted([
                                    round(recent_low, 0),
                                    round(current_price - atr_usd, 0),
                                    round(current_price - 2 * atr_usd, 0),
                                ], reverse=True),
                                "resistances": sorted([
                                    round(recent_high, 0),
                                    round(current_price + atr_usd, 0),
                                    round(current_price + 2 * atr_usd, 0),
                                ]),
                                "invalidation": round(current_price - 3 * atr_usd, 0),
                            }

            # 5. Triggers
            triggers = []

            # Check upcoming economic events
            upcoming_q = await session.execute(
                select(EconomicEvent)
                .where(
                    EconomicEvent.datetime_utc > datetime.now(timezone.utc),
                    EconomicEvent.datetime_utc < datetime.now(timezone.utc) + timedelta(days=7),
                    EconomicEvent.impact == "high",
                )
                .order_by(EconomicEvent.datetime_utc)
                .limit(2)
            )
            for ev in upcoming_q.scalars().all():
                dt_str = ev.datetime_utc.strftime("%d %b") if ev.datetime_utc else ""
                triggers.append({
                    "label_fa": f"{ev.event_name_fa or ev.event_name} ({dt_str})",
                    "type": "event",
                })

            # Key level triggers
            if key_levels and gold_rows:
                current = gold_rows[0].close
                if current and key_levels["resistances"]:
                    nearest_res = min(key_levels["resistances"], key=lambda x: abs(x - current))
                    triggers.append({
                        "label_fa": f"شکست مقاومت ${nearest_res:.0f}",
                        "type": "level",
                    })

            # Regime trigger
            regime_q = await session.execute(
                select(RegimeScore).order_by(desc(RegimeScore.ts)).limit(1)
            )
            regime_row = regime_q.scalar_one_or_none()
            if regime_row and regime_row.chosen_regime:
                regime_labels = {
                    "tightening": "انقباضی", "expansion": "انبساطی",
                    "stress": "بحرانی", "recovery": "بازیابی",
                }
                triggers.append({
                    "label_fa": f"تغییر رژیم از {regime_labels.get(regime_row.chosen_regime, regime_row.chosen_regime)}",
                    "type": "regime",
                })

            return {
                "bias_score": round(bias_score),
                "bias_label_fa": bias_label,
                "story_fa": story,
                "stance_fa": stance,
                "triggers": triggers[:3],
                "confidence": confidence,
                "confidence_reasons": confidence_reasons,
                "expected_range_1d_usd": atr_usd,
                "expected_range_1d_pct": atr_pct,
                "key_levels": key_levels,
            }
    except Exception as exc:
        logger.exception("action-summary error: %s", exc)
        return {
            "bias_score": None,
            "bias_label_fa": "خطا",
            "story_fa": None,
            "stance_fa": None,
            "triggers": [],
            "confidence": "low",
            "confidence_reasons": [],
            "expected_range_1d_usd": None,
            "expected_range_1d_pct": None,
            "key_levels": None,
        }


# ══════════════════════════════════════════════════════════════════════════
# 20. GET /deltas — 1d and 5d changes for key metrics
# ══════════════════════════════════════════════════════════════════════════

@router.get("/deltas")
async def deltas():
    """Compute 1-day and 5-day deltas for key metrics using existing DB data."""
    try:
        async with AsyncSessionLocal() as session:
            result_deltas = []
            now = datetime.now(timezone.utc)

            # ── Sentiment delta ──
            sent_q = await session.execute(
                select(SentimentTimeline)
                .where(SentimentTimeline.composite_score.is_not(None))
                .order_by(desc(SentimentTimeline.recorded_at))
                .limit(1500)  # ~5 days of 5min records
            )
            sent_rows = sent_q.scalars().all()
            if sent_rows:
                current_sent = sent_rows[0].composite_score
                # Find ~1d ago (288 5min periods)
                prev_1d = None
                prev_5d = None
                for r in sent_rows:
                    age = (now - r.recorded_at).total_seconds() / 3600
                    if prev_1d is None and age >= 23:
                        prev_1d = r.composite_score
                    if prev_5d is None and age >= 119:
                        prev_5d = r.composite_score
                if current_sent is not None:
                    result_deltas.append({
                        "id": "sentiment",
                        "label_fa": "شاخص احساسات",
                        "current": round(current_sent, 1),
                        "prev_1d": round(prev_1d, 1) if prev_1d is not None else None,
                        "prev_5d": round(prev_5d, 1) if prev_5d is not None else None,
                        "change_1d": round(current_sent - prev_1d, 1) if prev_1d is not None else None,
                        "change_5d": round(current_sent - prev_5d, 1) if prev_5d is not None else None,
                        "unit": "score",
                        "direction": "up" if prev_1d and current_sent > prev_1d else "down" if prev_1d and current_sent < prev_1d else "flat",
                        "gold_impact": "bullish" if current_sent and current_sent > 55 else "bearish" if current_sent and current_sent < 45 else "neutral",
                    })

            # Helper for asset price deltas
            async def _price_delta(symbol: str, label_fa: str, unit: str, gold_impact_fn=None):
                pq = await session.execute(
                    select(AssetPriceDaily)
                    .where(AssetPriceDaily.symbol == symbol)
                    .order_by(desc(AssetPriceDaily.trade_date))
                    .limit(10)
                )
                rows = pq.scalars().all()
                if not rows or rows[0].close is None:
                    return
                current = rows[0].close
                prev_1d = rows[1].close if len(rows) > 1 and rows[1].close else None
                prev_5d = rows[min(5, len(rows) - 1)].close if len(rows) > 5 else (rows[-1].close if len(rows) > 1 else None)
                c1d = round(current - prev_1d, 4) if prev_1d is not None else None
                c5d = round(current - prev_5d, 4) if prev_5d is not None else None
                direction = "up" if c1d and c1d > 0 else "down" if c1d and c1d < 0 else "flat"
                gi = gold_impact_fn(c1d) if gold_impact_fn and c1d is not None else "neutral"
                result_deltas.append({
                    "id": symbol.replace("=", "_").replace("^", "").replace("-", "_").lower(),
                    "label_fa": label_fa,
                    "current": round(current, 2),
                    "prev_1d": round(prev_1d, 2) if prev_1d is not None else None,
                    "prev_5d": round(prev_5d, 2) if prev_5d is not None else None,
                    "change_1d": round(c1d, 2) if c1d is not None else None,
                    "change_5d": round(c5d, 2) if c5d is not None else None,
                    "unit": unit,
                    "direction": direction,
                    "gold_impact": gi,
                })

            # DFII10
            dfii_q = await session.execute(
                select(MacroIndicator)
                .where(MacroIndicator.series_id == "DFII10")
                .order_by(desc(MacroIndicator.observation_date))
                .limit(10)
            )
            dfii_rows = dfii_q.scalars().all()
            if dfii_rows and dfii_rows[0].value is not None:
                current = dfii_rows[0].value
                p1 = dfii_rows[1].value if len(dfii_rows) > 1 else None
                p5 = dfii_rows[min(5, len(dfii_rows) - 1)].value if len(dfii_rows) > 5 else (dfii_rows[-1].value if len(dfii_rows) > 1 else None)
                c1 = round(current - p1, 4) if p1 is not None else None
                c5 = round(current - p5, 4) if p5 is not None else None
                result_deltas.append({
                    "id": "dfii10",
                    "label_fa": "نرخ بهره واقعی",
                    "current": round(current, 2),
                    "prev_1d": round(p1, 2) if p1 is not None else None,
                    "prev_5d": round(p5, 2) if p5 is not None else None,
                    "change_1d": round(c1, 2) if c1 is not None else None,
                    "change_5d": round(c5, 2) if c5 is not None else None,
                    "unit": "%",
                    "direction": "up" if c1 and c1 > 0 else "down" if c1 and c1 < 0 else "flat",
                    "gold_impact": "bullish" if c1 and c1 < 0 else "bearish" if c1 and c1 > 0 else "neutral",
                })

            # DXY
            await _price_delta("DX-Y.NYB", "شاخص دلار (DXY)", "index",
                               lambda c: "bullish" if c < 0 else "bearish" if c > 0 else "neutral")

            # VIX
            await _price_delta("^VIX", "شاخص ترس (VIX)", "index",
                               lambda c: "bullish" if c > 0 else "bearish" if c < 0 else "neutral")

            # Gold price
            await _price_delta("GC=F", "قیمت طلا", "$",
                               lambda c: "bullish" if c > 0 else "bearish" if c < 0 else "neutral")

            # GLD holdings
            gld_q = await session.execute(
                select(EtfHolding)
                .where(EtfHolding.fund == "GLD")
                .order_by(desc(EtfHolding.holding_date))
                .limit(10)
            )
            gld_rows = gld_q.scalars().all()
            if gld_rows and gld_rows[0].total_tonnes is not None:
                current = gld_rows[0].total_tonnes
                p1 = gld_rows[1].total_tonnes if len(gld_rows) > 1 else None
                p5 = gld_rows[min(5, len(gld_rows) - 1)].total_tonnes if len(gld_rows) > 5 else (gld_rows[-1].total_tonnes if len(gld_rows) > 1 else None)
                c1 = round(current - p1, 2) if p1 is not None else None
                c5 = round(current - p5, 2) if p5 is not None else None
                result_deltas.append({
                    "id": "gld_holdings",
                    "label_fa": "موجودی GLD (تن)",
                    "current": round(current, 1),
                    "prev_1d": round(p1, 1) if p1 is not None else None,
                    "prev_5d": round(p5, 1) if p5 is not None else None,
                    "change_1d": round(c1, 2) if c1 is not None else None,
                    "change_5d": round(c5, 2) if c5 is not None else None,
                    "unit": "tonnes",
                    "direction": "up" if c1 and c1 > 0 else "down" if c1 and c1 < 0 else "flat",
                    "gold_impact": "bullish" if c1 and c1 > 0 else "bearish" if c1 and c1 < 0 else "neutral",
                })

            # COT net
            cot_q = await session.execute(
                select(CotData)
                .where(CotData.asset == "gold")
                .order_by(desc(CotData.report_date))
                .limit(5)
            )
            cot_rows = cot_q.scalars().all()
            if cot_rows and cot_rows[0].non_commercial_net is not None:
                current = cot_rows[0].non_commercial_net
                p1 = cot_rows[1].non_commercial_net if len(cot_rows) > 1 and cot_rows[1].non_commercial_net is not None else None
                c1 = current - p1 if p1 is not None else None
                result_deltas.append({
                    "id": "cot_net",
                    "label_fa": "موقعیت خالص COT",
                    "current": current,
                    "prev_1d": p1,
                    "prev_5d": None,
                    "change_1d": c1,
                    "change_5d": None,
                    "unit": "contracts",
                    "direction": "up" if c1 and c1 > 0 else "down" if c1 and c1 < 0 else "flat",
                    "gold_impact": "bullish" if c1 and c1 > 0 else "bearish" if c1 and c1 < 0 else "neutral",
                })

            return {
                "deltas": result_deltas,
                "computed_at": now.isoformat(),
            }
    except Exception as exc:
        logger.exception("deltas error: %s", exc)
        return {"deltas": [], "computed_at": datetime.now(timezone.utc).isoformat()}


# ══════════════════════════════════════════════════════════════════════════
# 21. GET /live/snapshot — complete market snapshot for Data Copilot
# ══════════════════════════════════════════════════════════════════════════

@router.get("/live/snapshot")
async def live_snapshot(asset: str = Query("XAUUSD")):
    """Complete market snapshot with all registered metrics + computed scores."""
    from api.copilot.snapshot import build_live_snapshot
    from api.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        return await build_live_snapshot(session, asset)
