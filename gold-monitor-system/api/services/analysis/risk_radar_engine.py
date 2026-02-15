"""Risk Radar Engine — statistically robust, percentile/z-score based risk scoring.

Computes a 0-100 composite risk score from 6 components, each normalized via
rolling percentiles or z-scores with confidence-based dynamic weighting.

Components:
    1. Volatility (VIX / GVZ) — percentile over 10-year lookback
    2. Regime — data-driven via realized gold vol conditioned on regime
    3. Sentiment extreme — continuous distance-from-neutral + rate-of-change
    4. COT — net-as-%-of-OI percentile over 5 years, with acceleration
    5. ETF flow — z-score of daily change + 10-day cumulative persistence
    6. Gold-DXY correlation — deviation from typical median over 3 years

All magic numbers live in RISK_CONFIG.  Pure math helpers have no DB deps.
"""

from __future__ import annotations

import logging
import math
import statistics
from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.analysis.models import (
    AssetPriceDaily,
    CorrelationCache,
    CotData,
    EtfHolding,
    RegimeScore,
)
from api.data_collection.models import SentimentTimeline

logger = logging.getLogger("gold_monitor.risk_radar_engine")

# ═══════════════════════════════════════════════════════════════════════
#  Configuration — all tunable constants in one place
# ═══════════════════════════════════════════════════════════════════════

RISK_CONFIG = {
    "base_weights": {
        "volatility": 20,
        "regime": 25,
        "sentiment": 15,
        "cot": 15,
        "etf": 10,
        "correlation": 15,
    },
    # Volatility
    "vol_lookback_years": 10,
    "vol_zscore_multiplier": 15,  # maps 1σ to 15 points
    # Regime
    "regime_vol_window": 10,      # 10-day realized vol
    "regime_lookback_years": 5,
    "regime_fallback_score": 50,
    # Sentiment
    "sent_level_weight": 0.6,
    "sent_change_weight": 0.4,
    "sent_change_scale": 3.0,     # k: daily change multiplier
    # COT
    "cot_lookback_years": 5,
    "cot_acceleration_scale": 20, # multiplier for wow_change_pct_oi
    "cot_stale_threshold_days": 10,
    "cot_confidence_decay_days": 7,
    # ETF
    "etf_zscore_window": 90,
    "etf_zscore_multiplier": 15,  # maps 1σ to 15 points
    "etf_cumulative_window": 10,
    "etf_cumulative_factor": 5,   # maps 1σ of cum_10 to 5 points
    "etf_stale_threshold_days": 3,
    # Correlation
    "corr_lookback_years": 3,
    "corr_iqr_multiplier": 25,    # maps 1 IQR to 25 points
    # Label thresholds
    "label_high": 65,
    "label_moderate": 40,
    # Confidence decay
    "confidence_decay_rates": {
        "volatility": 4,    # days before confidence starts decaying
        "regime": 3,
        "sentiment": 1,     # intraday data, stale fast
        "cot": 7,           # weekly data
        "etf": 2,
        "correlation": 4,
    },
}


# ═══════════════════════════════════════════════════════════════════════
#  Pure math helpers (no DB, no async)
# ═══════════════════════════════════════════════════════════════════════

def percentile_rank(value: float, distribution: list[float]) -> float:
    """Percentile of *value* within *distribution* (0.0-1.0).

    Uses mean method for ties.
    """
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


def logistic_map(x: float, midpoint: float = 50.0, steepness: float = 0.1) -> float:
    """Logistic sigmoid mapping to [0, 100]."""
    return 100.0 / (1.0 + math.exp(-steepness * (x - midpoint)))


def compute_confidence(data_age_days: float, decay_start_days: float) -> float:
    """Confidence decays linearly from 1.0 to 0.3 after decay_start_days.

    Fully stale (>3x decay_start) → confidence 0.3 (never fully zero).
    """
    if data_age_days <= decay_start_days:
        return 1.0
    extra = data_age_days - decay_start_days
    max_extra = decay_start_days * 2  # full decay over 2x period
    decay = min(extra / max_extra, 1.0) * 0.7
    return max(0.3, 1.0 - decay)


