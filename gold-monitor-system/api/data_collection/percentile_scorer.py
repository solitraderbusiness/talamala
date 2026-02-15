"""Reusable percentile-based scoring utility for sentiment components.

All components produce a score in [0..100] where 50 = neutral.
The pipeline: raw → winsorize → EMA smooth → percentile → direction → neutral band → score.

This module is intentionally pure math (no DB, no I/O) so it can be unit-tested
and swapped for a different scoring method later.
"""

from __future__ import annotations

from typing import NamedTuple


class ScoreResult(NamedTuple):
    """Result of percentile-based scoring for one component."""

    score: int                              # 0-100 final score
    percentile: float                       # 0.0-1.0 raw percentile
    raw_value: float                        # Original (untransformed) metric value
    smoothed_value: float                   # Value after EMA smoothing
    window_size: int                        # Number of historical observations used
    winsorize_bounds: tuple[float, float] | None  # (low, high) clip bounds
    smoothing_applied: bool
    direction: str                          # "bullish_when_higher" or "inverse"
    crowded: bool                           # True if at extreme percentile


# ── Building blocks ────────────────────────────────────────────────────


def winsorize(
    values: list[float],
    lower_pct: float = 1.0,
    upper_pct: float = 99.0,
) -> tuple[list[float], tuple[float, float]]:
    """Clip *values* to the [lower_pct, upper_pct] percentile bounds.

    Returns ``(clipped_values, (lo_bound, hi_bound))``.
    """
    if not values:
        return values, (0.0, 0.0)

    sorted_vals = sorted(values)
    n = len(sorted_vals)
    lo_idx = max(0, int(n * lower_pct / 100.0))
    hi_idx = min(n - 1, int(n * upper_pct / 100.0))
    lo_bound = sorted_vals[lo_idx]
    hi_bound = sorted_vals[hi_idx]

    clipped = [max(lo_bound, min(hi_bound, v)) for v in values]
    return clipped, (lo_bound, hi_bound)


def ema_smooth(values: list[float], span: int = 3) -> list[float]:
    """Apply exponential moving average (EMA) smoothing.

    ``span`` controls the decay factor: alpha = 2 / (span + 1).
    Input must be in chronological order (oldest first).
    """
    if not values or span < 2:
        return list(values)

    alpha = 2.0 / (span + 1)
    result = [values[0]]
    for v in values[1:]:
        result.append(alpha * v + (1 - alpha) * result[-1])
    return result


def percentile_rank(value: float, distribution: list[float]) -> float:
    """Compute the percentile rank of *value* within *distribution*.

    Uses the "mean" method for ties: rank = (below + equal/2) / N.
    Returns a float in [0.0, 1.0].
    """
    if not distribution:
        return 0.5

    n = len(distribution)
    count_below = sum(1 for v in distribution if v < value)
    count_equal = sum(1 for v in distribution if v == value)
    rank = (count_below + count_equal / 2.0) / n
    return max(0.0, min(1.0, rank))


def apply_neutral_band(
    p_directed: float,
    band_low: float = 0.40,
    band_high: float = 0.60,
    score_low: float = 45.0,
    score_high: float = 55.0,
) -> float:
    """Compress percentiles near the midpoint into a narrow score range.

    Percentiles in [band_low, band_high] → scores in [score_low, score_high].
    Outside the band, the remaining score range is distributed linearly.

    This reduces noise: small random percentile fluctuations near 0.50 don't
    move the score very far from 50.
    """
    if p_directed <= 0.0:
        return 0.0
    if p_directed >= 1.0:
        return 100.0

    if p_directed < band_low:
        # [0, band_low) → [0, score_low)
        return p_directed / band_low * score_low
    elif p_directed > band_high:
        # (band_high, 1] → (score_high, 100]
        return score_high + (p_directed - band_high) / (1.0 - band_high) * (100.0 - score_high)
    else:
        # [band_low, band_high] → [score_low, score_high]
        t = (p_directed - band_low) / (band_high - band_low)
        return score_low + t * (score_high - score_low)


# ── Main scoring function ──────────────────────────────────────────────


