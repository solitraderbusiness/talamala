"""Historical backtest for the Risk Radar engine.

Downloads 3-5 years of daily data, reconstructs the composite risk score for
each trading day, compares against future realized gold volatility, and produces
correlation / bucket-analysis / hit-rate metrics.

Pure logic module — no DB, no FastAPI.  Importable from an API router.
"""

from __future__ import annotations

import logging
import math
import statistics
from datetime import date, timedelta
from typing import Any

import yfinance as yf

logger = logging.getLogger("analysis.backtest_risk_radar")


# ── Data download ─────────────────────────────────────────────────────

SYMBOLS = {
    "gold": "GC=F",
    "vix": "^VIX",
    "gvz": "^GVZ",
    "dxy": "DX-Y.NYB",
    "gld": "GLD",
}


def fetch_backtest_data(
    start: str = "2020-01-01",
    end: str | None = None,
) -> dict[str, dict[date, float]]:
    """Download daily close prices from Yahoo Finance."""
    if end is None:
        end = date.today().isoformat()

    result: dict[str, dict[date, float]] = {}
    for label, symbol in SYMBOLS.items():
        logger.info("Fetching %s (%s) %s→%s", label, symbol, start, end)
        ticker = yf.Ticker(symbol)
        hist = ticker.history(start=start, end=end, interval="1d")
        if hist.empty:
            logger.warning("No data for %s", symbol)
            result[label] = {}
            continue
        series: dict[date, float] = {}
        for ts, row in hist.iterrows():
            d = ts.date() if hasattr(ts, "date") else ts
            series[d] = float(row["Close"])
        result[label] = series
        logger.info("  %s: %d data points", label, len(series))
    return result


# ── Pure math helpers (duplicated to keep this module self-contained) ──

def _percentile_rank(value: float, distribution: list[float]) -> float:
    if not distribution:
        return 0.5
    n = len(distribution)
    below = sum(1 for v in distribution if v < value)
    equal = sum(1 for v in distribution if v == value)
    return max(0.0, min(1.0, (below + equal / 2.0) / n))


