# Talamala - Gold Market Monitor (سامانه رصد طلا)

## What This Is
Real-time gold market intelligence system for Persian (Farsi) users. Monitors news sources (RSS, HTML, JSON APIs), matches against YAML-based rules, generates severity-rated alerts with optional Persian LLM summaries. Two sub-projects: `gold-monitor-system/` (production) and `gold-monitor/` (legacy prototype with mock data).

## Tech Stack
- **Frontend:** Next.js 14, React 18, TypeScript 5, Tailwind CSS 3, Vazirmatn font (Persian RTL)
- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2.0 (asyncpg), Pydantic v2
- **Database:** PostgreSQL 16, Redis 7 (cache + dedup + worker lock)
- **Deployment:** Docker Compose (6 services: db, redis, api, worker, signal-worker, web)
- **AI/LLM:** OpenRouter API (Claude Sonnet 4) — alert text generation + AI chat assistant
- **Signal Aggregator:** Telethon (Telegram), Anthropic Claude API (signal parsing), Recharts (charts)

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
Six Docker services: **PostgreSQL** (port 5432, 21 tables), **Redis** (6379, dedup cache + worker lock + chat rate limiting), **FastAPI API** (8000, REST endpoints + auto-migrations on startup), **Worker** (same image as API, 60s fetch-match-alert pipeline), **Signal Worker** (same image, runs signal aggregator: Telegram listener, TradingView scraper, signal parser, price checker, consensus builder, performance tracker), **Next.js Web** (3000, RTL Persian dashboard + AI chat widget + AI Analysis page, proxies `/api/*` to API). Worker acquires Redis distributed lock (55s TTL), fetches enabled sources, deduplicates via SHA-256 content hash, matches against YAML rules, determines severity deterministically, optionally enriches with LLM Persian text, persists alerts. Background jobs: calendar sync (6h), price outcome tracker (15min). AI chat widget provides conversational access to alerts, calendar, and prices via SSE streaming with tool-use pattern.

## Code Conventions
- **Async-first**: all DB ops use `AsyncSession` via asyncpg; worker uses aiohttp for HTTP
- **Python**: snake_case files/functions/vars, PascalCase classes; routers in `api/routers/`, fetchers in `api/worker/fetchers/`, chat services in `api/services/chat/`, signal aggregator in `api/signal_aggregator/`
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

## Access Points
| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| Admin | http://localhost:3000/admin/login |
| Swagger | http://localhost:8000/docs |
| Health | http://localhost:8000/api/health |
| AI Analysis | http://localhost:3000/ai-analysis |
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
