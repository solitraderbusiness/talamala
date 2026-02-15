"""Unit tests for the canonical scoring engine.

No DB, no async — tests the pure math functions only.
"""

import pytest

from api.analysis.scoring_engine import (
    CROWDING_THRESHOLD,
    MIN_DATA_POINTS,
    NEUTRAL_BAND_HIGH,
    NEUTRAL_BAND_LOW,
    NEUTRAL_SCORE_HIGH,
    NEUTRAL_SCORE_LOW,
    IndicatorResult,
    compute_zscore,
    crowding_flag,
    direction_flip,
    ema_smooth,
    neutral_band_compress,
    percentile_rank,
    robust_quantile,
    rolling_average,
    rolling_change,
    rolling_pct_return,
    score_indicator,
    winsorize,
)


# ═══════════════════════════════════════════════════════════════════════
#  robust_quantile
# ═══════════════════════════════════════════════════════════════════════

class TestRobustQuantile:
    def test_empty(self):
        assert robust_quantile([], 0.5) == 0.0

    def test_single_value(self):
        assert robust_quantile([10.0], 0.5) == 10.0

    def test_median_of_two(self):
        result = robust_quantile([1.0, 3.0], 0.5)
        assert 1.0 <= result <= 3.0

    def test_p01_lower_bound(self):
        vals = sorted(list(range(100)))
        result = robust_quantile([float(v) for v in vals], 0.01)
        assert result < 2.0

    def test_p99_upper_bound(self):
        vals = sorted([float(v) for v in range(100)])
        result = robust_quantile(vals, 0.99)
        assert result > 97.0

    def test_p50_is_median(self):
        vals = sorted([float(v) for v in range(101)])
        result = robust_quantile(vals, 0.5)
        assert abs(result - 50.0) < 2.0

    def test_exact_endpoints(self):
        vals = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert robust_quantile(vals, 0.0) == pytest.approx(1.0, abs=0.5)
        assert robust_quantile(vals, 1.0) == pytest.approx(5.0, abs=0.5)


# ═══════════════════════════════════════════════════════════════════════
#  winsorize
# ═══════════════════════════════════════════════════════════════════════

class TestWinsorize:
    def test_empty(self):
        clipped, bounds = winsorize([])
        assert clipped == []
        assert bounds == (0.0, 0.0)

    def test_no_clipping_needed(self):
        vals = [5.0, 6.0, 7.0, 8.0, 9.0]
        clipped, bounds = winsorize(vals)
        # With only 5 values, bounds should encompass all
        assert all(lo <= v <= hi for v, lo, hi in
                    [(c, bounds[0], bounds[1]) for c in clipped])

    def test_outliers_clipped(self):
        vals = [1.0] * 50 + [100.0] * 50 + [999.0]
        clipped, (lo, hi) = winsorize(vals)
        assert max(clipped) <= hi
        assert min(clipped) >= lo

    def test_bounds_returned(self):
        vals = list(range(100))
        _, (lo, hi) = winsorize([float(v) for v in vals])
        assert lo < hi
        assert lo >= 0
        assert hi <= 99


# ═══════════════════════════════════════════════════════════════════════
#  ema_smooth
# ═══════════════════════════════════════════════════════════════════════

class TestEmaSmooth:
    def test_empty(self):
        assert ema_smooth([]) == []

    def test_single_value(self):
        assert ema_smooth([5.0]) == [5.0]

    def test_span_1_returns_copy(self):
        vals = [1.0, 2.0, 3.0]
        assert ema_smooth(vals, span=1) == vals

    def test_smoothing_reduces_volatility(self):
        # Volatile series
        vals = [10.0, 0.0, 10.0, 0.0, 10.0, 0.0]
        smoothed = ema_smooth(vals, span=3)
        # Smoothed should have less range
        raw_range = max(vals) - min(vals)
        smooth_range = max(smoothed) - min(smoothed)
        assert smooth_range < raw_range

    def test_preserves_length(self):
        vals = list(range(20))
        result = ema_smooth([float(v) for v in vals], span=5)
        assert len(result) == len(vals)


# ═══════════════════════════════════════════════════════════════════════
#  percentile_rank
# ═══════════════════════════════════════════════════════════════════════

