"""Unit tests for pure math helpers in momentum_engine.py.

No DB, no async — these test the 8 pure functions only.
"""

import pytest

from api.services.analysis.momentum_engine import (
    MOMENTUM_CONFIG,
    clamp,
    compute_confidence,
    direction_from_score,
    linear_slope,
    percentile_rank,
    slope_to_trend,
    strength_from_score,
    zscore,
)


# ═══════════════════════════════════════════════════════════════
#  percentile_rank
# ═══════════════════════════════════════════════════════════════

class TestPercentileRank:
    def test_empty_distribution_returns_half(self):
        assert percentile_rank(5.0, []) == 0.5

    def test_single_value_below(self):
        assert percentile_rank(0.0, [10.0]) == 0.0

    def test_single_value_above(self):
        assert percentile_rank(20.0, [10.0]) == 1.0

    def test_single_value_equal(self):
        # Mean method: (0 + 1/2) / 1 = 0.5
        assert percentile_rank(10.0, [10.0]) == 0.5

    def test_median_of_uniform(self):
        dist = list(range(100))
        result = percentile_rank(50, dist)
        assert 0.49 <= result <= 0.52

    def test_max_value(self):
        dist = list(range(100))
        result = percentile_rank(99, dist)
        assert result > 0.98

    def test_min_value(self):
        dist = list(range(100))
        result = percentile_rank(0, dist)
        assert result < 0.02

    def test_clamped_to_0_1(self):
        # Below all values
        result = percentile_rank(-100, [1, 2, 3, 4, 5])
        assert result == 0.0

    def test_above_all(self):
        result = percentile_rank(1000, [1, 2, 3, 4, 5])
        assert result == 1.0

    def test_ties_handled(self):
        dist = [5.0, 5.0, 5.0, 10.0, 10.0]
        result = percentile_rank(5.0, dist)
        # below=0, equal=3, (0 + 1.5)/5 = 0.3
        assert result == pytest.approx(0.3)


# ═══════════════════════════════════════════════════════════════
#  zscore
# ═══════════════════════════════════════════════════════════════

class TestZscore:
    def test_insufficient_data(self):
        assert zscore(5.0, [5.0]) is None
        assert zscore(5.0, []) is None

    def test_zero_stdev(self):
        assert zscore(5.0, [5.0, 5.0, 5.0, 5.0]) is None

    def test_positive_zscore(self):
        values = list(range(50))
        result = zscore(100, values)
        assert result is not None
        assert result > 0

    def test_negative_zscore(self):
        values = list(range(50))
        result = zscore(-50, values)
        assert result is not None
        assert result < 0

    def test_mean_value_gives_zero(self):
        values = [10.0, 20.0, 30.0, 40.0, 50.0]
        mean = 30.0
        result = zscore(mean, values)
        assert result == pytest.approx(0.0, abs=0.001)

    def test_one_stdev_above(self):
        import statistics
        values = [10.0, 20.0, 30.0, 40.0, 50.0]
        m = statistics.mean(values)
        s = statistics.stdev(values)
        result = zscore(m + s, values)
        assert result == pytest.approx(1.0, abs=0.01)


# ═══════════════════════════════════════════════════════════════
#  clamp
# ═══════════════════════════════════════════════════════════════

class TestClamp:
    def test_within_range(self):
        assert clamp(50) == 50

    def test_below_min(self):
        assert clamp(-10) == 0.0

    def test_above_max(self):
        assert clamp(150) == 100.0

    def test_custom_bounds(self):
        assert clamp(5, lo=10, hi=20) == 10
        assert clamp(25, lo=10, hi=20) == 20
        assert clamp(15, lo=10, hi=20) == 15


# ═══════════════════════════════════════════════════════════════
#  compute_confidence
# ═══════════════════════════════════════════════════════════════

