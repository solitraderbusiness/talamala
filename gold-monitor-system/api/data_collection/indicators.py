"""Pure-Python technical indicator calculations.

No external dependencies — uses only built-in math on lists of floats.
Designed to work with daily closing prices from ``asset_prices_daily``.
"""

from __future__ import annotations


def compute_rsi(closes: list[float], period: int = 14) -> float | None:
    """Compute RSI (Relative Strength Index) from a list of closing prices.

    Requires at least ``period + 1`` data points.
    Returns a value between 0 and 100, or None if insufficient data.
    """
    if len(closes) < period + 1:
        return None

    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))

    # Initial averages (SMA)
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    # Smoothed (Wilder's EMA)
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def compute_sma(values: list[float], period: int) -> float | None:
    """Compute Simple Moving Average.

    Returns the SMA of the last ``period`` values, or None if insufficient data.
    """
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def compute_atr(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> float | None:
    """Compute Average True Range.

    Requires at least ``period + 1`` bars.
    Returns ATR or None if insufficient data.
    """
    n = len(closes)
    if n < period + 1 or len(highs) < n or len(lows) < n:
        return None

    true_ranges: list[float] = []
    for i in range(1, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        true_ranges.append(tr)

    if len(true_ranges) < period:
        return None

    # Initial ATR = SMA of first `period` TRs
    atr = sum(true_ranges[:period]) / period

    # Smoothed (Wilder's method)
    for i in range(period, len(true_ranges)):
        atr = (atr * (period - 1) + true_ranges[i]) / period

    return atr
