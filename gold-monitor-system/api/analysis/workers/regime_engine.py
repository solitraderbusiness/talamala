"""Liquidity Regime Engine — deterministic macro regime classifier.

Computes daily scores for 4 (+1 mixed) macro regimes:
- EXPANSION: low yields, weak dollar, low stress
- TIGHTENING: high yields, strong dollar, low stress
- STRESS: high VIX, credit widening, equity drawdown
- RECOVERY: falling stress (delta_LSI > 0)
- MIXED: scores too close to call (top < 0.45 or gap < 0.08)

Indices
-------
- LSI (Liquidity Stress Index): 0.5*z_vix + 0.3*z_credit + 0.2*z_spx_dd
- USDX: zscore(20d return of DXY)
- RYPI (Real Yield Pressure Index): zscore(DFII10 level) with fallback chain

Credit proxy
------------
- Primary: FRED BAMLH0A0HYM2 (ICE BofA US High Yield OAS)
- Fallback: -ln(HYG/IEF) price-based proxy
- Source tracked as credit_proxy_source = "fred_oas" | "hyg_ief" | "none"

Real yield
----------
- Primary: DFII10 (TIPS-derived real yield)
- Fallback A: DGS10 - T10YIE (nominal minus breakeven inflation)
- Fallback B: None — RYPI excluded from scoring when missing
- Source tracked as real_yield_source = "dfii10" | "nominal_minus_breakeven" | "missing"

Scoring
-------
- S_stress  = 1.2*LSI + 0.3*USDX + 0.3*RYPI
- S_tight   = 0.8*RYPI + 0.6*USDX - 0.4*LSI
- S_exp     = -0.7*RYPI - 0.6*USDX - 0.8*LSI
- S_recov   = -0.8*LSI - 0.2*RYPI - 0.2*USDX + 0.5*delta_LSI_20

Raw scores via softmax → EWMA smoothed (alpha=0.2).
Output labeled "relative_regime_scores" (NOT probabilities).

Mixed regime
------------
- top = max(smoothed_scores), second = 2nd highest
- If top < 0.45 OR (top - second) < 0.08 → chosen_regime = "mixed"
- chosen_regime_raw always contains the argmax (for debugging)

No-lookahead guarantee: all series alignment uses only data at or before date t.
"""

from __future__ import annotations

import logging
import math
import os
from datetime import date, datetime, timedelta, timezone
from typing import Sequence

from sqlalchemy import select

from api.database import AsyncSessionLocal
from api.analysis.models import (
    AssetPriceDaily,
    MacroIndicator,
    RegimeAuditLog,
    RegimeScore,
)

logger = logging.getLogger("analysis.regime")

# ── Configuration ────────────────────────────────────────────────────

Z_WINDOW = int(os.environ.get("REGIME_ZSCORE_WINDOW", "252"))
EWMA_ALPHA = float(os.environ.get("REGIME_EWMA_ALPHA", "0.2"))

# Mixed regime thresholds
MIXED_MIN_TOP = 0.45        # top score must exceed this to be decisive
MIXED_MIN_GAP = 0.08        # gap between top and second must exceed this

REGIMES = ["expansion", "tightening", "stress", "recovery"]
REGIME_LABELS = {0: "expansion", 1: "tightening", 2: "stress", 3: "recovery"}


# ── Pure-math helpers (no DB, no pandas) ─────────────────────────────

def rolling_zscore(values: list[float | None], n: int = 252) -> list[float | None]:
    """Compute rolling z-score with window *n*, clipped to [-3, +3].

    Returns None for positions with insufficient history or zero std.
    """
    result: list[float | None] = []
    eps = 1e-9
    for i in range(len(values)):
        if values[i] is None:
            result.append(None)
            continue
        # Collect window
        window: list[float] = []
        for j in range(max(0, i - n + 1), i + 1):
            if values[j] is not None:
                window.append(values[j])
        if len(window) < 20:  # minimum samples for meaningful z-score
            result.append(None)
            continue
        mean = sum(window) / len(window)
        var = sum((x - mean) ** 2 for x in window) / len(window)
        std = math.sqrt(var) if var > 0 else eps
        z = (values[i] - mean) / std
        z = max(-3.0, min(3.0, z))
        result.append(z)
    return result


