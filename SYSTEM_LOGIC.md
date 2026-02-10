# Talamala — System Logic & Formulas (منطق سیستم)

> This document explains how every calculation, score, and decision in the system works.
> Intended for: admin panel "How It Works" page + developer reference.

---

## Table of Contents

1. [Sentiment Score (شاخص احساسات بازار)](#1-sentiment-score)
2. [Risk / Activity Score (شاخص فعالیت بازار)](#2-risk--activity-score)
3. [Rule Matching (تطبیق قوانین)](#3-rule-matching)
4. [Severity Assignment (تعیین شدت هشدار)](#4-severity-assignment)
5. [Direction Detection (تشخیص جهت بازار)](#5-direction-detection)
6. [Per-Alert Score (امتیاز هر هشدار)](#6-per-alert-score)
7. [News Type Classification (طبقه‌بندی نوع خبر)](#7-news-type-classification)
8. [Time Horizon (افق زمانی)](#8-time-horizon)
9. [News Categorization (دسته‌بندی اخبار)](#9-news-categorization)
10. [Alert Building (ساخت هشدار)](#10-alert-building)
11. [Deduplication (حذف تکراری‌ها)](#11-deduplication)
12. [Price Data (داده‌های قیمت)](#12-price-data)
13. [News Sources & Fetchers (منابع خبری)](#13-news-sources--fetchers)
14. [Key Thresholds & Constants (مقادیر ثابت)](#14-key-thresholds--constants)

---

## 1. Sentiment Score

**What it shows:** A 0-100 gauge of market sentiment direction.
- 50 = neutral (no signal)
- 0 = extremely bearish
- 100 = extremely bullish

**File:** `api/routers/sentiment.py`

### Pre-filtering
Before computing sentiment, these alerts are **excluded**:
- `news_type == "price_report"` — just reports prices, no causal information
- `news_type == "background_context"` — existing conditions already priced in

Only `causal_event` and `mixed` alerts contribute to the gauge.

### Formula (3-Layer Weighted System)

**Layer 1 — Per-Alert Polarity:**
Each alert gets a polarity from its server-computed `direction` field (set by `direction.py`):
```
Polarity = +1.0 if bullish
           -1.0 if bearish
            0.0 if neutral  ← contributes NOTHING to directional signal
```
Neutral polarity = 0 means alerts without detected direction are excluded from the directional calculation entirely.

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
| critical | 4.0 |
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

**Directional Ratio Dampening:**
If most alerts are neutral (no clear direction), the score is pulled toward 50:
```
directional_ratio = directional_alerts / total_alerts
dampened = dampened × directional_ratio
```
With mostly neutral alerts, the score stays near 50 regardless of the few directional ones.

**Final Score:**
```
score = clamp(50 + dampened / 2, 0, 100)
```

### Score → Label Mapping

| Score Range | Label | Persian | Color |
|-------------|-------|---------|-------|
| 0–19 | very_bearish | بسیار نزولی | Red |
| 20–34 | bearish | نزولی | Red |
| 35–44 | slightly_bearish | نسبتا نزولی | Amber |
| 45–54 | neutral | خنثی | Amber |
| 55–64 | slightly_bullish | نسبتا صعودی | Green |
| 65–79 | bullish | صعودی | Green |
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
MIN_MATCH_SCORE = 0.15
```
- 1 keyword out of 10 = 0.06 → **filtered out**
- 1 keyword out of 5 = 0.12 → **filtered out**
- 2 keywords out of 6 = 0.20 → **passes**
- 1 keyword + 2 signals (5 kw + 10 sig) = 0.20 → **passes**

### LLM Relevance Filter (Optional)

For borderline matches (score between 0.10 and 0.30), if LLM is enabled, the system asks the LLM: "Is this article relevant to gold/financial markets?" Articles that score >= 0.30 skip this check (high confidence). This prevents false positives like sports or IT articles that happen to contain a financial keyword.

```
HIGH_CONFIDENCE_SCORE = 0.30  # above this, no LLM check needed
```

### Confidence (derived from match score)

**Match confidence** (from `severity.py:calculate_confidence`):
```
match_confidence = 0.3 + match_score × 0.65
```
- Score 0.0 → confidence 0.30 (30%)
- Score 1.0 → confidence 0.95 (95%)
- Never reaches 100% — system never claims certainty

**Final confidence** (from `alert_builder.py`):
For directional (bullish/bearish) alerts, the final confidence blends match and direction:
```
final_confidence = 0.5 × match_confidence + 0.5 × direction_confidence
```
For neutral alerts, only match confidence is used.

---

## 4. Severity Assignment

**What it decides:** Whether an alert is critical (بحرانی), high (بالا), medium (متوسط), or low (پایین).

**File:** `api/rule_engine/severity.py`

### Algorithm (3-Stage Cascade)

For each matched rule, severity is determined by a 3-stage cascade:

**Stage 1 — Event-Type Regex Classification (catches critical events):**
```
Check title + content against critical-event regex patterns:
- War/conflict:    جنگ, حمله نظامی, war, attack, invasion, escalat...
- Fed rate:        نرخ بهره فدرال, fed.*rate, rate.*decision...
- Sanctions:       تحریم.*جدید, new.*sanction, embargo...
- Currency crisis: سقوط.*ارز, currency.*crash/crisis...
- Nuclear:         مذاکرات هسته‌ای, nuclear.*negotiat/talks...
- ATH/crash:       رکورد.*تاریخی, all.time.high, crash, سقوط...
```
If any pattern matches → severity = "critical"

**Stage 2 — YAML `importance_criteria` Conditions:**
```
1. Normalize the alert content
2. Check high_if conditions → if any substring matches → "high"
3. Check medium_if conditions → if any substring matches → "medium"
4. Check low_if conditions → if any substring matches → "low"
```

**Stage 3 — Score-Based Fallback:**
```
If no YAML condition matched:
- score >= 0.35 → "high"
- score >= 0.25 AND horizon == "immediate" → "high"
- score < 0.15 → "low"
- otherwise → "medium"
```

### When Multiple Rules Match

Each rule gets its own severity. The **highest** severity across all matched rules is used for the alert.

### Non-Causal Override
After severity is determined, if `news_type` is `price_report` or `background_context`, severity is forced to `"low"` regardless of what the cascade determined.

---

## 5. Direction Detection

**What it decides:** Whether an alert is bullish (صعودی), bearish (نزولی), or neutral (خنثی) for gold.

**File:** `api/rule_engine/direction.py`

### 3-Stage Pipeline

**Stage 1 — Regex Patterns (catches ~60%):**
Flexible word-order patterns with `.{0,N}` gaps match explicit directional phrases in title + content:
```
Bullish examples:
- "gold" + gap + "rises/surges/climbs"
- "rate" + gap + "cut/reduce/lower"
- "قیمت طلا" + gap + "افزایش/رشد/صعود"
- "demand" + gap + "rises/increases"

Bearish examples:
- "gold" + gap + "falls/drops/declines"
- "rate" + gap + "hike/raise/increase"
- "قیمت طلا" + gap + "کاهش/افت/سقوط"
- "dollar" + gap + "strengthens/rises"
```
Confidence: 0.7–0.9 (high — explicit language)

**Stage 2 — Lexicon Scoring (catches ~20% more):**
Gold-domain word weights are summed across title + content:
```
Bullish terms: safe haven (+2), rate cut (+2), inflation fears (+1.5), demand (+1)...
Bearish terms: rate hike (-2), dollar strength (-1.5), profit taking (-1)...
```
Net score above threshold → direction. Confidence: 0.5–0.6.

**Stage 3 — LLM Fallback (last resort):**
If Stages 1-2 return neutral/low-confidence, queued for LLM batch detection. Returns direction with LLM-reported confidence.

### Output Per Alert
```json
{
  "direction": "bullish",           // bullish | bearish | neutral
  "direction_confidence": 0.8,      // 0.0 – 1.0
  "direction_method": "regex"        // regex | lexicon | llm
}
```

### Persian Word Boundary Gotcha
`\b` word boundaries don't work for Persian characters. Use `(?<=\s)` and `(?=\s|$)` instead.
Example: "افت" (decline) matches inside "یافت" (happened) → need `(?<=\s)افت(?=\s|$)`.

---

## 6. Per-Alert Score

**What it shows:** A 0-100 score per alert indicating market direction and confidence.
- 50 = neutral (no directional signal)
- 95 = very bullish (high confidence, high severity)
- 5 = very bearish (high confidence, high severity)

**File:** `api/rule_engine/direction.py` (`calculate_alert_score`)

### Formula

```
alert_score = 50 + sign × swing × severity_multiplier
```

Components:
- `sign`: +1 (bullish), -1 (bearish), 0 (neutral → score always 50)
- `swing`: `15 + (confidence - 0.3) × (30 / 0.7)` — maps confidence [0.3, 1.0] to swing [15, 45]
- `severity_multiplier`:
  | Severity | Multiplier |
  |----------|-----------|
  | critical | 1.0 |
  | high | 0.8 |
  | medium | 0.6 |
  | low | 0.35 |

Result clamped to [0, 100].

### Examples
- Bullish + critical + confidence 0.9 → score ≈ 87
- Bearish + high + confidence 0.7 → score ≈ 26
- Neutral (any severity) → score = 50 always

### Confidence Blending
Final alert confidence = 50% match confidence + 50% direction confidence (for directional alerts). Neutral alerts use match confidence only.

---

## 7. News Type Classification

**What it decides:** Whether a news item is a price report, background context, causal event, or mixed.

**File:** `api/rule_engine/news_type.py`

### Key Principle
**Only NEW information moves markets.** Existing conditions (ongoing sanctions, persistent tensions, historical anniversaries) are already priced in and should not affect the sentiment gauge or trigger high severity.

### 4 Types

| Type | Examples | Score | Severity | Direction | In Gauge? |
|------|----------|-------|----------|-----------|-----------|
| `price_report` | "Gold reaches $5000", "قیمت طلا ۳ میلیون تومان" | 50 | low | neutral | No |
| `background_context` | "47th anniversary of Revolution", "sanctions continue", editorials | 50 | low | neutral | No |
| `causal_event` | "Fed cuts rate", "New sanctions imposed", "War breaks out" | Computed | Computed | Computed | Yes |
| `mixed` | "Gold rises due to Fed rate cut" (price + cause) | Computed | Computed | Computed | Yes |

### Classification Order (first match wins)

1. **Background check:** Title/content matches background patterns?
   - Title patterns: سالگرد, سالروز, anniversary, یادبود, مراسم, تاریخچه, مروری بر, نگاهی به, editorial, سرمقاله, opinion, تحلیل, بررسی...
   - Content patterns: status-quo phrases, commemorative language, historical recap
   - **Override:** If new-event indicators present (جدید, اعلام شد, تصویب شد, imposed, launched, escalat, broke out...) → NOT background
   - If background AND no override → `background_context`

2. **Price check:** Title/content matches price patterns?
   - Title: "قیمت طلا", "gold price", "gold at $X"
   - Content: price tables, تومان/ریال amounts, price-reporting verbs
   - If price + causal indicators → `mixed`
   - If pure price → `price_report`

3. **Default:** → `causal_event`

---

## 8. Time Horizon

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

## 9. News Categorization

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

## 10. Alert Building

**What it does:** Converts a raw news item + matched rules into a structured alert.

**File:** `api/rule_engine/alert_builder.py`

### Pipeline

```
Raw News Item
    ↓
Match against 32 rules (see §3)
    ↓
Classify news type: price_report / background_context / causal_event / mixed (see §7)
    ↓
For each matched rule:
  - Determine severity (see §4)
  - Calculate confidence (see §3)
    ↓
Pick highest severity across all rules
Pick time horizon from highest-severity rule
Average confidence across all rules
    ↓
Detect direction: regex → lexicon → LLM fallback (see §5)
    ↓
Compute per-alert score (see §6)
    ↓
Build expected_impact from all rules' impact_hypothesis
    ↓
NON-CAUSAL OVERRIDE: If price_report or background_context:
  → direction=neutral, severity=low, score=50, custom why_important_fa
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
| title | LLM title_fa (if enabled) or original title |
| timestamp_utc | From news item |
| source_name | From source config |
| source_url | From news item URL |
| matched_rule_ids | All rules that matched |
| severity | Highest across matched rules (overridden to "low" for non-causal) |
| time_horizon | From highest-severity rule |
| confidence | Blended: 50% match + 50% direction confidence |
| direction | From direction.py pipeline (overridden to "neutral" for non-causal) |
| direction_confidence | 0.0–1.0 |
| direction_method | regex / lexicon / llm / price_report / background_context |
| alert_score | 0–100 (overridden to 50 for non-causal) |
| news_type | price_report / background_context / causal_event / mixed |
| summary_fa | LLM output or truncated content (200 chars) |
| why_important_fa | LLM output or first rule's `why_important` (overridden for non-causal) |
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

## 11. Deduplication

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

**Level 3 — Event Fingerprint Dedup (semantic):**
```
entities = extract from title + content using regex patterns:
  - Price levels: numbers + currency words (دلار, تومان, ریال)
  - Instruments: طلا, gold, سکه, coin, دلار, bitcoin...
  - Organizations: فدرال رزرو, Fed, بانک مرکزی, ECB, BOJ, CME...
  - Events: جنگ, war, تحریم, sanction, نرخ بهره, interest rate...
  - Direction: رکورد, record, سقوط, crash, صعود, surge...
fingerprint = sorted(entities + significant_numbers) joined by "|"
```
- Check Redis key `event:fp:<fingerprint>` (TTL: 4 hours)
- Same underlying event with different headlines → same fingerprint → deduplicated
- Example: "طلا بالای ۵۰۰۰ دلار" and "قیمت طلا از ۵۰۰۰ دلار عبور کرد" → same fingerprint

### Dedupe Window

Default: **6 hours** (configurable in admin settings as `dedupe_window_hours`)

After 6 hours, the same story can create a new alert (useful if the story develops).

---

## 12. Price Data

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

## 13. News Sources & Fetchers

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
   d. Match against rules (min score: 0.15)
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

## 14. Key Thresholds & Constants

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
| Importance weight (critical) | 4.0 |
| Importance weight (high) | 2.0 |
| Importance weight (medium) | 1.0 |
| Importance weight (low) | 0.5 |
| Non-causal alerts | Excluded (price_report, background_context) |

### Rule Matching

| Parameter | Value |
|-----------|-------|
| Keyword weight in score | 60% |
| Signal weight in score | 40% |
| Min match score (worker) | 0.15 |
| High confidence score (skip LLM check) | 0.30 |
| Confidence range | 0.30–0.95 |

### Direction Detection

| Parameter | Value |
|-----------|-------|
| Stage 1 (regex) confidence | 0.7–0.9 |
| Stage 2 (lexicon) confidence | 0.5–0.6 |
| Stage 3 (LLM) confidence | LLM-reported |
| Neutral score | Always 50 |

### Per-Alert Score

| Parameter | Value |
|-----------|-------|
| Score range | 0–100 (50 = neutral) |
| Severity multiplier (critical) | 1.0 |
| Severity multiplier (high) | 0.8 |
| Severity multiplier (medium) | 0.6 |
| Severity multiplier (low) | 0.35 |
| Swing range | 15–45 (mapped from confidence 0.3–1.0) |

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
| Event fingerprint TTL | 4 hours |
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
| Direction detection | `api/rule_engine/direction.py` |
| News type classification | `api/rule_engine/news_type.py` |
| Alert construction | `api/rule_engine/alert_builder.py` |
| Rule loading from YAML | `api/rule_engine/load_rules.py` |
| Deduplication + fingerprinting | `api/worker/dedup.py` |
| Worker pipeline | `api/worker/main.py` |
| Price fetching | `api/routers/prices.py` |
| RSS fetcher | `api/worker/fetchers/rss_fetcher.py` |
| HTML fetcher | `api/worker/fetchers/html_fetcher.py` |
| JSON fetcher | `api/worker/fetchers/json_fetcher.py` |
| LLM enrichment | `api/llm/openrouter_client.py` |
| Rules definition | `gold_monitor_rules_fa.yaml` |