def annualized_realized_vol(log_returns: list[float]) -> float | None:
    """Annualized realized vol from daily log returns."""
    if len(log_returns) < 2:
        return None
    return statistics.stdev(log_returns) * math.sqrt(252)


def compute_log_returns(prices: list[float]) -> list[float]:
    """Compute log returns from a price series."""
    returns = []
    for i in range(1, len(prices)):
        if prices[i - 1] > 0 and prices[i] > 0:
            returns.append(math.log(prices[i] / prices[i - 1]))
    return returns


# ═══════════════════════════════════════════════════════════════════════
#  Component scorers (async DB queries → pure score)
# ═══════════════════════════════════════════════════════════════════════

async def _score_volatility(session: AsyncSession, as_of: date) -> dict:
    """Component 1: Volatility — try GVZ, fallback to VIX.

    Normalized by percentile over RISK_CONFIG['vol_lookback_years'].
    """
    cfg = RISK_CONFIG
    lookback = as_of - timedelta(days=cfg["vol_lookback_years"] * 365)

    # Try GVZ first, then VIX
    source_symbol = "^GVZ"
    rows = (await session.execute(
        select(AssetPriceDaily.trade_date, AssetPriceDaily.close)
        .where(AssetPriceDaily.symbol == "^GVZ", AssetPriceDaily.trade_date >= lookback)
        .order_by(AssetPriceDaily.trade_date)
    )).all()

    if len(rows) < 30:
        source_symbol = "^VIX"
        rows = (await session.execute(
            select(AssetPriceDaily.trade_date, AssetPriceDaily.close)
            .where(AssetPriceDaily.symbol == "^VIX", AssetPriceDaily.trade_date >= lookback)
            .order_by(AssetPriceDaily.trade_date)
        )).all()

    if not rows:
        return _fallback_component("volatility", "شاخص نوسان", "داده VIX/GVZ موجود نیست")

    values = [float(r.close) for r in rows]
    dates = [r.trade_date for r in rows]
    current = values[-1]
    latest_date = dates[-1]
    data_age = (as_of - latest_date).days

    # Primary: percentile over full lookback
    pct = percentile_rank(current, values)
    score = round(clamp(pct * 100))

    # If insufficient history (<250 days), fallback to z-score
    fallback_used = False
    if len(values) < 250:
        z = zscore(current, values)
        if z is not None:
            score = round(clamp(50 + z * cfg["vol_zscore_multiplier"]))
            fallback_used = True

    confidence = compute_confidence(data_age, cfg["confidence_decay_rates"]["volatility"])

    return {
        "name": "volatility",
        "name_fa": "شاخص نوسان",
        "score": score,
        "weight": cfg["base_weights"]["volatility"],
        "raw_value": round(current, 2),
        "raw_units": "index",
        "source": source_symbol,
        "last_updated_at": str(latest_date),
        "confidence": round(confidence, 2),
        "explanation_fa": (
            f"{'GVZ' if source_symbol == '^GVZ' else 'VIX'} = {current:.1f} "
            f"(صدک {round(pct * 100)}% در {cfg['vol_lookback_years']} سال). "
            f"{'نوسان بالا → ریسک بیشتر.' if score > 60 else 'نوسان عادی.' if score > 35 else 'نوسان پایین → ریسک کمتر.'}"
        ),
        "percentile": round(pct, 4),
        "window_size": len(values),
        "fallback_used": fallback_used,
        "data_age_days": data_age,
    }


