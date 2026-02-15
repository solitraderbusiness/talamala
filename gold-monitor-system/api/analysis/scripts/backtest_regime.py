"""Historical backtest for the liquidity regime engine.

Downloads 10+ years of data from Yahoo Finance and FRED, runs the exact same
regime math as ``regime_engine.py``, and validates against well-documented
macro periods.

Pure logic module — no DB, no FastAPI.  Importable from an API router.
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime

import httpx
import yfinance as yf

from api.analysis.workers.regime_engine import (
    EWMA_ALPHA,
    REGIME_LABELS,
    Z_WINDOW,
    _spx_drawdown,
    compute_credit_proxy,
    ewma_smooth,
    log_return,
    rolling_zscore,
    softmax,
)

logger = logging.getLogger("analysis.backtest")

# ── Yahoo Finance data ────────────────────────────────────────────────

YAHOO_SYMBOLS = ["DX-Y.NYB", "^VIX", "^GSPC", "HYG", "IEF"]


def fetch_yahoo_data(
    symbols: list[str] | None = None,
    start: str = "2014-01-01",
    end: str | None = None,
) -> dict[str, dict[date, float]]:
    """Download daily close prices from Yahoo Finance.

    Returns ``{symbol: {date: close_price}}``.
    """
    if symbols is None:
        symbols = YAHOO_SYMBOLS
    if end is None:
        end = date.today().isoformat()

    result: dict[str, dict[date, float]] = {}
    for symbol in symbols:
        logger.info("Fetching Yahoo data for %s (%s → %s)", symbol, start, end)
        ticker = yf.Ticker(symbol)
        hist = ticker.history(start=start, end=end, interval="1d")
        if hist.empty:
            logger.warning("No Yahoo data for %s", symbol)
            result[symbol] = {}
            continue
        series: dict[date, float] = {}
        for ts, row in hist.iterrows():
            d = ts.date() if hasattr(ts, "date") else ts
            series[d] = float(row["Close"])
        result[symbol] = series
        logger.info("  %s: %d data points", symbol, len(series))
    return result


# ── FRED data ─────────────────────────────────────────────────────────

FRED_SERIES = ["DFII10", "DGS10"]


def fetch_fred_data(
    series_ids: list[str] | None = None,
    start: str = "2014-01-01",
    end: str | None = None,
    api_key: str | None = None,
) -> dict[str, dict[date, float]]:
    """Download observations from the FRED REST API.

    Returns ``{series_id: {date: value}}``.
    """
    if series_ids is None:
        series_ids = FRED_SERIES
    if end is None:
        end = date.today().isoformat()
    if api_key is None:
        api_key = os.environ.get("FRED_API_KEY", "")

    result: dict[str, dict[date, float]] = {}
    for sid in series_ids:
        logger.info("Fetching FRED series %s (%s → %s)", sid, start, end)
        url = (
            f"https://api.stlouisfed.org/fred/series/observations"
            f"?series_id={sid}&observation_start={start}&observation_end={end}"
            f"&api_key={api_key}&file_type=json"
        )
        try:
            resp = httpx.get(url, timeout=30.0)
            resp.raise_for_status()
            data = resp.json()
            series: dict[date, float] = {}
            for obs in data.get("observations", []):
                val = obs.get("value", ".")
                if val == "." or val is None:
                    continue
                try:
                    d = datetime.strptime(obs["date"], "%Y-%m-%d").date()
                    series[d] = float(val)
                except (ValueError, KeyError):
                    continue
            result[sid] = series
            logger.info("  %s: %d data points", sid, len(series))
        except Exception:
            logger.warning("Failed to fetch FRED series %s", sid, exc_info=True)
            result[sid] = {}
    return result


# ── Core computation (mirrors regime_engine.run() lines 205-314) ──────

def align_and_compute(
    yahoo_data: dict[str, dict[date, float]],
    fred_data: dict[str, dict[date, float]],
) -> list[dict]:
    """Build aligned series, compute indices, scores, and smoothed probs.

    Returns a list of dicts sorted by date, one per trading day.
    """
    # Use DXY dates as reference calendar
    dxy_dates_set = yahoo_data.get("DX-Y.NYB", {})
    if not dxy_dates_set:
        return []

    all_dates = sorted(dxy_dates_set.keys())

    def _get(series: dict[date, float], d: date) -> float | None:
        return series.get(d)

    # Forward-fill helper for FRED (published on weekdays, may skip some)
    def _ffill(series: dict[date, float], dates: list[date]) -> list[float | None]:
        vals: list[float | None] = []
        last: float | None = None
        for d in dates:
            v = series.get(d)
            if v is not None:
                last = v
            vals.append(last)
        return vals

    # Build aligned lists
    dxy_prices = [_get(yahoo_data.get("DX-Y.NYB", {}), d) for d in all_dates]
    vix_prices = [_get(yahoo_data.get("^VIX", {}), d) for d in all_dates]
    spx_prices = [_get(yahoo_data.get("^GSPC", {}), d) for d in all_dates]
    hyg_prices = [_get(yahoo_data.get("HYG", {}), d) for d in all_dates]
    ief_prices = [_get(yahoo_data.get("IEF", {}), d) for d in all_dates]
    dfii10_vals = _ffill(fred_data.get("DFII10", {}), all_dates)
    dgs10_vals = _ffill(fred_data.get("DGS10", {}), all_dates)

    # ── Compute intermediate series (identical to regime_engine.py) ──
    dxy_ret20 = log_return(dxy_prices, lag=20)
    z_dxy_ret20 = rolling_zscore(dxy_ret20, Z_WINDOW)

    z_vix = rolling_zscore(vix_prices, Z_WINDOW)

    credit = compute_credit_proxy(hyg_prices, ief_prices)
    z_credit = rolling_zscore(credit, Z_WINDOW)

    spx_dd = _spx_drawdown(spx_prices, Z_WINDOW)
    z_spx_dd = rolling_zscore(spx_dd, Z_WINDOW)

    # Real yield with fallback chain
    real_yield_vals: list[float | None] = []
    for i in range(len(all_dates)):
        if dfii10_vals[i] is not None:
            real_yield_vals.append(dfii10_vals[i])
        elif dgs10_vals[i] is not None:
            real_yield_vals.append(dgs10_vals[i])
        else:
            real_yield_vals.append(None)
    z_real_yield = rolling_zscore(real_yield_vals, Z_WINDOW)

    # ── LSI ──
    lsi_values: list[float | None] = []
    for i in range(len(all_dates)):
        zv = z_vix[i]
        zc = z_credit[i]
        zs = z_spx_dd[i]
        if zv is not None:
            _zc = zc if zc is not None else 0.0
            _zs = zs if zs is not None else 0.0
            raw = 0.5 * zv + 0.3 * _zc + 0.2 * _zs
            lsi_values.append(max(-3.0, min(3.0, raw)))
        else:
            lsi_values.append(None)

    # ── delta_LSI_20 ──
    delta_lsi_20: list[float | None] = []
    for i in range(len(all_dates)):
        if i >= 20 and lsi_values[i] is not None and lsi_values[i - 20] is not None:
            delta_lsi_20.append(max(0.0, lsi_values[i - 20] - lsi_values[i]))
        else:
            delta_lsi_20.append(0.0)

    # ── Regime scores + softmax ──
    raw_probs: list[list[float] | None] = []
    computed_dates: list[date] = []
    computed_indices: list[dict] = []

    for i, d in enumerate(all_dates):
        lsi = lsi_values[i]
        usdx = z_dxy_ret20[i]
        rypi = z_real_yield[i]

        if lsi is None or usdx is None:
            raw_probs.append(None)
            continue

        _rypi = rypi if rypi is not None else 0.0
        _dlsi = delta_lsi_20[i] if delta_lsi_20[i] is not None else 0.0

        s_stress = 1.2 * lsi + 0.3 * usdx + 0.3 * _rypi
        s_tight = 0.8 * _rypi + 0.6 * usdx - 0.4 * lsi
        s_exp = -0.7 * _rypi - 0.6 * usdx - 0.8 * lsi
        s_recov = -0.8 * lsi - 0.2 * _rypi - 0.2 * usdx + 0.5 * _dlsi

        probs = softmax([s_exp, s_tight, s_stress, s_recov])
        raw_probs.append(probs)
        computed_dates.append(d)
        computed_indices.append({"lsi": lsi, "usdx": usdx, "rypi": _rypi})

    if not computed_dates:
        return []

    # ── EWMA smoothing ──
    valid_probs = [p for p in raw_probs if p is not None]
    smoothed = ewma_smooth(valid_probs, EWMA_ALPHA)

    # ── Build output ──
    results: list[dict] = []
    for idx, d in enumerate(computed_dates):
        sm_p = smoothed[idx]
        chosen = REGIME_LABELS[sm_p.index(max(sm_p))]
        results.append({
            "date": d.isoformat(),
            "lsi": round(computed_indices[idx]["lsi"], 4),
            "usdx": round(computed_indices[idx]["usdx"], 4),
            "rypi": round(computed_indices[idx]["rypi"], 4),
            "smoothed_p_expansion": round(sm_p[0], 4),
            "smoothed_p_tightening": round(sm_p[1], 4),
            "smoothed_p_stress": round(sm_p[2], 4),
            "smoothed_p_recovery": round(sm_p[3], 4),
            "chosen_regime": chosen,
        })

    return results


# ── Benchmark validation ──────────────────────────────────────────────

BENCHMARKS = [
    {
        "name": "2018 Q4 Sell-off",
        "start": "2018-10-01",
        "end": "2018-12-31",
        "expected": ["stress"],
        "threshold": 0.35,
    },
    {
        "name": "COVID Crash",
        "start": "2020-02-20",
        "end": "2020-03-31",
        "expected": ["stress"],
        "threshold": 0.45,
    },
    {
        "name": "Post-COVID QE",
        "start": "2020-06-01",
        "end": "2021-06-30",
        "expected": ["expansion", "recovery"],
        "threshold": 0.35,
    },
    {
        "name": "2022 H1 Rate Hikes",
        "start": "2022-01-01",
        "end": "2022-06-30",
        "expected": ["tightening"],
        "threshold": 0.35,
    },
    {
        "name": "SVB Crisis",
        "start": "2023-03-01",
        "end": "2023-03-31",
        "expected": ["stress"],
        "threshold": 0.30,
    },
    {
        "name": "Late 2023 Pivot",
        "start": "2023-11-01",
        "end": "2024-01-31",
        "expected": ["expansion"],
        "threshold": 0.30,
    },
    {
        "name": "2025-2026 Current",
        "start": "2025-06-01",
        "end": "2026-02-28",
        "expected": ["expansion"],
        "threshold": 0.35,
    },
]


def validate_benchmarks(results: list[dict]) -> list[dict]:
    """Compare backtest output against known macro periods.

    A benchmark passes if the average smoothed probability for the expected
    regime exceeds the threshold, OR the expected regime is dominant for
    >50% of the days in the period.
    """
    # Index results by date for fast lookup
    by_date: dict[str, dict] = {r["date"]: r for r in results}

    validations: list[dict] = []
    for bm in BENCHMARKS:
        start_d = date.fromisoformat(bm["start"])
        end_d = date.fromisoformat(bm["end"])
        expected_regimes: list[str] = bm["expected"]
        threshold: float = bm["threshold"]

        # Collect rows in the benchmark period
        period_rows = [
            r for d_str, r in by_date.items()
            if start_d <= date.fromisoformat(d_str) <= end_d
        ]

        if not period_rows:
            validations.append({
                "name": bm["name"],
                "start": bm["start"],
                "end": bm["end"],
                "expected": ", ".join(expected_regimes),
                "avg_prob": 0.0,
                "pct_days_correct": 0.0,
                "passed": False,
                "reason": "No data in period",
            })
            continue

        # Avg smoothed prob for best expected regime
        best_avg = 0.0
        best_regime = expected_regimes[0]
        for regime in expected_regimes:
            key = f"smoothed_p_{regime}"
            avg = sum(r.get(key, 0.0) for r in period_rows) / len(period_rows)
            if avg > best_avg:
                best_avg = avg
                best_regime = regime

        # Pct of days where expected regime is dominant
        days_correct = sum(
            1 for r in period_rows if r["chosen_regime"] in expected_regimes
        )
        pct_correct = days_correct / len(period_rows)

        passed = best_avg >= threshold or pct_correct > 0.5

        if passed:
            reason = f"{best_regime} avg={best_avg:.1%}, dominant {pct_correct:.0%} of days"
        else:
            reason = f"{best_regime} avg={best_avg:.1%} < {threshold:.0%}, dominant only {pct_correct:.0%}"

        validations.append({
            "name": bm["name"],
            "start": bm["start"],
            "end": bm["end"],
            "expected": ", ".join(expected_regimes),
            "avg_prob": round(best_avg, 4),
            "pct_days_correct": round(pct_correct, 4),
            "passed": passed,
            "reason": reason,
        })

    return validations


# ── Main entry point ──────────────────────────────────────────────────

def run_backtest(fred_api_key: str | None = None) -> dict:
    """Download historical data, run regime engine, validate benchmarks.

    Returns::

        {
            "history": [...],       # one dict per trading day
            "benchmarks": [...],    # 7 benchmark results
            "summary": {
                "total_days": int,
                "passed": int,
                "failed": int,
                "date_range": str,
            },
        }
    """
    logger.info("Starting historical backtest ...")

    # 1. Download data
    yahoo_data = fetch_yahoo_data(start="2014-01-01")
    fred_data = fetch_fred_data(api_key=fred_api_key, start="2014-01-01")

    # 2. Compute regime history
    history = align_and_compute(yahoo_data, fred_data)
    logger.info("Computed %d regime data points", len(history))

    # 3. Validate benchmarks
    benchmarks = validate_benchmarks(history)
    passed = sum(1 for b in benchmarks if b["passed"])
    failed = len(benchmarks) - passed

    # 4. Subsample history if too large (keep under ~300KB response)
    if len(history) > 3000:
        step = len(history) // 2500
        history = history[::step]
        logger.info("Subsampled history to %d points (step=%d)", len(history), step)

    date_range = ""
    if history:
        date_range = f"{history[0]['date']} → {history[-1]['date']}"

    summary = {
        "total_days": len(history),
        "passed": passed,
        "failed": failed,
        "date_range": date_range,
    }

    logger.info("Backtest complete: %d days, %d/%d benchmarks passed",
                len(history), passed, len(benchmarks))

    return {
        "history": history,
        "benchmarks": benchmarks,
        "summary": summary,
    }
