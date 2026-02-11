"""Source confidence weight calculator for the Signal Aggregator.

Computes a dynamic weight for a signal source based on its historical
accuracy, volume of signals, and recency of its last signal.

Formula
-------
    weight = base_weight * recency_factor * volume_factor

* **base_weight** -- derived from ``accuracy_rate`` (0.0 to 1.0).
  Sources with no track record default to 0.5.
* **recency_factor** -- decays exponentially as the time since the
  source's last signal increases, rewarding recently-active sources.
* **volume_factor** -- logarithmic scaling that gives more weight to
  sources with a larger signal history (diminishing returns).
"""

from __future__ import annotations

import math
from datetime import datetime, timezone


def calculate_source_weight(
    accuracy_rate: float | None,
    total_signals: int | None,
    last_signal_at: datetime | None,
) -> float:
    """Return a weight in the range ``[0.05, 1.0]``.

    Parameters
    ----------
    accuracy_rate:
        Fraction of correct signals (0.0-1.0).  ``None`` means no data
        yet -- treated as 0.5 (neutral).
    total_signals:
        Lifetime signal count for the source.
    last_signal_at:
        UTC timestamp of the source's most recent signal.

    Returns
    -------
    float
        Computed weight clamped to ``[0.05, 1.0]``.
    """
    # -- Base weight (from accuracy) ---------------------------------
    if accuracy_rate is not None and accuracy_rate > 0:
        # Map accuracy to a 0.1-1.0 range (floor at 0.1 so even bad
        # sources contribute minimally).
        base_weight = max(0.1, min(1.0, accuracy_rate))
    else:
        base_weight = 0.5  # neutral prior

    # -- Recency factor ----------------------------------------------
    # Exponential decay: factor = exp(-days_since_last / half_life)
    # Half-life = 7 days -- after 7 days the factor ~ 0.37, after 14
    # days ~ 0.14, etc.
    _RECENCY_HALF_LIFE_DAYS = 7.0

    if last_signal_at is not None:
        now = datetime.now(timezone.utc)
        # Handle both tz-aware and naive datetimes gracefully
        if last_signal_at.tzinfo is None:
            last_signal_at = last_signal_at.replace(tzinfo=timezone.utc)
        days_since = max(0.0, (now - last_signal_at).total_seconds() / 86400.0)
        recency_factor = math.exp(-days_since / _RECENCY_HALF_LIFE_DAYS)
    else:
        # No signal ever -> low recency, but not zero
        recency_factor = 0.2

    # Clamp
    recency_factor = max(0.1, min(1.0, recency_factor))

    # -- Volume factor -----------------------------------------------
    # log2 scaling: 0 signals -> 0.3, 1 -> ~0.33, 2 -> ~0.45,
    # 10 -> ~0.74, 50 -> ~0.91, 100+ -> ~1.0
    _VOLUME_LOG_BASE = 2
    _VOLUME_SCALE = 100  # signals needed to reach factor ~1.0

    signals = max(0, total_signals or 0)
    if signals == 0:
        volume_factor = 0.3
    else:
        volume_factor = 0.3 + 0.7 * min(
            1.0,
            math.log(1 + signals, _VOLUME_LOG_BASE)
            / math.log(1 + _VOLUME_SCALE, _VOLUME_LOG_BASE),
        )

    # -- Final weight ------------------------------------------------
    weight = base_weight * recency_factor * volume_factor
    return round(max(0.05, min(1.0, weight)), 4)
