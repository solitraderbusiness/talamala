"""
Deterministic rule matcher — matches news items against rules by keyword and
signal substring matching.

All matching is performed on normalised text so that Persian character
variations (e.g. ``\u06cc`` vs ``\u064a`` for *ye*, ``\u06a9`` vs ``\u0643``
for *kaf*), diacritics, and whitespace differences do not affect results.

No LLM is involved; every match decision is reproducible.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Sequence

from api.rule_engine.load_rules import Rule

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MatchResult:
    """The outcome of matching a single :class:`Rule` against a news item."""

    rule: Rule
    matched_keywords: list[str] = field(default_factory=list)
    matched_signals: list[str] = field(default_factory=list)
    match_score: float = 0.0  # 0.0 – 1.0

    def __post_init__(self) -> None:
        # Clamp match_score to [0, 1] at construction time.
        if not (0.0 <= self.match_score <= 1.0):
            object.__setattr__(
                self, "match_score", max(0.0, min(1.0, self.match_score))
            )


# ---------------------------------------------------------------------------
# Persian / Arabic normalisation maps
# ---------------------------------------------------------------------------

# Arabic yaa -> Persian yaa
_ARABIC_YAA = "\u064a"
_PERSIAN_YAA = "\u06cc"

# Arabic kaf -> Persian kaf
_ARABIC_KAF = "\u0643"
_PERSIAN_KAF = "\u06a9"

# Half-space (ZWNJ) — keep it as a regular space
_ZWNJ = "\u200c"

# Characters to strip entirely (zero-width joiner, LRM, RLM, BOM, …)
_INVISIBLE_RE = re.compile(r"[\u200b\u200d\u200e\u200f\ufeff]")

# Collapse any run of whitespace (including ZWNJ) into one space
_WHITESPACE_RE = re.compile(r"[\s\u200c]+")


def normalize_text(text: str) -> str:
    """Return a canonical lower-case form of *text*.

    Steps performed:

    1. Unicode NFC normalisation.
    2. Strip Unicode category **Mn** (non-spacing marks / diacritics such as
       Arabic tashkeel).
    3. Map Arabic ``\u064a`` (yaa) to Persian ``\u06cc`` and Arabic
       ``\u0643`` (kaf) to Persian ``\u06a9``.
    4. Remove invisible control characters (ZWJ, LRM, RLM, BOM).
    5. Collapse all whitespace (incl. ZWNJ) into a single ASCII space and
       strip leading / trailing whitespace.
    6. Lower-case the result.

    Parameters
    ----------
    text:
        Raw input string (may contain Persian, Arabic, or English).

    Returns
    -------
    str
        Normalised string ready for matching.
    """
    if not text:
        return ""

    # 1. NFC
    text = unicodedata.normalize("NFC", text)

    # 2. Strip diacritics / tashkeel  (category Mn = Mark, Non-spacing)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")

    # 3. Arabic -> Persian character normalisation
    text = text.replace(_ARABIC_YAA, _PERSIAN_YAA)
    text = text.replace(_ARABIC_KAF, _PERSIAN_KAF)

    # 4. Remove invisible characters
    text = _INVISIBLE_RE.sub("", text)

    # 5. Collapse whitespace (ZWNJ becomes space)
    text = _WHITESPACE_RE.sub(" ", text).strip()

    # 6. Lower-case
    text = text.lower()

    return text


# ---------------------------------------------------------------------------
# Keyword matching
# ---------------------------------------------------------------------------


def keyword_match(text: str, keywords: list[str]) -> list[str]:
    """Return the subset of *keywords* that appear in *text*.

    Both *text* and each keyword are normalised before comparison.  A keyword
    matches if it appears as a substring of the normalised text.  Matching is
    case-insensitive for English and handles Persian/Arabic character
    variations.

    Parameters
    ----------
    text:
        The haystack — typically concatenation of title + content.
    keywords:
        Candidate keywords to search for.

    Returns
    -------
    list[str]
        Original (un-normalised) keywords that matched, preserving order but
        without duplicates.
    """
    if not text or not keywords:
        return []

    norm_text = normalize_text(text)
    matched: list[str] = []
    seen: set[str] = set()

    for kw in keywords:
        if kw in seen:
            continue
        norm_kw = normalize_text(kw)
        if not norm_kw:
            continue
        if norm_kw in norm_text:
            matched.append(kw)
            seen.add(kw)

    return matched


# ---------------------------------------------------------------------------
# Signal matching (fuzzy substring)
# ---------------------------------------------------------------------------


def signal_match(text: str, signals: list[str]) -> list[str]:
    """Return the subset of *signals* whose normalised form appears in *text*.

    This is intentionally a fuzzy *substring* match after normalisation.
    Signals tend to be short descriptive phrases (e.g. "افزایش نرخ بهره")
    that should match if any contiguous run of the normalised text contains
    them.

    Parameters
    ----------
    text:
        The haystack.
    signals:
        Candidate signal phrases.

    Returns
    -------
    list[str]
        Original signal strings that matched, unique and order-preserving.
    """
    if not text or not signals:
        return []

    norm_text = normalize_text(text)
    matched: list[str] = []
    seen: set[str] = set()

    for sig in signals:
        if sig in seen:
            continue
        norm_sig = normalize_text(sig)
        if not norm_sig:
            continue
        # Fuzzy substring: check if the normalised signal phrase is a
        # contiguous substring of the normalised text.
        if norm_sig in norm_text:
            matched.append(sig)
            seen.add(sig)

    return matched


# ---------------------------------------------------------------------------
# Full rule matching
# ---------------------------------------------------------------------------


def match_rules(
    title: str,
    content: str,
    rules: Sequence[Rule],
) -> list[MatchResult]:
    """Match *title* and *content* against every rule in *rules*.

    For each rule the function checks :func:`keyword_match` and
    :func:`signal_match` against the concatenation of title and content.  Only
    rules with **at least one** keyword or signal match are included in the
    result.

    Parameters
    ----------
    title:
        News item title / headline.
    content:
        News item body text.
    rules:
        Iterable of :class:`Rule` objects to test.

    Returns
    -------
    list[MatchResult]
        Matching rules sorted by ``match_score`` descending (highest first).
    """
    combined = f"{title} {content}"
    results: list[MatchResult] = []

    for rule in rules:
        # Check negative keywords first — if any match, skip this rule
        if rule.negative_keywords:
            neg_matches = keyword_match(combined, rule.negative_keywords)
            if neg_matches:
                continue

        kw_matches = keyword_match(combined, rule.watch_for_keywords)
        sig_matches = signal_match(combined, rule.watch_for_signals)

        if not kw_matches and not sig_matches:
            continue

        score = _compute_score(
            kw_matches=kw_matches,
            sig_matches=sig_matches,
            total_keywords=len(rule.watch_for_keywords),
            total_signals=len(rule.watch_for_signals),
        )

        results.append(
            MatchResult(
                rule=rule,
                matched_keywords=kw_matches,
                matched_signals=sig_matches,
                match_score=score,
            )
        )

    # Sort descending by score, then by rule id for determinism at equal score
    results.sort(key=lambda mr: (-mr.match_score, mr.rule.id))
    return results


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _compute_score(
    *,
    kw_matches: list[str],
    sig_matches: list[str],
    total_keywords: int,
    total_signals: int,
) -> float:
    """Compute a match score in [0, 1].

    The score is the weighted average of the keyword-match ratio and the
    signal-match ratio.  Keywords are weighted 0.6, signals 0.4 — reflecting
    the fact that keywords tend to be more specific and reliable.

    Denominators are capped so that adding more keywords/signals to a rule
    does not dilute individual match scores.  Without the cap, a rule with
    18 keywords would score a single match at 0.033 (useless), while a rule
    with 5 keywords scores the same match at 0.12 (useful).  The cap ensures
    that a single compound-keyword match always has a meaningful score.

    If a rule has no keywords at all, the signal ratio alone is used and
    vice-versa.
    """
    kw_weight = 0.6
    sig_weight = 0.4

    # Cap denominators to prevent score dilution on rules with many terms.
    # With KW_CAP=5:  1 keyword match → 0.6 × (1/5) = 0.12 (always passes 0.10)
    # With SIG_CAP=10: 1 signal match → 0.4 × (1/10) = 0.04 (need 3 for 0.12)
    KW_CAP = 5
    SIG_CAP = 10

    if total_keywords == 0 and total_signals == 0:
        return 0.0

    if total_keywords == 0:
        return len(sig_matches) / min(total_signals, SIG_CAP)

    if total_signals == 0:
        return len(kw_matches) / min(total_keywords, KW_CAP)

    kw_ratio = len(kw_matches) / min(total_keywords, KW_CAP)
    sig_ratio = len(sig_matches) / min(total_signals, SIG_CAP)

    return kw_weight * kw_ratio + sig_weight * sig_ratio
