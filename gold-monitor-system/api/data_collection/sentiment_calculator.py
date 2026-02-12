"""Reusable sentiment gauge computation.

Extracted from ``api/routers/analysis.py`` so it can be called by both the
``/sentiment-gauge`` endpoint and by snapshot/timeline workers.
"""

from __future__ import annotations

import logging

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.analysis.models import (
    AssetPriceDaily,
    CotData,
    EtfHolding,
    MacroIndicator,
)

logger = logging.getLogger("gold_monitor.sentiment_calc")


async def compute_sentiment(session: AsyncSession) -> dict:
    """Compute composite 0-100 sentiment score from 6 components.

    Returns::

        {
            "composite_score": int | None,
            "direction": str,          # very_bullish / bullish / neutral / bearish / very_bearish / pending
            "label_fa": str,
            "components": [
                {"name": str, "label_fa": str, "score": int, "weight": int},
                ...
            ],
            "component_count": int,
            "max_components": 6,
        }
    """
    components: list[dict] = []
    total_score = 0.0
    total_weight = 0

    # 1. ETF flow component (weight 20)
    etf_q = await session.execute(
        select(EtfHolding)
        .where(EtfHolding.fund == "GLD")
        .order_by(desc(EtfHolding.holding_date))
        .limit(5)
    )
    etf_rows = etf_q.scalars().all()
    if etf_rows:
        avg_change = sum(r.change_tonnes or 0 for r in etf_rows) / len(etf_rows)
        etf_score = max(0, min(100, 50 + avg_change * 10))
        components.append({
            "name": "etf_flows", "label_fa": "جریان ETF",
            "score": round(etf_score), "weight": 20,
        })
        total_score += etf_score * 20
        total_weight += 20

    # 2. COT positioning (weight 20)
    cot_q = await session.execute(
        select(CotData).where(CotData.asset == "gold")
        .order_by(desc(CotData.report_date)).limit(1)
    )
    cot = cot_q.scalar_one_or_none()
    if cot and cot.non_commercial_net is not None:
        cot_score = max(0, min(100, (cot.non_commercial_net / 200000) * 50 + 50))
        components.append({
            "name": "cot_positioning", "label_fa": "موقعیت COT",
            "score": round(cot_score), "weight": 20,
        })
        total_score += cot_score * 20
        total_weight += 20

    # 3. Real rates (weight 20) — lower real rates = bullish gold
    rr_q = await session.execute(
        select(MacroIndicator).where(MacroIndicator.series_id == "DFII10")
        .order_by(desc(MacroIndicator.observation_date)).limit(1)
    )
    rr = rr_q.scalar_one_or_none()
    if rr:
        rr_score = max(0, min(100, 60 - rr.value * 20))
        components.append({
            "name": "real_rates", "label_fa": "نرخ بهره واقعی",
            "score": round(rr_score), "weight": 20,
        })
        total_score += rr_score * 20
        total_weight += 20

    # 4. Dollar strength (weight 15) — strong dollar = bearish gold
    dxy_q = await session.execute(
        select(AssetPriceDaily).where(AssetPriceDaily.symbol == "DX-Y.NYB")
        .order_by(desc(AssetPriceDaily.trade_date)).limit(5)
    )
    dxy_rows = dxy_q.scalars().all()
    if len(dxy_rows) >= 2:
        dxy_change = dxy_rows[0].close - dxy_rows[-1].close
        dxy_score = max(0, min(100, 50 - dxy_change * 25))
        components.append({
            "name": "dollar_strength", "label_fa": "قدرت دلار",
            "score": round(dxy_score), "weight": 15,
        })
        total_score += dxy_score * 15
        total_weight += 15

    # 5. VIX / Risk sentiment (weight 15) — high VIX = bullish gold
    vix_q = await session.execute(
        select(AssetPriceDaily).where(AssetPriceDaily.symbol == "^VIX")
        .order_by(desc(AssetPriceDaily.trade_date)).limit(1)
    )
    vix = vix_q.scalar_one_or_none()
    if vix:
        vix_score = max(0, min(100, (vix.close - 10) / 30 * 100))
        components.append({
            "name": "risk_sentiment", "label_fa": "ریسک بازار",
            "score": round(vix_score), "weight": 15,
        })
        total_score += vix_score * 15
        total_weight += 15

    # 6. Price momentum (weight 10) — gold price trend
    gold_q = await session.execute(
        select(AssetPriceDaily).where(AssetPriceDaily.symbol == "GC=F")
        .order_by(desc(AssetPriceDaily.trade_date)).limit(10)
    )
    gold_rows = gold_q.scalars().all()
    if len(gold_rows) >= 2:
        pct_change = (gold_rows[0].close - gold_rows[-1].close) / gold_rows[-1].close * 100
        momentum_score = max(0, min(100, 50 + pct_change * 10))
        components.append({
            "name": "price_momentum", "label_fa": "شتاب قیمت",
            "score": round(momentum_score), "weight": 10,
        })
        total_score += momentum_score * 10
        total_weight += 10

    # Composite score
    composite = round(total_score / total_weight) if total_weight > 0 else None

    # Determine label
    if composite is None:
        direction = "pending"
        label_fa = "در انتظار داده"
    elif composite >= 70:
        direction = "very_bullish"
        label_fa = "بسیار صعودی"
    elif composite >= 55:
        direction = "bullish"
        label_fa = "صعودی"
    elif composite >= 45:
        direction = "neutral"
        label_fa = "خنثی"
    elif composite >= 30:
        direction = "bearish"
        label_fa = "نزولی"
    else:
        direction = "very_bearish"
        label_fa = "بسیار نزولی"

    return {
        "composite_score": composite,
        "label": direction,
        "label_fa": label_fa,
        "components": components,
        "component_count": len(components),
        "max_components": 6,
    }
