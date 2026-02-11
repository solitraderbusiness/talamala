# API Reference

Base URL: `http://localhost:8000`

## Public Endpoints

| Method | Path | Description | Key Params |
|--------|------|-------------|------------|
| GET | `/api/alerts` | List alerts (paginated) | severity, time_horizon, asset, q, from_date, to_date, limit, offset |
| GET | `/api/alerts/stats/today` | Today's stats + sentiment + top 3 alerts | — |
| GET | `/api/alerts/{id}` | Single alert detail | — |
| GET | `/api/prices` | Real-time gold/USD/coin prices (60s cache) | — |
| GET | `/api/sentiment` | Multi-timeframe sentiment (1h, 4h, 24h) | — |
| GET | `/api/sentiment/history` | Historical sentiment scores | timeframe, hours |
| GET | `/api/rules/library` | All rules grouped by section | — |
| GET | `/api/rules/{rule_id}` | Single rule with metadata | — |
| GET | `/api/health` | Health check (DB + Redis + rules) | — |
| GET | `/api/calendar` | Economic events | from, to, asset, impact |
| GET | `/api/calendar/upcoming` | Next high-impact events | limit, impact |
| GET | `/api/calendar/sync-status` | Calendar sync status | — |
| POST | `/api/calendar/sync` | Trigger manual calendar sync | — |

## Admin Endpoints (JWT Required)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/admin/login` | Authenticate → JWT token |
| GET | `/api/admin/me` | Current admin profile |
| GET | `/api/admin/settings` | List all key-value settings |
| PUT | `/api/admin/settings/{key}` | Create/update setting |
| GET | `/api/sources` | List all sources |
| GET | `/api/sources/{id}` | Single source |
| POST | `/api/sources` | Create source |
| PUT | `/api/sources/{id}` | Update source |
| DELETE | `/api/sources/{id}` | Delete source + cascade |
| POST | `/api/sources/{id}/fetch-now` | Trigger immediate fetch |
| GET | `/api/sources/{id}/logs` | Fetch logs (last 50) |
| GET | `/api/sources/{id}/raw-items` | Raw items (last 50) |

## Authentication
- POST `/api/admin/login` with `{email, password}` → returns `{access_token}`
- Use header: `Authorization: Bearer <token>`
- Default: `admin@goldmonitor.ir` / `admin123`

## Settings Keys
`openrouter_model`, `temperature`, `max_tokens`, `enable_llm`, `dedupe_window_hours`
