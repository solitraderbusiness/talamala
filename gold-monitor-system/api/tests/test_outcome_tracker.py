"""Unit tests for the outcome tracker logic."""

import pytest

from api.data_collection.outcome_tracker import _check_direction, _compute_final_metrics


class TestCheckDirection:
    def test_bullish_positive_change(self):
        """Bullish direction + positive change = correct."""
        assert _check_direction("bullish", 1.5) is True

    def test_bullish_negative_change(self):
        """Bullish direction + negative change = incorrect."""
        assert _check_direction("bullish", -0.5) is False

    def test_bearish_negative_change(self):
        """Bearish direction + negative change = correct."""
        assert _check_direction("bearish", -2.0) is True

    def test_bearish_positive_change(self):
        """Bearish direction + positive change = incorrect."""
        assert _check_direction("bearish", 0.3) is False

    def test_neutral_returns_none(self):
        """Neutral direction should return None."""
        assert _check_direction("neutral", 1.0) is None

    def test_none_direction_returns_none(self):
        """None direction should return None."""
        assert _check_direction(None, 1.0) is None

    def test_empty_direction_returns_none(self):
        """Empty string direction should return None."""
        assert _check_direction("", 1.0) is None

    def test_zero_change_bearish(self):
        """Zero change with bearish direction = not correct."""
        assert _check_direction("bearish", 0.0) is False

    def test_zero_change_bullish(self):
        """Zero change with bullish direction = not correct."""
        assert _check_direction("bullish", 0.0) is False


class TestComputeFinalMetrics:
    """Test the final metrics computation using a mock outcome object."""

    class MockOutcome:
        """Minimal mock of AlertOutcome for testing."""
        def __init__(self, direction="bullish"):
            self.alert_direction = direction
            self.change_pct_30min = None
            self.change_pct_1h = None
            self.change_pct_4h = None
            self.change_pct_24h = None
            self.change_pct_48h = None
            self.change_pct_7d = None
            self.direction_correct_1h = None
            self.direction_correct_4h = None
            self.direction_correct_24h = None
            self.max_favorable_move_pct = None
            self.max_adverse_move_pct = None
            self.time_to_max_favorable_hours = None
            self.reverted_within_4h = None
            self.reverted_within_24h = None

    def test_bullish_favorable_moves(self):
        outcome = self.MockOutcome("bullish")
        outcome.change_pct_30min = 0.5
        outcome.change_pct_1h = 1.0
        outcome.change_pct_4h = -0.3
        outcome.change_pct_24h = 2.0
        outcome.change_pct_48h = 1.5
        outcome.change_pct_7d = 3.0

        _compute_final_metrics(outcome)

        assert outcome.max_favorable_move_pct == 3.0
        assert outcome.max_adverse_move_pct == 0.3

    def test_bearish_favorable_moves(self):
        outcome = self.MockOutcome("bearish")
        outcome.change_pct_30min = -0.5
        outcome.change_pct_1h = -1.0
        outcome.change_pct_4h = 0.3
        outcome.change_pct_24h = -2.0
        outcome.change_pct_48h = -1.5
        outcome.change_pct_7d = -3.0

        _compute_final_metrics(outcome)

        assert outcome.max_favorable_move_pct == 3.0
        assert outcome.max_adverse_move_pct == 0.3

    def test_reversion_detected_4h(self):
        """Reversion at 4h: correct at 1h but wrong at 4h."""
        outcome = self.MockOutcome("bullish")
        outcome.change_pct_1h = 1.0
        outcome.change_pct_4h = -0.5
        outcome.direction_correct_1h = True
        outcome.direction_correct_4h = False
        outcome.direction_correct_24h = False

        _compute_final_metrics(outcome)

        assert outcome.reverted_within_4h is True
        # reverted_within_24h: correct_4h=False, so no 4h→24h reversion
        assert outcome.reverted_within_24h is False

    def test_reversion_detected_24h(self):
        """Reversion at 24h: correct at 4h but wrong at 24h."""
        outcome = self.MockOutcome("bullish")
        outcome.change_pct_1h = 1.0
        outcome.change_pct_4h = 2.0
        outcome.change_pct_24h = -0.5
        outcome.direction_correct_1h = True
        outcome.direction_correct_4h = True
        outcome.direction_correct_24h = False

        _compute_final_metrics(outcome)

        assert outcome.reverted_within_4h is False
        assert outcome.reverted_within_24h is True

    def test_no_reversion(self):
        outcome = self.MockOutcome("bullish")
        outcome.change_pct_1h = 1.0
        outcome.change_pct_4h = 2.0
        outcome.change_pct_24h = 3.0
        outcome.direction_correct_1h = True
        outcome.direction_correct_4h = True
        outcome.direction_correct_24h = True

        _compute_final_metrics(outcome)

        assert outcome.reverted_within_4h is False
        assert outcome.reverted_within_24h is False

    def test_no_changes(self):
        outcome = self.MockOutcome("bullish")
        _compute_final_metrics(outcome)
        assert outcome.max_favorable_move_pct is None
        assert outcome.max_adverse_move_pct is None

    def test_time_to_max_favorable(self):
        outcome = self.MockOutcome("bullish")
        outcome.change_pct_30min = 0.1
        outcome.change_pct_1h = 0.5
        outcome.change_pct_4h = 2.0  # max favorable
        outcome.change_pct_24h = 1.5

        _compute_final_metrics(outcome)

        assert outcome.time_to_max_favorable_hours == 4