async def _score_regime(session: AsyncSession, as_of: date) -> dict:
    """Component 2: Regime — data-driven via historical realized vol per regime."""
    cfg = RISK_CONFIG
    lookback = as_of - timedelta(days=cfg["regime_lookback_years"] * 365)

    # Get latest regime
    regime_q = await session.execute(
        select(RegimeScore).where(RegimeScore.ts <= as_of).order_by(desc(RegimeScore.ts)).limit(1)
    )
    regime_row = regime_q.scalar_one_or_none()

    if not regime_row or not regime_row.chosen_regime:
        return _fallback_component("regime", "رژیم بازار", "داده رژیم موجود نیست")

    current_regime = regime_row.chosen_regime
    regime_date = regime_row.ts
    data_age = (as_of - regime_date).days

    # Get gold prices for realized vol calculation
    gold_prices_q = await session.execute(
        select(AssetPriceDaily.trade_date, AssetPriceDaily.close)
        .where(AssetPriceDaily.symbol == "GC=F", AssetPriceDaily.trade_date >= lookback)
        .order_by(AssetPriceDaily.trade_date)
    )
    gold_rows = gold_prices_q.all()

    # Get all regime scores for the lookback period
    regime_history_q = await session.execute(
        select(RegimeScore.ts, RegimeScore.chosen_regime)
        .where(RegimeScore.ts >= lookback, RegimeScore.chosen_regime.isnot(None))
        .order_by(RegimeScore.ts)
    )
    regime_history = regime_history_q.all()

    if len(gold_rows) < 20 or len(regime_history) < 10:
        # Not enough data for data-driven approach — use static mapping
        static_map = {"stress": 85, "tightening": 60, "recovery": 40, "expansion": 20}
        score = static_map.get(current_regime, cfg["regime_fallback_score"])
        return {
            "name": "regime",
            "name_fa": "رژیم بازار",
            "score": score,
            "weight": cfg["base_weights"]["regime"],
            "raw_value": current_regime,
            "raw_units": "label",
            "source": "regime_engine",
            "last_updated_at": str(regime_date),
            "confidence": round(compute_confidence(data_age, cfg["confidence_decay_rates"]["regime"]), 2),
            "explanation_fa": f"رژیم فعلی: {current_regime}. داده تاریخی کافی برای تحلیل آماری نیست.",
            "percentile": None,
            "window_size": len(regime_history),
            "fallback_used": True,
            "data_age_days": data_age,
        }

    # Build date→regime map
    regime_map: dict[date, str] = {r.ts: r.chosen_regime for r in regime_history}
    gold_map: dict[date, float] = {r.trade_date: float(r.close) for r in gold_rows}
    gold_dates_sorted = sorted(gold_map.keys())

    # Compute 10-day realized vol for each date and group by regime
    vol_by_regime: dict[str, list[float]] = {}
    window = cfg["regime_vol_window"]
    for i in range(window, len(gold_dates_sorted)):
        d = gold_dates_sorted[i]
        # Find which regime this date was in
        regime_for_date = None
        for rd in sorted(regime_map.keys(), reverse=True):
            if rd <= d:
                regime_for_date = regime_map[rd]
                break
        if regime_for_date is None:
            continue

        window_prices = [gold_map[gold_dates_sorted[j]] for j in range(i - window, i + 1)]
        log_rets = compute_log_returns(window_prices)
        if len(log_rets) >= 2:
            vol = statistics.stdev(log_rets)
            vol_by_regime.setdefault(regime_for_date, []).append(vol)

    # Get current realized vol
    recent_prices = [gold_map[d] for d in gold_dates_sorted[-window - 1:] if d in gold_map]
    current_vol = None
    if len(recent_prices) >= window:
        log_rets = compute_log_returns(recent_prices[-window - 1:])
        if len(log_rets) >= 2:
            current_vol = statistics.stdev(log_rets)

    # Compute percentile of current vol within this regime's historical distribution
    same_regime_vols = vol_by_regime.get(current_regime, [])

    if current_vol is not None and len(same_regime_vols) >= 10:
        pct = percentile_rank(current_vol, same_regime_vols)
        score = round(clamp(pct * 100))
        explanation = (
            f"رژیم: {current_regime}. نوسان محقق‌شده ۱۰ روزه = {current_vol:.4f} "
            f"(صدک {round(pct * 100)}% در این رژیم). "
            f"{'بالاتر از حد عادی → ریسک زیاد.' if score > 60 else 'در محدوده عادی.' if score > 35 else 'پایین‌تر از حد عادی.'}"
        )
        pct_val = round(pct, 4)
    else:
        # Fallback
        static_map = {"stress": 85, "tightening": 60, "recovery": 40, "expansion": 20}
        score = static_map.get(current_regime, cfg["regime_fallback_score"])
        explanation = f"رژیم فعلی: {current_regime}. داده‌های تاریخی محدود — از نقشه ثابت استفاده شد."
        pct_val = None

    confidence = compute_confidence(data_age, cfg["confidence_decay_rates"]["regime"])

    return {
        "name": "regime",
        "name_fa": "رژیم بازار",
        "score": score,
        "weight": cfg["base_weights"]["regime"],
        "raw_value": current_regime,
        "raw_units": "label",
        "source": "regime_engine",
        "last_updated_at": str(regime_date),
        "confidence": round(confidence, 2),
        "explanation_fa": explanation,
        "percentile": pct_val,
        "window_size": len(same_regime_vols),
        "fallback_used": pct_val is None,
        "data_age_days": data_age,
    }


