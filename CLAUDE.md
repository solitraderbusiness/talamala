# Talamala - Gold Market Monitor (سامانه رصد طلا)

## What This Is
Real-time gold market intelligence system for Persian (Farsi) users. Monitors news sources (RSS, HTML, JSON APIs), matches against YAML-based rules, generates severity-rated alerts with optional Persian LLM summaries. Two sub-projects: `gold-monitor-system/` (production) and `gold-monitor/` (legacy prototype with mock data).

## Tech Stack
- **Frontend:** Next.js 14, React 18, TypeScript 5, Tailwind CSS 3, Vazirmatn font (Persian RTL)
- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2.0 (asyncpg), Pydantic v2
- **Database:** PostgreSQL 16, Redis 7 (cache + dedup + worker lock)
- **Deployment:** Docker Compose (7 services: db, redis, api, worker, signal-worker, analysis-worker, web)
- **AI/LLM:** OpenRouter API (Claude Sonnet 4) — alert text generation + AI chat assistant
- **Signal Aggregator:** Telethon (Telegram), Anthropic Claude API (signal parsing), Recharts (charts)
- **Fundamental Analysis:** yfinance, pandas, FRED API, CFTC COT parser

## Key Commands
```bash
# Start everything
cd gold-monitor-system && docker compose up -d

# Rebuild and restart
docker compose up -d --build

# View logs
docker compose logs -f worker    # Worker fetch cycles
docker compose logs -f api       # API logs
docker compose logs -f web       # Next.js

# Restart specific service
docker compose restart worker

# Run tests
cd gold-monitor-system && pip install -r api/requirements.txt && python -m pytest api/tests/ -v

# Database access
docker compose exec db psql -U goldmon -d goldmonitor

# Health check
curl http://localhost:8000/api/health
```

## Services & Architecture
Seven Docker services: **PostgreSQL** (port 5432, 27 tables), **Redis** (6379, dedup cache + worker lock + chat rate limiting), **FastAPI API** (8000, REST endpoints + auto-migrations on startup), **Worker** (same image as API, 60s fetch-match-alert pipeline), **Signal Worker** (same image, runs signal aggregator: Telegram listener, TradingView scraper, signal parser, price checker, consensus builder, performance tracker), **Analysis Worker** (same image, runs fundamental analysis: Yahoo Finance prices, FRED indicators, ETF holdings, COT reports, correlation calc, event generator), **Next.js Web** (3000, RTL Persian dashboard + AI chat widget + fundamental analysis page, proxies `/api/*` to API). Worker acquires Redis distributed lock (55s TTL), fetches enabled sources, deduplicates via SHA-256 content hash, matches against YAML rules, determines severity deterministically, optionally enriches with LLM Persian text, persists alerts. Background jobs: calendar sync (6h), price outcome tracker (15min). AI chat widget provides conversational access to alerts, calendar, and prices via SSE streaming with tool-use pattern.

## Code Conventions
- **Async-first**: all DB ops use `AsyncSession` via asyncpg; worker uses aiohttp for HTTP
- **Python**: snake_case files/functions/vars, PascalCase classes; routers in `api/routers/`, fetchers in `api/worker/fetchers/`, chat services in `api/services/chat/`, signal aggregator in `api/signal_aggregator/`, analysis module in `api/analysis/`
- **TypeScript**: camelCase functions/vars, PascalCase components; pages in `src/app/`, components in `src/components/`
- **API routes**: `/api/{resource}` with kebab-case multi-word paths
- **Rule IDs**: `SECTION_DESCRIPTIVE_NAME` (e.g., `GLOB_RATE_DECISION`, `IR_FX_USD`)
- **Pydantic v2**: `ConfigDict(from_attributes=True, populate_by_name=True)`, Persian field aliases
- **UUID PKs** and **UTC timestamps** everywhere
- **LLM never classifies** — severity/confidence/time_horizon are always deterministic from rules
- **Compound keywords** in rules (multi-word like "gold price") to prevent false positives
- **RTL layout**: `<html lang="fa" dir="rtl">`, Vazirmatn font, gold color palette

