# CLAUDE.md — Gold Monitor System

## 1. Project Overview

**Gold Monitor** (سامانه رصد طلا) is a real-time gold market intelligence and alerting system built for **Persian (Farsi) users**. It monitors news sources (RSS, HTML, JSON APIs) for gold-market-relevant content, matches items against a deterministic YAML-based rule engine, and generates alerts with severity levels and optional Persian-language LLM summaries.

**Key goals:**
- Automated monitoring of global and Iranian gold market news
- Deterministic rule-based alert classification (no LLM for severity/scoring)
- Persian RTL dashboard for market analysts
- Admin panel for managing sources and LLM settings
- Deduplication via Redis (fast) + PostgreSQL (durable)

The repo contains two sub-projects:
- **`gold-monitor-system/`** — The full-stack production system (API + Worker + Web + Docker)
- **`gold-monitor/`** — An earlier standalone Next.js prototype with mock data (no backend)

## 2. Tech Stack

### Backend (Python 3.12)
- **FastAPI** — REST API framework with async support
- **SQLAlchemy 2.0** — Async ORM (`asyncpg` driver) + sync engine (`psycopg2`) for Alembic
- **Alembic** — Database migrations
- **Pydantic v2 / pydantic-settings** — Request/response schemas and config
- **Redis (async)** — Deduplication cache, worker distributed lock
- **aiohttp** — HTTP client for worker fetchers
- **feedparser** — RSS/Atom feed parsing
- **BeautifulSoup4 + lxml** — HTML content extraction
- **PyYAML** — Rule file parsing
- **python-jose** — JWT authentication (HS256)
- **passlib + bcrypt** — Password hashing
- **httpx** — OpenRouter API client
- **hazm** — Persian NLP library (installed but not yet heavily used)
- **pytest + pytest-asyncio** — Testing

### Frontend (TypeScript)
- **Next.js 14** (App Router) — React framework
- **React 18** — UI library
- **TypeScript 5** — Type safety
- **Tailwind CSS 3** — Utility-first styling
- **Vazirmatn** — Persian font (loaded via CDN)

### Infrastructure
- **PostgreSQL 16** (Alpine) — Primary data store
- **Redis 7** (Alpine) — Cache and worker coordination
- **Docker Compose** — 5-service orchestration
- **Node 22** (Alpine) — Web container base image

### External Services
- **OpenRouter API** — LLM text generation (optional; default model: `anthropic/claude-sonnet-4`)

## 3. Architecture

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

### Service Roles

| Service | Image / Build | Port | Purpose |
|---------|---------------|------|---------|
| `db` | `postgres:16-alpine` | 5432 | Primary data store (8 tables) |
| `redis` | `redis:7-alpine` | 6379 | Dedup cache, worker lock |
| `api` | `api/Dockerfile` (Python 3.12) | 8000 | FastAPI REST API + startup migrations |
| `worker` | Same image as `api` | — | Periodic fetch-match-alert pipeline (60s cycle) |
| `web` | `web/Dockerfile` (Node 22) | 3000 | Next.js frontend (proxies `/api/*` to API) |

### Data Flow (every 60 seconds)
1. Worker acquires Redis distributed lock (`worker:lock`, 55s TTL)
2. Queries enabled sources whose `poll_interval_seconds` has elapsed
3. Fetches content via appropriate fetcher (RSS/HTML/JSON)
4. Deduplicates raw items by SHA-256 content hash (Redis 24h TTL → DB fallback)
5. Matches items against YAML rules (keyword + signal substring matching)
6. Determines severity deterministically from `importance_criteria`
7. Optionally enriches with LLM-generated Persian text (OpenRouter)
8. Persists alerts and fetch log entries

### API Proxy
The Next.js frontend uses `next.config.js` rewrites to proxy `/api/*` requests to the FastAPI backend (`INTERNAL_API_URL`, default `http://api:8000`). The web client's `api.ts` uses relative paths (empty `API_URL`).

## 4. Folder Structure

