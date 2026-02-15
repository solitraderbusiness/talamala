"""Macro Momentum Engine — statistically robust scoring for 6 fundamental drivers.

Computes a 0-100 composite momentum score where 50=neutral, >55=bullish, <45=bearish.
All normalization uses rolling percentiles or z-scores instead of hand-tuned multipliers.

Drivers:
    1. ETF Flow (GLD) — z-score of daily change + 10-day cumulative persistence
    2. COT Positioning — net-as-%-of-OI percentile over 5 years
    3. Real Rates (DFII10) — inverted percentile over 10 years
    4. Dollar Strength (DXY) — z-score of 5-day log return over 3 years
    5. Macro Regime — data-driven forward gold return mapping
    6. Sentiment Trend — slope-based trend + level blend

All tunable constants live in MOMENTUM_CONFIG.
"""

from __future__ import annotations

import logging
import math
import statistics
from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import desc, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from api.analysis.models import (
    AssetPriceDaily,
    CotData,
    EtfHolding,
    MacroIndicator,
    RegimeScore,
)
from api.data_collection.models import SentimentTimeline

logger = logging.getLogger("gold_monitor.momentum_engine")

# ═══════════════════════════════════════════════════════════════════════
#  Configuration — all tunable constants
# ═══════════════════════════════════════════════════════════════════════

MOMENTUM_CONFIG = {
    "base_weights": {
        "etf_flow": 20,
        "cot_positioning": 20,
        "real_rates": 20,
        "dollar_strength": 15,
        "risk_regime": 15,
        "sentiment_trend": 10,
    },
    # ETF Flow
    "etf_zscore_window": 180,         # last N available records
    "etf_zscore_multiplier": 15,      # maps 1σ to 15 points
    "etf_cumulative_window": 10,      # 10-day cumulative
    "etf_cumulative_factor": 5,       # maps 1σ of cum10 to 5 points
    "etf_stale_days": 3,
    # COT Positioning
    "cot_lookback_years": 5,          # 5-year rolling percentile
    "cot_stale_days": 10,
    "cot_confidence_decay_days": 7,
    # Real Rates
    "rr_lookback_years": 10,          # 10-year percentile window
    "rr_stale_days": 5,
    # Dollar Strength
    "dxy_return_lag": 5,              # 5-day log return
    "dxy_lookback_years": 3,          # 3-year z-score window
    "dxy_zscore_multiplier": 15,      # maps 1σ to 15 points
    "dxy_trend_window": 20,           # slope over 20 days
    # Regime
    "regime_lookback_years": 5,
    "regime_forward_days": 10,
    "regime_stale_days": 3,
    # Sentiment
    "sent_6h_records": 72,            # ~6h at 5min intervals
    "sent_24h_records": 288,          # ~24h at 5min intervals
    "sent_trend_weight": 0.7,
    "sent_level_weight": 0.3,
    "sent_slope_scale": 5.0,          # scale slope to score range
    # Confidence decay
    "confidence_decay_rates": {
        "etf_flow": 2,
        "cot_positioning": 7,
        "real_rates": 5,
        "dollar_strength": 2,
        "risk_regime": 3,
        "sentiment_trend": 1,
    },
    # Labels
    "label_very_bullish": 70,
    "label_bullish": 55,
    "label_neutral_low": 45,
    "label_bearish": 30,
}


# ═══════════════════════════════════════════════════════════════════════
#  Pure math helpers (no DB, no async)
# ═══════════════════════════════════════════════════════════════════════

def percentile_rank(value: float, distribution: list[float]) -> float:
    """Percentile of *value* within *distribution* (0.0-1.0). Mean method for ties."""
    if not distribution:
        return 0.5
    n = len(distribution)
    below = sum(1 for v in distribution if v < value)
    equal = sum(1 for v in distribution if v == value)
    return max(0.0, min(1.0, (below + equal / 2.0) / n))


def zscore(value: float, values: list[float]) -> float | None:
    """Z-score of *value* vs *values*. Returns None if std=0 or len<2."""
    if len(values) < 2:
        return None
    m = statistics.mean(values)
    s = statistics.stdev(values)
    if s == 0:
        return None
    return (value - m) / s


def clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def compute_confidence(data_age_days: float, decay_start_days: float) -> float:
    """Confidence decays from 1.0 to 0.3 after decay_start_days."""
    if data_age_days <= decay_start_days:
        return 1.0
    extra = data_age_days - decay_start_days
    max_extra = decay_start_days * 2
    decay = min(extra / max_extra, 1.0) * 0.7
    return max(0.3, 1.0 - decay)


def linear_slope(values: list[float]) -> float | None:
    """Simple linear regression slope over equally-spaced values."""
    n = len(values)
    if n < 3:
        return None
    x_mean = (n - 1) / 2.0
    y_mean = statistics.mean(values)
    num = sum((i - x_mean) * (values[i] - y_mean) for i in range(n))
    den = sum((i - x_mean) ** 2 for i in range(n))
    if den == 0:
        return 0.0
    return num / den


