# Talamala — System Logic & Formulas (منطق سیستم)

> This document explains how every calculation, score, and decision in the system works.
> Intended for: admin panel "How It Works" page + developer reference.

---

## Table of Contents

1. [Sentiment Score (شاخص احساسات بازار)](#1-sentiment-score)
2. [Risk / Activity Score (شاخص فعالیت بازار)](#2-risk--activity-score)
3. [Rule Matching (تطبیق قوانین)](#3-rule-matching)
4. [Severity Assignment (تعیین شدت هشدار)](#4-severity-assignment)
5. [Time Horizon (افق زمانی)](#5-time-horizon)
6. [News Categorization (دسته‌بندی اخبار)](#6-news-categorization)
7. [Alert Building (ساخت هشدار)](#7-alert-building)
8. [Deduplication (حذف تکراری‌ها)](#8-deduplication)
9. [Price Data (داده‌های قیمت)](#9-price-data)
10. [News Sources & Fetchers (منابع خبری)](#10-news-sources--fetchers)
11. [Key Thresholds & Constants (مقادیر ثابت)](#11-key-thresholds--constants)

---

## 1. Sentiment Score

**What it shows:** A 0-100 gauge of market sentiment direction.
- 50 = neutral (no signal)
- 0 = extremely bearish
- 100 = extremely bullish

**File:** `api/routers/sentiment.py`

### Formula (3-Layer Weighted System)

**Layer 1 — Per-Alert Polarity:**
Each alert gets a raw sentiment from its `expected_impact.direction`:
```
Polarity = +1.0 if bullish
           -1.0 if bearish
            0.0 if mixed/unclear
```
If no direction found, a severity-based default is used (gold's safe-haven bias):
- high severity → +0.3
- medium severity → +0.15
- low severity → +0.05

Raw sentiment per alert:
```
RSS = Polarity × Confidence
```

**Layer 2 — Importance Weighting:**
```
Weighted = RSS × ImportanceWeight
```
Importance weights by severity:
| Severity | Weight |
|----------|--------|
| critical | 3.0 |
| high | 2.0 |
| medium | 1.0 |
| low | 0.5 |

**Layer 3 — Exponential Time Decay:**
Newer alerts matter more. Each alert's contribution decays over time:
```
Contribution = Weighted × e^(-lambda × hours_since_alert)
```
Lambda values per timeframe:
| Timeframe | Lambda | Half-life |
|-----------|--------|-----------|
| 1h | 2.0 | ~21 min |
| 4h | 0.5 | ~1.4 hours |
| 24h | 0.1 | ~7 hours |

**Aggregation:**
```
sentiment_raw = (Sum of all contributions / Sum of all absolute weights) × 100
```
Range: -100 to +100

**Volume Dampening:**
Prevents noisy signals when few alerts exist:
```
dampened = sentiment_raw × min(1.0, alert_count / volume_threshold)
```
Volume thresholds:
| Timeframe | Min alerts for full signal |
|-----------|--------------------------|
| 1h | 10 |
| 4h | 20 |
| 24h | 30 |

**Final Score:**
```
score = clamp(50 + dampened / 2, 0, 100)
```

### Score → Label Mapping

| Score Range | Label | Persian | Color |
|-------------|-------|---------|-------|
| 0–19 | very_bearish | بسیار نزولی | Red |
| 20–37 | bearish | نزولی | Red |
| 38–61 | neutral | خنثی | Amber |
| 62–79 | bullish | صعودی | Green |
| 80–100 | very_bullish | بسیار صعودی | Green |

---

## 2. Risk / Activity Score

**What it shows:** A 0-100 gauge of market activity/volatility. NOT direction — just "how much is happening."

**File:** `api/routers/alerts.py`

### Formula

```
For each alert:
  hours_ago = time since alert
  recency = e^(-0.173 × hours_ago)     // 4-hour half-life
  contribution = severity_weight × recency × confidence

raw_total = sum of all contributions
score = clamp(20 × ln(1 + raw_total), 0, 100)
```

Severity weights:
| Severity | Weight |
|----------|--------|
| high | 8.0 |
| medium | 2.0 |
| low | 0.5 |

Minimum confidence floor: 0.3

### Calibration (approximate)

| Situation | Expected Score |
|-----------|---------------|
| Quiet market, few low alerts | 10–20 |
| Normal day, some medium alerts | 30–45 |
| Active day, several high alerts | 50–70 |
| Crisis/shock, many high alerts | 75–90 |
| Extreme sustained volume | 90+ |

The logarithmic scale (`20 × ln(1+x)`) prevents saturation — even with many alerts, the score doesn't easily hit 100.

---

## 3. Rule Matching

**What it does:** Determines which of the 32 rules (+ 5 technical signals) apply to a news item.

**File:** `api/rule_engine/matcher.py`

### Text Normalization (6 steps)

Before any matching, all text goes through:
1. Unicode NFC normalization
2. Strip all diacritics (Arabic tashkeel)
3. Map Arabic chars to Persian: `ي→ی`, `ك→ک`
4. Remove invisible characters (ZWJ, LRM, RLM, BOM)
5. Collapse whitespace (ZWNJ→space), strip
6. Lowercase

### Matching Algorithm

For each rule, the system first checks **negative keywords** — if any match, the rule is skipped entirely (prevents false positives like "gold medal" matching gold price rules).

Then it checks keywords AND signals against the normalized title+content:

```
# Step 1: Negative keyword filter
if any(neg_kw in text for neg_kw in rule.negative_keywords):
    skip this rule

# Step 2: Positive matching
keyword_matches = [kw for kw in rule.keywords if normalized(kw) in normalized(text)]
signal_matches  = [sig for sig in rule.signals if normalized(sig) in normalized(text)]
```

Both use **substring matching** — no regex, no fuzzy matching.

A rule matches if it has **at least one keyword OR signal match**.

### Match Score

```
kw_ratio  = matched_keywords / total_keywords      (0.0 to 1.0)
sig_ratio = matched_signals / total_signals         (0.0 to 1.0)
score     = 0.6 × kw_ratio + 0.4 × sig_ratio       (0.0 to 1.0)
```

Keywords are weighted 60% (more specific) vs signals at 40%.

### Minimum Score Threshold

The worker filters out low-quality matches:
```
MIN_MATCH_SCORE = 0.10
```
- 1 keyword out of 10 = 0.06 → **filtered out**
- 1 keyword out of 5 = 0.12 → **passes** (enough for English title-only content)
- 2 keywords out of 6 = 0.20 → **passes**

### LLM Relevance Filter (Optional)

For borderline matches (score between 0.10 and 0.30), if LLM is enabled, the system asks the LLM: "Is this article relevant to gold/financial markets?" Articles that score >= 0.30 skip this check (high confidence). This prevents false positives like sports or IT articles that happen to contain a financial keyword.

```
HIGH_CONFIDENCE_SCORE = 0.30  # above this, no LLM check needed
```

### Confidence (derived from match score)

```
confidence = 0.3 + match_score × 0.65
```
- Score 0.0 → confidence 0.30 (30%)
- Score 1.0 → confidence 0.95 (95%)
- Never reaches 100% — system never claims certainty

---

## 4. Severity Assignment

**What it decides:** Whether an alert is high (بالا), medium (متوسط), or low (پایین).

**File:** `api/rule_engine/severity.py`

### Algorithm

For each matched rule, the system checks the rule's `importance_criteria` from the YAML:

```
1. Normalize the alert content
2. Check high_if conditions → if any substring matches → "high"
3. Check medium_if conditions → if any substring matches → "medium"
4. Check low_if conditions → if any substring matches → "low"
5. Default → "medium"
```

**Priority order:** high > medium > low. First match wins.

### Example (Rule: GLOB_GOLD_PRICE)

```yaml
importance_criteria:
  high_if:
    - "رکورد جدید یا حرکت شدید (بیش از ۲٪ در یک روز)"
    - "پیش‌بینی مهم از نهاد معتبر (Goldman Sachs, JP Morgan, WGC)"
  medium_if:
    - "حرکت عادی بازار با تحلیل"
  low_if:
    - "تکرار اخبار قبلی بدون داده جدید"
```

### When Multiple Rules Match

Each rule gets its own severity. The **highest** severity across all matched rules is used for the alert.

**Important limitation:** The condition phrases are matched as substrings against the content. So "Goldman Sachs" in the content would trigger high severity — but only if the full phrase "پیش‌بینی مهم از نهاد معتبر (Goldman Sachs, JP Morgan, WGC)" appears. In practice, most alerts fall to the **default: medium** because the exact condition phrases rarely appear verbatim.

---

## 5. Time Horizon

**What it decides:** The labels فوری / کوتاه‌مدت / میان‌مدت / بلندمدت on each alert.

**File:** `api/rule_engine/alert_builder.py`

### Logic

Time horizon is **NOT derived from the content**. It's a **fixed property of the rule** in the YAML:

```yaml
- id: "GLOB_RATE_DECISION"
  horizon: "immediate"        # ← Always "فوری" for rate decisions

- id: "GLOB_MINING_SUPPLY"
  horizon: "medium"           # ← Always "میان‌مدت" for mining supply
```

When multiple rules match, the horizon comes from whichever rule has the **highest severity**.

### Horizon Labels

| Value | Persian | Meaning |
|-------|---------|---------|
| immediate | فوری | Minutes to hours |
| short | کوتاه‌مدت | Days to weeks |
| medium | میان‌مدت | Weeks to months |
| long | بلندمدت | Months to years |

---

## 6. News Categorization

**What it decides:** Which section (tab/category) an alert belongs to on the dashboard.

**File:** `api/routers/alerts.py`

### Logic

```
1. Get matched_rule_ids from alert
2. If any rule is in GEOPOLITICS set → section = "geopolitics"
3. Otherwise, take first rule ID prefix:
   - GLOB_* → "global_gold"
   - IR_*   → "iran_gold"
   - COIN_* → "coin"
   - FUNDS_* → "gold_funds"
4. Default → "global_gold"
```

### Geopolitics Override Rules

These rules always get their own section regardless of prefix:
- `GLOB_GEOPOL_RISK` — War, attacks, escalation
- `GLOB_EQUITY_RISK_OFF` — Stock market crash, bank crisis
- `IR_RESERVES_SANCTIONS` — Sanctions, frozen assets
- `IR_FOREIGN_POLICY` — JCPOA negotiations
- `IR_INTERNAL_POL_SOCIAL` — Internal unrest

### Section Display

| Section ID | Label | Icon |
|-----------|-------|------|
| global_gold | طلای جهانی | 🌍 |
| iran_gold | طلا و ارز ایران | 🇮🇷 |
| coin | سکه | 🪙 |
| gold_funds | صندوق‌های طلا | 📈 |
| geopolitics | ژئوپلیتیک | ⚡ |

---

## 7. Alert Building

**What it does:** Converts a raw news item + matched rules into a structured alert.

**File:** `api/rule_engine/alert_builder.py`

### Pipeline

```
Raw News Item
    ↓
Match against 32 rules (see §3)
    ↓
For each matched rule:
  - Determine severity (see §4)
  - Calculate confidence (see §3)
    ↓
Pick highest severity across all rules
Pick time horizon from highest-severity rule
Average confidence across all rules
    ↓
Build expected_impact from all rules' impact_hypothesis
    ↓
Optional: LLM enrichment (Persian summary, why-important)
    ↓
Generate dedupe_key = SHA-256(sorted_rule_ids + "|" + normalized_title)
    ↓
Final Alert Object
```

### Alert Fields

| Field | Source |
|-------|--------|
| title | LLM (if enabled) or original title |
| timestamp_utc | From news item |
| source_name | From source config |
| source_url | From news item URL |
| matched_rule_ids | All rules that matched |
| severity | Highest across matched rules |
| time_horizon | From highest-severity rule |
| confidence | Average across matched rules (0.3–0.95) |
| summary_fa | LLM output or truncated content (200 chars) |
| why_important_fa | LLM output or first rule's `why_important` |
| expected_impact | Aggregated from all rules' `impact_hypothesis` |
| follow_up_questions | LLM output or empty |
| dedupe_key | SHA-256 hash |

### Expected Impact Aggregation

Each matched rule has `impact_hypothesis.typical_effect`:
```yaml
typical_effect:
  - asset: "global_gold"
    effect: "rate_up => bearish, rate_down => bullish"
```

The system collects all effects, deduplicates by (asset, direction, mechanism), and produces:
```json
[
  {"asset": "global_gold", "direction": "bullish", "mechanism": "کاهش نرخ بهره..."},
  {"asset": "iran_gold", "direction": "bullish", "mechanism": "تضعیف دلار..."}
]
```

---

## 8. Deduplication

**What it does:** Prevents the same news from creating duplicate alerts.

**File:** `api/worker/dedup.py`

### Two-Level System

**Level 1 — Raw Item Dedup (content hash):**
```
hash = SHA-256(title + "|" + url + "|" + content_text)
```
- Check Redis key `raw_items:hash:<hash>` (TTL: 24 hours)
- Fallback: check PostgreSQL `raw_items.content_hash`
- Same content from same URL = duplicate

**Level 2 — Alert Dedup (semantic):**
```
dedupe_key = SHA-256(sorted_rule_ids + "|" + normalized_title)
```
- Source is **intentionally excluded** — same story from Reuters and Kitco produces same key
- Check Redis key `alert:dedup:<key>` (TTL: configurable)
- Fallback: check PostgreSQL within time window

### Dedupe Window

Default: **6 hours** (configurable in admin settings as `dedupe_window_hours`)

After 6 hours, the same story can create a new alert (useful if the story develops).

---

## 9. Price Data

**What it shows:** Live prices for 4 assets on the dashboard.

**File:** `api/routers/prices.py`

### Sources (Priority Order)

**Primary: BrsAPI**
- URL: `https://brsapi.ir/Api/Market/Gold_Currency.php`
- Auth: API key in query string
- Prices: Already in Toman (no conversion)

**Fallback: TGJU**
- URL: `https://call4.tgju.org/ajax.json`
- Auth: None required
- Prices: In Rial (divided by 10 for Toman display)

### Price Mapping

| Dashboard Card | BrsAPI Symbol | TGJU Indicator |
|---------------|--------------|----------------|
| طلای جهانی | XAUUSD | ons |
| طلای ۱۸ عیار | IR_GOLD_18K | geram18 |
| دلار (تتر) | USDT_IRT | usdt-irr |
| سکه امامی | IR_COIN_EMAMI | sekee |

### Caching

- Redis key: `prices:latest`
- TTL: **60 seconds**
- If Redis has fresh data → return cached
- If expired → fetch from API → cache → return

### Output per Price

```json
{
  "value": 2650.50,
  "formatted": "2,650.50",
  "label": "طلای جهانی",
  "unit": "USD/oz",
  "icon": "🌍",
  "change": "+15.30",
  "change_pct": "+0.58%",
  "direction": "up"
}
```

---

## 10. News Sources & Fetchers

**What it does:** Periodically fetches news from configured sources.

**File:** `api/worker/main.py`, `api/worker/fetchers/`

### Fetch Cycle (every 60 seconds)

```
1. Acquire distributed lock (55s TTL, prevents duplicate workers)
2. Find sources that are due (enabled + past their poll_interval)
3. For each source:
   a. Fetch items (RSS/HTML/JSON fetcher)
   b. Dedup raw items
   c. Store new raw items
   d. Match against rules (min score: 0.18)
   e. Build alerts
   f. Dedup alerts
   g. Optional LLM enrichment
   h. Persist alerts
   i. Update source status
```

### Fetcher Types

| Type | What it does |
|------|-------------|
| RSS | Parses RSS/Atom feeds. Max 30 entries per feed. Strips HTML from content. |
| HTML | Scrapes web pages with CSS selectors. |
| JSON | Parses JSON API responses with field mapping. |

### Safety Limits

| Limit | Value | Purpose |
|-------|-------|---------|
| Max entries per RSS feed | 30 | Prevent flooding from large feeds |
| Max alerts per source per cycle | 10 | Prevent one noisy source from dominating |
| Max article age | 48 hours | Skip old/stale RSS items |
| HTTP timeout | 30 seconds | Don't hang on slow sources |

### Current Sources (from seed data)

| Source | Type | Status | Categories |
|--------|------|--------|-----------|
| Reuters Gold News | RSS | Enabled | global_gold |
| تجارت‌نیوز | HTML | Enabled | iran_gold, coin |
| Kitco Gold News | RSS | Enabled | global_gold |
| TSETMC / کدال | JSON | **Disabled** | gold_funds |
| Google News (Persian) | RSS | Enabled | Mixed |

---

## 11. Key Thresholds & Constants

### Sentiment

| Parameter | Value |
|-----------|-------|
| Score range | 0–100 (50 = neutral) |
| Decay lambda (1h) | 2.0 |
| Decay lambda (4h) | 0.5 |
| Decay lambda (24h) | 0.1 |
| Volume threshold (1h) | 10 alerts |
| Volume threshold (4h) | 20 alerts |
| Volume threshold (24h) | 30 alerts |
| Importance weight (high) | 2.0 |
| Importance weight (medium) | 1.0 |
| Importance weight (low) | 0.5 |

### Rule Matching

| Parameter | Value |
|-----------|-------|
| Keyword weight in score | 60% |
| Signal weight in score | 40% |
| Min match score (worker) | 0.10 |
| High confidence score (skip LLM check) | 0.30 |
| Confidence range | 0.30–0.95 |

### Activity Score

| Parameter | Value |
|-----------|-------|
| Score range | 0–100 |
| Half-life | 4 hours |
| High severity weight | 8.0 |
| Medium severity weight | 2.0 |
| Low severity weight | 0.5 |
| Scale formula | 20 × ln(1 + raw) |

### Dedup & Fetching

| Parameter | Value |
|-----------|-------|
| Raw item dedup TTL | 24 hours |
| Alert dedup window | 6 hours (configurable) |
| Price cache TTL | 60 seconds |
| Worker cycle interval | 60 seconds |
| Lock TTL | 55 seconds |
| HTTP fetch timeout | 30 seconds |
| Max RSS entries | 30 per feed |
| Max alerts per source/cycle | 10 |
| Max article age | 48 hours |

---

## Source Code Reference

| Logic Area | File |
|-----------|------|
| Sentiment calculation | `api/routers/sentiment.py` |
| Activity/Risk score | `api/routers/alerts.py` |
| Rule matching | `api/rule_engine/matcher.py` |
| Severity determination | `api/rule_engine/severity.py` |
| Alert construction | `api/rule_engine/alert_builder.py` |
| Rule loading from YAML | `api/rule_engine/load_rules.py` |
| Deduplication | `api/worker/dedup.py` |
| Worker pipeline | `api/worker/main.py` |
| Price fetching | `api/routers/prices.py` |
| RSS fetcher | `api/worker/fetchers/rss_fetcher.py` |
| HTML fetcher | `api/worker/fetchers/html_fetcher.py` |
| JSON fetcher | `api/worker/fetchers/json_fetcher.py` |
| LLM enrichment | `api/llm/openrouter_client.py` |
| Rules definition | `gold_monitor_rules_fa.yaml` |
