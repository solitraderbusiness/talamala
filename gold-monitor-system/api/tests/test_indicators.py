"""Unit tests for technical indicator calculations."""

import pytest

from api.data_collection.indicators import compute_atr, compute_rsi, compute_sma


# ── RSI Tests ─────────────────────────────────────────────────────────────

class TestComputeRSI:
    def test_rsi_insufficient_data(self):
        """RSI returns None with fewer than period+1 data points."""
        assert compute_rsi([100, 101, 102], period=14) is None

    def test_rsi_all_gains(self):
        """RSI should be 100 when all changes are positive."""
        closes = [float(i) for i in range(100, 116)]  # 16 points, all rising
        rsi = compute_rsi(closes, period=14)
        assert rsi is not None
        assert rsi == 100.0

    def test_rsi_all_losses(self):
        """RSI should be 0 when all changes are negative."""
        closes = [float(i) for i in range(115, 99, -1)]  # 16 points, all falling
        rsi = compute_rsi(closes, period=14)
        assert rsi is not None
        assert rsi == pytest.approx(0.0, abs=0.01)

    def test_rsi_known_value(self):
        """RSI with a known dataset should produce expected value."""
        # Simple alternating gains/losses
        closes = [100.0]
        for i in range(1, 30):
            if i % 2 == 0:
                closes.append(closes[-1] + 2)
            else:
                closes.append(closes[-1] - 1)
        rsi = compute_rsi(closes, period=14)
        assert rsi is not None
        assert 0 <= rsi <= 100

    def test_rsi_range(self):
        """RSI should always be between 0 and 100."""
        import random
        random.seed(42)
        closes = [100.0]
        for _ in range(50):
            closes.append(closes[-1] + random.uniform(-5, 5))
        rsi = compute_rsi(closes, period=14)
        assert rsi is not None
        assert 0 <= rsi <= 100


# ── SMA Tests ─────────────────────────────────────────────────────────────

class TestComputeSMA:
    def test_sma_insufficient_data(self):
        assert compute_sma([1, 2], period=5) is None

    def test_sma_simple(self):
        assert compute_sma([1, 2, 3, 4, 5], period=5) == 3.0

    def test_sma_last_n_values(self):
        """SMA should use only the last N values."""
        result = compute_sma([10, 20, 1, 2, 3], period=3)
        assert result == pytest.approx(2.0)

    def test_sma_period_1(self):
        """SMA with period=1 should return the last value."""
        assert compute_sma([5, 10, 15], period=1) == 15.0


# ── ATR Tests ─────────────────────────────────────────────────────────────

class TestComputeATR:
    def test_atr_insufficient_data(self):
        assert compute_atr([10, 11], [9, 10], [10, 10], period=14) is None

    def test_atr_known_values(self):
        """ATR with constant range bars should equal that range."""
        n = 20
        highs = [110.0] * n
        lows = [100.0] * n
        closes = [105.0] * n
        atr = compute_atr(highs, lows, closes, period=14)
        assert atr is not None
        assert atr == pytest.approx(10.0, abs=0.1)

    def test_atr_positive(self):
        """ATR should always be positive."""
        highs = [100 + i * 0.5 for i in range(20)]
        lows = [99 + i * 0.5 for i in range(20)]
        closes = [99.5 + i * 0.5 for i in range(20)]
        atr = compute_atr(highs, lows, closes, period=14)
        assert atr is not None
        assert atr > 0

    def test_atr_with_gaps(self):
        """ATR accounts for gaps (close-to-high/low)."""
        highs = [110, 120, 110, 120, 110, 120, 110, 120, 110, 120,
                 110, 120, 110, 120, 110, 120]
        lows = [100, 100, 100, 100, 100, 100, 100, 100, 100, 100,
                100, 100, 100, 100, 100, 100]
        closes = [105, 115, 105, 115, 105, 115, 105, 115, 105, 115,
                  105, 115, 105, 115, 105, 115]
        atr = compute_atr(highs, lows, closes, period=14)
        assert atr is not None
        assert atr > 10  # Should be > range due to gaps