def log_return(prices: list[float | None], lag: int = 1) -> list[float | None]:
    """Compute ln(p[t] / p[t-lag]). Returns None where data is missing."""
    result: list[float | None] = [None] * len(prices)
    for i in range(lag, len(prices)):
        if prices[i] is not None and prices[i - lag] is not None:
            if prices[i - lag] > 0 and prices[i] > 0:
                result[i] = math.log(prices[i] / prices[i - lag])
    return result


def compute_credit_proxy(hyg: list[float | None], ief: list[float | None]) -> list[float | None]:
    """Credit proxy = -ln(HYG / IEF). Higher = wider spreads = more stress."""
    result: list[float | None] = []
    for h, e in zip(hyg, ief):
        if h is not None and e is not None and h > 0 and e > 0:
            result.append(-math.log(h / e))
        else:
            result.append(None)
    return result


def merge_credit_series(
    fred_oas: list[float | None],
    hyg_ief: list[float | None],
) -> tuple[list[float | None], list[str]]:
    """Merge FRED OAS (primary) with HYG/IEF fallback for credit stress.

    Returns (merged_values, source_per_date).
    """
    merged: list[float | None] = []
    sources: list[str] = []
    for oas, proxy in zip(fred_oas, hyg_ief):
        if oas is not None:
            merged.append(oas)
            sources.append("fred_oas")
        elif proxy is not None:
            merged.append(proxy)
            sources.append("hyg_ief")
        else:
            merged.append(None)
            sources.append("none")
    return merged, sources


def softmax(scores: list[float]) -> list[float]:
    """Numerically stable softmax."""
    max_s = max(scores)
    exps = [math.exp(s - max_s) for s in scores]
    total = sum(exps)
    return [e / total for e in exps]


def ewma_smooth(
    series: list[list[float]], alpha: float = 0.2,
) -> list[list[float]]:
    """EWMA on a sequence of score vectors.

    Each element is [s_exp, s_tight, s_stress, s_recov].
    Returns smoothed vectors that still sum to ~1.0.
    """
    if not series:
        return []
    result = [series[0][:]]  # first vector unchanged
    for i in range(1, len(series)):
        prev = result[-1]
        cur = series[i]
        smoothed = [alpha * c + (1 - alpha) * p for c, p in zip(cur, prev)]
        # Renormalize to sum to 1
        total = sum(smoothed)
        if total > 0:
            smoothed = [s / total for s in smoothed]
        result.append(smoothed)
    return result


def classify_regime(
    smoothed_scores: list[float],
    min_top: float = MIXED_MIN_TOP,
    min_gap: float = MIXED_MIN_GAP,
) -> tuple[str, str, str | None]:
    """Classify regime from smoothed softmax scores.

    Returns (chosen_regime, chosen_regime_raw, chosen_note_fa).
    - chosen_regime_raw = argmax (always)
    - chosen_regime = "mixed" if uncertainty is too high, else argmax
    """
    top_val = max(smoothed_scores)
    top_idx = smoothed_scores.index(top_val)
    regime_raw = REGIME_LABELS[top_idx]

    # Find second highest
    sorted_scores = sorted(smoothed_scores, reverse=True)
    second_val = sorted_scores[1] if len(sorted_scores) > 1 else 0.0
    gap = top_val - second_val

    if top_val < min_top or gap < min_gap:
        return (
            "mixed",
            regime_raw,
            "عدم قطعیت بالا — امتیاز رژیم‌ها نزدیک است",
        )

    return regime_raw, regime_raw, None