```
talamala/
├── CLAUDE.md                                    ← This file
├── README.md                                    ← Repo root readme
├── gold-monitor-system/                         ← Production full-stack system
│   ├── docker-compose.yml                       ← 5 services: db, redis, api, worker, web
│   ├── .env.example                             ← Environment variable template
│   ├── .gitignore
│   ├── README.md                                ← Detailed project documentation
│   ├── gold_monitor_rules_fa.yaml               ← 32+ monitoring rules (Persian)
│   ├── api/                                     ← Python backend
│   │   ├── Dockerfile                           ← Python 3.12 slim
│   │   ├── requirements.txt                     ← Python dependencies
│   │   ├── __init__.py
│   │   ├── main.py                              ← FastAPI app factory + startup lifecycle
│   │   ├── config.py                            ← Pydantic settings (env vars)
│   │   ├── database.py                          ← SQLAlchemy async/sync engines
│   │   ├── models.py                            ← ORM models (8 tables)
│   │   ├── schemas.py                           ← Pydantic request/response schemas
│   │   ├── auth.py                              ← JWT + bcrypt authentication
│   │   ├── seed.py                              ← Standalone data seeder script
│   │   ├── alembic.ini                          ← Alembic configuration
│   │   ├── alembic/
│   │   │   ├── env.py
│   │   │   ├── script.py.mako
│   │   │   └── versions/
│   │   │       └── 001_initial_schema.py        ← Initial migration (7 tables + seeds)
│   │   ├── routers/
│   │   │   ├── __init__.py
│   │   │   ├── alerts.py                        ← GET /api/alerts, /stats/today, /{id}
│   │   │   ├── sources.py                       ← CRUD + fetch-now + logs (admin-only)
│   │   │   ├── admin.py                         ← Login, settings, user info
│   │   │   ├── rules.py                         ← Rule library + single rule
│   │   │   ├── prices.py                        ← Real-time prices via TGJU API
│   │   │   ├── sentiment.py                     ← Multi-timeframe sentiment analysis + history
│   │   │   └── health.py                        ← Health check (DB + Redis + rules)
│   │   ├── rule_engine/
│   │   │   ├── __init__.py                      ← Public API re-exports
│   │   │   ├── load_rules.py                    ← YAML parser → Rule dataclasses (cached)
│   │   │   ├── matcher.py                       ← Persian-aware keyword/signal matching
│   │   │   ├── severity.py                      ← Deterministic severity from criteria
│   │   │   └── alert_builder.py                 ← Alert dict assembly + dedupe key
│   │   ├── worker/
│   │   │   ├── __init__.py
│   │   │   ├── main.py                          ← Worker loop (60s cycle) + pipeline
│   │   │   ├── dedup.py                         ← Redis + DB deduplication checker
│   │   │   └── fetchers/
│   │   │       ├── __init__.py                  ← Fetcher registry (get_fetcher)
│   │   │       ├── base.py                      ← BaseFetcher ABC + RawItem dataclass
│   │   │       ├── rss_fetcher.py               ← RSS/Atom via feedparser
│   │   │       ├── html_fetcher.py              ← HTML via BeautifulSoup
│   │   │       └── json_fetcher.py              ← JSON API with configurable field mapping
│   │   ├── llm/
│   │   │   ├── __init__.py
│   │   │   └── openrouter_client.py             ← Persian text generation (summary, why_important)
│   │   └── tests/
│   │       ├── __init__.py
│   │       ├── test_matcher.py                  ← Rule matching tests
│   │       ├── test_severity.py                 ← Severity determination tests
│   │       └── test_alert_builder.py            ← Alert building tests
│   └── web/                                     ← Next.js frontend
│       ├── Dockerfile                           ← Multi-stage Node 22 build
│       ├── package.json
│       ├── package-lock.json
│       ├── next.config.js                       ← API proxy rewrites
│       ├── tsconfig.json
│       ├── tailwind.config.ts                   ← Gold color palette, Vazirmatn font
│       ├── postcss.config.js
│       ├── next-env.d.ts
│       ├── public/.gitkeep
│       └── src/
│           ├── app/
│           │   ├── globals.css                  ← Tailwind + component classes + dark mode
│           │   ├── layout.tsx                   ← Root layout (RTL, lang="fa", Vazirmatn)
│           │   ├── page.tsx                     ← Dashboard (stats, risk gauge, alert feed)
│           │   ├── not-found.tsx                ← 404 page
│           │   ├── alert/[id]/page.tsx          ← Alert detail view
│           │   ├── library/page.tsx             ← Rule library browser
│           │   └── admin/
│           │       ├── layout.tsx               ← Admin auth guard + tab navigation
│           │       ├── login/page.tsx           ← Admin login form
│           │       ├── sources/page.tsx         ← Source CRUD + fetch logs
│           │       └── settings/page.tsx        ← LLM settings management
│           ├── components/
│           │   ├── TopBar.tsx                   ← Navigation bar + links
│           │   ├── AlertCard.tsx                ← Alert summary card
│           │   ├── RiskGauge.tsx                ← SVG half-circle sentiment gauge (0-100)
│           │   ├── SentimentChart.tsx            ← SVG sentiment history line chart
│           │   └── SeverityBadge.tsx            ← Colored severity label
│           └── lib/
│               ├── api.ts                       ← API client + TypeScript types
│               ├── auth.ts                      ← localStorage JWT token management
│               └── utils.ts                     ← Persian formatters + helpers
│
└── gold-monitor/                                ← Earlier standalone prototype (mock data)
    ├── README.md
    ├── DESIGN_NOTES.md
    ├── PROGRESS.md                              ← Detailed implementation tracker
    ├── package.json                             ← Next.js 16 + Tailwind v4
    ├── gold_monitor_rules_fa.yaml               ← Subset of rules
    └── src/
        ├── app/                                 ← 4 pages: dashboard, market, alert, library
        ├── components/                          ← 17 UI components (layout, ui, dashboard)
        ├── context/AppContext.tsx               ← Central state management
        ├── data/                                ← Mock alerts (18), markets (4), rules (32)
        ├── lib/                                 ← Constants + utils
        └── types/index.ts                       ← TypeScript types
```