## Active Work (update each session)
- [x] AI chat widget (SSE streaming, tool-use, analytics dashboard, admin settings)
- [x] Signal Aggregator + AI Analysis page (Telegram listener, TradingView scraper, Claude API parser, consensus algorithm, performance tracking, AI Analysis page with 5 sections)
- [x] Fundamental Analysis revamp — AI Analysis page replaced with macro dashboard (ETF flows, COT, real rates, correlations, sentiment gauge, market events)
- [x] Data Collection & Outcome Tracking — market snapshots at alert time, 6-window outcome tracking, sentiment timeline (5min), price history (5min candles + daily sync), admin data health dashboard
- [ ] Fix news source reliability (English feeds, negative keywords, LLM relevance filter)
- [ ] Impact matrix per alert (data exists in YAML, not displayed)
- [ ] Per-market pages (`/market/[marketId]`)

## Known Issues
- CORS fully permissive (`allow_origins=["*"]`) — restrict for production
- `fetchSourceNow` calls `/api/sources/{id}/fetch` but API route is `/fetch-now`
- Older alerts lack `direction`/`alert_score` in `match_evidence` (default to neutral)
- Older alerts lack price stamps (only after migration 003)
- `news_type`/`event_category` only populated after migration 003
- Gold fund rules exist in YAML but no data sources feed them (TSETMC disabled)
- Passwords truncated to 72 bytes for bcrypt (`auth.py:_truncate_for_bcrypt`)
- Chat session data stored as plaintext in DB (no encryption at rest)
- Chat system prompt template (`chat-system.txt`) uses Python `str.format()` — JSON curly braces must be doubled (`{{`/`}}`)
- CFTC COT CSV URL returns 404 — `cot_parser.py` may need updated URL for weekly reports
- FRED data requires `FRED_API_KEY` — without it, real rates section stays empty

## Environment Variables
Key vars in `gold-monitor-system/.env` (see `.env.example`):
- `DATABASE_URL` / `DATABASE_URL_SYNC` — PostgreSQL connection strings
- `REDIS_URL` — Redis connection
- `OPENROUTER_API_KEY` — LLM text generation + chat (required for chat)
- `BRSAPI_KEY` — BrsAPI market data (optional, TGJU fallback)
- `SECRET_KEY` — JWT signing secret
- `ADMIN_EMAIL` / `ADMIN_PASSWORD` — Default: `admin@goldmonitor.ir` / `admin123`
- `INTERNAL_API_URL` — API URL for Next.js proxy (default: `http://api:8000`)
- `CHAT_ENABLED` — Enable/disable AI chat widget (default: `true`)
- `CHAT_MODEL` — Chat LLM model (default: `anthropic/claude-sonnet-4`)
- `CHAT_RATE_LIMIT_IP` — Chat messages per hour per IP (default: `30`)
- `CHAT_RATE_LIMIT_GLOBAL` — Chat messages per hour total (default: `1000`)
- `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` / `TELEGRAM_PHONE` — Telegram user session for signal listening
- `ANTHROPIC_API_KEY` — Claude API for signal parsing
- `TRADINGVIEW_COOKIE` — Browser cookie for TradingView scraping (optional)
- `SIGNAL_PARSE_MODEL` — Claude model for parsing (default: `claude-sonnet-4-20250514`)
- `FRED_API_KEY` — FRED API for macro indicators (optional, free at fred.stlouisfed.org)

## Access Points
| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| Admin | http://localhost:3000/admin/login |
| Swagger | http://localhost:8000/docs |
| Health | http://localhost:8000/api/health |
| Fundamental Analysis | http://localhost:3000/ai-analysis |
| Analysis API | http://localhost:8000/api/analysis/macro-overview |
| AI Analysis API | http://localhost:8000/api/ai-analysis/consensus/latest |