async def _score_sentiment(session: AsyncSession, as_of: date) -> dict:
    """Component 3: Sentiment extreme — continuous distance + rate-of-change."""
    cfg = RISK_CONFIG

    # Get last 2 sentiment readings
    sent_q = await session.execute(
        select(SentimentTimeline)
        .where(SentimentTimeline.composite_score.isnot(None))
        .order_by(desc(SentimentTimeline.recorded_at))
        .limit(2)
    )
    sent_rows = sent_q.scalars().all()

    if not sent_rows or sent_rows[0].composite_score is None:
        return _fallback_component("sentiment", "احساسات بازار", "داده احساسات موجود نیست")

    current_sent = float(sent_rows[0].composite_score)
    prev_sent = float(sent_rows[1].composite_score) if len(sent_rows) > 1 and sent_rows[1].composite_score is not None else current_sent
    latest_at = sent_rows[0].recorded_at
    data_age = (datetime.now(timezone.utc) - latest_at).total_seconds() / 86400 if latest_at else 1

    # Level risk: how far from neutral (50)
    level_risk = abs(current_sent - 50) / 50 * 100  # 0-100

    # Change risk: rate of change
    change_risk = abs(current_sent - prev_sent) * cfg["sent_change_scale"]

    # Combined
    score = round(clamp(
        cfg["sent_level_weight"] * level_risk + cfg["sent_change_weight"] * change_risk
    ))

    direction = "صعودی افراطی" if current_sent > 75 else "نزولی افراطی" if current_sent < 25 else "خنثی"
    confidence = compute_confidence(data_age, cfg["confidence_decay_rates"]["sentiment"])

    return {
        "name": "sentiment",
        "name_fa": "احساسات بازار",
        "score": score,
        "weight": cfg["base_weights"]["sentiment"],
        "raw_value": round(current_sent, 1),
        "raw_units": "score (0-100)",
        "source": "sentiment_timeline",
        "last_updated_at": latest_at.isoformat() if latest_at else None,
        "confidence": round(confidence, 2),
        "explanation_fa": (
            f"احساسات = {current_sent:.0f}/100 ({direction}). "
            f"فاصله از خنثی: {level_risk:.0f}%. تغییر اخیر: {abs(current_sent - prev_sent):.1f} واحد. "
            f"{'احساسات افراطی → ریسک بالاتر (احتمال بازگشت).' if score > 60 else 'احساسات عادی.' if score > 35 else 'احساسات آرام.'}"
        ),
        "percentile": None,
        "window_size": 2,
        "fallback_used": False,
        "data_age_days": round(data_age, 1),
    }