## 5. Setup & Deployment

### Prerequisites
- Docker and Docker Compose

### Quick Start
```bash
cd gold-monitor-system
cp .env.example .env
# Edit .env — set OPENROUTER_API_KEY if you want LLM summaries
docker compose up -d
```

### Access Points
| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| Admin panel | http://localhost:3000/admin/login |
| API docs (Swagger) | http://localhost:8000/docs |
| API health | http://localhost:8000/api/health |

### Default Admin Credentials
- Email: `admin@goldmonitor.ir`
- Password: `admin123`

### Environment Variables (.env)
| Variable | Description | Default |
|----------|-------------|---------|
| `POSTGRES_USER` | PostgreSQL username | `goldmon` |
| `POSTGRES_PASSWORD` | PostgreSQL password | `goldmon_secret` |
| `POSTGRES_DB` | Database name | `goldmonitor` |
| `DATABASE_URL` | Async DB connection (asyncpg) | `postgresql+asyncpg://...@db:5432/goldmonitor` |
| `DATABASE_URL_SYNC` | Sync DB connection (psycopg2) | `postgresql://...@db:5432/goldmonitor` |
| `REDIS_URL` | Redis connection | `redis://redis:6379/0` |
| `OPENROUTER_API_KEY` | OpenRouter API key (optional) | empty |
| `SECRET_KEY` | JWT signing secret | `change-me-to-a-random-string` |
| `ADMIN_EMAIL` | Default admin email | `admin@goldmonitor.ir` |
| `ADMIN_PASSWORD` | Default admin password | `admin123` |
| `NEXT_PUBLIC_API_URL` | API URL for client-side (unused in Docker; proxy handles it) | `http://localhost:8000` |
| `INTERNAL_API_URL` | API URL for server-side Next.js proxy | `http://api:8000` |

### Startup Sequence
1. API runs Alembic migrations (`upgrade head`)
2. Seeds default admin user if not exists
3. Creates `sentiment_scores` table if not exists (via `checkfirst=True`)
4. Takes a snapshot of the YAML rules file
5. Runs one-time dedup flush (versioned marker `v10`) to reset Redis dedup after rule changes
6. Worker starts 60-second fetch cycle

### Running Tests
```bash
cd gold-monitor-system
pip install -r api/requirements.txt
python -m pytest api/tests/ -v
```

## 6. API Endpoints

### Public Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/alerts` | List alerts (filterable: severity, time_horizon, asset, q, from_date, to_date; paginated: limit, offset) |
| `GET` | `/api/alerts/stats/today` | Today's stats: sentiment score, severity counts, top 3 alerts, sections |
| `GET` | `/api/alerts/{id}` | Single alert detail |
| `GET` | `/api/prices` | Real-time gold, USD, coin prices via TGJU (30s cache) |
| `GET` | `/api/sentiment` | Multi-timeframe sentiment analysis (1h, 4h, 24h) with numeric scores |
| `GET` | `/api/sentiment/history` | Historical sentiment scores for charting (params: timeframe, hours) |
| `GET` | `/api/rules/library` | All rules grouped by section |
| `GET` | `/api/rules/{rule_id}` | Single rule with full metadata |
| `GET` | `/api/health` | Health check: DB, Redis, rules count, last worker run |

### Admin Endpoints (JWT required)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/admin/login` | Authenticate, returns JWT access token |
| `GET` | `/api/admin/me` | Current admin profile |
| `GET` | `/api/admin/settings` | List all key-value settings |
| `PUT` | `/api/admin/settings/{key}` | Create/update a setting |
| `GET` | `/api/sources` | List all sources (alphabetical) |
| `GET` | `/api/sources/{id}` | Single source detail |
| `POST` | `/api/sources` | Create a new source |
| `PUT` | `/api/sources/{id}` | Partial update a source |
| `DELETE` | `/api/sources/{id}` | Delete source + cascade |
| `POST` | `/api/sources/{id}/fetch-now` | Trigger immediate fetch |
| `GET` | `/api/sources/{id}/logs` | Fetch logs (last 50) |
| `GET` | `/api/sources/{id}/raw-items` | Raw items (last 50, searchable) |