class TestComputeConfidence:
    def test_fresh_data(self):
        assert compute_confidence(0, 5) == 1.0

    def test_at_threshold(self):
        assert compute_confidence(5, 5) == 1.0

    def test_fully_decayed(self):
        # data_age = decay_start + 2*decay_start = 3*decay_start
        result = compute_confidence(15, 5)
        assert result == pytest.approx(0.3)

    def test_partial_decay(self):
        # data_age=7, decay_start=5, extra=2, max_extra=10
        # decay = (2/10) * 0.7 = 0.14
        result = compute_confidence(7, 5)
        assert 0.3 < result < 1.0
        assert result == pytest.approx(0.86)

    def test_never_below_minimum(self):
        assert compute_confidence(1000, 1) >= 0.3


# ═══════════════════════════════════════════════════════════════
#  linear_slope
# ═══════════════════════════════════════════════════════════════

class TestLinearSlope:
    def test_too_few_values(self):
        assert linear_slope([1, 2]) is None
        assert linear_slope([]) is None

    def test_constant_values(self):
        result = linear_slope([5, 5, 5, 5])
        assert result == 0.0

    def test_positive_slope(self):
        result = linear_slope([1, 2, 3, 4, 5])
        assert result is not None
        assert result == pytest.approx(1.0)

    def test_negative_slope(self):
        result = linear_slope([5, 4, 3, 2, 1])
        assert result is not None
        assert result == pytest.approx(-1.0)

    def test_noisy_data(self):
        # Upward trend with noise
        result = linear_slope([1, 3, 2, 4, 3, 5, 4, 6])
        assert result is not None
        assert result > 0


# ═══════════════════════════════════════════════════════════════
#  slope_to_trend
# ═══════════════════════════════════════════════════════════════

class TestSlopeToTrend:
    def test_none_slope(self):
        assert slope_to_trend(None) == "steady"

    def test_accelerating(self):
        assert slope_to_trend(0.05) == "accelerating"

    def test_decelerating(self):
        assert slope_to_trend(-0.05) == "decelerating"

    def test_near_zero_is_steady(self):
        assert slope_to_trend(0.001) == "steady"

    def test_custom_threshold(self):
        assert slope_to_trend(0.2, threshold=0.1) == "accelerating"
        assert slope_to_trend(-0.2, threshold=0.1) == "decelerating"


# ═══════════════════════════════════════════════════════════════
#  direction_from_score
# ═══════════════════════════════════════════════════════════════

class TestDirectionFromScore:
    def test_very_bullish(self):
        d, fa = direction_from_score(75)
        assert d == "very_bullish"
        assert "صعودی" in fa

    def test_bullish(self):
        d, _ = direction_from_score(60)
        assert d == "bullish"

    def test_neutral(self):
        d, _ = direction_from_score(50)
        assert d == "neutral"

    def test_bearish(self):
        d, _ = direction_from_score(35)
        assert d == "bearish"

    def test_very_bearish(self):
        d, _ = direction_from_score(20)
        assert d == "very_bearish"

    def test_thresholds(self):
        cfg = MOMENTUM_CONFIG
        # Exactly at boundaries
        d, _ = direction_from_score(cfg["label_very_bullish"])
        assert d == "very_bullish"
        d, _ = direction_from_score(cfg["label_bullish"])
        assert d == "bullish"
        d, _ = direction_from_score(cfg["label_neutral_low"])
        assert d == "neutral"
        d, _ = direction_from_score(cfg["label_bearish"])
        assert d == "bearish"
        d, _ = direction_from_score(cfg["label_bearish"] - 1)
        assert d == "very_bearish"


# ═══════════════════════════════════════════════════════════════
#  strength_from_score
# ═══════════════════════════════════════════════════════════════

class TestStrengthFromScore:
    def test_strong_bullish(self):
        assert strength_from_score(80) == "strong"

    def test_strong_bearish(self):
        assert strength_from_score(20) == "strong"

    def test_moderate(self):
        assert strength_from_score(62) == "moderate"

    def test_weak(self):
        assert strength_from_score(52) == "weak"

    def test_exactly_neutral(self):
        assert strength_from_score(50) == "weak"
