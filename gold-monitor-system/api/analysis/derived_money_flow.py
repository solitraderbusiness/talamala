"""Pure-function derived statistics for the institutional money flow module.

No DB, no async — follows the pattern of ``api/data_collection/indicators.py``.
All functions accept plain lists/floats and return computed stats.
"""

from __future__ import annotations

import statistics
from typing import Any

from api.data_collection.percentile_scorer import percentile_rank

# ── Thresholds for combined signal classification ─────────────────────
# ETF z-score thresholds
ETF_Z_BULLISH = 0.5       # z > 0.5 = institutional accumulation
ETF_Z_BEARISH = -0.5      # z < -0.5 = institutional liquidation
ETF_Z_EXTREME = 2.0       # |z| > 2 = extreme (2-sigma event)

# COT percentile thresholds (3-year)
COT_PCT_BULLISH = 60.0    # > 60th pct = speculators mostly long
COT_PCT_BEARISH = 40.0    # < 40th pct = speculators mostly short
COT_PCT_EXTREME_HIGH = 95.0   # > 95th pct = extreme crowding
COT_PCT_EXTREME_LOW = 5.0     # < 5th pct = extreme selling

# Minimum data requirements
MIN_ZSCORE_WINDOW = 90     # need at least 90 values for z-score
MIN_PERCENTILE_VALUES = 30 # need at least 30 values for percentile
MAX_PERCENTILE_WINDOW = 500  # use up to 500 trading days (~2 years)


def compute_zscore_90d(changes: list[float]) -> float | None:
    """Compute z-score of the latest change relative to the last 90 values.

    z = (latest - mean_90) / std_90.
    Returns None if fewer than 90 values or std is zero.
    """
    if len(changes) < MIN_ZSCORE_WINDOW:
        return None

    window = changes[-MIN_ZSCORE_WINDOW:]
    mean = statistics.mean(window)
    std = statistics.stdev(window)

    if std == 0:
        return None

    return round((changes[-1] - mean) / std, 3)


def compute_percentile_2yr(changes: list[float]) -> float | None:
    """Compute percentile rank of the latest change within up to 2 years of data.

    Uses ``percentile_rank`` from the existing percentile scorer.
    Returns 0-100 float, or None if fewer than 30 values.
    """
    if len(changes) < MIN_PERCENTILE_VALUES:
        return None

    # Use at most the last 500 trading days
    distribution = changes[-MAX_PERCENTILE_WINDOW:]
    latest = distribution[-1]
    # percentile_rank returns 0.0-1.0; convert to 0-100
    rank = percentile_rank(latest, distribution)
    return round(rank * 100, 1)


def compute_cot_wow_pct_of_oi(
    change_net: float | None,
    oi: float | None,
) -> float | None:
    """Compute COT week-over-week change as a percentage of open interest.

    Returns change_net / oi * 100, or None if inputs are missing or OI is zero.
    """
    if change_net is None or oi is None or oi == 0:
        return None
    return round(change_net / oi * 100, 2)