### Sentiment Score (3-Layer Weighted Formula)
The dashboard's sentiment gauge shows a 0-100 numeric score per timeframe (1h, 4h, 24h), computed deterministically:

**Layer 1 — Per-alert signal:** `RSS_i = Polarity × Confidence`
- Polarity: +1 (bullish) / -1 (bearish) / 0 (neutral), detected from `expected_impact.direction`
- Falls back to severity-based default: high=0.3, medium=0.15, low=0.05

**Layer 2 — Importance weighting:** `WS_i = RSS_i × W_imp`
- Weights: critical=3.0, high=2.0, medium=1.0, low=0.5

**Layer 3 — Exponential time decay:** `W_time = e^(-λ × hours_ago)`
- λ: 1h=2.0, 4h=0.5, 24h=0.1

**Aggregation:**
- `raw = Σ(WS_i × W_time_i) / Σ(|W_imp_i × W_time_i|) × 100` → [-100, +100]
- Volume dampening: `min(1.0, n / threshold)` where thresholds are 1h=10, 4h=20, 24h=30
- Final: `50 + dampened / 2` clamped to [0, 100]

**Score → Category mapping:**
- 80+ = very_bullish (بسیار صعودی), 62-79 = bullish (صعودی), 38-61 = neutral (خنثی), 20-37 = bearish (نزولی), <20 = very_bearish (بسیار نزولی)

The LLM is used ONLY for generating text (summary, key_drivers, outlook). The numeric score is always deterministic.
- Scores persist to `sentiment_scores` table on each API call
- `/api/alerts/stats/today` returns the latest 4h score as `risk_score`
- Historical scores via `/api/sentiment/history?timeframe=4h&hours=48`

### Prices API
Real-time prices from TGJU (تی‌جی‌یو) with 30-second cache:
- **Primary endpoint**: `https://call4.tgju.org/ajax.json` — returns all prices in one call
- **Fallback**: Individual `api.tgju.org/v1/market/indicator/summary-table-data/{slug}` endpoints
- Returns: gold_global (USD/oz), gold_18k (toman/gram), usd (toman), emami_coin (toman)
- Each price includes: `value`, `formatted`, `change`, `change_pct`, `direction` (up/down/flat)

## 7. Data Sources

### Fetcher Types
| Type | Class | Method |
|------|-------|--------|
| `rss` | `RSSFetcher` | feedparser-based RSS/Atom parsing |
| `html` | `HTMLFetcher` | BeautifulSoup text extraction (supports CSS selectors via `metadata.css_selector`) |
| `json` | `JSONFetcher` | Configurable field mapping via `metadata` (`title_field`, `url_field`, `content_field`, `date_field`, `items_path`) |

### Configured News Sources
The worker fetches from these RSS sources (via Google News and direct feeds):

**International (English):**
1. **Reuters Gold** (RSS) — `news.google.com/rss/search?q=gold+price+reuters` — poll: 120s
2. **Kitco Gold** (RSS) — `news.google.com/rss/search?q=gold+kitco+price` — poll: 120s
3. **Bloomberg Commodities** (RSS) — `news.google.com/rss/search?q=gold+commodities+bloomberg` — poll: 180s
4. **CNBC Gold** (RSS) — `news.google.com/rss/search?q=gold+cnbc+market` — poll: 180s
5. **Investing.com Gold** (RSS) — `news.google.com/rss/search?q=gold+investing.com+price` — poll: 120s
6. **Goldbroker** (RSS) — `goldbroker.com/feed` — poll: 300s
7. **GoodReturns Gold** (RSS) — `news.google.com/rss/search?q=gold+price+good+returns` — poll: 300s
8. **Commodity-TV Gold** (RSS) — `news.google.com/rss/search?q=gold+commodity-tv` — poll: 300s
9. **DailyForex Gold** (RSS) — `news.google.com/rss/search?q=gold+dailyforex` — poll: 300s

**Iranian/Persian:**
10. **خبر فارسی - طلا** (RSS) — `khabarfarsi.com/rss/gold` — poll: 180s

**Note:** Persian Google News feeds were disabled (migration v6) as they return zero items from outside Iran. All Persian gold news now comes via international sources that mention gold-related Persian keywords.

