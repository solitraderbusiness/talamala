# System Logic — Rule Matching, Severity, Dedup, Prices

## Rule Matching
File: `api/rule_engine/matcher.py`

### Text Normalization (6 steps)
1. Unicode NFC normalization
2. Strip diacritics (Arabic tashkeel)
3. Arabic→Persian chars: `ي→ی`, `ك→ک`
4. Remove invisible chars (ZWJ, LRM, RLM, BOM)
5. Collapse whitespace (ZWNJ→space), strip
6. Lowercase

### Matching Algorithm
1. Check **negative keywords** — if any match, skip rule entirely
2. Substring match keywords and signals against normalized title+content
3. A rule matches if ≥1 keyword OR signal matches

### Match Score
```
score = 0.6 × (matched_kw / total_kw) + 0.4 × (matched_sig / total_sig)
```
If only one type present, pure ratio. MIN_MATCH_SCORE = 0.15 (worker threshold).

### LLM Relevance Filter
For borderline scores (0.10–0.30), LLM checks relevance if enabled. Score ≥ 0.30 skips check.

### Confidence
```
confidence = 0.3 + match_score × 0.65    → [0.30, 0.95]
```

## Severity Assignment
File: `api/rule_engine/severity.py`

4 levels: critical, high, medium, low.

1. **Critical**: Regex patterns for war/conflict, Fed rate decisions, sanctions, currency crises
2. **High/Medium/Low**: Check rule's `importance_criteria` (high_if → medium_if → low_if), first match wins
3. **Fallback**: Score-based (high ≥ 0.35 or ≥ 0.25 for immediate; low < 0.15; else medium)

Multiple rules → highest severity wins.

## Direction Detection (3-stage)
File: `api/rule_engine/direction.py`

1. **Regex patterns** (~60%): Flexible word-order patterns for explicit directional phrases. Confidence 0.7-0.9.
2. **Lexicon scoring** (~20%): Gold-domain word weights summed. Medium confidence 0.5-0.6.
3. **LLM fallback** (last resort): OpenRouter batch direction detection.

Output: direction (bullish/bearish/neutral), confidence (0-1), method (regex/lexicon/llm).

## Deduplication
File: `api/worker/dedup.py`

### Raw Items
```
hash = SHA-256(title | url | content_text)
```
Redis key `raw_items:hash:<hash>` (24h TTL) → DB fallback.

### Alerts
```
dedupe_key = SHA-256(sorted_rule_ids | normalized_title)
```
Source excluded intentionally (cross-source dedup). Redis key `alert:dedup:<key>` (default 6h window, configurable).

### Semantic Event Fingerprinting
Extracts entities (instruments, orgs, events, numbers) to build fingerprint. Same event with different headlines → same fingerprint. Redis key `event:fp:<fingerprint>` (4h TTL).

## Price Data
File: `api/routers/prices.py`, `api/price_snapshot.py`

### Sources (priority order)
1. **Redis cache** (`prices:latest`, 60s TTL)
2. **BrsAPI** (`brsapi.ir`) — requires `BRSAPI_KEY`, prices in Toman
3. **TGJU** (`call4.tgju.org`) — free fallback, prices in Rial (÷10)

### Price Mapping
| Asset | BrsAPI | TGJU |
|-------|--------|------|
| Gold global | XAUUSD | ons |
| 18K gold | IR_GOLD_18K | geram18 |
| USD (Tether) | USDT_IRT | usdt-irr |
| Emami coin | IR_COIN_EMAMI | sekee |

## Price Outcome Tracking
File: `api/worker/price_tracker.py`

Every 15min, checks prices 1h/4h/24h after each alert:
- 1h: eligible 45min–1h15min after alert
- 4h: eligible 3h30min–4h30min
- 24h: eligible 23h–25h
- Max 50 alerts per run, ignores alerts > 48h old
- Stores change_pct and direction_correct in `alert_price_outcomes`

## Alert Classification
File: `api/alert_classify.py`

- **news_type**: price_report / causal_event / mixed / commentary (from rule ID categories)
- **event_category**: fed_policy / geopolitics / usd_dxy / inflation / etf_flows / mining_supply / equity_risk / gold_price / iran_forex / iran_policy / iran_demand / coin / other (first matched category wins)

## News Categorization (Dashboard Sections)
Rule prefix mapping: GLOB_* → global_gold, IR_* → iran_gold, COIN_* → coin, FUNDS_* → gold_funds.
Geopolitics override rules get their own section regardless of prefix.

## Key Thresholds
| Parameter | Value |
|-----------|-------|
| Worker cycle | 60s |
| Lock TTL | 55s |
| Min match score | 0.15 |
| High confidence (skip LLM) | 0.30 |
| Raw item dedup TTL | 24h |
| Alert dedup window | 6h (configurable) |
| Event fingerprint TTL | 4h |
| Price cache TTL | 60s |
| HTTP timeout | 30s |
| Max RSS entries | 30/feed |
| Max alerts/source/cycle | 10 |
| Max article age | 48h |
| Price tracker interval | 15min |
| Calendar sync interval | 6h |
