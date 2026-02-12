"""Fundamental analysis API — macro overview, money flow, real rates,
correlations, sentiment gauge, Shanghai premium, market activity.

All endpoints return graceful empty/pending responses when no data exists.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Query
from sqlalchemy import desc, func, select, text

from api.database import AsyncSessionLocal
from api.analysis.models import (
    AssetPriceDaily,
    CorrelationCache,
    CotData,
    EtfHolding,
    MacroIndicator,
    MarketEventAnalysis,
)

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
    "FEDFUNDS": {"en": "Fed Funds Rate", "fa": "نرخ بهره فدرال"},
    "CPIAUCSL": {"en": "CPI (All Urban)", "fa": "شاخص تورم مصرف‌کننده"},
    "DFII10": {"en": "10Y Real Rate (TIPS)", "fa": "نرخ بهره واقعی ۱۰ ساله"},
    "DGS10": {"en": "10Y Treasury Yield", "fa": "بازده ۱۰ ساله خزانه‌داری"},
    "T10YIE": {"en": "10Y Breakeven Inflation", "fa": "انتظارات تورمی ۱۰ ساله"},
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
            data = {}
            if gld_latest:
                data["gld_tonnes"] = gld_latest.total_tonnes
                data["gld_change"] = gld_latest.change_tonnes
            if cot_latest:
                data["cot_net"] = cot_latest.non_commercial_net
                data["cot_change"] = cot_latest.change_non_commercial_net
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
                "data": {"real_rate": real_rate.value, "date": str(real_rate.observation_date)},
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
                "data": {"dxy": dxy_latest.close, "change": change, "date": str(dxy_latest.trade_date)},
            }

        def _risk_card():
            if not vix_latest:
                return {"id": "risk", "title_fa": "ریسک بازار", "status": "pending", "data": None}
            impact = "bullish" if vix_latest.close > 25 else "bearish" if vix_latest.close < 15 else "neutral"
            return {
                "id": "risk", "title_fa": "ریسک بازار", "status": "ready",
                "impact": impact,
                "data": {"vix": vix_latest.close, "date": str(vix_latest.trade_date)},
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
            }
            for r in cot_rows
        ]

        return {
            "etf_holdings": etf_by_fund,
            "cot_positions": cot_history,
            "period_days": days,
        }


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
        for series_id, label_info in FRED_LABELS.items():
            latest = latest_by_series.get(series_id)
            indicators.append({
                "series_id": series_id,
                "label_en": label_info["en"],
                "label_fa": label_info["fa"],
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
                "impact": impact,
                "window_days": row.window_days,
            })

        return {"pairs": pairs, "computed_date": str(latest_date)}


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
