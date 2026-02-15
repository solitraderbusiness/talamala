"""Sentiment gauge computation — percentile-based scoring.

Each of the 6 components converts a raw financial metric into a 0-100 score
using its rolling historical distribution (2-year window for daily, 5-year for
weekly COT).  The pipeline is:

    raw value → winsorize(p1,p99) → EMA(3) smooth → percentile → direction → neutral band → score

Scores:  50 = neutral,  >50 = bullish for gold,  <50 = bearish for gold.

Component weights (DO NOT CHANGE):
    ETF Flows 20%  |  COT 20%  |  Real Rates 20%  |  Dollar 15%  |  Risk 15%  |  Momentum 10%
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.analysis.models import (
    AssetPriceDaily,
    CotData,
    EtfHolding,
    MacroIndicator,
)
from api.data_collection.percentile_scorer import (
    ScoreResult,
    rolling_average,
    rolling_change,
    rolling_pct_return,
    score_percentile,
)

logger = logging.getLogger("gold_monitor.sentiment_calc")

# ── Component config ───────────────────────────────────────────────────
# Weights, labels, scoring parameters.  Raw inputs and transforms are
# documented inline; no magic numbers.

COMPONENT_CONFIG = {
    "etf_flows": {
        "weight": 20,
        "label_fa": "جریان ETF",
        "direction": "bullish_when_higher",      # inflows → bullish
        "raw_transform": "5-day average of daily GLD change_tonnes",
        "raw_units": "tonnes/day",
        "data_source_id": "etf_holdings.GLD.change_tonnes",
        "window_years": 2,
        "smooth": True,
        "staleness_days": 4,                      # weekend + 2 business days
    },
    "cot_positioning": {
        "weight": 20,
        "label_fa": "موقعیت COT",
        "direction": "bullish_when_higher",      # net long → bullish
        "raw_transform": "non_commercial_net (longs - shorts)",
        "raw_units": "contracts",
        "data_source_id": "cot_data.gold.non_commercial_net",
        "window_years": 5,                       # weekly data, 5-year window
        "smooth": False,                         # weekly data, no smoothing
        "staleness_days": 10,
    },
    "real_rates": {
        "weight": 20,
        "label_fa": "نرخ بهره واقعی",
        "direction": "inverse",                  # higher rates → bearish
        "raw_transform": "DFII10 latest observation",
        "raw_units": "%",
        "data_source_id": "macro_indicators.DFII10.value",
        "window_years": 2,
        "smooth": True,
        "staleness_days": 30,                    # FRED is slow
    },
    "dollar_strength": {
        "weight": 15,
        "label_fa": "قدرت دلار",
        "direction": "inverse",                  # strong dollar → bearish
        "raw_transform": "5-day DXY close change",
        "raw_units": "index points",
        "data_source_id": "asset_prices_daily.DX-Y.NYB.close",
        "window_years": 2,
        "smooth": True,
        "staleness_days": 4,
    },
    "risk_sentiment": {
        "weight": 15,
        "label_fa": "ریسک بازار",
        "direction": "bullish_when_higher",      # high VIX → gold safe-haven
        "raw_transform": "VIX close level",
        "raw_units": "index",
        "data_source_id": "asset_prices_daily.^VIX.close",
        "window_years": 2,
        "smooth": True,
        "staleness_days": 4,
    },
    "price_momentum": {
        "weight": 10,
        "label_fa": "شتاب قیمت",
        "direction": "bullish_when_higher",      # positive momentum → bullish
        "raw_transform": "10-day gold (GC=F) percentage return",
        "raw_units": "%",
        "data_source_id": "asset_prices_daily.GC=F.close",
        "window_years": 2,
        "smooth": True,
        "staleness_days": 4,
    },
}


# ── Explanation builders (Persian) ──────────────────────────────────────

def _explain(
    description_fa: str,
    raw_label: str,
    raw_value_str: str,
    pct: float,
    window_years: int,
    score_labels: tuple[str, str, str],
    crowded: bool = False,
) -> str:
    """Build a rich Persian explanation string for a component.

    ``score_labels`` = (label_0, label_50, label_100).
    """
    lines = [
        description_fa,
        f"مقدار فعلی: {raw_value_str}",
        f"درصدک {round(pct * 100)}% در {window_years} سال اخیر",
        f"۰={score_labels[0]}، ۵۰={score_labels[1]}، ۱۰۰={score_labels[2]}",
    ]
    if crowded:
        lines.append("⚠️ هشدار: موقعیت‌ها نزدیک محدوده‌های افراطی هستند (احتمال اشباع)")
    return "\n".join(lines)


# ── Data fetch + scoring per component ──────────────────────────────────

async def _score_etf(session: AsyncSession, now: datetime) -> dict | None:
    """ETF Flows — 5-day average of GLD daily change_tonnes."""
    cfg = COMPONENT_CONFIG["etf_flows"]
    cutoff = now - timedelta(days=cfg["window_years"] * 365 + 30)

    rows = (
        await session.execute(
            select(EtfHolding.holding_date, EtfHolding.change_tonnes)
            .where(EtfHolding.fund == "GLD")
            .where(EtfHolding.holding_date >= cutoff.date())
            .order_by(EtfHolding.holding_date)
        )
    ).all()

    if len(rows) < 10:
        return None

    # Build daily change series (chronological, oldest first)
    changes = [float(r.change_tonnes or 0) for r in rows]
    dates = [r.holding_date for r in rows]

    # Compute rolling 5-day average
    avg_series = rolling_average(changes, 5)
    if not avg_series:
        return None

    current_val = avg_series[-1]
    hist_vals = avg_series[:-1]

    # Staleness check
    latest_date = dates[-1]
    stale = (now.date() - latest_date).days > cfg["staleness_days"]

    result = score_percentile(
        current_val, hist_vals,
        direction=cfg["direction"],
        smooth=cfg["smooth"],
    )

    explanation = _explain(
        "جریان ورودی/خروجی سرمایه نهادی به صندوق GLD.",
        "میانگین ۵ روز", f"{current_val:+.2f} تن/روز",
        result.percentile, cfg["window_years"],
        ("خروج شدید", "خنثی", "ورود قوی"),
        result.crowded,
    )

    return _build_component(
        "etf_flows", cfg, result, explanation,
        stale=stale,
        fetched_at=str(latest_date),
        window_start=str(dates[0]) if dates else None,
        window_end=str(latest_date),
    )


async def _score_cot(session: AsyncSession, now: datetime) -> dict | None:
    """COT Positioning — net non-commercial (speculator) position."""
    cfg = COMPONENT_CONFIG["cot_positioning"]
    cutoff = now - timedelta(days=cfg["window_years"] * 365 + 30)

    rows = (
        await session.execute(
            select(CotData.report_date, CotData.non_commercial_net)
            .where(CotData.asset == "gold")
            .where(CotData.non_commercial_net.isnot(None))
            .where(CotData.report_date >= cutoff.date())
            .order_by(CotData.report_date)
        )
    ).all()

    if not rows:
        return None

    values = [float(r.non_commercial_net) for r in rows]
    dates = [r.report_date for r in rows]
    current_val = values[-1]
    hist_vals = values[:-1] if len(values) > 1 else values

    stale = (now.date() - dates[-1]).days > cfg["staleness_days"]

    result = score_percentile(
        current_val, hist_vals,
        direction=cfg["direction"],
        smooth=False,  # weekly data — no EMA
    )

    explanation = _explain(
        "موقعیت خالص سفته‌بازان بزرگ در بازار آتی طلا (CFTC COT).",
        "موقعیت خالص", f"{current_val:,.0f} قرارداد",
        result.percentile, cfg["window_years"],
        ("فروش خالص بالا", "خنثی", "خرید خالص بالا"),
        result.crowded,
    )

    return _build_component(
        "cot_positioning", cfg, result, explanation,
        stale=stale,
        fetched_at=str(dates[-1]),
        window_start=str(dates[0]) if dates else None,
        window_end=str(dates[-1]),
    )


async def _score_real_rates(session: AsyncSession, now: datetime) -> dict | None:
    """Real Rates — DFII10 (10-year real yield from FRED)."""
    cfg = COMPONENT_CONFIG["real_rates"]
    cutoff = now - timedelta(days=cfg["window_years"] * 365 + 30)

    rows = (
        await session.execute(
            select(MacroIndicator.observation_date, MacroIndicator.value)
            .where(MacroIndicator.series_id == "DFII10")
            .where(MacroIndicator.observation_date >= cutoff.date())
            .order_by(MacroIndicator.observation_date)
        )
    ).all()

    if not rows:
        return None

    values = [float(r.value) for r in rows]
    dates = [r.observation_date for r in rows]
    current_val = values[-1]
    hist_vals = values[:-1] if len(values) > 1 else values

    stale = (now.date() - dates[-1]).days > cfg["staleness_days"]

    result = score_percentile(
        current_val, hist_vals,
        direction=cfg["direction"],  # inverse: higher rate → lower score
        smooth=cfg["smooth"],
    )

    explanation = _explain(
        "نرخ بهره واقعی ۱۰ ساله آمریکا (DFII10). نرخ پایین‌تر → صعودی‌تر برای طلا.",
        "DFII10", f"{current_val:.2f}%",
        result.percentile, cfg["window_years"],
        ("نرخ بالا (نزولی)", "خنثی", "نرخ پایین/منفی (صعودی)"),
        result.crowded,
    )

    return _build_component(
        "real_rates", cfg, result, explanation,
        stale=stale,
        fetched_at=str(dates[-1]),
        window_start=str(dates[0]) if dates else None,
        window_end=str(dates[-1]),
    )


async def _score_dollar(session: AsyncSession, now: datetime) -> dict | None:
    """Dollar Strength — 5-day change in DXY (DX-Y.NYB)."""
    cfg = COMPONENT_CONFIG["dollar_strength"]
    cutoff = now - timedelta(days=cfg["window_years"] * 365 + 30)

    rows = (
        await session.execute(
            select(AssetPriceDaily.trade_date, AssetPriceDaily.close)
            .where(AssetPriceDaily.symbol == "DX-Y.NYB")
            .where(AssetPriceDaily.trade_date >= cutoff.date())
            .order_by(AssetPriceDaily.trade_date)
        )
    ).all()

    if len(rows) < 6:
        return None

    closes = [float(r.close) for r in rows]
    dates = [r.trade_date for r in rows]

    # Compute rolling 5-day change for the entire history
    change_series = rolling_change(closes, 5)
    if not change_series:
        return None

    current_val = change_series[-1]
    hist_vals = change_series[:-1]

    stale = (now.date() - dates[-1]).days > cfg["staleness_days"]

    result = score_percentile(
        current_val, hist_vals,
        direction=cfg["direction"],  # inverse: stronger dollar → lower score
        smooth=cfg["smooth"],
    )

    explanation = _explain(
        "تغییر ۵ روزه شاخص دلار (DXY). تضعیف دلار → صعودی برای طلا.",
        "تغییر ۵ روزه", f"{current_val:+.2f} واحد",
        result.percentile, cfg["window_years"],
        ("تقویت شدید دلار (نزولی)", "خنثی", "تضعیف دلار (صعودی)"),
        result.crowded,
    )

    return _build_component(
        "dollar_strength", cfg, result, explanation,
        stale=stale,
        fetched_at=str(dates[-1]),
        window_start=str(dates[0]) if dates else None,
        window_end=str(dates[-1]),
    )


async def _score_vix(session: AsyncSession, now: datetime) -> dict | None:
    """Risk Sentiment — VIX close level (higher VIX → gold safe-haven)."""
    cfg = COMPONENT_CONFIG["risk_sentiment"]
    cutoff = now - timedelta(days=cfg["window_years"] * 365 + 30)

    rows = (
        await session.execute(
            select(AssetPriceDaily.trade_date, AssetPriceDaily.close)
            .where(AssetPriceDaily.symbol == "^VIX")
            .where(AssetPriceDaily.trade_date >= cutoff.date())
            .order_by(AssetPriceDaily.trade_date)
        )
    ).all()

    if not rows:
        return None

    values = [float(r.close) for r in rows]
    dates = [r.trade_date for r in rows]
    current_val = values[-1]
    hist_vals = values[:-1] if len(values) > 1 else values

    stale = (now.date() - dates[-1]).days > cfg["staleness_days"]

    result = score_percentile(
        current_val, hist_vals,
        direction=cfg["direction"],  # bullish_when_higher: high VIX → gold up
        smooth=cfg["smooth"],
    )

    explanation = _explain(
        "شاخص ترس بازار (VIX). ترس بالاتر → تقاضای پناهگاهی بیشتر برای طلا.",
        "VIX", f"{current_val:.1f}",
        result.percentile, cfg["window_years"],
        ("ترس پایین (نزولی)", "خنثی", "ترس بالا (صعودی)"),
        result.crowded,
    )

    return _build_component(
        "risk_sentiment", cfg, result, explanation,
        stale=stale,
        fetched_at=str(dates[-1]),
        window_start=str(dates[0]) if dates else None,
        window_end=str(dates[-1]),
    )


async def _score_momentum(session: AsyncSession, now: datetime) -> dict | None:
    """Price Momentum — 10-day percentage return of gold (GC=F)."""
    cfg = COMPONENT_CONFIG["price_momentum"]
    cutoff = now - timedelta(days=cfg["window_years"] * 365 + 30)

    rows = (
        await session.execute(
            select(AssetPriceDaily.trade_date, AssetPriceDaily.close)
            .where(AssetPriceDaily.symbol == "GC=F")
            .where(AssetPriceDaily.trade_date >= cutoff.date())
            .order_by(AssetPriceDaily.trade_date)
        )
    ).all()

    if len(rows) < 11:
        return None

    closes = [float(r.close) for r in rows]
    dates = [r.trade_date for r in rows]

    # Compute rolling 10-day % return
    return_series = rolling_pct_return(closes, 10)
    if not return_series:
        return None

    current_val = return_series[-1]
    hist_vals = return_series[:-1]

    stale = (now.date() - dates[-1]).days > cfg["staleness_days"]

    result = score_percentile(
        current_val, hist_vals,
        direction=cfg["direction"],  # bullish_when_higher
        smooth=cfg["smooth"],
    )

    explanation = _explain(
        "بازده ۱۰ روزه قیمت طلا (GC=F). مومنتوم مثبت → صعودی.",
        "بازده ۱۰ روزه", f"{current_val:+.2f}%",
        result.percentile, cfg["window_years"],
        ("افت شدید (نزولی)", "خنثی", "رشد قوی (صعودی)"),
        result.crowded,
    )

    return _build_component(
        "price_momentum", cfg, result, explanation,
        stale=stale,
        fetched_at=str(dates[-1]),
        window_start=str(dates[0]) if dates else None,
        window_end=str(dates[-1]),
    )


# ── Helpers ─────────────────────────────────────────────────────────────

def _build_component(
    name: str,
    cfg: dict,
    result: ScoreResult,
    explanation: str,
    *,
    stale: bool = False,
    fallback_used: bool = False,
    fetched_at: str | None = None,
    window_start: str | None = None,
    window_end: str | None = None,
) -> dict:
    """Assemble a component dict for the API response + audit log."""
    return {
        # Existing fields (API contract)
        "name": name,
        "label_fa": cfg["label_fa"],
        "score": result.score,
        "weight": cfg["weight"],
        "raw_value": round(result.raw_value, 6),
        "explanation": explanation,
        # New metadata (backwards-compatible additions)
        "percentile": result.percentile,
        "direction": result.direction,
        "window_size": result.window_size,
        "crowded": result.crowded,
        "stale": stale,
        "fallback_used": fallback_used,
        "data_fetched_at": fetched_at,
        # Audit-only fields (included in log, transparent in response)
        "raw_units": cfg["raw_units"],
        "raw_transform": cfg["raw_transform"],
        "data_source_id": cfg["data_source_id"],
        "window_start": window_start,
        "window_end": window_end,
        "winsorization_applied": result.winsorize_bounds is not None,
        "winsorize_bounds": (
            list(result.winsorize_bounds) if result.winsorize_bounds else None
        ),
        "smoothing_applied": result.smoothing_applied,
    }


def _label_from_score(score: int | None) -> tuple[str, str]:
    """Return ``(label_key, label_fa)`` from a composite score.

    Thresholds:  >=60 → bullish,  40 < x < 60 → neutral,  <=40 → bearish.
    """
    if score is None:
        return "pending", "در انتظار داده"
    if score >= 60:
        return "bullish", "صعودی"
    if score <= 40:
        return "bearish", "نزولی"
    return "neutral", "خنثی"


# ── Audit log persistence ───────────────────────────────────────────────

async def _save_audit_log(
    session: AsyncSession,
    run_id: str,
    run_at: datetime,
    overall_score: int | None,
    label: str,
    label_fa: str,
    components: list[dict],
    warnings: list[str],
) -> None:
    """Persist a sentiment calc log row (fire-and-forget)."""
    try:
        from api.data_collection.sentiment_audit import SentimentCalcLog

        log = SentimentCalcLog(
            id=run_id,
            run_at=run_at,
            overall_score=overall_score,
            overall_label=label,
            overall_label_fa=label_fa,
            components=components,
            warnings=warnings if warnings else None,
        )
        session.add(log)
        await session.commit()
    except Exception:
        logger.warning("Failed to save sentiment calc audit log", exc_info=True)
        await session.rollback()


# ── Main entry point ────────────────────────────────────────────────────

async def compute_sentiment(session: AsyncSession) -> dict:
    """Compute composite 0-100 sentiment score from 6 components.

    Each component uses percentile-based scoring against a rolling historical
    window.  Returns a dict matching the existing API contract with additional
    metadata fields.
    """
    now = datetime.now(timezone.utc)
    run_id = str(uuid4())
    warnings: list[str] = []

    # Score all 6 components concurrently (sequential DB queries are fine
    # since we're inside a single async session).
    scorers = [
        ("etf_flows", _score_etf),
        ("cot_positioning", _score_cot),
        ("real_rates", _score_real_rates),
        ("dollar_strength", _score_dollar),
        ("risk_sentiment", _score_vix),
        ("price_momentum", _score_momentum),
    ]

    components: list[dict] = []
    total_score = 0.0
    total_weight = 0

    for comp_name, scorer_fn in scorers:
        try:
            comp = await scorer_fn(session, now)
        except Exception:
            logger.exception("Error scoring component %s", comp_name)
            warnings.append(f"Error scoring {comp_name}")
            comp = None

        if comp is None:
            cfg = COMPONENT_CONFIG[comp_name]
            warnings.append(f"Missing data for {comp_name} — setting score to 50")
            # Fallback: neutral score with stale/fallback markers
            comp = {
                "name": comp_name,
                "label_fa": cfg["label_fa"],
                "score": 50,
                "weight": cfg["weight"],
                "raw_value": None,
                "explanation": "داده کافی در دسترس نیست. امتیاز پیش‌فرض ۵۰ اعمال شده.",
                "percentile": 0.5,
                "direction": cfg["direction"],
                "window_size": 0,
                "crowded": False,
                "stale": True,
                "fallback_used": True,
                "data_fetched_at": None,
                "raw_units": cfg["raw_units"],
                "raw_transform": cfg["raw_transform"],
                "data_source_id": cfg["data_source_id"],
                "window_start": None,
                "window_end": None,
                "winsorization_applied": False,
                "winsorize_bounds": None,
                "smoothing_applied": False,
            }

        if comp.get("stale"):
            warnings.append(f"{comp_name} data is stale")

        components.append(comp)
        total_score += comp["score"] * comp["weight"]
        total_weight += comp["weight"]

    # Composite score
    composite = round(total_score / total_weight) if total_weight > 0 else None
    label, label_fa = _label_from_score(composite)

    # Build normalization info for transparency
    normalization = {}
    for name, cfg in COMPONENT_CONFIG.items():
        normalization[name] = {
            "method": "percentile",
            "direction": cfg["direction"],
            "window_years": cfg["window_years"],
            "weight": cfg["weight"],
            "unit": cfg["raw_units"],
        }

    # Save audit log (using a separate session to avoid transaction issues)
    from api.database import AsyncSessionLocal
    try:
        async with AsyncSessionLocal() as audit_session:
            await _save_audit_log(
                audit_session, run_id, now,
                composite, label, label_fa, components, warnings,
            )
    except Exception:
        logger.warning("Audit log save failed", exc_info=True)

    return {
        # Existing API contract
        "composite_score": composite,
        "label": label,
        "label_fa": label_fa,
        "components": components,
        "component_count": len([c for c in components if not c.get("fallback_used")]),
        "max_components": 6,
        "normalization": normalization,
        # New metadata
        "run_id": run_id,
        "scoring_method": "percentile",
    }