## Reference Docs
When you need detailed information, read these files:
- `docs/architecture.md` — Full system architecture, folder structure, service details
- `docs/progress.md` — What's done, what's in progress, roadmap
- `docs/api-reference.md` — All API endpoints with parameters
- `docs/schema.md` — Database tables, columns, relationships
- `docs/sentiment-scoring.md` — Sentiment formula, scoring logic, all thresholds
- `docs/system-logic.md` — Rule matching, severity, dedup, price tracking formulas
- `api/prompts/chat-system.txt` — AI chat system prompt template

Only read these when the current task specifically requires that info. Do NOT read all of them at session start.

## Rules
- **ALWAYS rebuild Docker after any code change**: run `cd gold-monitor-system && docker compose up -d --build` after modifying backend or frontend files — changes are NOT visible until containers are rebuilt
- Always read only the docs/ files relevant to the current task
- Run `python -m pytest api/tests/ -v` before committing backend changes
- Never add `DELETE FROM alerts` or `DELETE FROM raw_items` to migrations (runs on every startup)
- Never use LLM for classification — severity/confidence/horizon must be deterministic
- Use compound keywords in rules to prevent false positives
- Redis FLUSHDB is safe (only clears dedup cache, no data loss)
- New columns should use `checkfirst=True` pattern
- `MIN_MATCH_SCORE = 0.15` in `worker/main.py` — don't change without understanding implications
- Safe checkpoint tag: `safe-checkpoint-2026-02-09`

## Signal Aggregator Module
Crowd-sourced analyst consensus system for XAUUSD. Collects trading signals from Telegram channels and TradingView, parses with Claude API, builds weighted consensus from multiple analysts, tracks outcomes, serves results via the AI Analysis page.

### Module Structure
```
api/signal_aggregator/
├── config.py           -- env vars, constants, timeframe mappings
├── models.py           -- 7 new tables (signal_sources, raw_posts, parsed_signals, consensus_snapshots, signal_price_ticks, signal_daily_performance, signal_monthly_performance)
├── workers/
│   ├── main.py             -- unified worker entry point
│   ├── telegram_listener.py -- Telethon channel listener
│   ├── tradingview_scraper.py -- TradingView ideas scraper
│   ├── signal_parser.py    -- Claude API parsing pipeline
│   ├── price_checker.py    -- outcome tracking + source weight updates
│   ├── consensus_builder.py -- weighted consensus algorithm (4 views)
│   ├── performance_tracker.py -- daily/monthly aggregation
│   └── journal_generator.py -- template-based daily summaries
├── api/
│   └── routes.py       -- /api/ai-analysis/* endpoints
├── utils/
│   ├── weight_calculator.py -- source confidence scoring
│   └── deduplication.py -- duplicate post detection
└── scripts/
    └── setup_sources.py -- seed initial Telegram channels + TradingView
```

### API Endpoints
- `GET /api/ai-analysis/consensus/latest` — latest consensus for all 4 timeframes
- `GET /api/ai-analysis/signals/recent` — recent parsed signals with filters
- `GET /api/ai-analysis/performance/summary` — key metrics
- `GET /api/ai-analysis/performance/daily` — daily performance for date range
- `GET /api/ai-analysis/performance/monthly` — monthly performance
- `GET /api/ai-analysis/sources/leaderboard` — ranked sources
- `GET /api/ai-analysis/price/current` — current XAUUSD price
- `GET /api/ai-analysis/journal/recent` — daily journal entries

### Consensus Views
| View | Signal timeframes | Description |
|------|------------------|-------------|
| scalp | 5min, 15min, 30min | Short-term scalping |
| intraday | 15min, 30min, 1h, 4h | Intraday trading |
| swing | 4h, daily | Multi-day swing |
| position | daily, weekly | Long-term position |

### First-time Telegram Setup
Requires manual phone verification: set `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_PHONE` in `.env`, then run `python -m api.signal_aggregator.scripts.setup_sources` to verify and seed channels.

## Fundamental Analysis Module
Macro-economic analysis dashboard for gold. Fetches institutional money flows (ETF holdings, COT reports), real interest rates (FRED API), asset prices (Yahoo Finance), computes correlations and composite sentiment, generates market events automatically.

