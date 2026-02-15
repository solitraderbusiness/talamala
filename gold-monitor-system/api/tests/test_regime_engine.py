"""Pure-math unit tests for the regime engine helpers.

No database or network access — tests only the deterministic math functions.
"""

import math

import pytest

from api.analysis.workers.regime_engine import (
    classify_regime,
    compute_credit_proxy,
    ewma_smooth,
    log_return,
    merge_credit_series,
    rolling_zscore,
    softmax,
    MIXED_MIN_GAP,
    MIXED_MIN_TOP,
)


# ── Softmax ─────────────────────────────────────────────────────────

class TestSoftmax:
    def test_sums_to_one(self):
        scores = [1.0, 2.0, 3.0, 0.5]
        probs = softmax(scores)
        assert abs(sum(probs) - 1.0) < 1e-9

    def test_numerical_stability(self):
        """Large inputs should not overflow."""
        scores = [1000.0, 1001.0, 999.0, 1000.5]
        probs = softmax(scores)
        assert abs(sum(probs) - 1.0) < 1e-9
        assert all(0 <= p <= 1 for p in probs)
        # Largest score should have highest probability
        assert probs[1] == max(probs)

    def test_equal_scores(self):
        scores = [1.0, 1.0, 1.0, 1.0]
        probs = softmax(scores)
        for p in probs:
            assert abs(p - 0.25) < 1e-9

    def test_negative_scores(self):
        """Negative scores should still produce valid probabilities."""
        scores = [-5.0, -3.0, -1.0, -10.0]
        probs = softmax(scores)
        assert abs(sum(probs) - 1.0) < 1e-9
        assert all(0 <= p <= 1 for p in probs)
        # -1.0 is the largest, so index 2 should have highest
        assert probs[2] == max(probs)

    def test_extreme_spread(self):
        """Very wide spread should push almost all weight to the max."""
        scores = [0.0, 0.0, 100.0, 0.0]
        probs = softmax(scores)
        assert probs[2] > 0.99


# ── Rolling Z-score ──────────────────────────────────────────────────

class TestRollingZscore:
    def test_clipping(self):
        """Values should be clamped to [-3, +3]."""
        values: list[float | None] = [1.0] * 100 + [100.0]
        zscores = rolling_zscore(values, n=100)
        last = zscores[-1]
        assert last is not None
        assert -3.0 <= last <= 3.0

    def test_clipping_negative(self):
        """Negative outliers should also be clamped."""
        values: list[float | None] = [50.0] * 100 + [-200.0]
        zscores = rolling_zscore(values, n=100)
        last = zscores[-1]
        assert last is not None
        assert last == -3.0

    def test_zero_std(self):
        """When all values are identical, z-score should be ~0 (epsilon guard)."""
        values: list[float | None] = [5.0] * 50
        zscores = rolling_zscore(values, n=50)
        last = zscores[-1]
        assert last is not None
        assert abs(last) < 0.1

    def test_none_values(self):
        """None values should propagate."""
        values: list[float | None] = [None] * 10
        zscores = rolling_zscore(values, n=10)
        assert all(z is None for z in zscores)

    def test_insufficient_history(self):
        """Should return None when window too small (< 20 observations)."""
        values: list[float | None] = [1.0] * 10
        zscores = rolling_zscore(values, n=252)
        assert all(z is None for z in zscores)

    def test_exactly_20_samples(self):
        """Should return a value when exactly 20 samples available."""
        values: list[float | None] = list(range(20))
        zscores = rolling_zscore(values, n=252)
        # First 19 should be None, 20th should have a value
        assert all(z is None for z in zscores[:19])
        assert zscores[19] is not None

    def test_mixed_none_values(self):
        """None values in the middle should be skipped for window stats."""
        values: list[float | None] = [1.0] * 25 + [None] + [1.0] * 5
        zscores = rolling_zscore(values, n=252)
        # Position after None should still compute (25 valid values in window)
        assert zscores[26] is not None

    def test_known_values(self):
        """Z-score of mean should be 0."""
        values: list[float | None] = list(range(1, 31))  # 1..30
        zscores = rolling_zscore(values, n=30)
        # The last value (30) should have positive z-score
        assert zscores[-1] is not None
        assert zscores[-1] > 0


# ── Log Return ───────────────────────────────────────────────────────

class TestLogReturn:
    def test_basic(self):
        """ln(110/100) should be approximately 0.0953."""
        prices: list[float | None] = [100.0, 110.0]
        returns = log_return(prices, lag=1)
        assert returns[0] is None
        assert returns[1] is not None
        assert abs(returns[1] - math.log(110 / 100)) < 1e-9

    def test_none_propagation(self):
        prices: list[float | None] = [100.0, None, 120.0]
        returns = log_return(prices, lag=1)
        assert returns[1] is None
        assert returns[2] is None  # previous is None

    def test_lag_20(self):
        prices: list[float | None] = [100.0] * 20 + [120.0]
        returns = log_return(prices, lag=20)
        assert returns[20] is not None
        assert abs(returns[20] - math.log(120 / 100)) < 1e-9