def classify_combined_signal(
    etf_zscore: float | None,
    cot_pct_3yr: float | None,
) -> dict[str, Any]:
    """Classify the combined ETF + COT signal into a category.

    Rule-based classification:
    - EXTREME_RISK: |ETF z| > 2 OR COT pct > 95 or < 5
    - CONFIRMING: ETF z > +0.5 AND COT pct > 60
    - CONFIRMING_BEARISH: ETF z < -0.5 AND COT pct < 40
    - DIVERGING: one bullish, one bearish
    - NEUTRAL: otherwise (or insufficient data)

    Returns dict with signal, label_fa, confidence (0-100), reasons.
    """
    reasons: list[str] = []

    # If both are None, return neutral
    if etf_zscore is None and cot_pct_3yr is None:
        return {
            "signal": "NEUTRAL",
            "label_fa": "خنثی",
            "confidence": 0,
            "reasons": ["داده کافی برای محاسبه سیگنال وجود ندارد"],
        }

    # Check for extreme conditions first (highest priority)
    is_extreme = False
    if etf_zscore is not None and abs(etf_zscore) > ETF_Z_EXTREME:
        is_extreme = True
        direction = "صعودی" if etf_zscore > 0 else "نزولی"
        reasons.append(f"z-score تغییرات ETF در سطح بحرانی ({etf_zscore:+.2f}σ) — حرکت {direction} شدید نهادی")

    if cot_pct_3yr is not None and (cot_pct_3yr > COT_PCT_EXTREME_HIGH or cot_pct_3yr < COT_PCT_EXTREME_LOW):
        is_extreme = True
        if cot_pct_3yr > COT_PCT_EXTREME_HIGH:
            reasons.append(f"موقعیت سفته‌بازان در صدک {cot_pct_3yr:.0f}% — ازدحام خرید (ریسک اصلاح)")
        else:
            reasons.append(f"موقعیت سفته‌بازان در صدک {cot_pct_3yr:.0f}% — فروش افراطی (فرصت بازگشت)")

    if is_extreme:
        return {
            "signal": "EXTREME_RISK",
            "label_fa": "ریسک بحرانی",
            "confidence": 85,
            "reasons": reasons,
        }

    # Determine individual signals
    etf_bullish = etf_zscore is not None and etf_zscore > ETF_Z_BULLISH
    etf_bearish = etf_zscore is not None and etf_zscore < ETF_Z_BEARISH
    cot_bullish = cot_pct_3yr is not None and cot_pct_3yr > COT_PCT_BULLISH
    cot_bearish = cot_pct_3yr is not None and cot_pct_3yr < COT_PCT_BEARISH

    # Confirming bullish
    if etf_bullish and cot_bullish:
        if etf_zscore is not None:
            reasons.append(f"ورود پول به ETF بالاتر از میانگین (z={etf_zscore:+.2f})")
        if cot_pct_3yr is not None:
            reasons.append(f"سفته‌بازان در صدک {cot_pct_3yr:.0f}% — موضع صعودی")
        return {
            "signal": "CONFIRMING",
            "label_fa": "تأیید صعودی",
            "confidence": 75,
            "reasons": reasons,
        }

    # Confirming bearish
    if etf_bearish and cot_bearish:
        if etf_zscore is not None:
            reasons.append(f"خروج پول از ETF (z={etf_zscore:+.2f})")
        if cot_pct_3yr is not None:
            reasons.append(f"سفته‌بازان در صدک {cot_pct_3yr:.0f}% — موضع نزولی")
        return {
            "signal": "CONFIRMING_BEARISH",
            "label_fa": "تأیید نزولی",
            "confidence": 75,
            "reasons": reasons,
        }

    # Diverging: one bullish, one bearish
    if (etf_bullish and cot_bearish) or (etf_bearish and cot_bullish):
        if etf_zscore is not None:
            etf_label = "ورود پول" if etf_bullish else "خروج پول"
            reasons.append(f"ETF: {etf_label} (z={etf_zscore:+.2f})")
        if cot_pct_3yr is not None:
            cot_label = "صعودی" if cot_bullish else "نزولی"
            reasons.append(f"COT: موضع {cot_label} (صدک {cot_pct_3yr:.0f}%)")
        reasons.append("واگرایی بین جریان نهادی و موقعیت سفته‌بازان")
        return {
            "signal": "DIVERGING",
            "label_fa": "واگرایی",
            "confidence": 55,
            "reasons": reasons,
        }

    # Neutral
    if etf_zscore is not None:
        reasons.append(f"z-score تغییرات ETF در محدوده عادی ({etf_zscore:+.2f})")
    if cot_pct_3yr is not None:
        reasons.append(f"موقعیت سفته‌بازان در صدک {cot_pct_3yr:.0f}% — محدوده عادی")
    if not reasons:
        reasons.append("داده کافی برای محاسبه سیگنال وجود ندارد")

    return {
        "signal": "NEUTRAL",
        "label_fa": "خنثی",
        "confidence": 30,
        "reasons": reasons,
    }
