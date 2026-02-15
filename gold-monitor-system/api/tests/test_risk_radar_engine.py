"""Unit tests for api.services.analysis.risk_radar_engine — pure function tests."""

import math

import pytest

from api.services.analysis.risk_radar_engine import (
    RISK_CONFIG,
    annualized_realized_vol,
    clamp,
    compute_confidence,
    compute_log_returns,
    logistic_map,
    percentile_rank,
    zscore,
)


# ── percentile_rank ──────────────────────────────────────────────────


class TestPercentileRank:
    def test_empty_distribution(self):
        assert percentile_rank(5.0, []) == 0.5

    def test_at_max(self):
        dist = list(range(100))
        result = percentile_rank(99, dist)
        assert result >= 0.99

    def test_at_min(self):
        dist = list(range(100))
        result = percentile_rank(0, dist)
        assert result <= 0.01

    def test_median(self):
        dist = list(range(101))
        result = percentile_rank(50, dist)
        assert 0.45 <= result <= 0.55

    def test_below_all(self):
        dist = [10, 20, 30]
        result = percentile_rank(1, dist)
        assert result == 0.0

    def test_above_all(self):
        dist = [10, 20, 30]
        result = percentile_rank(100, dist)
        assert result == 1.0

    def test_ties(self):
        dist = [5, 5, 5, 5]
        result = percentile_rank(5, dist)
        assert result == 0.5


# ── zscore ───────────────────────────────────────────────────────────


class TestZscore:
    def test_insufficient_data(self):
        assert zscore(5.0, [5.0]) is None

    def test_zero_std(self):
        assert zscore(5.0, [5.0, 5.0, 5.0]) is None

    def test_positive_zscore(self):
        values = list(range(50))  # mean=24.5, std>0
        z = zscore(49, values)
        assert z is not None
        assert z > 0

    def test_negative_zscore(self):
        values = list(range(50))  # mean=24.5, std>0
        z = zscore(0, values)
        assert z is not None
        assert z < 0

    def test_known_value(self):
        # mean=5, std=sqrt(2.5)=~1.58
        values = [3, 4, 5, 6, 7]
        z = zscore(5, values)
        assert z is not None
        assert abs(z) < 0.01  # should be ~0


# ── clamp ────────────────────────────────────────────────────────────


class TestClamp:
    def test_within_range(self):
        assert clamp(50) == 50

    def test_below_min(self):
        assert clamp(-10) == 0.0

    def test_above_max(self):
        assert clamp(150) == 100.0

    def test_at_bounds(self):
        assert clamp(0) == 0.0
        assert clamp(100) == 100.0

    def test_custom_bounds(self):
        assert clamp(5, 0, 10) == 5
        assert clamp(-1, 0, 10) == 0
        assert clamp(15, 0, 10) == 10


# ── logistic_map ─────────────────────────────────────────────────────


class TestLogisticMap:
    def test_at_midpoint(self):
        result = logistic_map(50, midpoint=50)
        assert abs(result - 50) < 0.1

    def test_high_value(self):
        result = logistic_map(100, midpoint=50, steepness=0.1)
        assert result > 90

    def test_low_value(self):
        result = logistic_map(0, midpoint=50, steepness=0.1)
        assert result < 10

    def test_range(self):
        result = logistic_map(50, midpoint=50, steepness=0.1)
        assert 0 <= result <= 100


# ── compute_confidence ───────────────────────────────────────────────


class TestComputeConfidence:
    def test_fresh_data(self):
        assert compute_confidence(0, 4) == 1.0
        assert compute_confidence(3, 4) == 1.0

    def test_at_decay_start(self):
        assert compute_confidence(4, 4) == 1.0

    def test_decaying(self):
        conf = compute_confidence(8, 4)
        assert 0.3 < conf < 1.0

    def test_very_stale(self):
        conf = compute_confidence(100, 4)
        assert conf == pytest.approx(0.3)

    def test_never_zero(self):
        conf = compute_confidence(1000, 1)
        assert conf >= 0.3


# ── compute_log_returns ──────────────────────────────────────────────


class TestComputeLogReturns:
    def test_basic(self):
        prices = [100, 110, 121]
        returns = compute_log_returns(prices)
        assert len(returns) == 2
        assert abs(returns[0] - math.log(1.1)) < 0.001

    def test_empty(self):
        assert compute_log_returns([]) == []

    def test_single(self):
        assert compute_log_returns([100]) == []

    def test_zero_price_skipped(self):
        returns = compute_log_returns([100, 0, 110])
        # log(0/100) is invalid, log(110/0) is invalid
        assert len(returns) == 0


# ── annualized_realized_vol ──────────────────────────────────────────


class TestAnnualizedRealizedVol:
    def test_insufficient_data(self):
        assert annualized_realized_vol([]) is None
        assert annualized_realized_vol([0.01]) is None

    def test_positive_result(self):
        returns = [0.01, -0.02, 0.015, -0.005, 0.01]
        vol = annualized_realized_vol(returns)
        assert vol is not None
        assert vol > 0

    def test_zero_vol(self):
        returns = [0.01, 0.01, 0.01]
        vol = annualized_realized_vol(returns)
        assert vol is not None
        assert vol == 0.0


# ── RISK_CONFIG ──────────────────────────────────────────────────────


class TestRiskConfig:
    def test_base_weights_sum_to_100(self):
        total = sum(RISK_CONFIG["base_weights"].values())
        assert total == 100

    def test_all_components_have_weights(self):
        expected = {"volatility", "regime", "sentiment", "cot", "etf", "correlation"}
        assert set(RISK_CONFIG["base_weights"].keys()) == expected

    def test_all_components_have_confidence_decay(self):
        expected = {"volatility", "regime", "sentiment", "cot", "etf", "correlation"}
        assert set(RISK_CONFIG["confidence_decay_rates"].keys()) == expected

    def test_label_thresholds_ordered(self):
        assert RISK_CONFIG["label_high"] > RISK_CONFIG["label_moderate"]
