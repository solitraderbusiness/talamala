"""Pure-math unit tests for the regime engine helpers.

No database or network access — tests only the deterministic math functions.
"""

import math

import pytest

from api.analysis.workers.regime_engine import (
    compute_credit_proxy,
    ewma_smooth,
    log_return,
    rolling_zscore,
    softmax,
)


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


class TestRollingZscore:
    def test_clipping(self):
        """Values should be clamped to [-3, +3]."""
        # Create a series with an extreme outlier
        values: list[float | None] = [1.0] * 100 + [100.0]
        zscores = rolling_zscore(values, n=100)
        last = zscores[-1]
        assert last is not None
        assert -3.0 <= last <= 3.0

    def test_zero_std(self):
        """When all values are identical, z-score should be ~0 (epsilon guard)."""
        values: list[float | None] = [5.0] * 50
        zscores = rolling_zscore(values, n=50)
        # At the end of the series, z-score should be near 0
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


class TestRegimeScenarios:
    """Integration-style tests that combine multiple helpers to verify
    regime classification under known conditions."""

    def _compute_regime(
        self, z_vix: float, z_credit: float, z_spx_dd: float,
        usdx: float, rypi: float, delta_lsi_20: float = 0.0,
    ) -> str:
        """Helper: compute regime from indices."""
        lsi = max(-3.0, min(3.0, 0.5 * z_vix + 0.3 * z_credit + 0.2 * z_spx_dd))
        s_stress = 1.2 * lsi + 0.3 * usdx + 0.3 * rypi
        s_tight = 0.8 * rypi + 0.6 * usdx - 0.4 * lsi
        s_exp = -0.7 * rypi - 0.6 * usdx - 0.8 * lsi
        s_recov = -0.8 * lsi - 0.2 * rypi - 0.2 * usdx + 0.5 * delta_lsi_20
        probs = softmax([s_exp, s_tight, s_stress, s_recov])
        labels = ["expansion", "tightening", "stress", "recovery"]
        return labels[probs.index(max(probs))]

    def test_stress_scenario(self):
        """High VIX + high yields + strong dollar -> STRESS."""
        regime = self._compute_regime(
            z_vix=2.5, z_credit=2.0, z_spx_dd=2.0,
            usdx=1.5, rypi=1.5,
        )
        assert regime == "stress"

    def test_tightening_scenario(self):
        """High yields + strong dollar + low VIX -> TIGHTENING."""
        regime = self._compute_regime(
            z_vix=-1.0, z_credit=-0.5, z_spx_dd=-0.5,
            usdx=2.0, rypi=2.5,
        )
        assert regime == "tightening"

    def test_expansion_scenario(self):
        """Low yields + weak dollar + low VIX -> EXPANSION."""
        regime = self._compute_regime(
            z_vix=-1.5, z_credit=-1.0, z_spx_dd=-0.5,
            usdx=-2.0, rypi=-2.0,
        )
        assert regime == "expansion"

    def test_recovery_scenario(self):
        """Falling LSI (delta_LSI_20 > 0) boosts RECOVERY."""
        regime = self._compute_regime(
            z_vix=-0.5, z_credit=-0.3, z_spx_dd=-0.2,
            usdx=-0.3, rypi=-0.2,
            delta_lsi_20=3.0,
        )
        assert regime == "recovery"
