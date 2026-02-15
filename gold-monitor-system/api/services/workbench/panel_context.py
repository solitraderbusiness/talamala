"""Panel context builder — fetches live data from active panels
and formats as concise text for the system prompt."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def build_panel_context(
    active_panels: list[str],
    db: AsyncSession,
) -> str:
    """Build a text summary of active panel data for LLM context.

    Each panel produces ~200 words. Total capped at ~2000 tokens.
    """
    if not active_panels:
        return ""

    sections: list[str] = []

    for panel_id in active_panels[:5]:  # Cap at 5 panels
        try:
            text = await _fetch_panel(panel_id, db)
            if text:
                sections.append(text)
        except Exception as e:
            logger.warning("Panel context error for %s: %s", panel_id, e)

    if not sections:
        return ""

    return (
        "\n\n## Active Analysis Panels (live data)\n"
        + "\n\n".join(sections)
    )


async def _fetch_panel(panel_id: str, db: AsyncSession) -> str | None:
    fetchers = {
        "macro_overview": _panel_macro,
        "sentiment_gauge": _panel_sentiment,
        "regime_monitor": _panel_regime,
        "correlation_matrix": _panel_correlations,
        "money_flow": _panel_money_flow,
        "real_rates": _panel_real_rates,
        "market_activity": _panel_market_activity,
    }
    fetcher = fetchers.get(panel_id)
    if not fetcher:
        return None
    return await fetcher(db)


async def _panel_macro(db: AsyncSession) -> str:
    from api.routers.analysis import macro_overview
    data = await macro_overview()
    cards = data.get("cards", [])
    lines = ["### Macro Overview"]
    for c in cards:
        status = c.get("status", "pending")
        if status == "pending":
            lines.append(f"- {c['title_fa']}: در انتظار داده")
        else:
            impact = c.get("impact", "neutral")
            d = c.get("data", {}) or {}
            vals = ", ".join(f"{k}: {v}" for k, v in d.items() if v is not None)
            lines.append(f"- {c['title_fa']}: {impact} ({vals})")
    return "\n".join(lines)


async def _panel_sentiment(db: AsyncSession) -> str:
    from api.data_collection.sentiment_calculator import compute_sentiment
    data = await compute_sentiment(db)
    score = data.get("composite_score")
    label = data.get("label_fa", "")
    components = data.get("components", [])
    lines = [f"### Sentiment Gauge: {score}/100 ({label})"]
    for c in components:
        lines.append(f"- {c['label_fa']}: {c['score']}")
    return "\n".join(lines)


async def _panel_regime(db: AsyncSession) -> str:
    from sqlalchemy import select, desc
    from api.analysis.models import RegimeScore
    q = await db.execute(select(RegimeScore).order_by(desc(RegimeScore.ts)).limit(1))
    row = q.scalar_one_or_none()
    if not row:
        return "### Regime Monitor: در انتظار داده"
    probs = {
        "expansion": row.smoothed_p_expansion or row.p_expansion or 0,
        "tightening": row.smoothed_p_tightening or row.p_tightening or 0,
        "stress": row.smoothed_p_stress or row.p_stress or 0,
        "recovery": row.smoothed_p_recovery or row.p_recovery or 0,
    }
    prob_str = ", ".join(f"{k}: {v:.1%}" for k, v in probs.items())
    return f"### Regime Monitor: {row.chosen_regime} (as of {row.ts})\nProbabilities: {prob_str}"


async def _panel_correlations(db: AsyncSession) -> str:
    from api.routers.analysis import correlations
    data = await correlations()
    pairs = data.get("pairs", [])
    if not pairs:
        return "### Correlations: در انتظار داده"
    lines = [f"### Correlations (30d, as of {data.get('computed_date', '?')})"]
    for p in pairs:
        lines.append(f"- Gold vs {p['label_fa']}: {p['correlation']}")
    return "\n".join(lines)


async def _panel_money_flow(db: AsyncSession) -> str:
    from api.routers.analysis import money_flow
    data = await money_flow(days=30)
    etf = data.get("etf_holdings", {})
    cot = data.get("cot_positions", [])
    lines = ["### Money Flow (30d)"]
    for fund, entries in etf.items():
        if entries:
            latest = entries[-1]
            lines.append(f"- {fund}: {latest.get('total_tonnes')} tonnes (change: {latest.get('change_tonnes')})")
    if cot:
        latest_cot = cot[-1]
        lines.append(f"- COT net: {latest_cot.get('non_commercial_net')} (change: {latest_cot.get('change')})")
    return "\n".join(lines)


async def _panel_real_rates(db: AsyncSession) -> str:
    from api.routers.analysis import real_rates
    data = await real_rates(days=30)
    indicators = data.get("indicators", [])
    lines = ["### Real Rates (FRED)"]
    for ind in indicators:
        val = ind.get("latest_value")
        if val is not None:
            lines.append(f"- {ind['label_fa']}: {val}{ind.get('unit', '')}")
    return "\n".join(lines)


async def _panel_market_activity(db: AsyncSession) -> str:
    from api.routers.analysis import market_activity
    data = await market_activity(hours=24)
    events = data.get("events", [])[:5]
    lines = [f"### Market Activity (last 24h, {data.get('total', 0)} events)"]
    for e in events:
        lines.append(f"- [{e.get('impact')}] {e.get('title_fa') or e.get('title')}")
    return "\n".join(lines)
