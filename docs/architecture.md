# Architecture

## Service Diagram

```
┌─────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   Next.js Web   │────▶│   FastAPI API     │     │   Worker         │
│   :3000         │     │   :8000           │     │   (60s loop)     │
│   (RTL/Persian) │     │   REST endpoints  │     │   fetch→match→   │
└─────────────────┘     └────────┬──────────┘     │   alert pipeline │
                                 │                 └────────┬─────────┘
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

## Services

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| `db` | postgres:16-alpine | 5432 | Primary data store (14 tables) |
| `redis` | redis:7-alpine | 6379 | Dedup cache, worker lock, chat rate limiting |
| `api` | api/Dockerfile (Python 3.12) | 8000 | FastAPI REST API + auto-migrations |
| `worker` | Same image as api | — | Periodic fetch-match-alert pipeline (60s) |
| `web` | web/Dockerfile (Node 22) | 3000 | Next.js frontend (proxies /api/* to API) |

## Worker Data Flow (every 60 seconds)
1. Acquire Redis distributed lock (`worker:lock`, 55s TTL)
2. Fetch price snapshot (Redis cache → BrsAPI → TGJU fallback)
3. Query enabled sources past their `poll_interval_seconds`
4. Fetch content via RSS/HTML/JSON fetcher
5. Deduplicate raw items by SHA-256 content hash (Redis 24h TTL → DB fallback)
6. Match items against YAML rules (keyword + signal substring matching)
7. Determine severity from `importance_criteria` + critical event regex
8. Classify: news_type + event_category from rule IDs
9. Stamp 4 market prices on alert
10. Optionally enrich with LLM Persian text (OpenRouter)
11. Persist alerts and fetch log entries

## Background Jobs (API process)
- **Calendar sync** (`calendar_sync.py`): JBlanked + Finnhub every 6h
- **Price tracker** (`price_tracker.py`): Check prices 1h/4h/24h after each alert, every 15min

## AI Chat Widget
Conversational assistant for Persian gold market queries, accessible from every page via floating bubble (bottom-left).

### Architecture
```
User → ChatBubble → ChatPanel → POST /api/chat (SSE)
                                       │
                    ┌──────────────────▼──────────────────┐
                    │  Session manager (30min TTL, 50 msg) │
                    │  Rate limiter (Redis, 30/h per IP)   │
                    │  OpenRouter Claude Sonnet 4           │
                    │  Tool executor (search, calendar,     │
                    │                  prices)              │
                    │  Intent classifier + analytics        │
                    └──────────────────────────────────────┘
```

### Chat Flow
1. Frontend sends user message via POST `/api/chat` with session_id
2. Backend validates rate limits, creates/retrieves session
3. Loads conversation history, builds system prompt with Shamsi date
4. Calls OpenRouter with tool definitions (search_news, get_calendar_events, get_price_data)
5. If LLM returns tool_calls → execute against DB → second LLM call with results
6. Streams final response via SSE with meta-tag buffering (`<chat_meta>` stripped before display)
7. Saves messages + analytics (intent, topics, assets, feature gaps)

### Chat Services (`api/services/chat/`)
| File | Purpose |
|------|---------|
| `openrouter.py` | OpenRouter API client, system prompt templating, Shamsi date conversion |
| `rate_limiter.py` | Redis-backed per-IP (30/h) + global (1000/h) rate limiting |
| `session_manager.py` | Session lifecycle, conversation history, message persistence |
| `intent_classifier.py` | Parse `<chat_meta>` from LLM response, save analytics |
| `tool_executor.py` | Execute LLM tool calls against DB (alerts, calendar, prices) |
| `tools.py` | OpenAI-compatible tool definitions for the LLM |

### SSE Event Types
- `{"type": "status", "content": "thinking|searching|generating"}` — Progress indicator
- `{"type": "content", "content": "..."}` — Streamed response chunks
- `{"type": "suggestions", "content": [...]}` — Follow-up suggestion chips
- `{"type": "done", "session_id": "..."}` — End of response
- `{"type": "error", "content": "..."}` — Error message

## API Proxy
Next.js `next.config.js` rewrites `/api/*` to FastAPI (`INTERNAL_API_URL`, default `http://api:8000`). Web client uses relative paths.

## Folder Structure

```
gold-monitor-system/
├── docker-compose.yml
├── .env.example
├── gold_monitor_rules_fa.yaml          # 32+ rules (Persian)
├── api/
│   ├── main.py                         # FastAPI app + startup lifecycle
│   ├── config.py                       # Pydantic settings
│   ├── database.py                     # SQLAlchemy async/sync engines
│   ├── models.py                       # ORM models (10 tables)
│   ├── schemas.py                      # Pydantic schemas
│   ├── auth.py                         # JWT + bcrypt
│   ├── seed.py                         # Data seeder
│   ├── price_snapshot.py               # Shared price fetcher
│   ├── alert_classify.py               # Rule → news_type/event_category
│   ├── routers/                        # API endpoints
│   │   ├── alerts.py, sources.py, admin.py, rules.py
│   │   ├── prices.py, sentiment.py, calendar.py, health.py
│   │   ├── chat.py, chat_analytics.py
│   ├── rule_engine/                    # Deterministic matching
│   │   ├── load_rules.py, matcher.py, severity.py
│   │   ├── direction.py, alert_builder.py
│   ├── worker/                         # Background pipeline
│   │   ├── main.py, dedup.py, calendar_sync.py, price_tracker.py
│   │   └── fetchers/ (rss, html, json)
│   ├── services/chat/                  # AI chat services
│   │   ├── openrouter.py, rate_limiter.py, session_manager.py
│   │   ├── intent_classifier.py, tool_executor.py, tools.py
│   ├── prompts/chat-system.txt         # Chat system prompt template
│   ├── llm/openrouter_client.py        # Persian text generation (alerts)
│   ├── alembic/ (6 migrations)
│   └── tests/
└── web/src/
    ├── app/                            # Pages (dashboard, alert, calendar, prices, library, admin, admin/chat)
    ├── components/                     # TopBar, AlertCard, RiskGauge, SentimentChart, SeverityBadge
    │   └── ChatWidget/                 # index.tsx, ChatBubble.tsx, ChatPanel.tsx
    └── lib/                            # api.ts, auth.ts, utils.ts
```

## Fetcher Types
| Type | Class | Method |
|------|-------|--------|
| `rss` | RSSFetcher | feedparser, max 30 entries |
| `html` | HTMLFetcher | BeautifulSoup, CSS selectors via metadata |
| `json` | JSONFetcher | Configurable field mapping via metadata |

## External APIs
- **OpenRouter** — Persian text generation for alerts + AI chat assistant (requires `OPENROUTER_API_KEY`)
- **BrsAPI** — Primary price data (requires `BRSAPI_KEY`, prices in Toman)
- **TGJU** — Fallback prices (free, prices in Rial)
- **JBlanked** — Economic calendar events (primary)
- **Finnhub** — Economic calendar events (fallback)