async def _score_cot(session: AsyncSession, as_of: date) -> dict:
    """Component 4: COT — net as % of OI, 5-year rolling percentile, acceleration."""
    cfg = RISK_CONFIG
    lookback = as_of - timedelta(days=cfg["cot_lookback_years"] * 365)

    rows = (await session.execute(
        select(CotData.report_date, CotData.non_commercial_net,
               CotData.open_interest, CotData.change_non_commercial_net)
        .where(CotData.asset == "gold", CotData.report_date >= lookback)
        .where(CotData.non_commercial_net.isnot(None), CotData.open_interest.isnot(None))
        .order_by(CotData.report_date)
    )).all()

    if not rows:
        return _fallback_component("cot", "موقعیت معامله‌گران", "داده COT موجود نیست")

    # Compute net as % of OI for each row
    net_pct_oi = []
    dates = []
    for r in rows:
        if r.open_interest and r.open_interest > 0:
            net_pct_oi.append(float(r.non_commercial_net) / float(r.open_interest) * 100)
            dates.append(r.report_date)

    if not net_pct_oi:
        return _fallback_component("cot", "موقعیت معامله‌گران", "داده OI صفر است")

    current_pct = net_pct_oi[-1]
    latest_date = dates[-1]
    data_age = (as_of - latest_date).days

    # Percentile within rolling window
    pct = percentile_rank(current_pct, net_pct_oi)

    # Score: 0 at middle (50th percentile), 100 at extremes
    cot_score = 100 * (2 * abs(pct - 0.5))

    # Acceleration: week-over-week change as % of OI
    wow_change = 0.0
    if len(net_pct_oi) >= 2:
        wow_change = abs(net_pct_oi[-1] - net_pct_oi[-2])
    cot_score = clamp(cot_score + wow_change * cfg["cot_acceleration_scale"])

    score = round(cot_score)

    # Staleness: reduce confidence if data older than threshold
    confidence = compute_confidence(data_age, cfg["cot_confidence_decay_days"])
    if data_age > cfg["cot_stale_threshold_days"]:
        # Additionally flag as stale
        pass

    position_dir = "خالص خرید بالا" if current_pct > 30 else "خالص فروش" if current_pct < 10 else "متعادل"

    return {
        "name": "cot",
        "name_fa": "موقعیت معامله‌گران",
        "score": score,
        "weight": cfg["base_weights"]["cot"],
        "raw_value": round(current_pct, 2),
        "raw_units": "% of OI",
        "source": "CFTC",
        "last_updated_at": str(latest_date),
        "confidence": round(confidence, 2),
        "explanation_fa": (
            f"موقعیت خالص = {current_pct:.1f}% بهره باز ({position_dir}). "
            f"صدک {round(pct * 100)}% در {cfg['cot_lookback_years']} سال. "
            f"تغییر هفتگی: {wow_change:.2f}%. "
            f"{'نزدیک به افراط → ریسک بالا.' if score > 60 else 'محدوده عادی.' if score > 35 else 'موقعیت آرام.'}"
        ),
        "percentile": round(pct, 4),
        "window_size": len(net_pct_oi),
        "fallback_used": False,
        "data_age_days": data_age,
        "is_stale": data_age > cfg["cot_stale_threshold_days"],
    }


