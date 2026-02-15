"""Canonical indicator registry — the 6 indicators that power all analysis.

Each indicator is defined once here with its:
  - Canonical ID and Persian label
  - Data source + transform pipeline
  - Scoring direction and parameters
  - Score semantics (what the score means in each context)

This is the single source of truth.  Sentiment gauge, momentum dashboard,
and risk radar all use these definitions.  No indicator is defined ad-hoc
in any endpoint.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.analysis.models import (
    AssetPriceDaily,
    CotData,
    EtfHolding,
    MacroIndicator,
)
from api.analysis.scoring_engine import (
    IndicatorResult,
    rolling_average,
    rolling_change,
    rolling_pct_return,
    score_indicator,
)

logger = logging.getLogger("gold_monitor.indicator_registry")


# ═══════════════════════════════════════════════════════════════════════
#  Indicator definition dataclass
# ═══════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class IndicatorDef:
    """Definition of a canonical indicator."""
    id: str
    label_fa: str
    label_en: str
    direction: str                          # "bullish_when_higher" or "inverse"
    weight_sentiment: int                   # Weight in sentiment gauge (0-100)
    weight_risk: int                        # Weight in risk radar (0-100, 0 = not used)
    source_name: str
    source_url_template: str | None         # URL pattern (static or None)
    raw_units: str
    raw_transform: str                      # Human-readable transform description
    window_years: int                       # Historical window for percentile
    smooth: bool                            # Whether to EMA smooth
    staleness_days: int                     # After this many days, flag as stale
    score_semantics: dict[str, str] = field(default_factory=dict)
    # score_semantics maps context → meaning:
    #   "sentiment": "what this score means in sentiment gauge"
    #   "risk": "what this score means in risk radar"
    #   "momentum": "what this score means in momentum"


# ═══════════════════════════════════════════════════════════════════════
#  The 6 canonical indicators
# ═══════════════════════════════════════════════════════════════════════

INDICATORS: dict[str, IndicatorDef] = {
    "ETF_FLOW_GLD": IndicatorDef(
        id="ETF_FLOW_GLD",
        label_fa="جریان ETF (GLD)",
        label_en="GLD ETF Flows",
        direction="bullish_when_higher",
        weight_sentiment=20,
        weight_risk=10,
        source_name="SPDR",
        source_url_template="https://www.spdrgoldshares.com/",
        raw_units="tonnes/day",
        raw_transform="5-day rolling average of GLD daily change_tonnes",
        window_years=2,
        smooth=True,
        staleness_days=4,
        score_semantics={
            "sentiment": "ورود سرمایه نهادی ← صعودی | خروج ← نزولی",
            "risk": "خروج شدید نهادی ← ریسک بالاتر",
        },
    ),
    "COT_POSITION": IndicatorDef(
        id="COT_POSITION",
        label_fa="موقعیت COT",
        label_en="COT Net Position",
        direction="bullish_when_higher",
        weight_sentiment=20,
        weight_risk=15,
        source_name="CFTC",
        source_url_template="https://www.cftc.gov/dea/futures/deacmxsf.htm",
        raw_units="% of OI",
        raw_transform="non_commercial_net / open_interest (normalized)",
        window_years=5,
        smooth=False,
        staleness_days=10,
        score_semantics={
            "sentiment": "خرید خالص بالا ← صعودی | فروش خالص ← نزولی",
            "risk": "موقعیت‌های افراطی ← ریسک بازگشت",
        },
    ),
    "REAL_RATES": IndicatorDef(
        id="REAL_RATES",
        label_fa="نرخ بهره واقعی",
        label_en="Real Interest Rates",
        direction="inverse",
        weight_sentiment=20,
        weight_risk=0,
        source_name="FRED",
        source_url_template="https://fred.stlouisfed.org/series/DFII10",
        raw_units="%",
        raw_transform="DFII10 latest observation (10Y real yield)",
        window_years=2,
        smooth=True,
        staleness_days=30,
        score_semantics={
            "sentiment": "نرخ پایین‌تر ← صعودی برای طلا | نرخ بالاتر ← نزولی",
        },
    ),
    "DOLLAR_STRENGTH": IndicatorDef(
        id="DOLLAR_STRENGTH",
        label_fa="قدرت دلار",
        label_en="Dollar Strength",
        direction="inverse",
        weight_sentiment=15,
        weight_risk=0,
        source_name="Yahoo Finance",
        source_url_template=None,
        raw_units="%",
        raw_transform="5-day DXY percentage return",
        window_years=2,
        smooth=True,
        staleness_days=4,
        score_semantics={
            "sentiment": "تضعیف دلار ← صعودی برای طلا | تقویت ← نزولی",
        },
    ),
    "VIX_LEVEL": IndicatorDef(
        id="VIX_LEVEL",
        label_fa="شاخص ترس (VIX)",
        label_en="VIX Fear Index",
        direction="bullish_when_higher",
        weight_sentiment=15,
        weight_risk=25,
        source_name="Yahoo Finance",
        source_url_template=None,
        raw_units="index",
        raw_transform="VIX close level",
        window_years=2,
        smooth=True,
        staleness_days=4,
        score_semantics={
            "sentiment": "ترس بالاتر ← تقاضای پناهگاهی ← صعودی",
            "risk": "VIX بالا ← نوسان بیشتر ← ریسک بالاتر",
        },
    ),
    "GOLD_PRICE_MOMENTUM": IndicatorDef(
        id="GOLD_PRICE_MOMENTUM",
        label_fa="شتاب قیمت طلا",
        label_en="Gold Price Momentum",
        direction="bullish_when_higher",
        weight_sentiment=10,
        weight_risk=0,
        source_name="Yahoo Finance",
        source_url_template=None,
        raw_units="%",
        raw_transform="10-day gold (GC=F) percentage return",
        window_years=2,
        smooth=True,
        staleness_days=4,
        score_semantics={
            "sentiment": "مومنتوم مثبت ← صعودی | مومنتوم منفی ← نزولی",
        },
    ),
}


# ═══════════════════════════════════════════════════════════════════════
#  Data fetchers — each returns (current_value, historical_values, meta)
# ═══════════════════════════════════════════════════════════════════════

async def _fetch_etf_flow(
    session: AsyncSession, now: datetime, defn: IndicatorDef,
) -> tuple[float | None, list[float], dict]:
    """Fetch GLD ETF flows: 5-day rolling average of daily change_tonnes."""
    cutoff = now - timedelta(days=defn.window_years * 365 + 30)

    rows = (
        await session.execute(
            select(EtfHolding.holding_date, EtfHolding.change_tonnes, EtfHolding.source_url)
            .where(EtfHolding.fund == "GLD")
            .where(EtfHolding.holding_date >= cutoff.date())
            .order_by(EtfHolding.holding_date)
        )
    ).all()

    if len(rows) < 10:
        return None, [], {}

    changes = [float(r.change_tonnes or 0) for r in rows]
    dates = [r.holding_date for r in rows]
    source_url = next((r.source_url for r in reversed(rows) if r.source_url), None)

    avg_series = rolling_average(changes, 5)
    if not avg_series:
        return None, [], {}

    meta = {
        "latest_date": str(dates[-1]),
        "window_start": str(dates[0]),
        "source_url": source_url,
        "stale": (now.date() - dates[-1]).days > defn.staleness_days,
        "raw_value_display": f"{avg_series[-1]:+.2f} تن/روز",
    }

    return avg_series[-1], avg_series[:-1], meta


async def _fetch_cot_position(
    session: AsyncSession, now: datetime, defn: IndicatorDef,
) -> tuple[float | None, list[float], dict]:
    """Fetch COT position: non_commercial_net / open_interest (normalized)."""
    cutoff = now - timedelta(days=defn.window_years * 365 + 30)

    rows = (
        await session.execute(
            select(
                CotData.report_date,
                CotData.non_commercial_net,
                CotData.open_interest,
                CotData.source_url,
            )
            .where(CotData.asset == "gold")
            .where(CotData.non_commercial_net.isnot(None))
            .where(CotData.report_date >= cutoff.date())
            .order_by(CotData.report_date)
        )
    ).all()

    if not rows:
        return None, [], {}

    # Normalize: net / OI (as percentage)
    values: list[float] = []
    for r in rows:
        net = float(r.non_commercial_net)
        oi = float(r.open_interest) if r.open_interest else None
        if oi and oi > 0:
            values.append(net / oi * 100.0)
        else:
            values.append(0.0)

    dates = [r.report_date for r in rows]
    source_url = next((r.source_url for r in reversed(rows) if r.source_url), None)

    meta = {
        "latest_date": str(dates[-1]),
        "window_start": str(dates[0]),
        "source_url": source_url,
        "stale": (now.date() - dates[-1]).days > defn.staleness_days,
        "raw_value_display": f"{values[-1]:.1f}% of OI",
        "raw_net": float(rows[-1].non_commercial_net),
        "raw_oi": float(rows[-1].open_interest) if rows[-1].open_interest else None,
    }

    return values[-1], values[:-1] if len(values) > 1 else values, meta


async def _fetch_real_rates(
    session: AsyncSession, now: datetime, defn: IndicatorDef,
) -> tuple[float | None, list[float], dict]:
    """Fetch real rates: DFII10 from FRED."""
    cutoff = now - timedelta(days=defn.window_years * 365 + 30)

    rows = (
        await session.execute(
            select(MacroIndicator.observation_date, MacroIndicator.value)
            .where(MacroIndicator.series_id == "DFII10")
            .where(MacroIndicator.observation_date >= cutoff.date())
            .order_by(MacroIndicator.observation_date)
        )
    ).all()

    if not rows:
        return None, [], {}

    values = [float(r.value) for r in rows]
    dates = [r.observation_date for r in rows]

    meta = {
        "latest_date": str(dates[-1]),
        "window_start": str(dates[0]),
        "source_url": defn.source_url_template,
        "stale": (now.date() - dates[-1]).days > defn.staleness_days,
        "raw_value_display": f"{values[-1]:.2f}%",
    }

    return values[-1], values[:-1] if len(values) > 1 else values, meta


async def _fetch_dollar_strength(
    session: AsyncSession, now: datetime, defn: IndicatorDef,
) -> tuple[float | None, list[float], dict]:
    """Fetch dollar strength: 5-day DXY percentage return."""
    cutoff = now - timedelta(days=defn.window_years * 365 + 30)

    rows = (
        await session.execute(
            select(AssetPriceDaily.trade_date, AssetPriceDaily.close)
            .where(AssetPriceDaily.symbol == "DX-Y.NYB")
            .where(AssetPriceDaily.trade_date >= cutoff.date())
            .order_by(AssetPriceDaily.trade_date)
        )
    ).all()

    if len(rows) < 6:
        return None, [], {}

    closes = [float(r.close) for r in rows]
    dates = [r.trade_date for r in rows]

    # 5-day percentage return (not point change)
    return_series = rolling_pct_return(closes, 5)
    if not return_series:
        return None, [], {}

    meta = {
        "latest_date": str(dates[-1]),
        "window_start": str(dates[0]),
        "source_url": defn.source_url_template,
        "stale": (now.date() - dates[-1]).days > defn.staleness_days,
        "raw_value_display": f"{return_series[-1]:+.2f}%",
    }

    return return_series[-1], return_series[:-1], meta


async def _fetch_vix(
    session: AsyncSession, now: datetime, defn: IndicatorDef,
) -> tuple[float | None, list[float], dict]:
    """Fetch VIX level."""
    cutoff = now - timedelta(days=defn.window_years * 365 + 30)

    rows = (
        await session.execute(
            select(AssetPriceDaily.trade_date, AssetPriceDaily.close)
            .where(AssetPriceDaily.symbol == "^VIX")
            .where(AssetPriceDaily.trade_date >= cutoff.date())
            .order_by(AssetPriceDaily.trade_date)
        )
    ).all()

    if not rows:
        return None, [], {}

    values = [float(r.close) for r in rows]
    dates = [r.trade_date for r in rows]

    meta = {
        "latest_date": str(dates[-1]),
        "window_start": str(dates[0]),
        "source_url": defn.source_url_template,
        "stale": (now.date() - dates[-1]).days > defn.staleness_days,
        "raw_value_display": f"{values[-1]:.1f}",
    }

    return values[-1], values[:-1] if len(values) > 1 else values, meta


async def _fetch_gold_momentum(
    session: AsyncSession, now: datetime, defn: IndicatorDef,
) -> tuple[float | None, list[float], dict]:
    """Fetch gold price momentum: 10-day percentage return of GC=F."""
    cutoff = now - timedelta(days=defn.window_years * 365 + 30)

    rows = (
        await session.execute(
            select(AssetPriceDaily.trade_date, AssetPriceDaily.close)
            .where(AssetPriceDaily.symbol == "GC=F")
            .where(AssetPriceDaily.trade_date >= cutoff.date())
            .order_by(AssetPriceDaily.trade_date)
        )
    ).all()

    if len(rows) < 11:
        return None, [], {}

    closes = [float(r.close) for r in rows]
    dates = [r.trade_date for r in rows]

    return_series = rolling_pct_return(closes, 10)
    if not return_series:
        return None, [], {}

    meta = {
        "latest_date": str(dates[-1]),
        "window_start": str(dates[0]),
        "source_url": defn.source_url_template,
        "stale": (now.date() - dates[-1]).days > defn.staleness_days,
        "raw_value_display": f"{return_series[-1]:+.2f}%",
    }

    return return_series[-1], return_series[:-1], meta


# Map indicator ID → fetcher function
_FETCHERS = {
    "ETF_FLOW_GLD": _fetch_etf_flow,
    "COT_POSITION": _fetch_cot_position,
    "REAL_RATES": _fetch_real_rates,
    "DOLLAR_STRENGTH": _fetch_dollar_strength,
    "VIX_LEVEL": _fetch_vix,
    "GOLD_PRICE_MOMENTUM": _fetch_gold_momentum,
}


# ═══════════════════════════════════════════════════════════════════════
#  Public API
# ═══════════════════════════════════════════════════════════════════════

async def compute_indicator(
    session: AsyncSession,
    indicator_id: str,
    now: datetime | None = None,
) -> IndicatorResult:
    """Compute a single canonical indicator.

    Returns IndicatorResult with full metadata for provenance tracking.
    """
    if indicator_id not in INDICATORS:
        raise ValueError(f"Unknown indicator: {indicator_id}")

    defn = INDICATORS[indicator_id]
    if now is None:
        now = datetime.now(timezone.utc)

    fetcher = _FETCHERS[indicator_id]
    current_value, historical_values, meta = await fetcher(session, now, defn)

    if current_value is None:
        return IndicatorResult(
            indicator_id=indicator_id,
            score=50,
            percentile=0.5,
            raw_value=0.0,
            transformed_value=0.0,
            smoothed_value=0.0,
            direction=defn.direction,
            window_size=0,
            crowded=False,
            stale=True,
            fallback_used=True,
            last_updated_at=None,
            source_name=defn.source_name,
            source_url=defn.source_url_template,
            winsorize_bounds=None,
            smoothing_applied=False,
        )

    return score_indicator(
        indicator_id=indicator_id,
        current_value=current_value,
        historical_values=historical_values,
        direction=defn.direction,
        smooth=defn.smooth,
        do_winsorize=True,
        neutral_band=True,
        stale=meta.get("stale", False),
        last_updated_at=meta.get("latest_date"),
        source_name=defn.source_name,
        source_url=meta.get("source_url") or defn.source_url_template,
    )


async def compute_all_indicators(
    session: AsyncSession,
    now: datetime | None = None,
) -> dict[str, IndicatorResult]:
    """Compute all 6 canonical indicators.

    Returns dict mapping indicator_id → IndicatorResult.
    """
    results: dict[str, IndicatorResult] = {}
    for indicator_id in INDICATORS:
        try:
            results[indicator_id] = await compute_indicator(session, indicator_id, now)
        except Exception as e:
            logger.warning("Failed to compute %s: %s", indicator_id, e)
            defn = INDICATORS[indicator_id]
            results[indicator_id] = IndicatorResult(
                indicator_id=indicator_id,
                score=50,
                percentile=0.5,
                raw_value=0.0,
                transformed_value=0.0,
                smoothed_value=0.0,
                direction=defn.direction,
                window_size=0,
                crowded=False,
                stale=True,
                fallback_used=True,
                last_updated_at=None,
                source_name=defn.source_name,
                source_url=defn.source_url_template,
                winsorize_bounds=None,
                smoothing_applied=False,
            )
    return results


def indicator_to_dict(result: IndicatorResult, defn: IndicatorDef | None = None) -> dict:
    """Convert IndicatorResult to a JSON-serializable dict with full metadata.

    Includes score_semantics if defn is provided.
    """
    d = {
        "indicator_id": result.indicator_id,
        "score": result.score,
        "percentile": result.percentile,
        "raw_value": result.raw_value,
        "transformed_value": result.transformed_value,
        "smoothed_value": result.smoothed_value,
        "direction": result.direction,
        "window_size": result.window_size,
        "crowded": result.crowded,
        "stale": result.stale,
        "fallback_used": result.fallback_used,
        "last_updated_at": result.last_updated_at,
        "source_name": result.source_name,
        "source_url": result.source_url,
        "winsorize_bounds": list(result.winsorize_bounds) if result.winsorize_bounds else None,
        "smoothing_applied": result.smoothing_applied,
        "scoring_method": result.scoring_method,
        "zscore": result.zscore,
    }
    if defn:
        d["label_fa"] = defn.label_fa
        d["label_en"] = defn.label_en
        d["raw_units"] = defn.raw_units
        d["raw_transform"] = defn.raw_transform
        d["score_semantics"] = defn.score_semantics
    return d


async def persist_audit_logs(
    session: AsyncSession,
    run_id: str,
    results: dict[str, IndicatorResult],
    context: str = "debug",
) -> None:
    """Persist one audit log row per indicator for provenance tracking.

    Fire-and-forget — errors are logged but not raised.
    """
    import json as _json
    from sqlalchemy import text

    for ind_id, result in results.items():
        try:
            await session.execute(
                text("""
                    INSERT INTO analysis_audit_logs (
                        run_id, indicator_id, score, percentile, raw_value,
                        transformed_value, smoothed_value, direction, window_size,
                        crowded, stale, fallback_used, last_updated_at,
                        source_name, source_url, winsorize_bounds,
                        smoothing_applied, scoring_method, zscore, context
                    ) VALUES (
                        :run_id, :indicator_id, :score, :percentile, :raw_value,
                        :transformed_value, :smoothed_value, :direction, :window_size,
                        :crowded, :stale, :fallback_used, :last_updated_at,
                        :source_name, :source_url, CAST(:winsorize_bounds AS jsonb),
                        :smoothing_applied, :scoring_method, :zscore, :context
                    )
                """),
                {
                    "run_id": run_id,
                    "indicator_id": result.indicator_id,
                    "score": result.score,
                    "percentile": result.percentile,
                    "raw_value": result.raw_value,
                    "transformed_value": result.transformed_value,
                    "smoothed_value": result.smoothed_value,
                    "direction": result.direction,
                    "window_size": result.window_size,
                    "crowded": result.crowded,
                    "stale": result.stale,
                    "fallback_used": result.fallback_used,
                    "last_updated_at": result.last_updated_at,
                    "source_name": result.source_name,
                    "source_url": result.source_url,
                    "winsorize_bounds": (
                        _json.dumps(list(result.winsorize_bounds))
                        if result.winsorize_bounds else None
                    ),
                    "smoothing_applied": result.smoothing_applied,
                    "scoring_method": result.scoring_method,
                    "zscore": result.zscore,
                    "context": context,
                },
            )
        except Exception:
            logger.debug("Failed to persist audit log for %s", ind_id, exc_info=True)

    try:
        await session.commit()
    except Exception:
        logger.debug("Failed to commit audit logs", exc_info=True)
        await session.rollback()
