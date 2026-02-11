# Background Jobs & Scheduled Tasks

## Worker Pipeline
- **File:** `api/worker/main.py`
- **Schedule:** Every 60 seconds
- **Lock:** Redis `worker:lock` (55s TTL, prevents duplicate workers)
- **What it does:**
  1. Fetch price snapshot (Redis → BrsAPI → TGJU)
  2. Query enabled sources past their poll interval
  3. For each source: fetch → dedup raw items → match rules → build alerts → dedup alerts → LLM enrich → persist
  4. Update source status (last_fetched_at, last_success_at, last_error)
- **Limits:** Max 30 RSS entries/feed, max 10 alerts/source/cycle, max 48h article age, 30s HTTP timeout

## Calendar Sync
- **File:** `api/worker/calendar_sync.py`
- **Schedule:** Every 6 hours (runs in API process)
- **Sources:** JBlanked (primary) + Finnhub (fallback)
- **What it does:** Fetches economic events, applies ~120 Persian translations, maps assets, adds gold impact notes, upserts into `economic_events` table

## Price Outcome Tracker
- **File:** `api/worker/price_tracker.py`
- **Schedule:** Every 15 minutes (runs in API process)
- **What it does:** For alerts with price stamps (45min to 48h old), checks current prices at 1h/4h/24h intervals, calculates % change, verifies directional accuracy
- **Limits:** Max 50 alerts per run
- **Check windows:** 1h (45min–1h15min), 4h (3h30min–4h30min), 24h (23h–25h)

## Startup Tasks (API process, runs once)
- **File:** `api/main.py`
- Alembic migrations (`upgrade head`)
- Seed default admin user
- Create `sentiment_scores` table (checkfirst=True)
- Snapshot YAML rules file
- One-time Redis dedup flush (versioned marker)