async def _score_etf(session: AsyncSession, as_of: date) -> dict:
    """Component 5: ETF flow — z-score of daily change + 10-day cumulative."""
    cfg = RISK_CONFIG
    window_days = cfg["etf_zscore_window"]
    lookback = as_of - timedelta(days=window_days + 30)

    rows = (await session.execute(
        select(EtfHolding.holding_date, EtfHolding.change_tonnes)
        .where(EtfHolding.fund == "GLD", EtfHolding.holding_date >= lookback)
        .where(EtfHolding.change_tonnes.isnot(None))
        .order_by(EtfHolding.holding_date)
    )).all()

    if not rows:
        return _fallback_component("etf", "جریان صندوق‌ها", "داده ETF موجود نیست")

    changes = [float(r.change_tonnes) for r in rows]
    dates = [r.holding_date for r in rows]
    current_change = changes[-1]
    latest_date = dates[-1]
    data_age = (as_of - latest_date).days

    # Z-score of latest daily change vs last 90 available records
    window_values = changes[-window_days:] if len(changes) >= window_days else changes
    z = zscore(current_change, window_values)

    if z is not None:
        # Magnitude score: outflows (negative change) raise risk, inflows lower it
        # Negative z (outflows) → higher risk; positive z (inflows) → lower risk
        flow_score = clamp(50 - z * cfg["etf_zscore_multiplier"])
    else:
        flow_score = 50

    # Persistence: 10-day cumulative
    cum_values = changes[-cfg["etf_cumulative_window"]:]
    cum_10d = sum(cum_values) if cum_values else 0.0
    # Z-score of cumulative
    if len(changes) > cfg["etf_cumulative_window"]:
        all_cum = []
        for i in range(cfg["etf_cumulative_window"], len(changes)):
            all_cum.append(sum(changes[i - cfg["etf_cumulative_window"]:i]))
        cum_z = zscore(cum_10d, all_cum)
        if cum_z is not None:
            # Negative cumulative z → higher risk
            flow_score = clamp(flow_score - cum_z * cfg["etf_cumulative_factor"])

    score = round(flow_score)
    confidence = compute_confidence(data_age, cfg["confidence_decay_rates"]["etf"])

    direction = "خروج" if current_change < 0 else "ورود" if current_change > 0 else "بدون تغییر"

    return {
        "name": "etf",
        "name_fa": "جریان صندوق‌ها",
        "score": score,
        "weight": cfg["base_weights"]["etf"],
        "raw_value": round(current_change, 2),
        "raw_units": "tonnes/day",
        "source": "SPDR GLD",
        "last_updated_at": str(latest_date),
        "confidence": round(confidence, 2),
        "explanation_fa": (
            f"تغییر روزانه GLD: {current_change:+.2f} تن ({direction}). "
            f"{'z=' + f'{z:+.2f}σ' if z is not None else 'z=N/A'}. "
            f"تجمعی ۱۰ روز: {cum_10d:+.1f} تن. "
            f"{'خروج نهادی → ریسک بالاتر.' if score > 60 else 'جریان عادی.' if score > 35 else 'ورود نهادی → ریسک کمتر.'}"
        ),
        "percentile": None,
        "window_size": len(window_values),
        "fallback_used": z is None,
        "data_age_days": data_age,
    }


