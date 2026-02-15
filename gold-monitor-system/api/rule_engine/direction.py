"""
3-stage direction detection for gold market news.

Stage 1: Regex patterns with flexible word order (FREE, instant, ~60% hit rate)
Stage 2: Lexicon scoring with gold-domain word weights (FREE, ~20% more)
Stage 3: LLM classification for ambiguous cases (queued for batch processing)

Direction means: is this news BULLISH, BEARISH, or NEUTRAL for gold price?
"""

from __future__ import annotations

import re
from typing import Any

# ── Stage 1: Regex Patterns ─────────────────────────────────────────────
# Flexible patterns with .{0,N} gaps to handle word order variations.
# E.g. "قیمت طلا به بالای ۵۰۰۰" matches even with "به" between words.

BULLISH_PATTERNS = [
    # Price going up — flexible word order
    r"(قیمت|بها|نرخ).{0,20}(طلا|سکه|اونس|gold).{0,30}(افزایش|رشد|صعود|بالا|جهش|رکورد|surge|rise|jump|rally|high|soar)",
    r"(افزایش|رشد|صعود|جهش|رکورد).{0,20}(قیمت|بها|نرخ).{0,20}(طلا|سکه|gold)",
    r"(طلا|gold).{0,30}(بالای|بالاتر|above|over|surpass).{0,10}\d",
    # Weak dollar (bullish for gold)
    r"(تضعیف|کاهش|سقوط|ریزش).{0,20}(دلار|dollar|DXY)",
    r"(دلار|dollar|DXY).{0,20}(ضعیف|کاهش|سقوط|پایین|weak|fall|drop|decline)",
    # Rate cuts (bullish for gold) — NOTE: negation patterns below override these
    r"(کاهش|cut).{0,15}(نرخ\s*بهره|interest\s*rate)",
    r"(نرخ\s*بهره|rate).{0,15}(کاهش|cut|پایین|lower)",
    # Safe haven demand
    r"(تقاضا|demand).{0,20}(طلا|gold).{0,15}(افزایش|رشد|بالا|surge|rise)",
    r"(خرید|buy|purchase).{0,20}(بانک\s*مرکزی|central\s*bank).{0,20}(طلا|gold)",
    # Geopolitical tension (bullish for gold)
    r"(تنش|جنگ|حمله|تحریم|tension|war|attack|sanction).{0,30}(افزایش|تشدید|escalat)",
    # Inflation (bullish for gold)
    r"(تورم|inflation).{0,20}(افزایش|بالا|rise|high|surge)",
    # ETF inflows
    r"(ETF|صندوق).{0,20}(ورود|inflow|افزایش\s*سرمایه)",
    # China/India demand
    r"(چین|هند|china|india).{0,30}(خرید|تقاضا|buy|demand).{0,20}(طلا|gold)",
    r"(تقاضا|demand).{0,20}(چین|هند|china|india).{0,20}(طلا|gold)",
]

BEARISH_PATTERNS = [
    # Price going down — gold
    r"(قیمت|بها|نرخ).{0,20}(طلا|سکه|gold).{0,30}(کاهش|ریزش|سقوط|نزول|(?<=\s)افت(?=\s|$)|drop|fall|decline|crash|plunge)",
    r"(کاهش|ریزش|سقوط|نزول|افت).{0,20}(قیمت|بها).{0,20}(طلا|سکه|gold)",
    r"(طلا|gold).{0,30}(زیر|پایین|below|under).{0,10}\d",
    # Price going down — silver (correlated with gold)
    r"(سقوط|ریزش|نزول|افت|crash|plunge|drop).{0,30}(نقره|silver)",
    r"(نقره|silver).{0,30}(سقوط|ریزش|نزول|افت|crash|plunge|drop|fall|decline)",
    # Strong dollar (bearish for gold)
    r"(تقویت|رشد|صعود|جهش).{0,20}(دلار|dollar|DXY)",
    r"(دلار|dollar|DXY).{0,20}(قوی|صعود|رشد|بالا|strong|rise|surge|rally)",
    # Rate hikes (bearish for gold)
    r"(افزایش|hike|raise).{0,15}(نرخ\s*بهره|interest\s*rate)",
    r"(نرخ\s*بهره|rate).{0,15}(افزایش|hike|بالا|higher)",
    # Risk-on sentiment (bearish for gold)
    r"(بازار\s*سهام|stock\s*market).{0,20}(رشد|صعود|رکورد|rally|surge|boom)",
    # ETF outflows
    r"(ETF|صندوق).{0,20}(خروج|outflow|کاهش\s*سرمایه)",
    # Deflation / low inflation
    r"(تورم|inflation).{0,20}(کاهش|پایین|drop|low|cool)",
]