### Module Structure
```
api/analysis/
├── __init__.py
├── models.py               -- 6 tables (asset_prices_daily, macro_indicators, etf_holdings, cot_data, market_events_analysis, correlation_cache)
└── workers/
    ├── main.py             -- unified worker entry point
    ├── yahoo_fetcher.py    -- Yahoo Finance daily prices (7 symbols, every 6h)
    ├── fred_fetcher.py     -- FRED API macro indicators (5 series, every 6h)
    ├── etf_scraper.py      -- ETF holdings via Yahoo Finance (GLD, IAU, every 6h)
    ├── cot_parser.py       -- CFTC COT report parsing (weekly, Saturdays)
    ├── correlation_calc.py -- 30-day Pearson correlations (every 6h)
    ├── sentiment_scorer.py -- composite sentiment (computed on-the-fly)
    └── event_generator.py  -- auto-generated events from data changes (every 30min)
api/routers/
└── analysis.py             -- /api/analysis/* endpoints (7 routes)
```

### API Endpoints (`/api/analysis/`)
- `GET /macro-overview` — 4 summary cards (money flow, real rates, dollar, risk)
- `GET /money-flow` — ETF holdings + COT positions history
- `GET /real-rates` — FRED indicators with history
- `GET /correlations` — 30-day Pearson correlation pairs
- `GET /sentiment-gauge` — 0-100 composite score from 6 components
- `GET /shanghai-premium` — SGE vs LBMA price spread (pending data source)
- `GET /market-activity` — auto-generated event feed (last 48h)

### Frontend Components (`web/src/components/analysis/`)
| Component | Section |
|-----------|---------|
| `DataPending.tsx` | Reusable "به زودی" placeholder |
| `MacroOverview.tsx` | 4 summary cards |
| `MoneyFlowAnalysis.tsx` | ETF + COT charts |
| `RealRatesSection.tsx` | FRED data with history chart |
| `CorrelationMatrix.tsx` | Asset correlation bars |
| `SentimentGauge.tsx` | 0-100 gauge with components |
| `ShanghaiPremium.tsx` | Chinese physical demand |
| `MarketActivityFeed.tsx` | Chronological event feed |

## Data Collection & Outcome Tracking Module
Captures market context at alert creation time and tracks price outcomes over 6 intervals (30min, 1h, 4h, 24h, 48h, 7d). Records sentiment timeline every 5 minutes and builds price history candles. Provides admin dashboard for data health monitoring.

### Module Structure
```
api/data_collection/
├── __init__.py
├── models.py               -- 4 tables (alert_market_snapshots, alert_outcomes, sentiment_timeline, price_history)
├── indicators.py           -- RSI, SMA, ATR (pure Python, no deps)
├── sentiment_calculator.py -- extracted sentiment gauge logic (6 components)
├── snapshot_builder.py     -- market snapshot capture (hooked after _store_alert)
├── outcome_tracker.py      -- 6-window outcome tracking (5min loop in API)
├── sentiment_recorder.py   -- 5-min sentiment + price recording (analysis-worker)
└── candle_builder.py       -- 5min OHLCV from ticks + daily sync from asset_prices_daily
api/routers/
└── data_health.py          -- /api/admin/data-health/* endpoints (6 routes)
web/src/app/admin/
└── data-health/page.tsx    -- Admin data health dashboard
```

### API Endpoints (`/api/admin/data-health/`, auth required)
- `GET /overview` — snapshot coverage, pipeline counts, freshness
- `GET /snapshot-stats?period=today|week|month` — completeness details
- `GET /outcome-pipeline` — funnel counts, errors
- `GET /sentiment-timeline?hours=168` — sentiment + price time series
- `GET /price-status` — per-symbol freshness and record counts
- `GET /correlation?days=7` — Pearson correlation at multiple lags

### Background Tasks
| Task | Process | Interval |
|------|---------|----------|
| Market snapshot capture | worker (fire-and-forget) | On alert creation |
| Outcome tracker loop | API | Every 5 min |
| Sentiment recorder | analysis-worker | Every 5 min |
| 5min candle builder | analysis-worker | Every 5 min |
| Daily candle sync | analysis-worker | Every 6 hours |