async def _score_correlation(session: AsyncSession, as_of: date) -> dict:
    """Component 6: Gold-DXY correlation — deviation from median over 3 years."""
    cfg = RISK_CONFIG
    lookback = as_of - timedelta(days=cfg["corr_lookback_years"] * 365)

    # Get all Gold-DXY correlation values within lookback
    rows = (await session.execute(
        select(CorrelationCache.computed_date, CorrelationCache.correlation)
        .where(
            CorrelationCache.pair_a == "GC=F",
            CorrelationCache.pair_b == "DX-Y.NYB",
            CorrelationCache.computed_date >= lookback,
        )
        .order_by(CorrelationCache.computed_date)
    )).all()

    if not rows:
        return _fallback_component("correlation", "همبستگی دلار-طلا", "داده همبستگی موجود نیست")

    corr_values = [float(r.correlation) for r in rows]
    dates = [r.computed_date for r in rows]
    current_corr = corr_values[-1]
    latest_date = dates[-1]
    data_age = (as_of - latest_date).days

    # Compute median and IQR of historical correlations
    sorted_corrs = sorted(corr_values)
    n = len(sorted_corrs)
    median_corr = statistics.median(sorted_corrs)
    q1 = sorted_corrs[n // 4] if n >= 4 else sorted_corrs[0]
    q3 = sorted_corrs[3 * n // 4] if n >= 4 else sorted_corrs[-1]
    iqr = max(q3 - q1, 0.01)  # avoid division by zero

    # Score: deviation from median, scaled by IQR
    deviation = abs(current_corr - median_corr)
    corr_score = clamp(deviation / iqr * cfg["corr_iqr_multiplier"])

    # Extra penalty if correlation is positive (unusual for gold-dollar)
    if current_corr > 0:
        corr_score = clamp(corr_score + 20)

    score = round(corr_score)
    confidence = compute_confidence(data_age, cfg["confidence_decay_rates"]["correlation"])

    return {
        "name": "correlation",
        "name_fa": "همبستگی دلار-طلا",
        "score": score,
        "weight": cfg["base_weights"]["correlation"],
        "raw_value": round(current_corr, 3),
        "raw_units": "coefficient",
        "source": "correlation_cache (30d Pearson)",
        "last_updated_at": str(latest_date),
        "confidence": round(confidence, 2),
        "explanation_fa": (
            f"همبستگی طلا-دلار = {current_corr:.3f} "
            f"(میانه {cfg['corr_lookback_years']} ساله: {median_corr:.3f}، IQR: {iqr:.3f}). "
            f"{'انحراف بالا از حد عادی → ریسک زیاد.' if score > 60 else 'در محدوده عادی.' if score > 35 else 'رابطه معمول.'}"
        ),
        "percentile": round(percentile_rank(current_corr, corr_values), 4),
        "window_size": len(corr_values),
        "fallback_used": False,
        "data_age_days": data_age,
    }


def _fallback_component(name: str, name_fa: str, reason: str) -> dict:
    """Neutral fallback when data is unavailable."""
    return {
        "name": name,
        "name_fa": name_fa,
        "score": RISK_CONFIG["base_weights"].get(name, 50) and 50,
        "weight": RISK_CONFIG["base_weights"].get(name, 15),
        "raw_value": None,
        "raw_units": "N/A",
        "source": "N/A",
        "last_updated_at": None,
        "confidence": 0.3,
        "explanation_fa": f"{reason}. امتیاز پیش‌فرض ۵۰ اعمال شد.",
        "percentile": None,
        "window_size": 0,
        "fallback_used": True,
        "data_age_days": None,
    }


# ═══════════════════════════════════════════════════════════════════════
#  Main entry points
# ═══════════════════════════════════════════════════════════════════════

async def compute_risk_radar(
    session: AsyncSession,
    as_of: datetime | None = None,
) -> dict:
    """Compute the full risk radar — the single entry point.

    Returns backward-compatible dict with additional metadata.
    """
    if as_of is None:
        as_of_dt = datetime.now(timezone.utc)
    else:
        as_of_dt = as_of
    as_of_date = as_of_dt.date() if isinstance(as_of_dt, datetime) else as_of_dt
    run_id = str(uuid4())

    # Score all 6 components
    scorers = [
        _score_volatility,
        _score_regime,
        _score_sentiment,
        _score_cot,
        _score_etf,
        _score_correlation,
    ]

    components: list[dict] = []
    warnings: list[str] = []

    for scorer in scorers:
        try:
            comp = await scorer(session, as_of_date)
        except Exception as e:
            logger.exception("Risk radar component error: %s", scorer.__name__)
            comp_name = scorer.__name__.replace("_score_", "")
            comp = _fallback_component(comp_name, comp_name, f"خطا: {str(e)[:50]}")
            warnings.append(f"Error in {comp_name}: {str(e)[:100]}")
        components.append(comp)

    # Dynamic weighting: effective_weight = base_weight * confidence
    base_weights = {}
    effective_weights = {}
    confidences = {}
    total_effective = 0.0

    for comp in components:
        name = comp["name"]
        bw = comp["weight"]
        conf = comp.get("confidence", 1.0)
        ew = bw * conf
        base_weights[name] = bw
        effective_weights[name] = round(ew, 2)
        confidences[name] = conf
        total_effective += ew

    # Renormalize effective weights to sum to 100
    if total_effective > 0:
        for name in effective_weights:
            effective_weights[name] = round(effective_weights[name] / total_effective * 100, 2)

    # Compute composite score using effective weights
    composite = 0.0
    for comp in components:
        name = comp["name"]
        composite += comp["score"] * effective_weights.get(name, 0)
    composite = round(composite / 100, 1) if total_effective > 0 else None

    # Label
    if composite is None:
        label = None
    elif composite >= RISK_CONFIG["label_high"]:
        label = "high"
    elif composite >= RISK_CONFIG["label_moderate"]:
        label = "moderate"
    else:
        label = "low"

    # Build backward-compatible components list (existing fields)
    compat_components = [
        {
            "name": c["name"],
            "name_fa": c["name_fa"],
            "score": c["score"],
            "weight": c["weight"],
        }
        for c in components
    ]

    # Full detailed components
    detailed_components = [
        {
            "name": c["name"],
            "name_fa": c["name_fa"],
            "score": c["score"],
            "weight": c["weight"],
            "raw_value": c.get("raw_value"),
            "raw_units": c.get("raw_units"),
            "source": c.get("source"),
            "last_updated_at": c.get("last_updated_at"),
            "confidence": c.get("confidence"),
            "explanation_fa": c.get("explanation_fa"),
            "percentile": c.get("percentile"),
            "window_size": c.get("window_size"),
            "fallback_used": c.get("fallback_used", False),
            "data_age_days": c.get("data_age_days"),
        }
        for c in components
    ]

    computed_at = datetime.now(timezone.utc).isoformat()

    result = {
        # Backward-compatible fields
        "composite_score": composite,
        "label": label,
        "components": compat_components,
        "computed_at": computed_at,
        # New fields (ignored by old frontends)
        "components_detailed": detailed_components,
        "meta": {
            "run_id": run_id,
            "as_of": as_of_date.isoformat(),
            "computed_at": computed_at,
            "engine_version": "2.0",
            "notes": [],
        },
        "weights": {
            "base": base_weights,
            "effective": effective_weights,
        },
        "confidences": confidences,
        "warnings": warnings,
    }

    # Persist run log (fire-and-forget)
    try:
        await _persist_run_log(session, run_id, as_of_dt, result, components)
    except Exception:
        logger.debug("Failed to persist risk radar run log", exc_info=True)

    return result


async def _persist_run_log(
    session: AsyncSession,
    run_id: str,
    as_of: datetime,
    result: dict,
    components: list[dict],
) -> None:
    """Store the run in risk_radar_runs for admin debugging."""
    from sqlalchemy import text

    raw_inputs = {c["name"]: c.get("raw_value") for c in components}
    component_scores = {c["name"]: c["score"] for c in components}

    await session.execute(
        text("""
            INSERT INTO risk_radar_runs (id, computed_at, as_of, raw_inputs, component_scores,
                                         weights, confidences, final_score, label, warnings)
            VALUES (:id, :computed_at, :as_of, :raw_inputs::jsonb, :component_scores::jsonb,
                    :weights::jsonb, :confidences::jsonb, :final_score, :label, :warnings::jsonb)
        """),
        {
            "id": run_id,
            "computed_at": datetime.now(timezone.utc),
            "as_of": as_of,
            "raw_inputs": __import__("json").dumps(raw_inputs, default=str),
            "component_scores": __import__("json").dumps(component_scores),
            "weights": __import__("json").dumps(result.get("weights", {})),
            "confidences": __import__("json").dumps(result.get("confidences", {})),
            "final_score": result.get("composite_score"),
            "label": result.get("label"),
            "warnings": __import__("json").dumps(result.get("warnings", [])),
        },
    )
    await session.commit()
