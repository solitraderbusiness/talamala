# Gold Monitor System

Real-time gold market intelligence and alerting system with deterministic rule matching, Persian (Farsi) UI, and optional LLM text generation via OpenRouter.

## Architecture

```
┌─────────────┐   ┌─────────────┐   ┌─────────────┐
│   Next.js    │   │   FastAPI    │   │   Worker     │
│   Frontend   │──▶│   API        │   │   (60s loop) │
│   :3000      │   │   :8000      │   │              │
└─────────────┘   └──────┬───────┘   └──────┬───────┘
                         │                    │
                    ┌────▼────────────────────▼────┐
                    │     PostgreSQL + Redis        │
                    │     :5432        :6379        │
                    └─────────────────────────────┘
```

**6 Services** (Docker Compose):
- **db** — PostgreSQL 16 (data store)
- **redis** — Redis 7 (dedup cache, worker lock)
- **api** — FastAPI (REST endpoints)
- **worker** — Periodic fetch-match-alert pipeline
- **web** — Next.js frontend (dashboard + admin panel)

## Quick Start

```bash
# 1. Clone and enter the project
cd gold-monitor-system

# 2. Copy environment file
cp .env.example .env

# 3. Edit .env with your settings (especially OPENROUTER_API_KEY)
nano .env

# 4. Start all services
docker compose up -d

# 5. Access the applications
# Frontend:  http://localhost:3000
# API docs:  http://localhost:8000/docs
# Admin:     http://localhost:3000/admin/login
```

Default admin credentials (change in `.env`):
- Email: `admin@goldmonitor.ir`
- Password: `admin123`

## How It Works

### Data Flow (every 60 seconds)

1. **Worker** queries enabled sources from DB
2. For each due source, the appropriate **fetcher** (RSS/HTML/JSON) downloads content
3. New items are **deduplicated** by content hash (Redis + DB)
4. Each item is matched against **YAML rules** (keyword + signal substring matching)
5. **Severity** is determined deterministically from rule `importance_criteria`
6. If LLM is enabled, **OpenRouter** generates Persian summary text
7. **Alerts** are created and stored in PostgreSQL

### Rule Engine (Deterministic)

The rule engine uses `gold_monitor_rules_fa.yaml` which contains 32+ monitoring rules across 4 sections:
- **Global Gold** — Fed decisions, geopolitics, USD/DXY, mining supply, etc.
- **Iran Gold** — USD/IRR rate, sanctions, domestic policy, etc.
- **Gold Coins** — Premium/bubble, seasonal demand, etc.
- **Gold Funds** — NAV premium, fund flows, CODAL notices, etc.

**IMPORTANT**: The LLM (OpenRouter) is NEVER used for classification. It only generates Persian text fields (`summary_fa`, `why_important_fa`, `follow_up_questions`). Severity, time horizon, and confidence are always determined by the deterministic rule engine.

### Deduplication

- **Raw items**: SHA-256 hash of `title|url|content` — checked in Redis (24h TTL) then DB
- **Alerts**: `dedupe_key` from sorted rule IDs + normalized title + source — configurable window (default 6 hours, set in admin settings)

## Adding Sources from Admin Panel

1. Log in at `/admin/login`
2. Navigate to **Sources** page
3. Click **Add Source** and fill in:
   - **Name**: Display name (e.g., "Reuters Gold News")
   - **Type**: `rss`, `html`, or `json_api`
   - **Base URL**: Root URL of the source
   - **Endpoints**: JSON array of paths (e.g., `["/feed/rss/gold"]`)
   - **Poll Interval**: Seconds between fetches (default: 60)
   - **Categories**: JSON array (e.g., `["global_gold"]`)
   - **Rule Bindings**: JSON array of rule IDs to match against
   - **Reliability Score**: 0.0 to 1.0
4. Toggle **Enabled** to start fetching
5. Use **Fetch Now** button to test immediately

## Setting OpenRouter Model from Admin Panel

1. Log in at `/admin/login`
2. Navigate to **Settings** page
3. Configure:
   - **enable_llm**: `true` to enable LLM text generation
   - **openrouter_model**: Model ID (default: `anthropic/claude-sonnet-4`)
   - **temperature**: 0.0-1.0 (default: 0.3)
   - **max_tokens**: Max output tokens (default: 1000)
4. Set `OPENROUTER_API_KEY` in `.env` file

## API Endpoints