def _spx_drawdown(closes: list[float | None], window: int = 252) -> list[float | None]:
    """Compute S&P 500 drawdown from rolling high. Returns values in [0, +inf)."""
    result: list[float | None] = []
    for i in range(len(closes)):
        if closes[i] is None:
            result.append(None)
            continue
        lookback = closes[max(0, i - window + 1):i + 1]
        valid = [v for v in lookback if v is not None]
        if not valid:
            result.append(None)
            continue
        rolling_high = max(valid)
        dd = (rolling_high - closes[i]) / rolling_high if rolling_high > 0 else 0.0
        result.append(max(0.0, dd))
    return result


# ── Main worker ──────────────────────────────────────────────────────

async def run() -> dict:
    """Compute regime scores from existing price/macro data."""
    logger.info("Starting regime engine computation ...")

    async with AsyncSessionLocal() as session:
        # --- Fetch all required series from DB ---
        # Use earliest available price date (enables deep history after backfill)
        earliest_q = await session.execute(
            select(AssetPriceDaily.trade_date)
            .where(AssetPriceDaily.symbol == "DX-Y.NYB")
            .order_by(AssetPriceDaily.trade_date)
            .limit(1)
        )
        earliest_row = earliest_q.scalar_one_or_none()
        if earliest_row:
            cutoff = earliest_row
        else:
            cutoff = date.today() - timedelta(days=Z_WINDOW + 100)

        # Asset prices
        price_series: dict[str, dict[date, float]] = {}
        for symbol in ["DX-Y.NYB", "^VIX", "^GSPC", "HYG", "IEF"]:
            rows = await session.execute(
                select(AssetPriceDaily.trade_date, AssetPriceDaily.close)
                .where(
                    AssetPriceDaily.symbol == symbol,
                    AssetPriceDaily.trade_date >= cutoff,
                )
                .order_by(AssetPriceDaily.trade_date)
            )
            price_series[symbol] = {r.trade_date: r.close for r in rows}

        # FRED macro — DFII10 (real yield), DGS10, T10YIE, BAMLH0A0HYM2 (HY OAS)
        macro_series: dict[str, dict[date, float]] = {}
        for series_id in ["DFII10", "DGS10", "T10YIE", "BAMLH0A0HYM2"]:
            rows = await session.execute(
                select(MacroIndicator.observation_date, MacroIndicator.value)
                .where(
                    MacroIndicator.series_id == series_id,
                    MacroIndicator.observation_date >= cutoff,
                )
                .order_by(MacroIndicator.observation_date)
            )
            macro_series[series_id] = {r.observation_date: r.value for r in rows}

        # --- Build aligned date series ---
        # Collect all dates that have DXY data (as the reference calendar)
        all_dates = sorted(price_series.get("DX-Y.NYB", {}).keys())
        if not all_dates:
            logger.warning("No DXY price data — cannot compute regimes")
            return {"status": "skipped", "reason": "no DXY data"}

        def _get(series_dict: dict[date, float], d: date) -> float | None:
            return series_dict.get(d)

        # Build aligned lists (no forward fill — only exact date matches)
        dates: list[date] = all_dates
        dxy_prices = [_get(price_series.get("DX-Y.NYB", {}), d) for d in dates]
        vix_prices = [_get(price_series.get("^VIX", {}), d) for d in dates]
        spx_prices = [_get(price_series.get("^GSPC", {}), d) for d in dates]
        hyg_prices = [_get(price_series.get("HYG", {}), d) for d in dates]
        ief_prices = [_get(price_series.get("IEF", {}), d) for d in dates]
        dfii10_vals = [_get(macro_series.get("DFII10", {}), d) for d in dates]
        dgs10_vals = [_get(macro_series.get("DGS10", {}), d) for d in dates]
        t10yie_vals = [_get(macro_series.get("T10YIE", {}), d) for d in dates]
        hy_oas_vals = [_get(macro_series.get("BAMLH0A0HYM2", {}), d) for d in dates]

        # --- Compute intermediate series ---
        # DXY 20-day log return
        dxy_ret20 = log_return(dxy_prices, lag=20)
        z_dxy_ret20 = rolling_zscore(dxy_ret20, Z_WINDOW)

        # VIX z-score (level)
        z_vix = rolling_zscore(vix_prices, Z_WINDOW)

        # Credit proxy: primary = FRED OAS, fallback = -ln(HYG/IEF)
        hyg_ief_proxy = compute_credit_proxy(hyg_prices, ief_prices)
        credit_merged, credit_sources = merge_credit_series(hy_oas_vals, hyg_ief_proxy)
        z_credit = rolling_zscore(credit_merged, Z_WINDOW)

        # S&P 500 drawdown z-score
        spx_dd = _spx_drawdown(spx_prices, Z_WINDOW)
        z_spx_dd = rolling_zscore(spx_dd, Z_WINDOW)

        # Real yield: DFII10 → (DGS10 - T10YIE) → None
        real_yield_vals: list[float | None] = []
        real_yield_sources: list[str] = []
        for i, d in enumerate(dates):
            if dfii10_vals[i] is not None:
                real_yield_vals.append(dfii10_vals[i])
                real_yield_sources.append("dfii10")
            elif dgs10_vals[i] is not None and t10yie_vals[i] is not None:
                # Approximate real yield = nominal - breakeven inflation
                real_yield_vals.append(dgs10_vals[i] - t10yie_vals[i])
                real_yield_sources.append("nominal_minus_breakeven")
            else:
                real_yield_vals.append(None)
                real_yield_sources.append("missing")
        z_real_yield = rolling_zscore(real_yield_vals, Z_WINDOW)

        # Track staleness per series (last non-None date)
        def _last_valid_date(vals: list[float | None]) -> str | None:
            for i in range(len(vals) - 1, -1, -1):
                if vals[i] is not None:
                    return str(dates[i])
            return None

        staleness_info = {
            "vix_last": _last_valid_date(vix_prices),
            "dxy_last": _last_valid_date(dxy_prices),
            "hyg_last": _last_valid_date(hyg_prices),
            "ief_last": _last_valid_date(ief_prices),
            "hy_oas_last": _last_valid_date(hy_oas_vals),
            "dfii10_last": _last_valid_date(dfii10_vals),
            "dgs10_last": _last_valid_date(dgs10_vals),
            "t10yie_last": _last_valid_date(t10yie_vals),
            "spx_last": _last_valid_date(spx_prices),
        }

        # --- Compute LSI (Liquidity Stress Index) ---
        lsi_values: list[float | None] = []
        for i in range(len(dates)):
            zv = z_vix[i]
            zc = z_credit[i]
            zs = z_spx_dd[i]
            if zv is not None:
                # Use available components, default missing to 0
                _zc = zc if zc is not None else 0.0
                _zs = zs if zs is not None else 0.0
                raw = 0.5 * zv + 0.3 * _zc + 0.2 * _zs
                lsi_values.append(max(-3.0, min(3.0, raw)))
            else:
                lsi_values.append(None)

        # --- Compute delta_LSI_20 = max(0, LSI(t-20) - LSI(t)) ---
        delta_lsi_20: list[float | None] = []
        for i in range(len(dates)):
            if i >= 20 and lsi_values[i] is not None and lsi_values[i - 20] is not None:
                delta_lsi_20.append(max(0.0, lsi_values[i - 20] - lsi_values[i]))
            else:
                delta_lsi_20.append(0.0)

        # --- Compute regime scores for each date ---
        raw_probs: list[list[float] | None] = []
        computed_dates: list[date] = []
        computed_indices: list[dict] = []
        computed_scores_raw: list[dict] = []
        computed_ry_sources: list[str] = []
        computed_credit_sources: list[str] = []
        computed_rypi_included: list[bool] = []
        days_skipped = 0
        skipped_dates: list[str] = []

        for i, d in enumerate(dates):
            lsi = lsi_values[i]
            usdx = z_dxy_ret20[i]
            rypi = z_real_yield[i]

            # Need at minimum LSI and USDX
            if lsi is None or usdx is None:
                days_skipped += 1
                skipped_dates.append(str(d))
                raw_probs.append(None)
                continue

            # RYPI: if missing, exclude from scoring (set to 0 and flag)
            rypi_included = rypi is not None
            _rypi = rypi if rypi is not None else 0.0
            _dlsi = delta_lsi_20[i] if delta_lsi_20[i] is not None else 0.0

            s_stress = 1.2 * lsi + 0.3 * usdx + 0.3 * _rypi
            s_tight = 0.8 * _rypi + 0.6 * usdx - 0.4 * lsi
            s_exp = -0.7 * _rypi - 0.6 * usdx - 0.8 * lsi
            s_recov = -0.8 * lsi - 0.2 * _rypi - 0.2 * usdx + 0.5 * _dlsi

            probs = softmax([s_exp, s_tight, s_stress, s_recov])
            raw_probs.append(probs)
            computed_dates.append(d)
            computed_indices.append({
                "lsi": round(lsi, 6),
                "usdx": round(usdx, 6),
                "rypi": round(_rypi, 6),
                "delta_lsi_20": round(_dlsi, 6),
            })
            computed_scores_raw.append({
                "s_exp": round(s_exp, 6),
                "s_tight": round(s_tight, 6),
                "s_stress": round(s_stress, 6),
                "s_recov": round(s_recov, 6),
            })
            computed_ry_sources.append(real_yield_sources[i])
            computed_credit_sources.append(credit_sources[i])
            computed_rypi_included.append(rypi_included)

        if not computed_dates:
            logger.warning("No dates with sufficient data for regime computation")
            return {"status": "skipped", "reason": "insufficient data", "days_skipped": days_skipped}

        # --- Apply EWMA smoothing ---
        valid_probs = [p for p in raw_probs if p is not None]
        smoothed = ewma_smooth(valid_probs, EWMA_ALPHA)

        # --- Upsert into DB ---
        upserted = 0
        audit_rows: list[RegimeAuditLog] = []

        for idx, d in enumerate(computed_dates):
            raw_p = valid_probs[idx]
            sm_p = smoothed[idx]
            indices = computed_indices[idx]
            ry_source = computed_ry_sources[idx]
            cr_source = computed_credit_sources[idx]
            scores_raw = computed_scores_raw[idx]

            chosen, chosen_raw, note_fa = classify_regime(sm_p)

            # Check if row exists
            existing = await session.execute(
                select(RegimeScore).where(RegimeScore.ts == d)
            )
            row = existing.scalar_one_or_none()
            if row is None:
                row = RegimeScore(ts=d)
                session.add(row)

            row.liquidity_stress_index = indices["lsi"]
            row.usd_pressure_index = indices["usdx"]
            row.real_yield_pressure_index = indices["rypi"]
            row.p_expansion = raw_p[0]
            row.p_tightening = raw_p[1]
            row.p_stress = raw_p[2]
            row.p_recovery = raw_p[3]
            row.smoothed_p_expansion = sm_p[0]
            row.smoothed_p_tightening = sm_p[1]
            row.smoothed_p_stress = sm_p[2]
            row.smoothed_p_recovery = sm_p[3]
            row.chosen_regime = chosen
            row.chosen_regime_raw = chosen_raw
            row.chosen_note_fa = note_fa
            row.score_semantics = "relative_regime_scores"
            row.lookahead_safe = 1
            row.real_yield_source = ry_source
            row.credit_proxy_source = cr_source
            row.days_skipped = days_skipped
            upserted += 1

            # Build audit log row (only for last 30 days to avoid massive inserts)
            if idx >= max(0, len(computed_dates) - 30):
                audit_rows.append(RegimeAuditLog(
                    computed_at=datetime.now(timezone.utc),
                    ts=d,
                    inputs_json={
                        "z_vix": z_vix[dates.index(d)] if d in dates else None,
                        "z_credit": z_credit[dates.index(d)] if d in dates else None,
                        "z_spx_dd": z_spx_dd[dates.index(d)] if d in dates else None,
                        "z_dxy_ret20": z_dxy_ret20[dates.index(d)] if d in dates else None,
                        "z_real_yield": z_real_yield[dates.index(d)] if d in dates else None,
                        "rypi_included": computed_rypi_included[idx],
                    },
                    indices_json=indices,
                    scores_json=scores_raw,
                    raw_probs={
                        "expansion": round(raw_p[0], 6),
                        "tightening": round(raw_p[1], 6),
                        "stress": round(raw_p[2], 6),
                        "recovery": round(raw_p[3], 6),
                    },
                    smoothed_probs={
                        "expansion": round(sm_p[0], 6),
                        "tightening": round(sm_p[1], 6),
                        "stress": round(sm_p[2], 6),
                        "recovery": round(sm_p[3], 6),
                    },
                    chosen_regime=chosen,
                    chosen_regime_raw=chosen_raw,
                    chosen_note_fa=note_fa,
                    sources={
                        "real_yield": ry_source,
                        "credit": cr_source,
                    },
                    staleness=staleness_info,
                ))

        # Persist audit logs
        for al in audit_rows:
            session.add(al)

        await session.commit()

        # --- Provenance logging ---
        latest_raw = valid_probs[-1] if valid_probs else None
        latest_smoothed = smoothed[-1] if smoothed else None
        latest_cr_source = computed_credit_sources[-1] if computed_credit_sources else "none"
        latest_ry_source = computed_ry_sources[-1] if computed_ry_sources else "missing"

        try:
            from api.data_reliability.logger import start_run, log_transform, finish_run
            from api.data_reliability.validator import validate_metric, create_alert_if_needed

            async with AsyncSessionLocal() as prov_session:
                for metric_id in ["regime_lsi", "regime_usdx", "regime_rypi", "regime_composite"]:
                    run_obj = await start_run(prov_session, metric_id)
                    if metric_id == "regime_lsi" and computed_indices:
                        val = computed_indices[-1]["lsi"]
                    elif metric_id == "regime_usdx" and computed_indices:
                        val = computed_indices[-1]["usdx"]
                    elif metric_id == "regime_rypi" and computed_indices:
                        val = computed_indices[-1]["rypi"]
                    elif metric_id == "regime_composite" and latest_smoothed:
                        val = max(latest_smoothed)
                    else:
                        val = None

                    await log_transform(
                        prov_session, run_obj.id, 1, "compute",
                        output_value={
                            "dates_computed": len(computed_dates),
                            "days_skipped": days_skipped,
                            "real_yield_source": latest_ry_source,
                            "credit_proxy_source": latest_cr_source,
                            "raw_probs": latest_raw,
                            "smoothed_probs": latest_smoothed,
                        },
                        notes=f"Regime engine: {len(computed_dates)} dates, {days_skipped} skipped",
                    )
                    data_ts = datetime(
                        computed_dates[-1].year, computed_dates[-1].month,
                        computed_dates[-1].day, tzinfo=timezone.utc,
                    ) if computed_dates else None
                    qa = await validate_metric(prov_session, run_obj.id, metric_id, val, data_ts)
                    await finish_run(prov_session, run_obj, final_value=val, data_timestamp=data_ts, qa_result=qa)
                    await create_alert_if_needed(prov_session, metric_id, qa)
                await prov_session.commit()
        except Exception:
            logger.debug("Provenance logging not available", exc_info=True)

    # Final chosen regime
    latest_chosen, latest_chosen_raw, _ = classify_regime(
        smoothed[-1]
    ) if smoothed else ("unknown", "unknown", None)

    result = {
        "status": "ok",
        "dates_computed": len(computed_dates),
        "days_skipped": days_skipped,
        "upserted": upserted,
        "latest_regime": latest_chosen,
        "latest_regime_raw": latest_chosen_raw,
        "credit_proxy_source": latest_cr_source,
        "real_yield_source": latest_ry_source,
        "score_semantics": "relative_regime_scores",
        "lookahead_safe": True,
        "audit_logs_written": len(audit_rows),
    }
    logger.info("Regime engine: %s", result)
    return result