# ── Negation patterns ─────────────────────────────────────────────────
# These OVERRIDE bullish signals when "hopes fade" / "expectations reduce"
# for otherwise-bullish events (e.g. rate cuts hopes fading = bearish).

NEGATION_BEARISH_PATTERNS = [
    # "Reduced/fading hopes for rate cuts" — bearish, NOT bullish
    r"(کاهش|کم‌شدن|افت|تضعیف).{0,15}(امید|انتظار|احتمال).{0,20}(کاهش\s*نرخ\s*بهره|rate\s*cut)",
    r"(rate\s*cut|کاهش\s*نرخ\s*بهره).{0,15}(hopes?\s*fad|expectations?\s*f[ae]|unlikely|doubt)",
    r"(امید|انتظار|احتمال).{0,15}(کاهش\s*نرخ\s*بهره).{0,15}(کاهش|کم|ضعیف|از\s*بین)",
    # "No rate cut" / "rate cut ruled out"
    r"(عدم|بدون|no|without).{0,10}(کاهش|cut).{0,10}(نرخ\s*بهره|rate)",
    # "Rates to stay higher / higher for longer"
    r"(نرخ\s*بهره|rate).{0,20}(بالاتر|higher).{0,15}(ماندن|remain|stay|longer)",
    r"higher.{0,10}for.{0,10}longer",
]


# ── Stage 2: Lexicon with Gold-Domain Weights ───────────────────────────
# Words that are inherently bullish/bearish for GOLD specifically.

GOLD_BULLISH_WORDS: dict[str, float] = {
    # Strong bullish
    "رکورد": 0.8, "رکوردشکنی": 0.9, "جهش": 0.7, "صعود": 0.7,
    "surge": 0.7, "rally": 0.7, "soar": 0.8, "record": 0.8,
    "بالاترین": 0.6, "highest": 0.6, "all-time": 0.9,
    "تقاضا": 0.4, "demand": 0.4, "خرید": 0.4, "buying": 0.4,
    "پناهگاه": 0.5, "safe-haven": 0.5, "haven": 0.5,
    "تنش": 0.3, "tension": 0.3, "جنگ": 0.4, "war": 0.4,
    "تحریم": 0.3, "sanction": 0.3,
    "تورم": 0.3, "inflation": 0.3,
    # Medium bullish
    "افزایش": 0.3, "رشد": 0.3, "increase": 0.3, "rise": 0.3,
    "بالا": 0.2, "high": 0.2, "up": 0.2,
}

GOLD_BEARISH_WORDS: dict[str, float] = {
    "سقوط": 0.8, "ریزش": 0.7, "crash": 0.8, "plunge": 0.8,
    "نزول": 0.6, "افت": 0.5, "decline": 0.5, "drop": 0.5,
    "کاهش": 0.3, "فروش": 0.3, "selling": 0.3, "sell-off": 0.6,
    "پایین": 0.2, "low": 0.2, "down": 0.2, "fall": 0.4,
    # Silver drop is bearish for gold (correlated metals)
    "نقره": 0.2, "silver": 0.2,
}


# ── Public API ──────────────────────────────────────────────────────────


def detect_direction_regex(title: str, content: str = "") -> tuple[str, float]:
    """Stage 1: Regex-based direction detection with flexible patterns.

    Returns (direction, confidence) where direction is
    'bullish', 'bearish', or 'neutral'.
    """
    text = f"{title} {content}".strip()

    # Check negation patterns FIRST — these override bullish signals
    # (e.g. "rate cut hopes fade" should be bearish, not bullish)
    negation_matches = sum(
        1 for p in NEGATION_BEARISH_PATTERNS if re.search(p, text, re.IGNORECASE)
    )
    if negation_matches > 0:
        confidence = min(0.85, 0.6 + negation_matches * 0.1)
        return ("bearish", confidence)

    bull_matches = sum(
        1 for p in BULLISH_PATTERNS if re.search(p, text, re.IGNORECASE)
    )
    bear_matches = sum(
        1 for p in BEARISH_PATTERNS if re.search(p, text, re.IGNORECASE)
    )

    if bull_matches == 0 and bear_matches == 0:
        return ("neutral", 0.0)

    total = bull_matches + bear_matches

    if bull_matches > bear_matches:
        confidence = min(0.85, 0.5 + (bull_matches - bear_matches) / total * 0.5)
        return ("bullish", confidence)
    elif bear_matches > bull_matches:
        confidence = min(0.85, 0.5 + (bear_matches - bull_matches) / total * 0.5)
        return ("bearish", confidence)
    else:
        return ("neutral", 0.3)  # conflicting signals