def score_percentile(
    current_value: float,
    historical_values: list[float],
    direction: str = "bullish_when_higher",
    *,
    smooth: bool = True,
    smooth_span: int = 3,
    do_winsorize: bool = True,
    neutral_band: bool = True,
    crowding_threshold: float = 0.90,
) -> ScoreResult:
    """Compute a 0-100 score from a raw value using its historical distribution.

    Parameters
    ----------
    current_value
        Today's raw metric value (already transformed, e.g. 5-day avg).
    historical_values
        Chronologically ordered list of past values (oldest first).
    direction
        ``"bullish_when_higher"`` — higher value → higher score.
        ``"inverse"`` — higher value → lower score (e.g. real yields).
    smooth
        If True, apply 3-day EMA to the full series before percentile.
    smooth_span
        EMA span parameter.
    do_winsorize
        If True, clip values to [p1, p99] before computing percentile.
    neutral_band
        If True, compress scores near 50 to reduce noise.
    crowding_threshold
        Percentile above which (or below 1-threshold) ``crowded=True``.

    Returns
    -------
    ScoreResult
        Named tuple with score, percentile, and metadata.
    """
    if not historical_values:
        return ScoreResult(
            score=50,
            percentile=0.5,
            raw_value=current_value,
            smoothed_value=current_value,
            window_size=0,
            winsorize_bounds=None,
            smoothing_applied=False,
            direction=direction,
            crowded=False,
        )

    # Step 1: Build full series (history + current) in chronological order.
    full_series = list(historical_values) + [current_value]

    # Step 2: Optional EMA smoothing over the full series.
    smoothing_applied = smooth and len(full_series) > smooth_span
    if smoothing_applied:
        smoothed = ema_smooth(full_series, smooth_span)
        smoothed_value = smoothed[-1]
        smoothed_hist = smoothed[:-1]
    else:
        smoothed_value = current_value
        smoothed_hist = list(historical_values)

    # Step 3: Optional winsorization of the smoothed historical distribution.
    winsorize_bounds: tuple[float, float] | None = None
    if do_winsorize and len(smoothed_hist) >= 20:
        smoothed_hist, winsorize_bounds = winsorize(smoothed_hist)
        # Also clip the current smoothed value to the same bounds.
        lo, hi = winsorize_bounds
        smoothed_value = max(lo, min(hi, smoothed_value))

    # Step 4: Percentile rank of today's (smoothed) value in the
    #         (smoothed+winsorized) historical distribution.
    p = percentile_rank(smoothed_value, smoothed_hist)

    # Step 5: Apply direction.
    if direction == "inverse":
        p_directed = 1.0 - p
    else:
        p_directed = p

    # Step 6: Neutral band compression.
    if neutral_band:
        score_float = apply_neutral_band(p_directed)
    else:
        score_float = p_directed * 100.0

    score = round(max(0.0, min(100.0, score_float)))

    # Step 7: Crowding flag — extreme percentile (before direction flip).
    crowded = p >= crowding_threshold or p <= (1.0 - crowding_threshold)

    return ScoreResult(
        score=score,
        percentile=round(p, 4),
        raw_value=current_value,
        smoothed_value=round(smoothed_value, 6),
        window_size=len(historical_values),
        winsorize_bounds=(
            (round(winsorize_bounds[0], 6), round(winsorize_bounds[1], 6))
            if winsorize_bounds
            else None
        ),
        smoothing_applied=smoothing_applied,
        direction=direction,
        crowded=crowded,
    )


# ── Rolling metric helpers ──────────────────────────────────────────────
# These compute derived series from raw daily data before feeding into
# the percentile scorer.


def rolling_average(values: list[float], window: int) -> list[float]:
    """Compute rolling average over *window* items.

    Returns a list shorter by (window - 1) elements.
    Input must be in chronological order (oldest first).
    """
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
    """Compute rolling change (value[i] - value[i - window]).

    Returns a list shorter by *window* elements.
    """
    if len(values) <= window:
        return []
    return [values[i] - values[i - window] for i in range(window, len(values))]


def rolling_pct_return(values: list[float], window: int) -> list[float]:
    """Compute rolling percentage return over *window* items.

    Returns a list shorter by *window* elements.
    """
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
