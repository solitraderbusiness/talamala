"""Canonical scoring engine — single source of truth for indicator scoring.

Every indicator in the system flows through the same pipeline:

    raw value
      → build_history_series (fetch + transform)
      → winsorize (clip to robust quantile bounds, p1/p99)
      → EMA smooth (configurable span, chronological order)
      → percentile_rank (mean method for ties)
      → direction_flip (inverse indicators: higher raw = lower score)
      → neutral_band_compress (dampen noise near midpoint)
      → crowding_flag (extreme percentiles >= 0.90 or <= 0.10)
      → final 0-100 score

This module is pure math — no DB, no I/O, no async.  Every function is
independently testable.

Re-uses and extends the existing ``percentile_scorer.py`` building blocks
with improvements:
  - Robust quantile calculation (linear interpolation, not simple index)
  - Configurable constants as module-level with clear documentation
  - Full metadata output (IndicatorResult) for provenance tracking
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Literal


# ═══════════════════════════════════════════════════════════════════════
#  Constants — all thresholds in one place
# ═══════════════════════════════════════════════════════════════════════

# Winsorization: clip at these quantiles to limit outlier impact
WINSORIZE_LOWER_PCT = 1.0
WINSORIZE_UPPER_PCT = 99.0
WINSORIZE_MIN_SAMPLES = 20  # don't winsorize with < 20 data points

# EMA smoothing defaults
EMA_DEFAULT_SPAN = 3  # alpha = 2/(span+1) = 0.5

# Neutral band: compress scores near 50 to reduce noise
NEUTRAL_BAND_LOW = 0.40   # percentiles [0.40, 0.60] → scores [45, 55]
NEUTRAL_BAND_HIGH = 0.60
NEUTRAL_SCORE_LOW = 45.0
NEUTRAL_SCORE_HIGH = 55.0

# Crowding: flag extreme positioning
CROWDING_THRESHOLD = 0.90  # percentile >= 0.90 or <= 0.10

# Minimum data points needed for meaningful percentile
MIN_DATA_POINTS = 5


# ═══════════════════════════════════════════════════════════════════════
#  Result dataclass
# ═══════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class IndicatorResult:
    """Full metadata output for one scored indicator."""
    indicator_id: str
    score: int                           # 0-100 final score
    percentile: float                    # 0.0-1.0 raw percentile (before direction)
    raw_value: float                     # Original metric value
    transformed_value: float             # After rolling transform (e.g. 5d avg)
    smoothed_value: float                # After EMA smoothing
    direction: str                       # "bullish_when_higher" or "inverse"
    window_size: int                     # Historical observations used
    crowded: bool                        # Extreme percentile flag
    stale: bool                          # Data freshness flag
    fallback_used: bool                  # True if insufficient data, used neutral
    last_updated_at: str | None          # ISO date of latest data point
    source_name: str                     # e.g. "SPDR", "CFTC", "FRED"
    source_url: str | None               # Direct link to data source
    winsorize_bounds: tuple[float, float] | None
    smoothing_applied: bool
    scoring_method: str = "percentile"   # Pipeline identifier
    zscore: float | None = None          # Optional z-score for debugging


# ═══════════════════════════════════════════════════════════════════════
#  Building blocks — pure functions
# ═══════════════════════════════════════════════════════════════════════

def robust_quantile(sorted_values: list[float], q: float) -> float:
    """Compute quantile using linear interpolation (not simple index).

    Parameters
    ----------
    sorted_values : list[float]
        Must already be sorted ascending.
    q : float
        Quantile in [0.0, 1.0].  E.g. 0.01 for p1, 0.99 for p99.

    Returns
    -------
    float
        Interpolated quantile value.
    """
    n = len(sorted_values)
    if n == 0:
        return 0.0
    if n == 1:
        return sorted_values[0]

    # Use the "exclusive" method (like Excel PERCENTILE.EXC)
    pos = q * (n + 1) - 1  # 0-indexed
    pos = max(0.0, min(pos, n - 1.0))
    lo = int(math.floor(pos))
    hi = min(lo + 1, n - 1)
    frac = pos - lo
    return sorted_values[lo] + frac * (sorted_values[hi] - sorted_values[lo])


def winsorize(
    values: list[float],
    lower_pct: float = WINSORIZE_LOWER_PCT,
    upper_pct: float = WINSORIZE_UPPER_PCT,
) -> tuple[list[float], tuple[float, float]]:
    """Clip values to robust quantile bounds.

    Uses linear interpolation for quantile calculation instead of simple
    index lookup, which is more accurate for small sample sizes.

    Returns (clipped_values, (lo_bound, hi_bound)).
    """
    if not values:
        return values, (0.0, 0.0)

    sorted_vals = sorted(values)
    lo_bound = robust_quantile(sorted_vals, lower_pct / 100.0)
    hi_bound = robust_quantile(sorted_vals, upper_pct / 100.0)

    # Ensure lo <= hi
    if lo_bound > hi_bound:
        lo_bound, hi_bound = hi_bound, lo_bound

    clipped = [max(lo_bound, min(hi_bound, v)) for v in values]
    return clipped, (lo_bound, hi_bound)


def ema_smooth(values: list[float], span: int = EMA_DEFAULT_SPAN) -> list[float]:
    """Apply exponential moving average smoothing.

    alpha = 2 / (span + 1).  Input must be chronological (oldest first).
    """
    if not values or span < 2:
        return list(values)

    alpha = 2.0 / (span + 1)
    result = [values[0]]
    for v in values[1:]:
        result.append(alpha * v + (1 - alpha) * result[-1])
    return result


def percentile_rank(value: float, distribution: list[float]) -> float:
    """Compute percentile rank using the mean method for ties.

    rank = (count_below + count_equal / 2) / N

    Returns float in [0.0, 1.0].
    """
    if not distribution:
        return 0.5

    n = len(distribution)
    count_below = sum(1 for v in distribution if v < value)
    count_equal = sum(1 for v in distribution if v == value)
    rank = (count_below + count_equal / 2.0) / n
    return max(0.0, min(1.0, rank))


def direction_flip(p: float, direction: str) -> float:
    """Apply direction: inverse indicators get 1 - percentile."""
    if direction == "inverse":
        return 1.0 - p
    return p


def neutral_band_compress(
    p_directed: float,
    band_low: float = NEUTRAL_BAND_LOW,
    band_high: float = NEUTRAL_BAND_HIGH,
    score_low: float = NEUTRAL_SCORE_LOW,
    score_high: float = NEUTRAL_SCORE_HIGH,
) -> float:
    """Compress percentiles near midpoint into a narrow score range.

    Percentiles in [band_low, band_high] → scores in [score_low, score_high].
    Outside: linear distribution of remaining range.
    """
    if p_directed <= 0.0:
        return 0.0
    if p_directed >= 1.0:
        return 100.0

    if p_directed < band_low:
        return p_directed / band_low * score_low
    elif p_directed > band_high:
        return score_high + (p_directed - band_high) / (1.0 - band_high) * (100.0 - score_high)
    else:
        t = (p_directed - band_low) / (band_high - band_low)
        return score_low + t * (score_high - score_low)


def crowding_flag(percentile: float, threshold: float = CROWDING_THRESHOLD) -> bool:
    """True if percentile is at an extreme (above threshold or below 1-threshold)."""
    return percentile >= threshold or percentile <= (1.0 - threshold)


def compute_zscore(value: float, values: list[float]) -> float | None:
    """Compute z-score of value within the distribution.

    Returns None if insufficient data or zero standard deviation.
    """
    if len(values) < 3:
        return None
    try:
        m = statistics.mean(values)
        s = statistics.stdev(values)
        if s == 0:
            return None
        return (value - m) / s
    except (statistics.StatisticsError, ZeroDivisionError):
        return None


# ═══════════════════════════════════════════════════════════════════════
#  Main scoring pipeline
# ═══════════════════════════════════════════════════════════════════════

def score_indicator(
    indicator_id: str,
    current_value: float,
    historical_values: list[float],
    direction: str = "bullish_when_higher",
    *,
    smooth: bool = True,
    smooth_span: int = EMA_DEFAULT_SPAN,
    do_winsorize: bool = True,
    neutral_band: bool = True,
    stale: bool = False,
    last_updated_at: str | None = None,
    source_name: str = "Unknown",
    source_url: str | None = None,
) -> IndicatorResult:
    """Score a single indicator through the canonical pipeline.

    This is the single entry point for all indicator scoring in the system.
    Every indicator — whether it feeds into sentiment, momentum, or risk radar —
    goes through the exact same math pipeline.

    Parameters
    ----------
    indicator_id : str
        Canonical identifier (e.g. "ETF_FLOW_GLD", "COT_POSITION").
    current_value : float
        Today's transformed metric value.
    historical_values : list[float]
        Chronologically ordered (oldest first) historical values.
    direction : str
        "bullish_when_higher" or "inverse".
    smooth : bool
        Whether to apply EMA smoothing.
    smooth_span : int
        EMA span parameter.
    do_winsorize : bool
        Whether to clip outliers.
    neutral_band : bool
        Whether to compress scores near 50.
    stale : bool
        Whether the data is stale (exceeds freshness threshold).
    last_updated_at : str | None
        ISO date of the latest data point.
    source_name : str
        Human-readable source name.
    source_url : str | None
        Direct URL to data source.

    Returns
    -------
    IndicatorResult
        Full metadata output for provenance and debugging.
    """
    # Insufficient data → fallback neutral
    if len(historical_values) < MIN_DATA_POINTS:
        return IndicatorResult(
            indicator_id=indicator_id,
            score=50,
            percentile=0.5,
            raw_value=current_value,
            transformed_value=current_value,
            smoothed_value=current_value,
            direction=direction,
            window_size=len(historical_values),
            crowded=False,
            stale=stale,
            fallback_used=True,
            last_updated_at=last_updated_at,
            source_name=source_name,
            source_url=source_url,
            winsorize_bounds=None,
            smoothing_applied=False,
        )

    # Step 1: Build full series (history + current)
    full_series = list(historical_values) + [current_value]

    # Step 2: EMA smoothing
    smoothing_applied = smooth and len(full_series) > smooth_span
    if smoothing_applied:
        smoothed = ema_smooth(full_series, smooth_span)
        smoothed_value = smoothed[-1]
        smoothed_hist = smoothed[:-1]
    else:
        smoothed_value = current_value
        smoothed_hist = list(historical_values)

    # Step 3: Winsorization with robust quantiles
    w_bounds: tuple[float, float] | None = None
    if do_winsorize and len(smoothed_hist) >= WINSORIZE_MIN_SAMPLES:
        smoothed_hist, w_bounds = winsorize(smoothed_hist)
        # Clip current value to same bounds
        lo, hi = w_bounds
        smoothed_value = max(lo, min(hi, smoothed_value))

    # Step 4: Percentile rank
    p = percentile_rank(smoothed_value, smoothed_hist)

    # Step 5: Direction flip
    p_directed = direction_flip(p, direction)

    # Step 6: Neutral band compression
    if neutral_band:
        score_float = neutral_band_compress(p_directed)
    else:
        score_float = p_directed * 100.0

    score = round(max(0.0, min(100.0, score_float)))

    # Step 7: Crowding flag (on raw percentile, before direction)
    is_crowded = crowding_flag(p)

    # Optional z-score for debugging
    zs = compute_zscore(smoothed_value, smoothed_hist)

    return IndicatorResult(
        indicator_id=indicator_id,
        score=score,
        percentile=round(p, 4),
        raw_value=current_value,
        transformed_value=current_value,
        smoothed_value=round(smoothed_value, 6),
        direction=direction,
        window_size=len(historical_values),
        crowded=is_crowded,
        stale=stale,
        fallback_used=False,
        last_updated_at=last_updated_at,
        source_name=source_name,
        source_url=source_url,
        winsorize_bounds=(
            (round(w_bounds[0], 6), round(w_bounds[1], 6))
            if w_bounds else None
        ),
        smoothing_applied=smoothing_applied,
        zscore=round(zs, 4) if zs is not None else None,
    )


# ═══════════════════════════════════════════════════════════════════════
#  Rolling metric helpers (re-exported from percentile_scorer)
# ═══════════════════════════════════════════════════════════════════════

def rolling_average(values: list[float], window: int) -> list[float]:
    """Rolling average over *window* items.  Returns shorter list."""
    if len(values) < window:
        return []
    result: list[float] = []
    s = sum(values[:window])
    result.append(s / window)
    for i in range(window, len(values)):
        s += values[i] - values[i - window]
        result.append(s / window)
    return result


def rolling_change(values: list[float], window: int) -> list[float]:
    """Rolling change (value[i] - value[i-window])."""
    if len(values) <= window:
        return []
    return [values[i] - values[i - window] for i in range(window, len(values))]


def rolling_pct_return(values: list[float], window: int) -> list[float]:
    """Rolling percentage return over *window* items."""
    if len(values) <= window:
        return []
    result: list[float] = []
    for i in range(window, len(values)):
        prev = values[i - window]
        if prev != 0:
            result.append((values[i] - prev) / prev * 100.0)
        else:
            result.append(0.0)
    return result