### External APIs
- **OpenRouter** (`https://openrouter.ai/api/v1/chat/completions`) — Persian text generation for alert summaries and sentiment analysis. Only called when `OPENROUTER_API_KEY` is set.
- **TGJU** (`https://call4.tgju.org/ajax.json`) — Real-time gold, USD, and coin prices for Iranian market. No API key required.

## 8. Database Schema

**8 tables**, all using UUID primary keys and UTC timestamps.

### sources
Configurable data sources for the worker to fetch.
| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | PK |
| `name` | VARCHAR(255) | Display name |
| `type` | VARCHAR(20) | `rss`, `html`, `json_api`, `websocket`, `file`, `custom` |
| `base_url` | VARCHAR(2048) | Root URL |
| `endpoints` | JSONB | List of paths to fetch |
| `method` | VARCHAR(10) | HTTP method (default: GET) |
| `headers` | JSONB | Custom HTTP headers |
| `auth_config` | JSONB | Auth configuration |
| `parser` | VARCHAR(255) | Parser identifier |
| `enabled` | BOOLEAN | Whether worker should fetch |
| `poll_interval_seconds` | INTEGER | Fetch frequency (default: 60) |
| `categories` | JSONB | Category tags |
| `rule_bindings` | JSONB | Which rules to match against |
| `reliability_score` | FLOAT | Source reliability (0-1) |
| `last_fetched_at` | TIMESTAMPTZ | Last fetch attempt |
| `last_success_at` | TIMESTAMPTZ | Last successful fetch |
| `last_error` | TEXT | Last error message |

### raw_items
Fetched news items, deduplicated by content hash.
| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | PK |
| `source_id` | UUID | FK → sources (CASCADE) |
| `title` | VARCHAR(1024) | |
| `url` | VARCHAR(2048) | |
| `published_at` | TIMESTAMPTZ | Original publish date |
| `fetched_at` | TIMESTAMPTZ | When worker fetched it |
| `content_text` | TEXT | Extracted content |
| `content_hash` | VARCHAR(64) | SHA-256 for dedup (indexed) |
| `metadata` | JSONB | Extra fields |

### alerts
Generated alerts with severity, impact, and Persian text.
| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | PK |
| `title` | VARCHAR(1024) | |
| `timestamp_utc` | TIMESTAMPTZ | |
| `source_name` | VARCHAR(255) | |
| `source_url` | VARCHAR(2048) | |
| `matched_rule_ids` | JSONB | List of rule IDs that matched |
| `summary_fa` | TEXT | Persian summary (LLM or truncated content) |
| `why_important_fa` | TEXT | Persian importance explanation |
| `expected_impact` | JSONB | Impact on assets [{asset, direction, mechanism}] |
| `severity` | VARCHAR(10) | `high`, `medium`, `low` (deterministic) |
| `time_horizon` | VARCHAR(20) | `immediate`, `short`, `medium`, `long` |
| `confidence` | FLOAT | 0.3–0.95 (from match score) |
| `follow_up_questions` | JSONB | List of Persian follow-up questions |
| `dedupe_key` | VARCHAR(255) | Unique constraint for dedup |
| `raw_item_id` | UUID | FK → raw_items (SET NULL) |
| `match_evidence` | JSONB | {rule_id: {keywords: [], signals: []}} |

### fetch_logs
Per-source fetch history with timing and error tracking.
| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | PK |
| `source_id` | UUID | FK → sources (CASCADE) |
| `started_at` | TIMESTAMPTZ | |
| `finished_at` | TIMESTAMPTZ | |
| `status` | VARCHAR(20) | `success` or `error` |
| `items_fetched_count` | INTEGER | |
| `error_message` | TEXT | |
| `duration_ms` | INTEGER | |

### settings
Key-value configuration store.
| Column | Type | Notes |
|--------|------|-------|
| `key` | VARCHAR(255) | PK |
| `value` | JSONB | |
| `updated_at` | TIMESTAMPTZ | |

Default settings: `openrouter_model`, `temperature`, `max_tokens`, `enable_llm`, `dedupe_window_hours`

### admin_users
Admin credentials with bcrypt-hashed passwords.
| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | PK |
| `email` | VARCHAR(320) | Unique |
| `password_hash` | VARCHAR(255) | bcrypt |
| `role` | VARCHAR(50) | Default: `admin` |

### rules_snapshot
YAML version tracking (SHA-256 hash of content).
| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | PK |
| `version` | VARCHAR(100) | SHA-256 prefix (12 chars) |
| `yaml_content` | TEXT | Full YAML content |
| `loaded_at` | TIMESTAMPTZ | |

