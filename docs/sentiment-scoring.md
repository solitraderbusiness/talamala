# Sentiment Scoring

File: `api/routers/sentiment.py`

## Overview
0-100 gauge of market sentiment direction. 50 = neutral, 0 = extremely bearish, 100 = extremely bullish.
All numeric scoring is **deterministic** — LLM only generates text (summary, key_drivers, outlook).

## 3-Layer Weighted Formula

### Layer 1 — Per-Alert Polarity
```
RSS_i = Polarity × Confidence
```
- Polarity: +1 (bullish), -1 (bearish), 0 (neutral → contributes nothing)
- Confidence: from match score (0.3–0.95)

### Layer 2 — Importance Weighting
```
WS_i = RSS_i × W_imp
```
| Severity | Weight |
|----------|--------|
| critical | 4.0 |
| high | 2.0 |
| medium | 1.0 |
| low | 0.5 |

### Layer 3 — Exponential Time Decay
```
W_time = e^(-λ × hours_ago)
```
| Timeframe | λ | Half-life |
|-----------|---|-----------|
| 1h | 2.0 | ~21 min |
| 4h | 0.5 | ~1.4h |
| 24h | 0.1 | ~7h |

### Aggregation
```
raw = Σ(WS_i × W_time_i) / Σ(|W_imp_i × W_time_i|) × 100    → [-100, +100]
```

### Volume Dampening
```
dampened = raw × min(1.0, n / threshold)
```
| Timeframe | Threshold |
|-----------|-----------|
| 1h | 10 |
| 4h | 20 |
| 24h | 30 |

### Directional Ratio Dampening
If most alerts are neutral (no clear direction), score is pulled toward 50:
```
directional_ratio = directional_alerts / total_alerts
dampened = dampened × directional_ratio
```

### Final Score
```
score = clamp(50 + dampened / 2, 0, 100)
```

## Score → Category Mapping
| Range | Label | Persian |
|-------|-------|---------|
| 80+ | very_bullish | بسیار صعودی |
| 65-79 | bullish | صعودی |
| 55-64 | slightly_bullish | نسبتا صعودی |
| 45-54 | neutral | خنثی |
| 35-44 | slightly_bearish | نسبتا نزولی |
| 20-34 | bearish | نزولی |
| <20 | very_bearish | بسیار نزولی |

## Risk/Activity Score (separate from sentiment)
File: `api/routers/alerts.py`
```
contribution = severity_weight × e^(-0.173 × hours_ago) × confidence
score = clamp(20 × ln(1 + Σcontributions), 0, 100)
```
Severity weights: high=8.0, medium=2.0, low=0.5. Minimum confidence floor: 0.3.

## Per-Alert Score
Stored in `match_evidence.alert_score`:
```
alert_score = 50 + sign × swing × severity_multiplier
sign: +1 (bullish), -1 (bearish), 0 (neutral → always 50)
swing: 15 + (confidence - 0.3) × (30 / 0.7)    → [15, 45]
severity_multiplier: critical=1.0, high=0.8, medium=0.6, low=0.35
```
Clamped to [0, 100]. Bullish critical high-confidence ≈ 95, bearish ≈ 5.

## Persistence
- Scores saved to `sentiment_scores` table on each API call
- `/api/alerts/stats/today` returns latest 4h score as `risk_score`
- History: `/api/sentiment/history?timeframe=4h&hours=48`