def slope_to_trend(slope: float | None, threshold: float = 0.01) -> str:
    """Map a slope to trend label."""
    if slope is None:
        return "steady"
    if slope > threshold * 1.5:
        return "accelerating"
    if slope < -threshold * 1.5:
        return "decelerating"
    if abs(slope) > threshold * 0.3:
        return "steady"
    return "steady"


def direction_from_score(score: float) -> tuple[str, str]:
    """Return (direction, direction_fa) from a 0-100 score."""
    cfg = MOMENTUM_CONFIG
    if score >= cfg["label_very_bullish"]:
        return "very_bullish", "بسیار صعودی"
    if score >= cfg["label_bullish"]:
        return "bullish", "صعودی"
    if score >= cfg["label_neutral_low"]:
        return "neutral", "خنثی"
    if score >= cfg["label_bearish"]:
        return "bearish", "نزولی"
    return "very_bearish", "بسیار نزولی"


def strength_from_score(score: float) -> str:
    """Return strength label based on distance from neutral (50)."""
    dist = abs(score - 50)
    if dist >= 25:
        return "strong"
    if dist >= 10:
        return "moderate"
    return "weak"


# ═══════════════════════════════════════════════════════════════════════
#  Driver scorers (async DB queries → pure score)
# ═══════════════════════════════════════════════════════════════════════