### sentiment_scores
Historical sentiment scores for charting (created by sentiment API on each call).
| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | PK |
| `timeframe` | VARCHAR(10) | `1h`, `4h`, `24h` |
| `score` | INTEGER | 0-100 numeric score |
| `sentiment` | VARCHAR(20) | `very_bullish`, `bullish`, `neutral`, `bearish`, `very_bearish` |
| `sentiment_label` | VARCHAR(50) | Persian label (e.g., صعودی) |
| `alert_count` | INTEGER | Number of alerts in that window |
| `created_at` | TIMESTAMPTZ | Auto-set to now() |

Indexed on `(timeframe, created_at)` for efficient history queries.

### Relationships
- `sources` → `raw_items` (one-to-many, CASCADE delete)
- `sources` → `fetch_logs` (one-to-many, CASCADE delete)
- `raw_items` → `alerts` (one-to-one optional, SET NULL on delete)

## 9. Key Conventions

### Code Patterns
- **Async-first**: All DB operations use `AsyncSession` via `asyncpg`. Worker uses `aiohttp` for HTTP.
- **Dependency injection**: FastAPI `Depends()` for DB sessions and auth guards.
- **Pydantic v2**: All request/response schemas use `model_config = ConfigDict(from_attributes=True, populate_by_name=True)`.
- **Persian field aliases**: Schema fields have Persian aliases (e.g., `Field(..., alias="عنوان")`) for bilingual API responses.
- **UUID primary keys**: All tables use `uuid.uuid4()` as default.
- **UTC timestamps**: All `datetime` fields use `timezone.utc`.

### Rule Engine Design (Critical)
- **LLM is NEVER used for classification.** Severity, time horizon, and confidence are always deterministic.
- The LLM (OpenRouter) ONLY generates Persian text: `summary_fa`, `why_important_fa`, `follow_up_questions`.
- Rules are defined in `gold_monitor_rules_fa.yaml` with 4 sections: `global_gold`, `iran_gold`, `coin`, `gold_funds`.
- Matching uses Persian-normalized substring matching (`matcher.py:normalize_text`): NFC normalization, diacritic stripping, Arabic→Persian character mapping (yaa, kaf), ZWNJ→space, lowercase.
- Match score: 60% keyword ratio + 40% signal ratio.
- Severity: checked in priority order `high_if → medium_if → low_if`, defaults to `medium`.
- Confidence: linear map from match_score to [0.3, 0.95].

### Deduplication
- **Raw items**: SHA-256 of `title|url|content_text`. Redis key `raw_items:hash:<hash>` with 24h TTL. DB fallback.
- **Alerts**: `dedupe_key` = SHA-256 of sorted rule IDs + normalized title (source intentionally excluded for cross-source dedup — same story from IRNA/Mehr/ISNA produces same key). Redis key `alert:dedup:<key>` with configurable window (default 6h from settings table).

### Frontend Patterns
- **RTL layout**: `<html lang="fa" dir="rtl">` in root layout.
- **Vazirmatn font**: Loaded via CDN, applied globally.
- **Component CSS classes**: Defined in `globals.css` using `@layer components` (`.card`, `.btn-primary`, `.btn-secondary`, `.input-field`, `.select-field`).
- **Gold color palette**: Custom `gold-50` through `gold-900` in Tailwind config.
- **Dark mode**: Class-based (`darkMode: "class"` in Tailwind).
- **Auth**: JWT token stored in `localStorage` under key `gold_monitor_token`.
- **API client**: Centralized in `lib/api.ts` with typed functions. Uses Next.js rewrites for API proxy.

### Naming
- Python: snake_case for files, functions, variables. PascalCase for classes.
- TypeScript: camelCase for functions/variables, PascalCase for components/interfaces.
- API routes: `/api/{resource}` pattern with kebab-case for multi-word paths.
- Rule IDs: `SECTION_DESCRIPTIVE_NAME` (e.g., `GLOB_RATE_DECISION`, `IR_FX_USD`).

### File Organization
- Backend routers go in `api/routers/`. Each has its own `APIRouter` with tags.
- Worker fetchers go in `api/worker/fetchers/`. Each extends `BaseFetcher`.
- Frontend pages use Next.js App Router (`src/app/`). Components in `src/components/`.
- Shared types and API client in `src/lib/`.

## 10. Current Status