class TestPercentileRank:
    def test_empty_distribution(self):
        assert percentile_rank(5.0, []) == 0.5

    def test_below_all(self):
        assert percentile_rank(-100.0, [1, 2, 3, 4, 5]) == 0.0

    def test_above_all(self):
        assert percentile_rank(1000.0, [1, 2, 3, 4, 5]) == 1.0

    def test_median_value(self):
        dist = list(range(100))
        result = percentile_rank(50, [float(v) for v in dist])
        assert 0.49 <= result <= 0.52

    def test_ties_handled(self):
        dist = [5.0, 5.0, 5.0, 10.0, 10.0]
        result = percentile_rank(5.0, dist)
        # below=0, equal=3, (0 + 1.5)/5 = 0.3
        assert result == pytest.approx(0.3)

    def test_clamped_to_unit(self):
        result = percentile_rank(-999.0, [1, 2, 3])
        assert 0.0 <= result <= 1.0


# ═══════════════════════════════════════════════════════════════════════
#  direction_flip
# ═══════════════════════════════════════════════════════════════════════

class TestDirectionFlip:
    def test_bullish_no_change(self):
        assert direction_flip(0.8, "bullish_when_higher") == 0.8

    def test_inverse_flips(self):
        assert direction_flip(0.8, "inverse") == pytest.approx(0.2)

    def test_neutral_midpoint(self):
        assert direction_flip(0.5, "inverse") == pytest.approx(0.5)

    def test_boundaries(self):
        assert direction_flip(0.0, "inverse") == 1.0
        assert direction_flip(1.0, "inverse") == 0.0


# ═══════════════════════════════════════════════════════════════════════
#  neutral_band_compress
# ═══════════════════════════════════════════════════════════════════════

class TestNeutralBandCompress:
    def test_zero(self):
        assert neutral_band_compress(0.0) == 0.0

    def test_one(self):
        assert neutral_band_compress(1.0) == 100.0

    def test_midpoint_maps_to_50(self):
        result = neutral_band_compress(0.5)
        assert result == pytest.approx(50.0)

    def test_within_band_compressed(self):
        # Values within [0.40, 0.60] should map to [45, 55]
        r1 = neutral_band_compress(0.40)
        r2 = neutral_band_compress(0.60)
        assert r1 == pytest.approx(NEUTRAL_SCORE_LOW)
        assert r2 == pytest.approx(NEUTRAL_SCORE_HIGH)

    def test_below_band(self):
        result = neutral_band_compress(0.20)
        assert 0 < result < NEUTRAL_SCORE_LOW

    def test_above_band(self):
        result = neutral_band_compress(0.80)
        assert NEUTRAL_SCORE_HIGH < result < 100.0


# ═══════════════════════════════════════════════════════════════════════
#  crowding_flag
# ═══════════════════════════════════════════════════════════════════════

class TestCrowdingFlag:
    def test_neutral_not_crowded(self):
        assert crowding_flag(0.5) is False

    def test_high_extreme(self):
        assert crowding_flag(0.95) is True

    def test_low_extreme(self):
        assert crowding_flag(0.05) is True

    def test_at_threshold(self):
        assert crowding_flag(CROWDING_THRESHOLD) is True
        assert crowding_flag(1.0 - CROWDING_THRESHOLD) is True

    def test_just_below_threshold(self):
        assert crowding_flag(CROWDING_THRESHOLD - 0.01) is False


# ═══════════════════════════════════════════════════════════════════════
#  compute_zscore
# ═══════════════════════════════════════════════════════════════════════

class TestComputeZscore:
    def test_insufficient_data(self):
        assert compute_zscore(5.0, []) is None
        assert compute_zscore(5.0, [1.0]) is None
        assert compute_zscore(5.0, [1.0, 2.0]) is None

    def test_zero_stdev(self):
        assert compute_zscore(5.0, [5.0, 5.0, 5.0]) is None

    def test_mean_gives_zero(self):
        vals = [10.0, 20.0, 30.0, 40.0, 50.0]
        result = compute_zscore(30.0, vals)
        assert result == pytest.approx(0.0, abs=0.001)

    def test_positive(self):
        vals = list(range(50))
        result = compute_zscore(100.0, [float(v) for v in vals])
        assert result is not None
        assert result > 0

    def test_negative(self):
        vals = list(range(50))
        result = compute_zscore(-50.0, [float(v) for v in vals])
        assert result is not None
        assert result < 0


# ═══════════════════════════════════════════════════════════════════════
#  score_indicator (full pipeline)
# ═══════════════════════════════════════════════════════════════════════

