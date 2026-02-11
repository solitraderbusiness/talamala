# Progress Tracker

> Safe checkpoint: `safe-checkpoint-2026-02-09`

## Completed Features

| Date | Feature |
|------|---------|
| 2026-02-11 | Price tracking at alert time (4 prices stamped), alert classification (news_type + event_category), price outcome tracking (1h/4h/24h), migration 003 |
| 2026-02-10 | Economic event calendar (JBlanked + Finnhub APIs, 6h sync, ~120 Persian translations, list/week views, dashboard widget) |
| 2026-02-09 | Full Docker Compose orchestration, API endpoints, worker pipeline, rule engine (32+ rules), 3-stage direction detection, JWT auth, RTL dashboard, sentiment scoring, deduplication, admin panel |

## Working Features
- 5-service Docker Compose with health checks
- Worker: fetch → dedup → match → classify → stamp prices → alert (60s cycle)
- 3 fetcher types (RSS, HTML, JSON), 10 enabled sources (9 international, 1 Persian)
- Deterministic rule engine: compound keywords, severity classification, direction detection
- Sentiment scoring (0-100, 3-layer weighted, persisted to DB)
- Economic calendar with Persian translations and gold impact notes
- Price outcome tracking (background job, 15min interval)
- Alert classification (news_type + event_category from rule IDs)
- 136 tests passing (matcher, severity, alert_builder, direction)

## In Progress
- **News source reliability**: Lowered MIN_MATCH_SCORE, added negative keywords, LLM relevance filter for borderline matches

## Not Started (Priority Order)
1. Impact matrix per alert (data in YAML, not displayed — was in prototype)
2. Glossary tooltips (18 terms — was in prototype)
3. Cause-effect maps (Driver→Mechanism→Effect — was in prototype)
4. Mode switch (beginner/professional — was in prototype)
5. Per-market pages (`/market/[marketId]` — was in prototype)
6. Coin bubble calculation (حباب)
7. Watchlist / saved filters
8. Gold funds data pipeline (TSETMC/Codal)
9. Technical analysis
10. Push/Telegram notifications

## Known Bugs
- `fetchSourceNow` calls wrong endpoint (`/fetch` vs `/fetch-now`)
- CORS fully permissive (`allow_origins=["*"]`)
- Older alerts lack direction/alert_score/price stamps/classification fields

## Key Decisions
1. LLM never classifies — all scoring/severity is deterministic from YAML rules
2. Compound keywords prevent false positives (multi-word instead of bare "gold")
3. Cross-source dedup excludes source from hash (same story, one alert)
4. Persian Google News feeds disabled (return zero items from outside Iran)
5. BrsAPI primary price source, TGJU fallback (no API key needed)