### Working
- Full Docker Compose orchestration (5 services with health checks)
- API with all endpoints (alerts, sources, admin, rules, health, prices, sentiment)
- Database schema with Alembic migration + startup table creation
- Worker pipeline: fetch → dedup → match → alert (60s cycle)
- Three fetcher types (RSS, HTML, JSON)
- Deterministic rule engine with 32+ rules (catch-all rules limited to 3 keywords for match score threshold)
- Persian text normalization for matching
- JWT authentication for admin endpoints
- Web dashboard with:
  - Real-time price cards (gold, USD, coin) with change % and directional colors
  - Multi-timeframe sentiment gauge (1h/4h/Daily) with chart toggle
  - Categorized alert sections (global_gold, iran_gold, coin, gold_funds)
  - Alert feed with severity/time-horizon filters and pagination
  - Smart auto-refresh: 60s for data, sentiment refreshes on new alert detection (2min fallback)
  - Smooth CSS transitions for sentiment updates
- Admin panel (sources CRUD, settings, login)
- Alert detail page with:
  - Expected impact table (handles both array and dict formats)
  - Clean source URL display with "مشاهده منبع" button
  - Bullet-point rendering for why_important_fa
  - English title detection with Persian fallback
- Rule library browser
- Cross-source deduplication (same news from IRNA/Mehr/ISNA produces one alert)
- OpenRouter LLM integration for text generation (summary, key_drivers, outlook)
- **Deterministic 3-layer weighted sentiment scoring** (polarity × confidence × importance × time decay × volume dampening)
- Sentiment scoring system (0-100) with historical persistence
- 16 RSS sources (9 international, 1 Persian, 6 disabled)
- Worker LLM type safety (_ensure_str helper prevents list-to-str crashes)
- Rule engine unit tests (matcher, severity, alert_builder) — 105 tests passing

### Known Issues
- CORS is fully permissive (`allow_origins=["*"]`) — needs restriction for production
- Passwords are truncated to 72 bytes for bcrypt compatibility (`auth.py:_truncate_for_bcrypt`)
- Web frontend's `fetchSourceNow` calls `/api/sources/{id}/fetch` but the API route is `/api/sources/{id}/fetch-now`
- The `gold-monitor/` prototype uses mock data only; not connected to the backend
- Most existing alerts have empty `expected_impact.direction` — polarity defaults to severity-based heuristic

## 11. Common Tasks

### Add a New Data Source
1. Log in to admin: `http://localhost:3000/admin/login`
2. Go to Sources tab, click "Add Source"
3. Fill in: name, type (rss/html/json_api), base_url, endpoints (JSON array), poll_interval, categories, rule_bindings
4. Toggle enabled, click Save
5. Use "Fetch Now" to test

### Add a New Rule
1. Edit `gold-monitor-system/gold_monitor_rules_fa.yaml`
2. Add a new rule entry under the appropriate section with: `id`, `section`, `title`, `what_it_is`, `watch_for.keywords`, `watch_for.signals`, `why_important`, `importance_criteria` (high_if/medium_if/low_if), `impact_hypothesis`, `horizon`
3. Restart the API and worker to reload rules: `docker compose restart api worker`

### Update the Frontend UI
1. Edit files in `gold-monitor-system/web/src/`
2. For new pages: add under `src/app/` (Next.js App Router)
3. For new components: add under `src/components/`
4. Rebuild: `docker compose build web && docker compose up -d web`

### Restart Services
```bash
cd gold-monitor-system
docker compose restart           # Restart all
docker compose restart worker    # Restart just the worker
docker compose up -d --build     # Rebuild and restart
```

### Check Logs
```bash
docker compose logs -f api       # API logs
docker compose logs -f worker    # Worker logs (fetch cycles)
docker compose logs -f web       # Next.js logs
docker compose logs -f db        # PostgreSQL logs
```

### Run Database Migrations
Migrations run automatically on API startup. To run manually:
```bash
docker compose exec api alembic -c api/alembic.ini upgrade head
```

### Run the Seed Script
```bash
docker compose exec api python -m api.seed
```

### Run Tests
```bash
cd gold-monitor-system
pip install -r api/requirements.txt
python -m pytest api/tests/ -v
```

### Enable LLM Summaries
1. Set `OPENROUTER_API_KEY` in `.env`
2. Log in to admin panel → Settings
3. Set `enable_llm` to `true`
4. Optionally change `openrouter_model`, `temperature`, `max_tokens`
5. Restart worker: `docker compose restart worker`

### Access the Database Directly
```bash
docker compose exec db psql -U goldmon -d goldmonitor
```