def _zscore(value: float, values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    m = statistics.mean(values)
    s = statistics.stdev(values)
    if s == 0:
        return None
    return (value - m) / s


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _log_returns(prices: list[float]) -> list[float]:
    returns = []
    for i in range(1, len(prices)):
        if prices[i - 1] > 0 and prices[i] > 0:
            returns.append(math.log(prices[i] / prices[i - 1]))
    return returns


def _realized_vol(prices: list[float], window: int = 10) -> float | None:
    """Annualized realized vol from trailing window of prices."""
    if len(prices) < window + 1:
        return None
    log_rets = _log_returns(prices[-window - 1:])
    if len(log_rets) < 2:
        return None
    return statistics.stdev(log_rets) * math.sqrt(252)


# ── Simplified risk score (offline, no sentiment/COT/ETF daily) ────────

def _compute_daily_risk(
    d: date,
    data: dict[str, dict[date, float]],
    all_dates: list[date],
    idx: int,
) -> dict | None:
    """Compute a simplified risk score for a single day.

    Only uses data available from Yahoo (VIX/GVZ, gold vol, gold-DXY corr).
    This is a 3-component proxy of the full 6-component engine.
    """
    gold_prices = data.get("gold", {})
    vix_prices = data.get("vix", {})
    gvz_prices = data.get("gvz", {})
    dxy_prices = data.get("dxy", {})

    # Need at least 250 days of lookback
    if idx < 250:
        return None

    # ── Component 1: Volatility (GVZ or VIX) ──
    vol_values = []
    for j in range(max(0, idx - 2500), idx + 1):
        dd = all_dates[j]
        v = gvz_prices.get(dd) or vix_prices.get(dd)
        if v is not None:
            vol_values.append(v)

    current_vol = gvz_prices.get(d) or vix_prices.get(d)
    if current_vol is None or len(vol_values) < 30:
        vol_score = 50
    else:
        pct = _percentile_rank(current_vol, vol_values)
        vol_score = round(_clamp(pct * 100))

    # ── Component 2: Regime proxy (realized gold vol percentile) ──
    recent_gold = []
    for j in range(max(0, idx - 250), idx + 1):
        dd = all_dates[j]
        gp = gold_prices.get(dd)
        if gp is not None:
            recent_gold.append(gp)

    rv = _realized_vol(recent_gold, window=10) if len(recent_gold) >= 12 else None

    # Historical realized vols for percentile
    hist_rvs = []
    for j in range(250, idx + 1):
        window_prices = []
        for k in range(max(0, j - 10), j + 1):
            gp = gold_prices.get(all_dates[k])
            if gp is not None:
                window_prices.append(gp)
        rv_j = _realized_vol(window_prices, window=10) if len(window_prices) >= 12 else None
        if rv_j is not None:
            hist_rvs.append(rv_j)

    if rv is not None and len(hist_rvs) >= 30:
        regime_score = round(_clamp(_percentile_rank(rv, hist_rvs) * 100))
    else:
        regime_score = 50

    # ── Component 3: Gold-DXY correlation deviation ──
    corr_score = 50
    if idx >= 60:
        gold_window = []
        dxy_window = []
        for j in range(idx - 29, idx + 1):
            dd = all_dates[j]
            gp = gold_prices.get(dd)
            dp = dxy_prices.get(dd)
            if gp is not None and dp is not None:
                gold_window.append(gp)
                dxy_window.append(dp)

        if len(gold_window) >= 20:
            gold_rets = _log_returns(gold_window)
            dxy_rets = _log_returns(dxy_window)
            min_len = min(len(gold_rets), len(dxy_rets))
            if min_len >= 10:
                try:
                    corr = statistics.correlation(gold_rets[:min_len], dxy_rets[:min_len])
                    # Positive gold-DXY correlation is unusual → higher risk
                    deviation = abs(corr - (-0.3))  # typical median ~-0.3
                    corr_score = round(_clamp(deviation / 0.4 * 50))
                    if corr > 0:
                        corr_score = round(_clamp(corr_score + 20))
                except Exception:
                    corr_score = 50

    # ── Composite (3-component proxy) ──
    # Weights: vol=35, regime=35, corr=30
    composite = (vol_score * 35 + regime_score * 35 + corr_score * 30) / 100

    return {
        "date": d.isoformat(),
        "composite_score": round(composite, 1),
        "label": "high" if composite >= 65 else "moderate" if composite >= 40 else "low",
        "vol_score": vol_score,
        "regime_score": regime_score,
        "corr_score": corr_score,
    }


# ── Forward-looking realized vol (ground truth) ────────────────────────

def _future_realized_vol(
    d: date,
    gold_data: dict[date, float],
    sorted_dates: list[date],
    forward_days: int = 20,
) -> float | None:
    """Compute realized vol over the NEXT forward_days from date d."""
    try:
        idx = sorted_dates.index(d)
    except ValueError:
        return None

    if idx + forward_days >= len(sorted_dates):
        return None

    future_prices = []
    for j in range(idx, min(idx + forward_days + 1, len(sorted_dates))):
        gp = gold_data.get(sorted_dates[j])
        if gp is not None:
            future_prices.append(gp)

    if len(future_prices) < forward_days:
        return None

    log_rets = _log_returns(future_prices)
    if len(log_rets) < 2:
        return None

    return statistics.stdev(log_rets) * math.sqrt(252)


# ── Analysis functions ─────────────────────────────────────────────────

def compute_correlation(risk_scores: list[float], future_vols: list[float]) -> float | None:
    """Pearson correlation between risk scores and future realized vol."""
    if len(risk_scores) < 10 or len(risk_scores) != len(future_vols):
        return None
    try:
        return round(statistics.correlation(risk_scores, future_vols), 4)
    except Exception:
        return None


def bucket_analysis(results: list[dict]) -> list[dict]:
    """Group days by risk label and compute avg future vol for each bucket."""
    buckets: dict[str, list[float]] = {"low": [], "moderate": [], "high": []}
    for r in results:
        label = r.get("label", "moderate")
        fv = r.get("future_vol_20d")
        if fv is not None:
            buckets.setdefault(label, []).append(fv)

    analysis = []
    for label in ["low", "moderate", "high"]:
        vals = buckets.get(label, [])
        if vals:
            analysis.append({
                "label": label,
                "count": len(vals),
                "avg_future_vol": round(statistics.mean(vals), 4),
                "median_future_vol": round(statistics.median(vals), 4),
                "min_future_vol": round(min(vals), 4),
                "max_future_vol": round(max(vals), 4),
            })
        else:
            analysis.append({
                "label": label,
                "count": 0,
                "avg_future_vol": None,
                "median_future_vol": None,
                "min_future_vol": None,
                "max_future_vol": None,
            })
    return analysis


def hit_rate(results: list[dict], vol_threshold: float = 0.20) -> dict:
    """Compute hit rate: when risk=high, was future vol actually elevated?"""
    high_risk = [r for r in results if r.get("label") == "high" and r.get("future_vol_20d") is not None]
    low_risk = [r for r in results if r.get("label") == "low" and r.get("future_vol_20d") is not None]

    high_correct = sum(1 for r in high_risk if r["future_vol_20d"] > vol_threshold)
    low_correct = sum(1 for r in low_risk if r["future_vol_20d"] <= vol_threshold)

    return {
        "high_risk_days": len(high_risk),
        "high_risk_correct": high_correct,
        "high_risk_hit_rate": round(high_correct / len(high_risk), 4) if high_risk else None,
        "low_risk_days": len(low_risk),
        "low_risk_correct": low_correct,
        "low_risk_hit_rate": round(low_correct / len(low_risk), 4) if low_risk else None,
        "vol_threshold": vol_threshold,
    }


# ── Main entry point ──────────────────────────────────────────────────

def run_backtest(start: str = "2020-01-01") -> dict:
    """Download data, compute historical risk scores, compare to future vol.

    Returns::

        {
            "history": [...],        # one dict per trading day
            "correlation": float,    # Pearson corr(risk_score, future_vol)
            "bucket_analysis": [...],# avg future vol per risk bucket
            "hit_rate": {...},       # precision of high/low labels
            "summary": {...},
        }
    """
    logger.info("Starting risk radar backtest (%s → today) ...", start)

    # 1. Download
    data = fetch_backtest_data(start=start)

    gold_dates = sorted(data.get("gold", {}).keys())
    if not gold_dates:
        return {"error": "No gold price data available"}

    # Use gold dates as reference calendar
    all_dates = gold_dates

    # 2. Compute daily risk scores
    history: list[dict] = []
    for idx, d in enumerate(all_dates):
        result = _compute_daily_risk(d, data, all_dates, idx)
        if result is not None:
            # 3. Attach future realized vol (ground truth)
            fv = _future_realized_vol(d, data.get("gold", {}), all_dates, forward_days=20)
            result["future_vol_20d"] = round(fv, 4) if fv is not None else None
            history.append(result)

    logger.info("Computed %d risk score data points", len(history))

    if not history:
        return {"error": "Insufficient data for backtest"}

    # 4. Analysis
    scores = [r["composite_score"] for r in history if r.get("future_vol_20d") is not None]
    fvols = [r["future_vol_20d"] for r in history if r.get("future_vol_20d") is not None]

    corr = compute_correlation(scores, fvols)
    buckets = bucket_analysis(history)
    hr = hit_rate(history)

    # 5. Subsample history if too large
    if len(history) > 2000:
        step = len(history) // 1500
        history_out = history[::step]
    else:
        history_out = history

    date_range = ""
    if history:
        date_range = f"{history[0]['date']} → {history[-1]['date']}"

    summary = {
        "total_days": len(history),
        "date_range": date_range,
        "correlation_score_vs_future_vol": corr,
        "passed": corr is not None and corr > 0.15,
        "engine_note": "3-component proxy (VIX/GVZ, gold realized vol, gold-DXY corr). "
                       "Full 6-component engine requires DB data (sentiment, COT, ETF).",
    }

    logger.info(
        "Backtest complete: %d days, corr=%.4f, high_hit=%.2f%%",
        len(history),
        corr or 0,
        (hr.get("high_risk_hit_rate") or 0) * 100,
    )

    return {
        "history": history_out,
        "correlation": corr,
        "bucket_analysis": buckets,
        "hit_rate": hr,
        "summary": summary,
    }