async def _score_etf_flow(session: AsyncSession, as_of: date) -> dict:
    """Driver 1: ETF Flow (GLD) — z-score of daily change + cumulative persistence."""
    cfg = MOMENTUM_CONFIG
    window = cfg["etf_zscore_window"]

    rows = (await session.execute(
        select(EtfHolding.holding_date, EtfHolding.change_tonnes)
        .where(EtfHolding.fund == "GLD", EtfHolding.change_tonnes.isnot(None))
        .order_by(desc(EtfHolding.holding_date))
        .limit(window + 30)
    )).all()

    if not rows:
        return _fallback_driver("etf_flow", "جریان ETF", "داده ETF موجود نیست")

    rows = list(reversed(rows))  # oldest first
    changes = [float(r.change_tonnes) for r in rows]
    dates = [r.holding_date for r in rows]
    current = changes[-1]
    latest_date = dates[-1]
    data_age = (as_of - latest_date).days

    # Z-score of latest daily change vs last N records
    window_values = changes[-window:] if len(changes) >= window else changes
    z = zscore(current, window_values)

    if z is not None:
        # Positive inflows are bullish → score > 50
        score_level = clamp(50 + z * cfg["etf_zscore_multiplier"])
    else:
        score_level = 50

    # Persistence: 10-day cumulative
    cum_win = cfg["etf_cumulative_window"]
    cum_values = changes[-cum_win:]
    cum_10d = sum(cum_values) if cum_values else 0.0

    # Z-score of cumulative
    if len(changes) > cum_win:
        all_cum = [sum(changes[i - cum_win:i]) for i in range(cum_win, len(changes))]
        cum_z = zscore(cum_10d, all_cum)
        if cum_z is not None:
            score_level = clamp(score_level + cum_z * cfg["etf_cumulative_factor"])

    score = round(score_level)

    # Trend: slope over last 10 changes
    trend_data = changes[-10:] if len(changes) >= 10 else changes
    sl = linear_slope(trend_data)
    if sl is not None and len(trend_data) >= 5:
        # Check if direction reversed
        first_half_avg = statistics.mean(trend_data[:len(trend_data)//2])
        second_half_avg = statistics.mean(trend_data[len(trend_data)//2:])
        if first_half_avg * second_half_avg < 0:
            trend = "reversing"
        else:
            trend = slope_to_trend(sl, threshold=0.3)
    else:
        trend = "steady"

    # Streak counting
    streak = 0
    sign = 1 if current >= 0 else -1
    for c in reversed(changes):
        if (c >= 0) == (sign >= 0):
            streak += 1
        else:
            break

    avg_5 = statistics.mean(changes[-5:]) if len(changes) >= 5 else current
    confidence = compute_confidence(data_age, cfg["confidence_decay_rates"]["etf_flow"])

    if avg_5 > 0.5:
        explain = f"{streak} روز ورود متوالی به GLD — z-score={z:+.2f}σ" if z else f"{streak} روز ورود متوالی"
    elif avg_5 < -0.5:
        explain = f"{streak} روز خروج متوالی از GLD — z-score={z:+.2f}σ" if z else f"{streak} روز خروج متوالی"
    else:
        explain = f"جریان خنثی ETF — z-score={z:+.2f}σ" if z else "جریان خنثی ETF"
    explain += f". تجمعی ۱۰ روز: {cum_10d:+.1f} تن."

    direction, _ = direction_from_score(score)

    return {
        "id": "etf_flow",
        "label_fa": "جریان ETF",
        "score": score,
        "direction": direction,
        "strength": strength_from_score(score),
        "weight": cfg["base_weights"]["etf_flow"],
        "raw_value": round(avg_5, 2),
        "raw_unit": "تن/روز",
        "explanation_fa": explain,
        "trend": trend,
        "confidence": round(confidence, 2),
        "meta": {
            "zscore": round(z, 3) if z is not None else None,
            "cum_10d": round(cum_10d, 2),
            "window_used": len(window_values),
            "normalized_method": "zscore",
            "last_updated_at": str(latest_date),
            "data_age_days": data_age,
            "fallback_used": z is None,
        },
    }


async def _score_cot(session: AsyncSession, as_of: date) -> dict:
    """Driver 2: COT Positioning — net-as-%-of-OI percentile over 5 years."""
    cfg = MOMENTUM_CONFIG
    lookback = as_of - timedelta(days=cfg["cot_lookback_years"] * 365)

    rows = (await session.execute(
        select(CotData.report_date, CotData.non_commercial_net,
               CotData.open_interest, CotData.change_non_commercial_net)
        .where(CotData.asset == "gold", CotData.report_date >= lookback)
        .where(CotData.non_commercial_net.isnot(None), CotData.open_interest.isnot(None))
        .order_by(CotData.report_date)
    )).all()

    if not rows:
        return _fallback_driver("cot_positioning", "موقعیت COT", "داده COT موجود نیست")

    # Compute net as % of OI
    net_pct_oi = []
    dates = []
    for r in rows:
        if r.open_interest and r.open_interest > 0:
            net_pct_oi.append(float(r.non_commercial_net) / float(r.open_interest) * 100)
            dates.append(r.report_date)

    if not net_pct_oi:
        return _fallback_driver("cot_positioning", "موقعیت COT", "داده OI صفر")

    current_pct = net_pct_oi[-1]
    latest_date = dates[-1]
    data_age = (as_of - latest_date).days

    # Percentile-based momentum scoring: higher percentile = more bullish positioning
    pct = percentile_rank(current_pct, net_pct_oi)
    score = round(clamp(pct * 100))

    # Trend: WoW change in net_pct_oi
    if len(net_pct_oi) >= 3:
        recent_changes = [net_pct_oi[i] - net_pct_oi[i-1] for i in range(-min(4, len(net_pct_oi)-1), 0)]
        sl = linear_slope(recent_changes) if len(recent_changes) >= 3 else (recent_changes[-1] if recent_changes else 0)
        trend = slope_to_trend(sl, threshold=0.5) if isinstance(sl, float) else "steady"
    else:
        trend = "steady"

    # Weekly change for explanation
    weekly_change_net = rows[-1].change_non_commercial_net if rows[-1].change_non_commercial_net else 0

    confidence = compute_confidence(data_age, cfg["confidence_decay_rates"]["cot_positioning"])

    net = int(rows[-1].non_commercial_net)
    if net > 100000:
        explain = f"موقعیت خرید بالا: {net:,} قرارداد (صدک {round(pct*100)}% در {cfg['cot_lookback_years']} سال)"
    elif net < 0:
        explain = f"موقعیت فروش: {net:,} قرارداد (صدک {round(pct*100)}%)"
    else:
        explain = f"موقعیت متعادل: {net:,} قرارداد (صدک {round(pct*100)}%)"
    if weekly_change_net:
        explain += f". تغییر هفتگی: {int(weekly_change_net):+,}"

    direction, _ = direction_from_score(score)

    return {
        "id": "cot_positioning",
        "label_fa": "موقعیت COT",
        "score": score,
        "direction": direction,
        "strength": strength_from_score(score),
        "weight": cfg["base_weights"]["cot_positioning"],
        "raw_value": net,
        "raw_unit": "قرارداد",
        "explanation_fa": explain,
        "trend": trend,
        "confidence": round(confidence, 2),
        "meta": {
            "net_pct_oi": round(current_pct, 2),
            "percentile": round(pct, 4),
            "window_used": len(net_pct_oi),
            "normalized_method": "percentile",
            "last_updated_at": str(latest_date),
            "data_age_days": data_age,
            "fallback_used": False,
            "is_stale": data_age > cfg["cot_stale_days"],
        },
    }


async def _score_real_rates(session: AsyncSession, as_of: date) -> dict:
    """Driver 3: Real Rates (DFII10) — inverted percentile over 10 years."""
    cfg = MOMENTUM_CONFIG
    lookback = as_of - timedelta(days=cfg["rr_lookback_years"] * 365)

    rows = (await session.execute(
        select(MacroIndicator.observation_date, MacroIndicator.value)
        .where(MacroIndicator.series_id == "DFII10", MacroIndicator.observation_date >= lookback)
        .order_by(MacroIndicator.observation_date)
    )).all()

    if not rows:
        return _fallback_driver("real_rates", "نرخ بهره واقعی", "داده DFII10 موجود نیست")

    values = [float(r.value) for r in rows]
    dates = [r.observation_date for r in rows]
    current = values[-1]
    latest_date = dates[-1]
    data_age = (as_of - latest_date).days

    # Inverted percentile: higher real rates → lower gold momentum
    pct = percentile_rank(current, values)
    score = round(clamp((1 - pct) * 100))

    # Trend: slope over last 30 observations
    trend_data = values[-30:] if len(values) >= 30 else values
    sl = linear_slope(trend_data)
    if sl is not None:
        # Falling rates = bullish acceleration for gold
        if sl < -0.005:
            trend = "accelerating"
        elif sl > 0.005:
            trend = "decelerating"
        else:
            trend = "steady"
    else:
        trend = "steady"

    confidence = compute_confidence(data_age, cfg["confidence_decay_rates"]["real_rates"])

    if current < 0:
        explain = f"نرخ بهره واقعی منفی ({current:.2f}%) — بسیار حمایتی برای طلا. صدک {round((1-pct)*100)}%."
    elif current > 2:
        explain = f"نرخ بهره واقعی بالا ({current:.2f}%) — فشار نزولی بر طلا. صدک {round((1-pct)*100)}%."
    else:
        explain = f"نرخ بهره واقعی {current:.2f}% — فشار متعادل. صدک {round((1-pct)*100)}%."

    direction, _ = direction_from_score(score)

    return {
        "id": "real_rates",
        "label_fa": "نرخ بهره واقعی",
        "score": score,
        "direction": direction,
        "strength": strength_from_score(score),
        "weight": cfg["base_weights"]["real_rates"],
        "raw_value": round(current, 2),
        "raw_unit": "%",
        "explanation_fa": explain,
        "trend": trend,
        "confidence": round(confidence, 2),
        "meta": {
            "percentile": round(pct, 4),
            "inverted_percentile": round(1 - pct, 4),
            "window_used": len(values),
            "normalized_method": "percentile",
            "last_updated_at": str(latest_date),
            "data_age_days": data_age,
            "fallback_used": False,
        },
    }


async def _score_dollar(session: AsyncSession, as_of: date) -> dict:
    """Driver 4: Dollar Strength (DXY) — z-score of 5-day log return over 3 years."""
    cfg = MOMENTUM_CONFIG
    lookback = as_of - timedelta(days=cfg["dxy_lookback_years"] * 365 + 30)

    rows = (await session.execute(
        select(AssetPriceDaily.trade_date, AssetPriceDaily.close)
        .where(AssetPriceDaily.symbol == "DX-Y.NYB", AssetPriceDaily.trade_date >= lookback)
        .order_by(AssetPriceDaily.trade_date)
    )).all()

    if len(rows) < 10:
        return _fallback_driver("dollar_strength", "قدرت دلار", "داده DXY کافی نیست")

    closes = [float(r.close) for r in rows]
    dates = [r.trade_date for r in rows]
    latest_date = dates[-1]
    data_age = (as_of - latest_date).days

    lag = cfg["dxy_return_lag"]

    # Compute 5-day log returns for entire history
    log_returns_5d = []
    for i in range(lag, len(closes)):
        if closes[i - lag] > 0 and closes[i] > 0:
            log_returns_5d.append(math.log(closes[i] / closes[i - lag]))

    if not log_returns_5d:
        return _fallback_driver("dollar_strength", "قدرت دلار", "بازده DXY محاسبه نشد")

    current_ret = log_returns_5d[-1]

    # Z-score of current 5d return vs full history
    z = zscore(current_ret, log_returns_5d)

    if z is not None:
        # Weak dollar (negative z) = bullish for gold
        score = round(clamp(50 - z * cfg["dxy_zscore_multiplier"]))
    else:
        score = 50

    # Trend: slope of 5d returns over last 20 observations
    trend_win = cfg["dxy_trend_window"]
    trend_data = log_returns_5d[-trend_win:] if len(log_returns_5d) >= trend_win else log_returns_5d
    sl = linear_slope(trend_data)
    if sl is not None:
        # Rising DXY returns = decelerating for gold momentum
        if sl > 0.0005:
            trend = "decelerating"
        elif sl < -0.0005:
            trend = "accelerating"
        else:
            trend = "steady"
    else:
        trend = "steady"

    confidence = compute_confidence(data_age, cfg["confidence_decay_rates"]["dollar_strength"])

    # 5d change in DXY level for display
    dxy_5d_change = closes[-1] - closes[-min(lag + 1, len(closes))] if len(closes) > lag else 0

    if dxy_5d_change > 0.5:
        explain = f"تقویت دلار ({dxy_5d_change:+.2f} واحد ۵ روزه). z-score={z:+.2f}σ." if z else f"تقویت دلار ({dxy_5d_change:+.2f})"
    elif dxy_5d_change < -0.5:
        explain = f"تضعیف دلار ({dxy_5d_change:+.2f} واحد ۵ روزه). z-score={z:+.2f}σ." if z else f"تضعیف دلار ({dxy_5d_change:+.2f})"
    else:
        explain = f"دلار تقریباً ثابت ({dxy_5d_change:+.2f}). z-score={z:+.2f}σ." if z else f"دلار ثابت ({dxy_5d_change:+.2f})"

    direction, _ = direction_from_score(score)

    return {
        "id": "dollar_strength",
        "label_fa": "قدرت دلار",
        "score": score,
        "direction": direction,
        "strength": strength_from_score(score),
        "weight": cfg["base_weights"]["dollar_strength"],
        "raw_value": round(dxy_5d_change, 2),
        "raw_unit": "واحد",
        "explanation_fa": explain,
        "trend": trend,
        "confidence": round(confidence, 2),
        "meta": {
            "log_return_5d": round(current_ret, 6),
            "zscore": round(z, 3) if z is not None else None,
            "dxy_close": round(closes[-1], 2),
            "window_used": len(log_returns_5d),
            "normalized_method": "zscore",
            "last_updated_at": str(latest_date),
            "data_age_days": data_age,
            "fallback_used": z is None,
        },
    }


async def _score_regime(session: AsyncSession, as_of: date) -> dict:
    """Driver 5: Macro Regime — data-driven forward gold return mapping."""
    cfg = MOMENTUM_CONFIG
    lookback = as_of - timedelta(days=cfg["regime_lookback_years"] * 365)

    # Get latest regime
    regime_q = await session.execute(
        select(RegimeScore).order_by(desc(RegimeScore.ts)).limit(2)
    )
    regime_rows = regime_q.scalars().all()

    if not regime_rows or not regime_rows[0].chosen_regime:
        return _fallback_driver("risk_regime", "رژیم کلان", "داده رژیم موجود نیست")

    regime = regime_rows[0].chosen_regime
    regime_date = regime_rows[0].ts
    data_age = (as_of - regime_date).days

    # Try data-driven: compute mean forward 10d gold return for each regime
    fwd = cfg["regime_forward_days"]
    gold_q = await session.execute(
        select(AssetPriceDaily.trade_date, AssetPriceDaily.close)
        .where(AssetPriceDaily.symbol == "GC=F", AssetPriceDaily.trade_date >= lookback)
        .order_by(AssetPriceDaily.trade_date)
    )
    gold_rows = gold_q.all()

    regime_hist_q = await session.execute(
        select(RegimeScore.ts, RegimeScore.chosen_regime)
        .where(RegimeScore.ts >= lookback, RegimeScore.chosen_regime.isnot(None))
        .order_by(RegimeScore.ts)
    )
    regime_hist = regime_hist_q.all()

    fallback_used = True
    # Static fallback
    static_map = {"expansion": 55, "recovery": 60, "tightening": 35, "stress": 75}
    score = static_map.get(regime, 50)

    if len(gold_rows) >= 50 and len(regime_hist) >= 20:
        gold_map = {r.trade_date: float(r.close) for r in gold_rows}
        gold_dates = sorted(gold_map.keys())
        regime_map = {r.ts: r.chosen_regime for r in regime_hist}

        # For each gold date, find regime and compute forward 10d return
        returns_by_regime: dict[str, list[float]] = {}
        for i, d in enumerate(gold_dates):
            if i + fwd >= len(gold_dates):
                break
            # Find regime for this date
            regime_for_date = None
            for rd in sorted(regime_map.keys(), reverse=True):
                if rd <= d:
                    regime_for_date = regime_map[rd]
                    break
            if regime_for_date is None:
                continue
            p0 = gold_map.get(d)
            p1 = gold_map.get(gold_dates[i + fwd])
            if p0 and p1 and p0 > 0:
                fwd_ret = (p1 - p0) / p0 * 100
                returns_by_regime.setdefault(regime_for_date, []).append(fwd_ret)

        # Map current regime's mean forward return to score
        if regime in returns_by_regime and len(returns_by_regime[regime]) >= 10:
            current_mean = statistics.mean(returns_by_regime[regime])
            # Collect all mean forward returns across regimes
            all_means = []
            for rets in returns_by_regime.values():
                if len(rets) >= 5:
                    all_means.append(statistics.mean(rets))
            if all_means:
                pct = percentile_rank(current_mean, all_means)
                score = round(clamp(pct * 100))
                fallback_used = False

    # Detect regime change for trend
    if len(regime_rows) >= 2 and regime_rows[1].chosen_regime:
        prev_regime = regime_rows[1].chosen_regime
        trend = "reversing" if regime != prev_regime else "steady"
    else:
        trend = "steady"

    confidence = compute_confidence(data_age, cfg["confidence_decay_rates"]["risk_regime"])

    regime_labels = {
        "expansion": "انبساطی", "recovery": "بازیابی",
        "tightening": "انقباضی", "stress": "بحرانی",
    }
    label = regime_labels.get(regime, regime)
    if trend == "reversing" and len(regime_rows) >= 2:
        prev_label = regime_labels.get(regime_rows[1].chosen_regime, regime_rows[1].chosen_regime)
        explain = f"رژیم {label} (تغییر از {prev_label}) — تحول در محیط کلان."
    else:
        explain = f"رژیم {label} — {'محیط حمایتی برای طلا' if score >= 55 else 'محیط فشار بر طلا' if score < 45 else 'محیط خنثی'}."
    if fallback_used:
        explain += " (نقشه ثابت — داده تاریخی کافی نیست)"

    direction, _ = direction_from_score(score)

    return {
        "id": "risk_regime",
        "label_fa": "رژیم کلان",
        "score": score,
        "direction": direction,
        "strength": strength_from_score(score),
        "weight": cfg["base_weights"]["risk_regime"],
        "raw_value": regime,
        "raw_unit": "رژیم",
        "explanation_fa": explain,
        "trend": trend,
        "confidence": round(confidence, 2),
        "meta": {
            "regime": regime,
            "normalized_method": "percentile" if not fallback_used else "static_map",
            "last_updated_at": str(regime_date),
            "data_age_days": data_age,
            "fallback_used": fallback_used,
        },
    }


async def _score_sentiment(session: AsyncSession, as_of: date) -> dict:
    """Driver 6: Sentiment Trend — slope-based trend + level blend."""
    cfg = MOMENTUM_CONFIG

    sent_q = await session.execute(
        select(SentimentTimeline.recorded_at, SentimentTimeline.composite_score)
        .where(SentimentTimeline.composite_score.isnot(None))
        .order_by(desc(SentimentTimeline.recorded_at))
        .limit(cfg["sent_24h_records"])
    )
    sent_rows = sent_q.all()

    if len(sent_rows) < 4:
        return _fallback_driver("sentiment_trend", "روند احساسات", "داده احساسات کافی نیست")

    # Reverse to oldest-first
    sent_rows = list(reversed(sent_rows))
    scores = [float(r.composite_score) for r in sent_rows]
    latest_at = sent_rows[-1].recorded_at
    data_age = (datetime.now(timezone.utc) - latest_at).total_seconds() / 86400 if latest_at else 1

    # Level score: average of last ~6h
    n_6h = min(cfg["sent_6h_records"], len(scores))
    level_score = clamp(statistics.mean(scores[-n_6h:]))

    # Trend score: slope over last 6h and 24h
    slope_6h = linear_slope(scores[-n_6h:]) if n_6h >= 4 else None
    slope_24h = linear_slope(scores) if len(scores) >= 10 else None

    # Blend slopes — prefer 6h for trend detection
    if slope_6h is not None:
        trend_score = clamp(50 + slope_6h * cfg["sent_slope_scale"] * 60)  # scale 5min slope to meaningful range
    elif slope_24h is not None:
        trend_score = clamp(50 + slope_24h * cfg["sent_slope_scale"] * 60)
    else:
        trend_score = 50

    # Final blend
    final = round(clamp(
        cfg["sent_trend_weight"] * trend_score + cfg["sent_level_weight"] * level_score
    ))

    # Trend label
    if slope_6h is not None:
        if slope_6h > 0.05:
            trend = "accelerating"
        elif slope_6h < -0.05:
            trend = "decelerating"
        else:
            trend = "steady"
    else:
        trend = "steady"

    confidence = compute_confidence(data_age, cfg["confidence_decay_rates"]["sentiment_trend"])

    recent_avg = statistics.mean(scores[-n_6h:])
    prev_avg = statistics.mean(scores[:len(scores)//2]) if len(scores) > 2 else recent_avg
    shift = recent_avg - prev_avg
    if shift > 5:
        explain = f"احساسات در حال بهبود ({recent_avg:.0f} ← {prev_avg:.0f})"
    elif shift < -5:
        explain = f"احساسات در حال تضعیف ({recent_avg:.0f} ← {prev_avg:.0f})"
    else:
        explain = f"احساسات ثابت (حدود {recent_avg:.0f})"

    direction, _ = direction_from_score(final)

    return {
        "id": "sentiment_trend",
        "label_fa": "روند احساسات",
        "score": final,
        "direction": direction,
        "strength": strength_from_score(final),
        "weight": cfg["base_weights"]["sentiment_trend"],
        "raw_value": round(recent_avg, 1),
        "raw_unit": "امتیاز",
        "explanation_fa": explain,
        "trend": trend,
        "confidence": round(confidence, 2),
        "meta": {
            "slope_6h": round(slope_6h, 4) if slope_6h is not None else None,
            "slope_24h": round(slope_24h, 4) if slope_24h is not None else None,
            "level_score": round(level_score, 1),
            "trend_score": round(trend_score, 1),
            "window_used": len(scores),
            "normalized_method": "blend",
            "last_updated_at": latest_at.isoformat() if latest_at else None,
            "data_age_days": round(data_age, 1),
            "fallback_used": False,
        },
    }


def _fallback_driver(driver_id: str, label_fa: str, reason: str) -> dict:
    """Neutral fallback when data is unavailable."""
    return {
        "id": driver_id,
        "label_fa": label_fa,
        "score": 50,
        "direction": "neutral",
        "strength": "weak",
        "weight": MOMENTUM_CONFIG["base_weights"].get(driver_id, 15),
        "raw_value": None,
        "raw_unit": "N/A",
        "explanation_fa": f"{reason}. امتیاز پیش‌فرض ۵۰ اعمال شد.",
        "trend": "steady",
        "confidence": 0.3,
        "meta": {
            "normalized_method": "fallback",
            "last_updated_at": None,
            "data_age_days": None,
            "fallback_used": True,
            "window_used": 0,
        },
    }


# ═══════════════════════════════════════════════════════════════════════
#  Main entry point
# ═══════════════════════════════════════════════════════════════════════

async def compute_momentum(
    session: AsyncSession,
    as_of: datetime | None = None,
) -> dict:
    """Compute the full macro momentum dashboard — single entry point.

    Returns backward-compatible dict with additional metadata.
    """
    if as_of is None:
        as_of_dt = datetime.now(timezone.utc)
    else:
        as_of_dt = as_of
    as_of_date = as_of_dt.date() if isinstance(as_of_dt, datetime) else as_of_dt
    run_id = str(uuid4())

    # Score all 6 drivers
    scorers = [
        _score_etf_flow,
        _score_cot,
        _score_real_rates,
        _score_dollar,
        _score_regime,
        _score_sentiment,
    ]

    drivers: list[dict] = []
    warnings: list[str] = []

    for scorer in scorers:
        try:
            drv = await scorer(session, as_of_date)
        except Exception as e:
            logger.exception("Momentum driver error: %s", scorer.__name__)
            drv_name = scorer.__name__.replace("_score_", "")
            # Map back to driver ID
            id_map = {"etf_flow": "etf_flow", "cot": "cot_positioning",
                       "real_rates": "real_rates", "dollar": "dollar_strength",
                       "regime": "risk_regime", "sentiment": "sentiment_trend"}
            drv_id = id_map.get(drv_name, drv_name)
            drv = _fallback_driver(drv_id, drv_name, f"خطا: {str(e)[:50]}")
            warnings.append(f"Error in {drv_name}: {str(e)[:100]}")
        drivers.append(drv)

    # Dynamic weighting: effective_weight = base_weight * confidence
    base_weights = {}
    effective_weights = {}
    confidences = {}
    total_effective = 0.0

    for drv in drivers:
        name = drv["id"]
        bw = drv["weight"]
        conf = drv.get("confidence", 1.0)
        ew = bw * conf
        base_weights[name] = bw
        effective_weights[name] = round(ew, 2)
        confidences[name] = conf
        total_effective += ew

    # Renormalize effective weights to sum to 100
    if total_effective > 0:
        for name in effective_weights:
            effective_weights[name] = round(effective_weights[name] / total_effective * 100, 2)

    # Compute composite using effective weights
    composite = 0.0
    for drv in drivers:
        name = drv["id"]
        composite += drv["score"] * effective_weights.get(name, 0)
    composite = round(composite / 100, 1) if total_effective > 0 else None

    # Direction
    if composite is not None:
        comp_dir, comp_dir_fa = direction_from_score(composite)
    else:
        comp_dir, comp_dir_fa = "pending", "در انتظار داده"

    # Alignment analysis — weighted voting
    bullish_weight = sum(effective_weights.get(d["id"], 0) for d in drivers if d["score"] > 55)
    bearish_weight = sum(effective_weights.get(d["id"], 0) for d in drivers if d["score"] < 45)
    neutral_weight = 100 - bullish_weight - bearish_weight

    max_weight = max(bullish_weight, bearish_weight, neutral_weight)
    aligned = max_weight >= 70

    bullish_count = sum(1 for d in drivers if d["score"] > 55)
    bearish_count = sum(1 for d in drivers if d["score"] < 45)
    neutral_count = len(drivers) - bullish_count - bearish_count

    # Divergence: find highest-weight driver opposing majority
    divergence_warning = False
    divergence_note_fa = ""
    if drivers:
        majority_dir = "bullish" if bullish_weight >= bearish_weight else "bearish"
        best_opposing_weight = 0
        for drv in drivers:
            ew = effective_weights.get(drv["id"], 0)
            is_opposing = (
                (majority_dir == "bullish" and drv["score"] < 45)
                or (majority_dir == "bearish" and drv["score"] > 55)
            )
            if is_opposing and ew > best_opposing_weight:
                best_opposing_weight = ew
                divergence_warning = True
                divergence_note_fa = f"{drv['label_fa']} در جهت مخالف اکثریت — احتیاط کنید"

    alignment = {
        "aligned": aligned,
        "bullish_count": bullish_count,
        "bearish_count": bearish_count,
        "neutral_count": neutral_count,
        "divergence_warning": divergence_warning,
        "divergence_note_fa": divergence_note_fa,
    }

    # Technical context
    tech_ctx = await _compute_technical_context(session)

    # Build backward-compatible driver list (strip meta for old consumers)
    compat_drivers = [
        {
            "id": d["id"],
            "label_fa": d["label_fa"],
            "score": d["score"],
            "direction": d["direction"],
            "strength": d["strength"],
            "weight": d["weight"],
            "raw_value": d["raw_value"],
            "raw_unit": d["raw_unit"],
            "explanation_fa": d["explanation_fa"],
            "trend": d["trend"],
        }
        for d in drivers
    ]

    # Build drivers_meta
    drivers_meta = {
        d["id"]: d.get("meta", {})
        for d in drivers
    }

    computed_at = datetime.now(timezone.utc).isoformat()

    result = {
        # Backward-compatible fields
        "composite_score": composite,
        "composite_direction": comp_dir,
        "composite_direction_fa": comp_dir_fa,
        "alignment": alignment,
        "drivers": sorted(compat_drivers, key=lambda d: d["weight"], reverse=True),
        "technical_context": tech_ctx,
        # New fields (ignored by old frontends)
        "drivers_meta": drivers_meta,
        "weights": {
            "base": base_weights,
            "effective": effective_weights,
        },
        "confidences": confidences,
        "meta": {
            "run_id": run_id,
            "as_of": as_of_date.isoformat(),
            "computed_at": computed_at,
            "engine_version": "2.0",
            "notes": warnings,
        },
        "warnings": warnings,
    }

    # Persist run log
    try:
        await _persist_run_log(session, run_id, as_of_dt, result, drivers)
    except Exception:
        logger.debug("Failed to persist momentum run log", exc_info=True)

    return result


async def _compute_technical_context(session: AsyncSession) -> dict:
    """Compute gold technical context (RSI, daily change, 5d return)."""
    from api.data_collection.indicators import compute_rsi

    tech_ctx: dict = {
        "gold_rsi_14": None,
        "gold_rsi_zone": "unknown",
        "gold_daily_change_pct": None,
        "gold_5d_return_pct": None,
    }

    gold_q = await session.execute(
        select(AssetPriceDaily).where(AssetPriceDaily.symbol == "GC=F")
        .order_by(desc(AssetPriceDaily.trade_date)).limit(20)
    )
    gold_rows = gold_q.scalars().all()
    if gold_rows:
        closes = [r.close for r in reversed(gold_rows) if r.close is not None]
        if len(closes) >= 2:
            tech_ctx["gold_daily_change_pct"] = round(
                (closes[-1] - closes[-2]) / closes[-2] * 100, 2
            )
        if len(closes) >= 5:
            tech_ctx["gold_5d_return_pct"] = round(
                (closes[-1] - closes[-5]) / closes[-5] * 100, 2
            )
        if len(closes) >= 14:
            rsi = compute_rsi(closes)
            if rsi is not None:
                tech_ctx["gold_rsi_14"] = round(rsi, 1)
                if rsi >= 70:
                    tech_ctx["gold_rsi_zone"] = "overbought"
                elif rsi <= 30:
                    tech_ctx["gold_rsi_zone"] = "oversold"
                else:
                    tech_ctx["gold_rsi_zone"] = "neutral"

    return tech_ctx


async def _persist_run_log(
    session: AsyncSession,
    run_id: str,
    as_of: datetime,
    result: dict,
    drivers: list[dict],
) -> None:
    """Store the run in momentum_runs for admin debugging."""
    import json as _json

    raw_inputs = {d["id"]: d.get("raw_value") for d in drivers}
    driver_scores = {d["id"]: d["score"] for d in drivers}

    await session.execute(
        text("""
            INSERT INTO momentum_runs (id, computed_at, as_of, raw_inputs, driver_scores,
                                       weights, composite_score)
            VALUES (:id, :computed_at, :as_of, CAST(:raw_inputs AS jsonb),
                    CAST(:driver_scores AS jsonb), CAST(:weights AS jsonb),
                    :composite_score)
        """),
        {
            "id": run_id,
            "computed_at": datetime.now(timezone.utc),
            "as_of": as_of,
            "raw_inputs": _json.dumps(raw_inputs, default=str),
            "driver_scores": _json.dumps(driver_scores),
            "weights": _json.dumps(result.get("weights", {})),
            "composite_score": result.get("composite_score"),
        },
    )
    await session.commit()