### Useful SQL Queries
```sql
-- Count alerts by severity
SELECT severity, COUNT(*) FROM alerts GROUP BY severity;

-- Recent alerts
SELECT title, severity, created_at FROM alerts ORDER BY created_at DESC LIMIT 10;

-- Check sentiment scores
SELECT timeframe, score, sentiment_label, alert_count, created_at
FROM sentiment_scores ORDER BY created_at DESC LIMIT 20;

-- Check source fetch status
SELECT name, type, enabled, last_fetched_at, last_success_at, last_error
FROM sources ORDER BY name;

-- Count raw items per source
SELECT s.name, COUNT(r.id) as items
FROM sources s LEFT JOIN raw_items r ON s.id = r.source_id
GROUP BY s.name ORDER BY items DESC;

-- Clear dedup cache (forces re-processing of all items)
-- Run in Redis: FLUSHDB
-- Or bump the dedup flush version in api/main.py
```

## 12. Server & Deployment

### Production Server
The system runs on a server accessible at the configured domain. All services run via Docker Compose.

### Deploying Updates
After pushing code changes to the git branch:
```bash
# SSH into server, then:
cd ~/projects/talamala
git pull origin claude/analyze-project-structure-m8YuH
cd gold-monitor-system
docker compose up -d --build
```

This rebuilds all changed images and restarts containers. The API automatically runs migrations and seeds on startup.

### Monitoring
```bash
# Check all services are running
docker compose ps

# Watch worker cycles in real-time
docker compose logs -f worker

# Check API health
curl http://localhost:8000/api/health

# Check recent fetch logs
docker compose exec db psql -U goldmon -d goldmonitor -c \
  "SELECT s.name, f.status, f.items_fetched_count, f.started_at FROM fetch_logs f JOIN sources s ON f.source_id = s.id ORDER BY f.started_at DESC LIMIT 20;"
```

### Troubleshooting

**No alerts appearing:**
- Check worker logs: `docker compose logs -f worker`
- Verify sources are enabled: Admin panel → Sources
- Check MIN_MATCH_SCORE threshold (currently 0.18 in `worker/main.py`)
- Redis dedup might be blocking: bump dedup flush version in `api/main.py` and restart

**Prices not updating:**
- TGJU API (`call4.tgju.org/ajax.json`) is the primary source
- Some prices (دلار, سکه, طلای ۱۸ عیار) only update during Iran market hours (~9 AM to 6 PM IRST)
- طلای جهانی (global gold) updates 24/7
- Cache TTL is 30 seconds

**Sentiment score stuck at 50 (neutral):**
- Sentiment requires alerts to exist — if no alerts, fallback is neutral
- LLM sentiment analysis requires `OPENROUTER_API_KEY` to be set
- Without LLM, rule-based fallback is used (less nuanced)
- Check: `docker compose logs api | grep -i sentiment`

**Docker disk space:**
```bash
docker system prune -f           # Clean unused images/containers
docker volume ls                 # List volumes
```

## 13. Critical Rules for Development

### NEVER Do These
1. **NEVER add `DELETE FROM alerts` or `DELETE FROM raw_items` to migrations** — this wipes all user data on deploy. Migrations run on every startup.
2. **NEVER change matching rules and expect old alerts to update** — old alerts stay as-is. Only new items will match with new rules.
3. **NEVER force-push to the main branch** without explicit permission.

### Safe Operations
- **Redis FLUSHDB** is safe — it only clears dedup cache, causing items to be re-fetched and re-processed (no data loss)
- **Bumping dedup flush version** in `api/main.py` triggers a one-time Redis flush on next startup
- **Adding new columns** to existing tables should use `checkfirst=True` pattern (see `_create_sentiment_scores_table` in `main.py`)

### Match Score Tuning
- `MIN_MATCH_SCORE = 0.18` in `worker/main.py` — controls minimum threshold for alerts
- Match score = 60% keyword ratio + 40% signal ratio
- Example: 1 keyword match on 3-keyword rule = 0.333 (passes); 1 keyword on 6-keyword rule = 0.1 (rejected)
- **Critical**: Keep catch-all rules to ≤3 keywords so 1 match = 0.333, well above threshold
- Lowering this too much → spam alerts; raising too high → missed alerts

### Sentiment Score Tuning
- Formula parameters in `api/routers/sentiment.py`
- **Default polarity** (`_DEFAULT_POLARITY`): high=0.3, medium=0.15, low=0.05
- **Importance weights** (`_IMPORTANCE_WEIGHT`): critical=3.0, high=2.0, medium=1.0, low=0.5
- **Decay λ** (`_DECAY_LAMBDA`): 1h=2.0, 4h=0.5, 24h=0.1
- **Volume thresholds** (`_VOLUME_THRESHOLD`): 1h=10, 4h=20, 24h=30
- **Score ranges**: 80+ very_bullish, 62-79 bullish, 38-61 neutral, 20-37 bearish, <20 very_bearish
- With 16 medium alerts (no direction data): score ≈ 51-53 (neutral) — correctly reflects low-signal volume