### Public
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/alerts` | List alerts (filterable, paginated) |
| GET | `/api/alerts/stats/today` | Today's stats + risk score |
| GET | `/api/alerts/{id}` | Single alert detail |
| GET | `/api/rules/library` | All rules grouped by section |
| GET | `/api/rules/{id}` | Single rule detail |
| GET | `/api/health` | System health check |

### Admin (requires JWT)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/admin/login` | Get JWT token |
| GET | `/api/admin/me` | Current admin info |
| GET | `/api/admin/settings` | List all settings |
| PUT | `/api/admin/settings/{key}` | Update a setting |
| GET | `/api/sources` | List all sources |
| POST | `/api/sources` | Create a source |
| PUT | `/api/sources/{id}` | Update a source |
| DELETE | `/api/sources/{id}` | Delete a source |
| POST | `/api/sources/{id}/fetch-now` | Trigger immediate fetch |
| GET | `/api/sources/{id}/logs` | Fetch logs for a source |
| GET | `/api/sources/{id}/raw-items` | Raw items from a source |

## Database Schema

7 tables:
- **sources** — Configurable data sources (RSS, HTML, JSON API)
- **raw_items** — Fetched news items (deduplicated by content_hash)
- **alerts** — Generated alerts with severity, impact, and Persian text
- **fetch_logs** — Per-source fetch history with timing
- **settings** — Key-value configuration store
- **admin_users** — Admin credentials (bcrypt hashed)
- **rules_snapshot** — YAML version tracking

## Project Structure

```
gold-monitor-system/
├── docker-compose.yml
├── .env.example
├── gold_monitor_rules_fa.yaml     # 32+ monitoring rules
├── api/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── __init__.py
│   ├── main.py                    # FastAPI app + startup
│   ├── config.py                  # Pydantic settings
│   ├── database.py                # SQLAlchemy async setup
│   ├── models.py                  # ORM models (7 tables)
│   ├── schemas.py                 # Pydantic request/response
│   ├── auth.py                    # JWT + bcrypt
│   ├── seed.py                    # Initial data seeder
│   ├── alembic.ini
│   ├── alembic/                   # Database migrations
│   ├── routers/
│   │   ├── alerts.py
│   │   ├── sources.py
│   │   ├── admin.py
│   │   ├── rules.py
│   │   └── health.py
│   ├── rule_engine/
│   │   ├── load_rules.py          # YAML parser + caching
│   │   ├── matcher.py             # Keyword/signal matching
│   │   ├── severity.py            # Deterministic severity
│   │   └── alert_builder.py       # Alert assembly
│   ├── worker/
│   │   ├── main.py                # 60s cycle loop
│   │   ├── dedup.py               # Redis + DB dedup
│   │   └── fetchers/
│   │       ├── base.py            # BaseFetcher + RawItem
│   │       ├── rss_fetcher.py
│   │       ├── html_fetcher.py
│   │       └── json_fetcher.py
│   ├── llm/
│   │   └── openrouter_client.py   # Persian text generation
│   └── tests/
│       ├── test_matcher.py
│       ├── test_severity.py
│       └── test_alert_builder.py
└── web/
    ├── Dockerfile
    ├── package.json
    └── src/
        └── app/                   # Next.js pages
```

## Running Tests

```bash
# Rule engine tests (from project root)
cd gold-monitor-system
pip install -r api/requirements.txt
python -m pytest api/tests/ -v
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_USER` | `goldmon` | PostgreSQL username |
| `POSTGRES_PASSWORD` | `goldmon_secret` | PostgreSQL password |
| `POSTGRES_DB` | `goldmonitor` | Database name |
| `DATABASE_URL` | (see .env.example) | Async DB connection string |
| `DATABASE_URL_SYNC` | (see .env.example) | Sync DB connection string |
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection |
| `OPENROUTER_API_KEY` | (empty) | OpenRouter API key for LLM |
| `SECRET_KEY` | `change-me...` | JWT signing key |
| `ADMIN_EMAIL` | `admin@goldmonitor.ir` | Default admin email |
| `ADMIN_PASSWORD` | `admin123` | Default admin password |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | API URL for frontend |

## Tech Stack

- **Backend**: Python 3.12, FastAPI, SQLAlchemy (async), Alembic
- **Database**: PostgreSQL 16, Redis 7
- **Frontend**: Next.js 14, React 18, TypeScript, Tailwind CSS
- **Worker**: asyncio, aiohttp, feedparser, BeautifulSoup
- **LLM**: OpenRouter API (httpx client)
- **Auth**: JWT (python-jose), bcrypt (passlib)
- **Container**: Docker Compose with health checks
