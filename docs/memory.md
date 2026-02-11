# Memory — Key Context for Future Sessions

## Project Identity
- **Talamala** (طلاملا) = Gold Market Monitor for Persian users
- Production system: `gold-monitor-system/` — full-stack with Docker
- Legacy prototype: `gold-monitor/` — Next.js with mock data, useful as UI reference

## Critical Architecture Decisions
- **Deterministic classification**: LLM generates Persian text only. Severity, confidence, time_horizon, direction all come from YAML rules + regex/lexicon pipeline
- **Dedup excludes source**: Same story from Reuters and Kitco produces one alert (cross-source dedup by rule_ids + normalized title)
- **Compound keywords**: Rules use multi-word keywords ("gold price", "قیمت طلا") not bare words, to prevent false positives from sports/unrelated articles
- **Persian Google News disabled**: Returns zero items from outside Iran. All Persian news via international sources + khabarfarsi.com
- **Price data**: BrsAPI (requires key, prices in Toman) → TGJU fallback (free, prices in Rial ÷10)

## Tuning Parameters (Don't Change Without Understanding)
- `MIN_MATCH_SCORE = 0.15` in `worker/main.py` — lower = spam, higher = missed alerts
- Match score = 60% keyword ratio + 40% signal ratio
- Dedup window default: 6 hours (configurable in admin settings)
- Worker cycle: 60s, lock TTL: 55s

## What Prototype Has That Production Doesn't
These features exist in `gold-monitor/src/` and could be ported:
- `ImpactMatrix.tsx` — visual impact per asset
- `Tooltip.tsx` + `GlossaryText` — 18 financial term tooltips
- `CauseEffect.tsx` — Driver→Mechanism→Effect diagrams
- `ModeSwitch.tsx` — beginner/professional toggle
- `/market/[marketId]` — per-asset detail pages
- 17 UI components total vs ~5 in production

## Server Deployment
```bash
cd ~/projects/talamala && git pull origin <branch> && cd gold-monitor-system && docker compose up -d --build
```
API auto-runs migrations and seeds on startup. Redis FLUSHDB is safe (only dedup cache).