# ── Credit Proxy ─────────────────────────────────────────────────────

class TestCreditProxy:
    def test_formula(self):
        """-ln(HYG/IEF) correctness."""
        hyg = [80.0, 85.0]
        ief = [100.0, 95.0]
        result = compute_credit_proxy(hyg, ief)
        assert result[0] is not None
        expected_0 = -math.log(80.0 / 100.0)
        assert abs(result[0] - expected_0) < 1e-9
        expected_1 = -math.log(85.0 / 95.0)
        assert abs(result[1] - expected_1) < 1e-9

    def test_none_handling(self):
        hyg: list[float | None] = [80.0, None]
        ief: list[float | None] = [100.0, 100.0]
        result = compute_credit_proxy(hyg, ief)
        assert result[0] is not None
        assert result[1] is None


# ── Merge Credit Series ──────────────────────────────────────────────

class TestMergeCreditSeries:
    def test_fred_oas_preferred(self):
        """FRED OAS is primary when available."""
        fred_oas: list[float | None] = [3.5, 4.0, None]
        hyg_ief: list[float | None] = [0.2, 0.25, 0.3]
        merged, sources = merge_credit_series(fred_oas, hyg_ief)
        assert merged[0] == 3.5
        assert sources[0] == "fred_oas"
        assert merged[1] == 4.0
        assert sources[1] == "fred_oas"
        # Fallback to HYG/IEF when OAS missing
        assert merged[2] == 0.3
        assert sources[2] == "hyg_ief"

    def test_both_missing(self):
        fred_oas: list[float | None] = [None, None]
        hyg_ief: list[float | None] = [None, None]
        merged, sources = merge_credit_series(fred_oas, hyg_ief)
        assert merged == [None, None]
        assert sources == ["none", "none"]

    def test_all_fred_oas(self):
        fred_oas: list[float | None] = [3.0, 4.0, 5.0]
        hyg_ief: list[float | None] = [0.1, 0.2, 0.3]
        merged, sources = merge_credit_series(fred_oas, hyg_ief)
        assert merged == [3.0, 4.0, 5.0]
        assert all(s == "fred_oas" for s in sources)


# ── EWMA Smoothing ───────────────────────────────────────────────────

class TestEwmaSmoothing:
    def test_convergence(self):
        """Smoothed values should converge and still sum to ~1.0."""
        series = [
            [0.5, 0.2, 0.2, 0.1],
            [0.1, 0.6, 0.2, 0.1],
            [0.1, 0.6, 0.2, 0.1],
            [0.1, 0.6, 0.2, 0.1],
        ]
        smoothed = ewma_smooth(series, alpha=0.2)
        assert len(smoothed) == 4
        for vec in smoothed:
            assert abs(sum(vec) - 1.0) < 1e-6

    def test_first_unchanged(self):
        """First vector should be unchanged."""
        series = [[0.3, 0.3, 0.2, 0.2], [0.1, 0.5, 0.3, 0.1]]
        smoothed = ewma_smooth(series, alpha=0.3)
        for a, b in zip(smoothed[0], series[0]):
            assert abs(a - b) < 1e-9

    def test_empty(self):
        assert ewma_smooth([]) == []

    def test_single_element(self):
        """Single element should be returned as-is."""
        series = [[0.25, 0.25, 0.25, 0.25]]
        smoothed = ewma_smooth(series, alpha=0.5)
        assert len(smoothed) == 1
        for a, b in zip(smoothed[0], series[0]):
            assert abs(a - b) < 1e-9

    def test_alpha_1_means_no_smoothing(self):
        """Alpha=1 should produce the same as the input (no memory)."""
        series = [
            [0.5, 0.2, 0.2, 0.1],
            [0.1, 0.6, 0.2, 0.1],
        ]
        smoothed = ewma_smooth(series, alpha=1.0)
        for a, b in zip(smoothed[1], series[1]):
            assert abs(a - b) < 1e-6

    def test_alpha_0_means_full_memory(self):
        """Alpha=0 should keep the first vector forever."""
        series = [
            [0.5, 0.2, 0.2, 0.1],
            [0.1, 0.6, 0.2, 0.1],
            [0.0, 0.0, 1.0, 0.0],
        ]
        smoothed = ewma_smooth(series, alpha=0.0)
        for vec in smoothed:
            for a, b in zip(vec, series[0]):
                assert abs(a - b) < 1e-6


# ── Classify Regime (Mixed threshold) ────────────────────────────────

