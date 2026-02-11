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

## Chat Endpoints (Public)

| Method | Path | Description | Key Params |
|--------|------|-------------|------------|
| POST | `/api/chat` | Send message, returns SSE stream | messages (array of {role, content}), session_id |
| GET | `/api/chat/status` | Check if chat is enabled + welcome message | — |
| GET | `/api/chat/history` | Get messages for a session | session_id |

### SSE Stream Events (POST /api/chat response)
- `{"type": "status", "content": "thinking|searching|generating"}` — Progress updates
- `{"type": "content", "content": "..."}` — Streamed response text
- `{"type": "suggestions", "content": ["...", "..."]}` — Follow-up suggestion chips
- `{"type": "done", "session_id": "..."}` — End of response
- `{"type": "error", "content": "..."}` — Error message

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

### Chat Admin Endpoints (JWT Required)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/admin/chat/dashboard` | Overview cards (messages today/week/month) |
| GET | `/api/admin/chat/overview` | Trend comparison with previous period |
| GET | `/api/admin/chat/insights/intents` | Intent distribution (pie chart data) |
| GET | `/api/admin/chat/insights/topics` | Top topics (bar chart data) |
| GET | `/api/admin/chat/insights/assets` | Asset mention distribution |
| GET | `/api/admin/chat/insights/feature-gaps` | Missing features users asked for |
| GET | `/api/admin/chat/insights/usage-hours` | Usage heatmap (hourly x day-of-week) |
| GET | `/api/admin/chat/insights/session-depth` | Session depth histogram |
| GET | `/api/admin/chat/conversations` | Paginated conversation list (filter: intent, had_answer) |
| GET | `/api/admin/chat/conversations/{session_id}` | Full conversation detail + analytics |
| GET | `/api/admin/chat/popular-questions` | Most common first user questions |
| GET | `/api/admin/chat/export` | CSV export (type: messages/analytics/sessions, from, to) |
| GET | `/api/admin/chat/settings` | Get chat configuration |
| PUT | `/api/admin/chat/settings` | Update chat configuration |

## Authentication
- POST `/api/admin/login` with `{email, password}` → returns `{access_token}`
- Use header: `Authorization: Bearer <token>`
- Default: `admin@goldmonitor.ir` / `admin123`

## Settings Keys
`openrouter_model`, `temperature`, `max_tokens`, `enable_llm`, `dedupe_window_hours`

## Chat Settings Keys
`enabled`, `model`, `rate_limit_ip`, `rate_limit_global`, `welcome_message`, `system_prompt`
