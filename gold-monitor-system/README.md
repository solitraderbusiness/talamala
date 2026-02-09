# Gold Monitor System (سامانه رصد طلا)

Real-time gold market intelligence and alerting system for **Persian (Farsi) users**. Monitors global and Iranian news sources, matches content against deterministic YAML rules, and generates alerts with severity levels and optional LLM-generated Persian summaries.

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   Next.js Web   │────▶│   FastAPI API     │     │   Worker         │
│   :3000         │     │   :8000           │     │   (60s loop)     │
│   (RTL/Persian) │     │   REST endpoints  │     │   fetch→match→   │
└─────────────────┘     └────────┬──────────┘     │   alert pipeline │
       │                         │                 └────────┬─────────┘
       │ /api/* rewrite          │                          │
       └─────────────────────────┘                          │
                                 │                          │
                          ┌──────▼──────────────────────────▼──────┐
                          │        PostgreSQL 16 + Redis 7         │
                          │        :5432              :6379        │
                          └────────────────────────────────────────┘
                                                    │
                                           ┌────────▼────────┐
                                           │  OpenRouter API  │
                                           │  (optional LLM)  │
                                           └─────────────────┘
```

### Services (Docker Compose)

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| `db` | postgres:16-alpine | 5432 | Primary data store (8 tables) |
| `redis` | redis:7-alpine | 6379 | Dedup cache, worker distributed lock |
| `api` | Python 3.12 (FastAPI) | 8000 | REST API + startup migrations |
| `worker` | Same as api | — | Periodic fetch-match-alert pipeline |
| `web` | Node 22 (Next.js 14) | 3000 | Frontend dashboard + admin panel |

## Quick Start

```bash
cd gold-monitor-system
cp .env.example .env
# Edit .env — set OPENROUTER_API_KEY for LLM summaries, BRSAPI_KEY for prices
docker compose up -d
```

### Access Points

| Service | URL |
|---------|-----|
| Frontend Dashboard | http://localhost:3000 |
| Admin Panel | http://localhost:3000/admin/login |
| API Docs (Swagger) | http://localhost:8000/docs |
| API Health Check | http://localhost:8000/api/health |

### Default Admin Credentials
- Email: `admin@goldmonitor.ir`
- Password: `admin123`

(Configurable via `ADMIN_EMAIL` and `ADMIN_PASSWORD` in `.env`)

## How It Works

### Data Flow (every 60 seconds)

1. **Worker** acquires Redis distributed lock (`worker:lock`, 55s TTL)
2. Queries enabled sources whose `poll_interval_seconds` has elapsed
3. Appropriate **fetcher** (RSS/HTML/JSON) downloads content
4. New items are **deduplicated** by SHA-256 content hash (Redis 24h TTL → DB fallback)
5. Each item is matched against **YAML rules** (keyword + signal substring matching)
6. **Severity** is determined deterministically from rule `importance_criteria`
7. If LLM is enabled, **OpenRouter** generates Persian text (summary, why_important)
8. **Alerts** are persisted to PostgreSQL with dedup key

### Rule Engine (Deterministic)

The rule engine (`gold_monitor_rules_fa.yaml`) contains 32+ monitoring rules across 4 sections:

| Section | Rules | Examples |
|---------|-------|---------|
| `global_gold` | 14 | Fed decisions, geopolitics, USD/DXY, mining supply, gold prices |
| `iran_gold` | 10 | USD/IRR rate, sanctions, domestic policy, inflation |
| `coin` | 6 | Premium/bubble, seasonal demand, auctions, sentiment |
| `gold_funds` | 4 | NAV premium, fund flows, CODAL notices |

**CRITICAL**: The LLM is NEVER used for classification. It only generates Persian text fields (`summary_fa`, `why_important_fa`, `follow_up_questions`). Severity, time horizon, and confidence are always deterministic.

#### Matching Algorithm

1. **Text normalization** (`matcher.py:normalize_text`): Unicode NFC, strip diacritics, Arabic→Persian char mapping (yaa, kaf), ZWNJ→space, lowercase
2. **Keyword matching**: Normalized keyword must be a **substring** of normalized title+content
3. **Signal matching**: Same substring matching for signal phrases
4. **Score**: `0.6 × (keyword_matches/total_keywords) + 0.4 × (signal_matches/total_signals)`
5. **Threshold**: `MIN_MATCH_SCORE = 0.18` — items below this are rejected

#### Compound Keyword Strategy

Catch-all rules (GLOB_GOLD_PRICE, IR_GOLD_COIN_PRICE) use **compound keywords** like "gold price", "قیمت طلا" instead of bare "gold", "طلا". This prevents false positives from non-market articles (sports medals, land supply, etc.).

With 5 compound keywords + 10 signals:
- 1 keyword match alone = `0.6 × 0.2 = 0.12` → **FAILS** threshold
- 1 keyword + 2 signals = `0.12 + 0.08 = 0.20` → **PASSES** (requires market context)
- 2 keywords = `0.6 × 0.4 = 0.24` → **PASSES** (multiple market terms)

### Sentiment Analysis (0-100 Score)

Deterministic 3-layer weighted formula (no LLM for scoring):

1. **Per-alert signal**: `RSS_i = Polarity × Confidence`
   - Polarity from `expected_impact.direction`: +1 bullish, -1 bearish, 0 neutral
   - Falls back to severity: high=0.3, medium=0.15, low=0.05
2. **Importance weighting**: `WS_i = RSS_i × W_imp` (critical=3.0, high=2.0, medium=1.0, low=0.5)
3. **Exponential time decay**: `W_time = e^(-λ × hours_ago)` (λ: 1h=2.0, 4h=0.5, 24h=0.1)

Aggregated with volume dampening, mapped to [0, 100]:
- 80+ = very_bullish, 62-79 = bullish, 38-61 = neutral, 20-37 = bearish, <20 = very_bearish

Scores persist to `sentiment_scores` table for historical charting.

### Prices API

Real-time gold, USD, and coin prices with 60-second Redis cache:

- **Primary**: [BrsAPI](https://brsapi.ir) (`BRSAPI_KEY` required) — prices already in Toman
- **Fallback**: [TGJU](https://call4.tgju.org/ajax.json) — used when BrsAPI unavailable, prices in Rial (÷10)

Returns: gold_global (USD/oz), gold_18k (toman/gram), usd (toman), emami_coin (toman).

### Deduplication

- **Raw items**: SHA-256 of `title|url|content_text` → Redis (24h TTL) → DB fallback
- **Alerts**: `dedupe_key` = SHA-256 of sorted rule IDs + normalized title (source intentionally excluded for cross-source dedup)

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_USER` | `goldmon` | PostgreSQL username |
| `POSTGRES_PASSWORD` | `goldmon_secret` | PostgreSQL password |
| `POSTGRES_DB` | `goldmonitor` | Database name |
| `DATABASE_URL` | (see .env.example) | Async DB connection (asyncpg) |
| `DATABASE_URL_SYNC` | (see .env.example) | Sync DB connection (psycopg2) |
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection |
| `OPENROUTER_API_KEY` | (empty) | OpenRouter API key for LLM text generation |
| `BRSAPI_KEY` | (empty) | BrsAPI key for real-time prices |
| `SECRET_KEY` | `change-me...` | JWT signing secret |
| `ADMIN_EMAIL` | `admin@goldmonitor.ir` | Default admin email |
| `ADMIN_PASSWORD` | `admin123` | Default admin password |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | API URL (unused in Docker; proxy handles it) |
| `INTERNAL_API_URL` | `http://api:8000` | API URL for Next.js server-side proxy |

## API Endpoints

### Public

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/alerts` | List alerts (severity, time_horizon, asset, q, from_date, to_date, limit, offset) |
| `GET` | `/api/alerts/stats/today` | Today's stats: sentiment score, severity counts, top alerts, sections |
| `GET` | `/api/alerts/{id}` | Single alert detail |
| `GET` | `/api/prices` | Real-time gold, USD, coin prices (BrsAPI primary, TGJU fallback) |
| `GET` | `/api/sentiment` | Multi-timeframe sentiment (1h, 4h, 24h) with numeric scores |
| `GET` | `/api/sentiment/history` | Historical sentiment scores (params: timeframe, hours) |
| `GET` | `/api/rules/library` | All rules grouped by section |
| `GET` | `/api/rules/{rule_id}` | Single rule with full metadata |
| `GET` | `/api/health` | Health check: DB, Redis, rules count, last worker run |

### Admin (JWT required)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/admin/login` | Authenticate, returns JWT token |
| `GET` | `/api/admin/me` | Current admin profile |
| `GET/PUT` | `/api/admin/settings` | Read/update key-value settings |
| `GET` | `/api/sources` | List all sources |
| `POST` | `/api/sources` | Create a new source |
| `PUT` | `/api/sources/{id}` | Partial update a source |
| `DELETE` | `/api/sources/{id}` | Delete source + cascade |
| `POST` | `/api/sources/{id}/fetch-now` | Trigger immediate fetch |
| `GET` | `/api/sources/{id}/logs` | Fetch logs (last 50) |
| `GET` | `/api/sources/{id}/raw-items` | Raw items (last 50, searchable) |

## Database Schema

**8 tables**, all using UUID primary keys and UTC timestamps.

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `sources` | Configurable data sources | name, type (rss/html/json_api), base_url, endpoints, enabled, poll_interval_seconds, categories, rule_bindings |
| `raw_items` | Fetched news items (deduped) | title, url, content_text, content_hash (SHA-256, indexed), source_id FK |
| `alerts` | Generated alerts | title, severity, time_horizon, confidence, summary_fa, why_important_fa, expected_impact (JSONB), dedupe_key (unique), matched_rule_ids |
| `fetch_logs` | Per-source fetch history | source_id FK, status, items_fetched_count, duration_ms, error_message |
| `settings` | Key-value config store | key (PK), value (JSONB) |
| `admin_users` | Admin credentials | email (unique), password_hash (bcrypt), role |
| `rules_snapshot` | YAML version tracking | version (SHA-256 prefix), yaml_content |
| `sentiment_scores` | Historical sentiment | timeframe (1h/4h/24h), score (0-100), sentiment, alert_count |

### Relationships
- `sources` → `raw_items` (one-to-many, CASCADE delete)
- `sources` → `fetch_logs` (one-to-many, CASCADE delete)
- `raw_items` → `alerts` (one-to-one optional, SET NULL on delete)

## Project Structure

```
gold-monitor-system/
├── docker-compose.yml                       # 5 services: db, redis, api, worker, web
├── .env.example                             # Environment variable template
├── gold_monitor_rules_fa.yaml               # 32+ monitoring rules (Persian/English)
├── api/                                     # Python backend
│   ├── Dockerfile                           # Python 3.12 slim
│   ├── requirements.txt
│   ├── main.py                              # FastAPI app + startup lifecycle + migrations
│   ├── config.py                            # Pydantic settings (env vars)
│   ├── database.py                          # SQLAlchemy async/sync engines
│   ├── models.py                            # ORM models (8 tables)
│   ├── schemas.py                           # Pydantic request/response schemas
│   ├── auth.py                              # JWT + bcrypt authentication
│   ├── seed.py                              # Standalone data seeder script
│   ├── alembic.ini + alembic/               # Database migrations
│   ├── routers/
│   │   ├── alerts.py                        # GET /api/alerts, /stats/today, /{id}
│   │   ├── sources.py                       # CRUD + fetch-now + logs (admin-only)
│   │   ├── admin.py                         # Login, settings, user info
│   │   ├── rules.py                         # Rule library + single rule
│   │   ├── prices.py                        # Real-time prices (BrsAPI + TGJU fallback)
│   │   ├── sentiment.py                     # Multi-timeframe sentiment + history
│   │   └── health.py                        # Health check (DB + Redis + rules)
│   ├── rule_engine/
│   │   ├── load_rules.py                    # YAML parser → Rule dataclasses (cached)
│   │   ├── matcher.py                       # Persian-aware keyword/signal matching
│   │   ├── severity.py                      # Deterministic severity from criteria
│   │   └── alert_builder.py                 # Alert dict assembly + dedupe key
│   ├── worker/
│   │   ├── main.py                          # Worker loop (60s cycle) + pipeline
│   │   ├── dedup.py                         # Redis + DB deduplication checker
│   │   └── fetchers/
│   │       ├── base.py                      # BaseFetcher ABC + RawItem dataclass
│   │       ├── rss_fetcher.py               # RSS/Atom via feedparser
│   │       ├── html_fetcher.py              # HTML via BeautifulSoup
│   │       └── json_fetcher.py              # JSON API with field mapping
│   ├── llm/
│   │   └── openrouter_client.py             # Persian text generation via OpenRouter
│   └── tests/
│       ├── test_matcher.py                  # 81 tests for matching
│       ├── test_severity.py                 # Severity + confidence tests
│       └── test_alert_builder.py            # Alert building tests
└── web/                                     # Next.js frontend
    ├── Dockerfile                           # Multi-stage Node 22 build
    ├── package.json
    ├── next.config.js                       # API proxy rewrites (/api/* → FastAPI)
    ├── tailwind.config.ts                   # Gold color palette, Vazirmatn font
    └── src/
        ├── app/
        │   ├── globals.css                  # Tailwind + component classes + dark mode
        │   ├── layout.tsx                   # Root layout (RTL, lang="fa", Vazirmatn)
        │   ├── page.tsx                     # Dashboard (stats, risk gauge, alert feed)
        │   ├── alert/[id]/page.tsx          # Alert detail view
        │   ├── library/page.tsx             # Rule library browser
        │   └── admin/                       # Admin panel (login, sources, settings)
        ├── components/
        │   ├── TopBar.tsx                   # Navigation bar
        │   ├── AlertCard.tsx                # Alert summary card
        │   ├── RiskGauge.tsx                # SVG half-circle sentiment gauge (0-100)
        │   ├── SentimentChart.tsx            # SVG sentiment history line chart
        │   └── SeverityBadge.tsx            # Colored severity label
        └── lib/
            ├── api.ts                       # API client + TypeScript types
            ├── auth.ts                      # localStorage JWT management
            └── utils.ts                     # Persian formatters + helpers
```

## Tech Stack

### Backend (Python 3.12)
- **FastAPI** — REST API with async support
- **SQLAlchemy 2.0** — Async ORM (asyncpg) + sync engine (psycopg2) for Alembic
- **Alembic** — Database migrations
- **Pydantic v2 / pydantic-settings** — Schemas and config
- **Redis (async)** — Dedup cache, worker lock
- **aiohttp** — HTTP client for fetchers
- **feedparser** — RSS/Atom parsing
- **BeautifulSoup4 + lxml** — HTML extraction
- **httpx** — OpenRouter + BrsAPI client
- **python-jose** — JWT (HS256)
- **passlib + bcrypt** — Password hashing
- **pytest + pytest-asyncio** — 105 tests

### Frontend (TypeScript)
- **Next.js 14** (App Router) — React framework
- **React 18** — UI library
- **Tailwind CSS 3** — Utility-first styling with gold palette
- **Vazirmatn** — Persian font (CDN)

### Infrastructure
- **PostgreSQL 16** (Alpine) — Primary data store
- **Redis 7** (Alpine) — Cache and coordination
- **Docker Compose** — 5-service orchestration with health checks

### External APIs
- **OpenRouter** (`openrouter.ai`) — Optional LLM for Persian text generation
- **BrsAPI** (`brsapi.ir`) — Primary real-time price data (gold, USD, coins)
- **TGJU** (`call4.tgju.org`) — Fallback price data

## Common Tasks

### Add a New Data Source

1. Admin panel → Sources → Add Source
2. Fill: name, type (rss/html/json_api), base_url, endpoints (JSON array), poll_interval, categories, rule_bindings
3. Toggle enabled → Save → Use "Fetch Now" to test

### Add a New Rule

1. Edit `gold_monitor_rules_fa.yaml`
2. Add rule with: id, section, title, what_it_is, watch_for (keywords + signals), why_important, importance_criteria, impact_hypothesis, horizon
3. Restart: `docker compose restart api worker`

### Enable LLM Summaries

1. Set `OPENROUTER_API_KEY` in `.env`
2. Admin panel → Settings → `enable_llm` = `true`
3. Optionally change `openrouter_model`, `temperature`, `max_tokens`
4. Restart worker: `docker compose restart worker`

### Run Tests

```bash
cd gold-monitor-system
pip install -r api/requirements.txt
python -m pytest api/tests/ -v
# 105 tests pass
```

### Deploy Updates

```bash
cd gold-monitor-system
docker compose up -d --build    # Rebuild and restart all services
# API automatically runs migrations and seeds on startup
```

### Check Logs

```bash
docker compose logs -f api       # API logs
docker compose logs -f worker    # Worker logs (fetch cycles)
docker compose logs -f web       # Next.js logs
docker compose ps                # Check service status
```

### Access Database

```bash
docker compose exec db psql -U goldmon -d goldmonitor

-- Useful queries:
SELECT severity, COUNT(*) FROM alerts GROUP BY severity;
SELECT title, severity, created_at FROM alerts ORDER BY created_at DESC LIMIT 10;
SELECT name, enabled, last_fetched_at, last_error FROM sources ORDER BY name;
SELECT timeframe, score, sentiment_label, created_at FROM sentiment_scores ORDER BY created_at DESC LIMIT 10;
```

## Startup Sequence

On every API container start:
1. Run Alembic migrations (`upgrade head`)
2. Seed default admin user if not exists
3. Seed default news sources if none exist
4. Run one-time data migrations (v1-v8, marker-guarded)
5. Create `sentiment_scores` table (`checkfirst=True`)
6. Flush Redis dedup keys if version changed (triggers re-processing)
7. Snapshot current YAML rules

## Troubleshooting

### No alerts appearing
- Check worker logs: `docker compose logs -f worker`
- Verify sources enabled: Admin → Sources
- Check MIN_MATCH_SCORE (0.18 in `worker/main.py`)
- Bump dedup flush version in `api/main.py` and restart

### Prices not updating
- Primary: BrsAPI requires `BRSAPI_KEY` in `.env` AND in `docker-compose.yml` environment
- Fallback: TGJU (no key needed)
- Some Iranian prices only update during market hours (~9 AM - 6 PM IRST)
- Cache TTL is 60 seconds

### Sentiment stuck at 50
- Requires alerts to exist; no alerts = neutral fallback
- LLM (`OPENROUTER_API_KEY`) needed for text analysis, but score is deterministic
- Check: `docker compose logs api | grep sentiment`

## Critical Rules

### NEVER Do These
1. **NEVER add `DELETE FROM alerts/raw_items` to migrations** — wipes user data on deploy
2. **NEVER use bare keywords** like "طلا" (gold) or "سکه" (coin) alone — matches sports, land, etc.
3. **NEVER force-push** without explicit permission

### Safe Operations
- Redis FLUSHDB — only clears dedup cache (items get re-fetched)
- Bumping dedup flush version — triggers one-time Redis flush on restart
- Adding new DB columns — use `checkfirst=True` pattern

## Frontend Patterns

- **RTL layout**: `<html lang="fa" dir="rtl">`
- **Vazirmatn font**: Loaded via CDN, applied globally
- **Gold color palette**: Custom `gold-50` through `gold-900` in Tailwind config
- **Dark mode**: Class-based (`darkMode: "class"`)
- **API proxy**: Next.js rewrites `/api/*` to FastAPI backend
- **Auth**: JWT in localStorage (`gold_monitor_token`)
- **Component CSS**: `.card`, `.btn-primary`, `.btn-secondary` in `globals.css`