class TestClassifyRegime:
    def test_clear_dominant(self):
        """When one regime is clearly dominant, no mixed."""
        scores = [0.1, 0.1, 0.7, 0.1]  # stress dominant
        chosen, raw, note = classify_regime(scores)
        assert chosen == "stress"
        assert raw == "stress"
        assert note is None

    def test_mixed_low_top(self):
        """Top < 0.45 triggers mixed."""
        scores = [0.30, 0.30, 0.20, 0.20]  # top = 0.30 < 0.45
        chosen, raw, note = classify_regime(scores)
        assert chosen == "mixed"
        assert raw == "expansion"  # argmax
        assert note is not None
        assert "عدم قطعیت" in note

    def test_mixed_small_gap(self):
        """Gap < 0.08 between top and second triggers mixed."""
        scores = [0.28, 0.27, 0.25, 0.20]  # top=0.28, second=0.27, gap=0.01
        chosen, raw, note = classify_regime(scores)
        assert chosen == "mixed"
        assert raw in ["expansion", "tightening"]
        assert note is not None

    def test_exact_threshold_top(self):
        """Top exactly at MIXED_MIN_TOP should NOT be mixed (must be strictly less)."""
        scores = [0.45, 0.25, 0.15, 0.15]  # top = 0.45, gap = 0.20
        chosen, raw, note = classify_regime(scores)
        assert chosen != "mixed"

    def test_exact_threshold_gap(self):
        """Gap exactly at MIXED_MIN_GAP should NOT be mixed."""
        scores = [0.50, 0.42, 0.04, 0.04]  # top = 0.50, gap = 0.08
        chosen, raw, note = classify_regime(scores)
        assert chosen != "mixed"

    def test_expansion_clear(self):
        scores = [0.6, 0.15, 0.15, 0.1]
        chosen, raw, note = classify_regime(scores)
        assert chosen == "expansion"
        assert raw == "expansion"
        assert note is None

    def test_recovery_clear(self):
        scores = [0.1, 0.05, 0.05, 0.8]
        chosen, raw, note = classify_regime(scores)
        assert chosen == "recovery"
        assert raw == "recovery"

    def test_tightening_clear(self):
        scores = [0.05, 0.7, 0.15, 0.1]
        chosen, raw, note = classify_regime(scores)
        assert chosen == "tightening"
        assert raw == "tightening"

    def test_borderline_just_above_mixed(self):
        """Just above both thresholds — should not be mixed."""
        scores = [0.46, 0.37, 0.10, 0.07]  # top=0.46, gap=0.09
        chosen, raw, note = classify_regime(scores)
        assert chosen == "expansion"
        assert note is None

    def test_borderline_just_below_mixed(self):
        """Just below gap threshold — should be mixed."""
        scores = [0.46, 0.39, 0.10, 0.05]  # top=0.46, gap=0.07
        chosen, raw, note = classify_regime(scores)
        assert chosen == "mixed"


# ── Regime Scenarios (integration-style) ─────────────────────────────

class TestRegimeScenarios:
    """Integration-style tests that combine multiple helpers to verify
    regime classification under known conditions."""

    def _compute_regime(
        self, z_vix: float, z_credit: float, z_spx_dd: float,
        usdx: float, rypi: float, delta_lsi_20: float = 0.0,
    ) -> tuple[str, str]:
        """Helper: compute regime from indices. Returns (chosen, raw)."""
        lsi = max(-3.0, min(3.0, 0.5 * z_vix + 0.3 * z_credit + 0.2 * z_spx_dd))
        s_stress = 1.2 * lsi + 0.3 * usdx + 0.3 * rypi
        s_tight = 0.8 * rypi + 0.6 * usdx - 0.4 * lsi
        s_exp = -0.7 * rypi - 0.6 * usdx - 0.8 * lsi
        s_recov = -0.8 * lsi - 0.2 * rypi - 0.2 * usdx + 0.5 * delta_lsi_20
        probs = softmax([s_exp, s_tight, s_stress, s_recov])
        chosen, raw, _ = classify_regime(probs)
        return chosen, raw

    def test_stress_scenario(self):
        """High VIX + high yields + strong dollar -> STRESS."""
        chosen, raw = self._compute_regime(
            z_vix=2.5, z_credit=2.0, z_spx_dd=2.0,
            usdx=1.5, rypi=1.5,
        )
        assert raw == "stress"

    def test_tightening_scenario(self):
        """High yields + strong dollar + low VIX -> TIGHTENING."""
        chosen, raw = self._compute_regime(
            z_vix=-1.0, z_credit=-0.5, z_spx_dd=-0.5,
            usdx=2.0, rypi=2.5,
        )
        assert raw == "tightening"

    def test_expansion_scenario(self):
        """Low yields + weak dollar + low VIX -> EXPANSION."""
        chosen, raw = self._compute_regime(
            z_vix=-1.5, z_credit=-1.0, z_spx_dd=-0.5,
            usdx=-2.0, rypi=-2.0,
        )
        assert raw == "expansion"

    def test_recovery_scenario(self):
        """Falling LSI (delta_LSI_20 > 0) boosts RECOVERY."""
        chosen, raw = self._compute_regime(
            z_vix=-0.5, z_credit=-0.3, z_spx_dd=-0.2,
            usdx=-0.3, rypi=-0.2,
            delta_lsi_20=3.0,
        )
        assert raw == "recovery"