class TestScoreIndicator:
    def test_insufficient_data_fallback(self):
        result = score_indicator(
            "TEST", 50.0, [1.0, 2.0],
            source_name="Test",
        )
        assert result.score == 50
        assert result.fallback_used is True
        assert result.window_size == 2

    def test_full_pipeline_bullish(self):
        # Create a distribution where current value is high → bullish
        hist = [float(i) for i in range(100)]
        result = score_indicator(
            "TEST", 95.0, hist,
            direction="bullish_when_higher",
            source_name="Test",
        )
        assert result.score > 60
        assert result.fallback_used is False
        assert result.window_size == 100

    def test_full_pipeline_inverse(self):
        # High value with inverse direction → low score
        hist = [float(i) for i in range(100)]
        result = score_indicator(
            "TEST", 95.0, hist,
            direction="inverse",
            source_name="Test",
        )
        assert result.score < 40

    def test_returns_indicator_result(self):
        hist = [float(i) for i in range(50)]
        result = score_indicator(
            "MY_INDICATOR", 25.0, hist,
            source_name="TestSource",
            source_url="https://example.com",
            last_updated_at="2026-02-15",
            stale=True,
        )
        assert isinstance(result, IndicatorResult)
        assert result.indicator_id == "MY_INDICATOR"
        assert result.source_name == "TestSource"
        assert result.source_url == "https://example.com"
        assert result.last_updated_at == "2026-02-15"
        assert result.stale is True

    def test_smoothing_applied(self):
        hist = [float(i) for i in range(50)]
        result_smooth = score_indicator(
            "TEST", 25.0, hist, smooth=True, source_name="T",
        )
        result_raw = score_indicator(
            "TEST", 25.0, hist, smooth=False, source_name="T",
        )
        assert result_smooth.smoothing_applied is True
        assert result_raw.smoothing_applied is False

    def test_winsorization_applied(self):
        # Need >= 20 samples after smoothing
        hist = [float(i) for i in range(30)]
        result = score_indicator(
            "TEST", 15.0, hist, do_winsorize=True, source_name="T",
        )
        assert result.winsorize_bounds is not None

    def test_no_winsorization_small_sample(self):
        hist = [float(i) for i in range(10)]
        result = score_indicator(
            "TEST", 5.0, hist, do_winsorize=True, source_name="T",
        )
        assert result.winsorize_bounds is None

    def test_crowding_detected(self):
        # Value above almost everything → crowded
        hist = [float(i) for i in range(100)]
        result = score_indicator(
            "TEST", 99.0, hist, source_name="T",
        )
        assert result.crowded is True

    def test_neutral_value_not_crowded(self):
        hist = [float(i) for i in range(100)]
        result = score_indicator(
            "TEST", 50.0, hist, source_name="T",
        )
        assert result.crowded is False

    def test_zscore_populated(self):
        hist = [float(i) for i in range(50)]
        result = score_indicator(
            "TEST", 25.0, hist, source_name="T",
        )
        assert result.zscore is not None

    def test_score_in_valid_range(self):
        import random
        random.seed(42)
        for _ in range(20):
            hist = [random.gauss(0, 1) for _ in range(100)]
            val = random.gauss(0, 1)
            result = score_indicator(
                "TEST", val, hist, source_name="T",
            )
            assert 0 <= result.score <= 100


# ═══════════════════════════════════════════════════════════════════════
#  Rolling helpers
# ═══════════════════════════════════════════════════════════════════════

class TestRollingAverage:
    def test_too_few(self):
        assert rolling_average([1.0, 2.0], 5) == []

    def test_basic(self):
        result = rolling_average([1.0, 2.0, 3.0, 4.0, 5.0], 3)
        assert len(result) == 3
        assert result[0] == pytest.approx(2.0)
        assert result[-1] == pytest.approx(4.0)


class TestRollingChange:
    def test_too_few(self):
        assert rolling_change([1.0, 2.0], 5) == []

    def test_basic(self):
        result = rolling_change([10.0, 20.0, 35.0], 1)
        assert result == [10.0, 15.0]


class TestRollingPctReturn:
    def test_too_few(self):
        assert rolling_pct_return([1.0, 2.0], 5) == []

    def test_basic(self):
        result = rolling_pct_return([100.0, 110.0], 1)
        assert result == [pytest.approx(10.0)]

    def test_zero_prev(self):
        result = rolling_pct_return([0.0, 10.0], 1)
        assert result == [0.0]
