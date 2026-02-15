"""Unit tests for api.analysis.derived_money_flow — pure functions, no DB."""

import pytest

from api.analysis.derived_money_flow import (
    classify_combined_signal,
    compute_cot_wow_pct_of_oi,
    compute_percentile_2yr,
    compute_zscore_90d,
)


# ── Helpers ─────────────────────────────────────────────────────────


def _make_changes(n: int, base: float = 0.0, step: float = 0.1) -> list[float]:
    """Generate a list of n float values starting from base."""
    return [base + i * step for i in range(n)]


# ── TestComputeZscore90d ───────────────────────────────────────────


class TestComputeZscore90d:
    def test_insufficient_data_returns_none(self):
        assert compute_zscore_90d([1.0] * 89) is None

    def test_exactly_90_values(self):
        changes = [1.0] * 89 + [2.0]
        result = compute_zscore_90d(changes)
        # Latest = 2.0, mean of 90 values = (89*1 + 2)/90, std > 0
        assert result is not None

    def test_zero_std_returns_none(self):
        # All identical values → std = 0
        assert compute_zscore_90d([5.0] * 100) is None

    def test_known_positive_zscore(self):
        # 89 zeros + one 10.0 → latest is far above mean
        changes = [0.0] * 89 + [10.0]
        result = compute_zscore_90d(changes)
        assert result is not None
        assert result > 0

    def test_known_negative_zscore(self):
        # 89 tens + one 0.0 → latest is far below mean
        changes = [10.0] * 89 + [0.0]
        result = compute_zscore_90d(changes)
        assert result is not None
        assert result < 0

    def test_values_beyond_90_are_ignored(self):
        # Only the last 90 values matter
        padding = [100.0] * 50  # These are outside the window
        window = [1.0] * 89 + [2.0]
        result = compute_zscore_90d(padding + window)
        result_without_padding = compute_zscore_90d(window)
        assert result == result_without_padding


# ── TestComputePercentile2yr ──────────────────────────────────────


class TestComputePercentile2yr:
    def test_insufficient_data_returns_none(self):
        assert compute_percentile_2yr([1.0] * 29) is None

    def test_max_value_near_100(self):
        changes = list(range(50))
        result = compute_percentile_2yr(changes)
        assert result is not None
        assert result >= 90.0

    def test_min_value_near_0(self):
        changes = list(range(49, -1, -1))  # 49, 48, ..., 0 → latest is 0
        result = compute_percentile_2yr(changes)
        assert result is not None
        assert result <= 10.0

    def test_median_value_near_50(self):
        changes = list(range(100))
        # Latest (99) is the max — should be high
        # Let's build a case where latest is the median
        changes_sorted = list(range(101))  # 0..100, latest=100 → max
        # For median, put median at end
        vals = list(range(50)) + list(range(51, 101)) + [50]
        result = compute_percentile_2yr(vals)
        assert result is not None
        assert 40.0 <= result <= 60.0

    def test_caps_at_500_days(self):
        # More than 500 values → only last 500 used
        changes = [0.0] * 600 + [100.0]
        result = compute_percentile_2yr(changes)
        assert result is not None


# ── TestCotWowPctOi ───────────────────────────────────────────────


class TestCotWowPctOi:
    def test_normal_calculation(self):
        result = compute_cot_wow_pct_of_oi(5000.0, 500000.0)
        assert result == pytest.approx(1.0)

    def test_negative_change(self):
        result = compute_cot_wow_pct_of_oi(-2500.0, 500000.0)
        assert result == pytest.approx(-0.5)

    def test_zero_oi_returns_none(self):
        assert compute_cot_wow_pct_of_oi(1000.0, 0.0) is None

    def test_none_change_returns_none(self):
        assert compute_cot_wow_pct_of_oi(None, 500000.0) is None

    def test_none_oi_returns_none(self):
        assert compute_cot_wow_pct_of_oi(1000.0, None) is None

    def test_both_none_returns_none(self):
        assert compute_cot_wow_pct_of_oi(None, None) is None


# ── TestClassifyCombinedSignal ────────────────────────────────────


class TestClassifyCombinedSignal:
    def test_confirming_bullish(self):
        result = classify_combined_signal(etf_zscore=1.0, cot_pct_3yr=70.0)
        assert result["signal"] == "CONFIRMING"
        assert result["confidence"] > 0
        assert len(result["reasons"]) > 0

    def test_confirming_bearish(self):
        result = classify_combined_signal(etf_zscore=-1.0, cot_pct_3yr=30.0)
        assert result["signal"] == "CONFIRMING_BEARISH"

    def test_diverging_etf_bull_cot_bear(self):
        result = classify_combined_signal(etf_zscore=1.0, cot_pct_3yr=30.0)
        assert result["signal"] == "DIVERGING"

    def test_diverging_etf_bear_cot_bull(self):
        result = classify_combined_signal(etf_zscore=-1.0, cot_pct_3yr=70.0)
        assert result["signal"] == "DIVERGING"

    def test_extreme_risk_high_zscore(self):
        result = classify_combined_signal(etf_zscore=2.5, cot_pct_3yr=50.0)
        assert result["signal"] == "EXTREME_RISK"

    def test_extreme_risk_low_cot_pct(self):
        result = classify_combined_signal(etf_zscore=0.0, cot_pct_3yr=3.0)
        assert result["signal"] == "EXTREME_RISK"

    def test_extreme_risk_high_cot_pct(self):
        result = classify_combined_signal(etf_zscore=0.0, cot_pct_3yr=97.0)
        assert result["signal"] == "EXTREME_RISK"

    def test_neutral_both_normal(self):
        result = classify_combined_signal(etf_zscore=0.2, cot_pct_3yr=50.0)
        assert result["signal"] == "NEUTRAL"

    def test_all_none_returns_neutral(self):
        result = classify_combined_signal(etf_zscore=None, cot_pct_3yr=None)
        assert result["signal"] == "NEUTRAL"
        assert result["confidence"] == 0

    def test_etf_none_cot_bullish(self):
        # Only COT available, bullish — but ETF is None so not confirming
        result = classify_combined_signal(etf_zscore=None, cot_pct_3yr=70.0)
        assert result["signal"] == "NEUTRAL"

    def test_extreme_takes_priority(self):
        # ETF extreme + COT bullish → extreme should win
        result = classify_combined_signal(etf_zscore=3.0, cot_pct_3yr=70.0)
        assert result["signal"] == "EXTREME_RISK"

    def test_result_has_all_fields(self):
        result = classify_combined_signal(etf_zscore=0.0, cot_pct_3yr=50.0)
        assert "signal" in result
        assert "label_fa" in result
        assert "confidence" in result
        assert "reasons" in result
        assert isinstance(result["reasons"], list)