def detect_direction_lexicon(title: str) -> tuple[str, float]:
    """Stage 2: Lexicon-based scoring with gold-domain word weights.

    Fallback for when Stage 1 regex patterns don't match.
    Returns (direction, confidence).
    """
    words = title.lower().split()

    bull_score = sum(GOLD_BULLISH_WORDS.get(w, 0) for w in words)
    bear_score = sum(GOLD_BEARISH_WORDS.get(w, 0) for w in words)

    if bull_score == 0 and bear_score == 0:
        return ("neutral", 0.0)

    net = bull_score - bear_score
    total = bull_score + bear_score
    confidence = min(0.70, abs(net) / max(total, 1) * 0.7)

    if net > 0.15:
        return ("bullish", confidence)
    elif net < -0.15:
        return ("bearish", confidence)
    return ("neutral", 0.2)


def detect_direction(
    title: str,
    content: str = "",
    use_llm: bool = False,
) -> dict[str, Any]:
    """3-stage direction detection for gold market news.

    1. Regex patterns (flexible word order) — catches ~60%
    2. Lexicon scoring (gold-domain weights) — catches ~20% more
    3. LLM fallback (queued for batch) — last resort

    Returns dict with keys: direction, confidence, method.
    """
    # Stage 1: Regex patterns
    direction, confidence = detect_direction_regex(title, content)
    if confidence >= 0.5:
        return {"direction": direction, "confidence": confidence, "method": "regex"}

    # Stage 2: Lexicon scoring
    direction2, confidence2 = detect_direction_lexicon(title)
    if confidence2 >= 0.4:
        return {"direction": direction2, "confidence": confidence2, "method": "lexicon"}

    # If Stage 1 had some signal but below threshold, use it
    if confidence > 0:
        return {"direction": direction, "confidence": confidence, "method": "regex_weak"}

    # Stage 3: LLM would be called here in batch mode
    if use_llm:
        return {"direction": "pending_llm", "confidence": 0.0, "method": "llm_queued"}

    # Final fallback
    return {"direction": "neutral", "confidence": 0.15, "method": "fallback"}


def calculate_alert_score(
    direction: str,
    confidence: float,
    severity: str,
    *,
    match_score: float = 0.0,
    num_rules_matched: int = 0,
    num_keywords_matched: int = 0,
    num_signals_matched: int = 0,
    direction_method: str = "",
    content_length: int = 0,
) -> int:
    """Calculate per-alert sentiment score (0-100).

    50 = neutral, 100 = extremely bullish, 0 = extremely bearish.
    Severity acts as a multiplier on the base swing.  Additional enrichment
    factors (match quality, evidence depth, detection method, content length)
    widen the spread so that stronger alerts score further from 50.

    All keyword-only params default to zero so that callers without enrichment
    data (e.g. legacy recalculation) produce the same output as before.
    """
    SEVERITY_MULTIPLIER = {
        "critical": 1.0,  # full range: 0-100
        "high": 0.8,      # range: 10-90
        "medium": 0.6,    # range: 20-80
        "low": 0.35,      # range: 32-68
    }

    METHOD_BONUS = {
        "regex": 3,
        "lexicon": 1,
        "regex_weak": -1,
        "fallback": -2,
    }

    if direction == "neutral" or direction == "pending_llm":
        return 50

    sign = 1 if direction == "bullish" else -1

    # confidence 0.3-1.0 maps to 15-45 points from center
    conf_clamped = max(0.3, min(1.0, confidence))
    base_swing = 15 + (conf_clamped - 0.3) * (30 / 0.7)

    multiplier = SEVERITY_MULTIPLIER.get(severity, 0.6)

    # --- enrichment bonuses ------------------------------------------------ #
    match_quality_bonus = match_score * 6                            # 0-6
    multi_rule_bonus = min(num_rules_matched - 1, 3) * 2            # 0-6 (neg when 0 rules)
    multi_rule_bonus = max(0, multi_rule_bonus)                      # clamp to 0
    evidence_depth_bonus = min(num_keywords_matched + num_signals_matched, 8) * 0.75  # 0-6
    method_bonus = METHOD_BONUS.get(direction_method, 0)             # -2 to 3
    content_bonus = min(content_length / 500, 1) * 3                 # 0-3

    total_bonus = (
        match_quality_bonus
        + multi_rule_bonus
        + evidence_depth_bonus
        + method_bonus
        + content_bonus
    )

    score = 50 + sign * (base_swing * multiplier + total_bonus)

    return max(0, min(100, round(score)))
