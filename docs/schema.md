# Database Schema

PostgreSQL 16, 14 tables, all UUID PKs, UTC timestamps.

## Tables

### sources
News data sources for worker to fetch.
- `id` UUID PK, `name` VARCHAR(255), `type` VARCHAR(20) [rss/html/json_api/...], `base_url` VARCHAR(2048)
- `endpoints` JSONB, `method` VARCHAR(10), `headers` JSONB, `auth_config` JSONB, `parser` VARCHAR(255)
- `enabled` BOOLEAN, `poll_interval_seconds` INTEGER (default 60)
- `categories` JSONB, `rule_bindings` JSONB, `reliability_score` FLOAT
- `last_fetched_at`, `last_success_at` TIMESTAMPTZ, `last_error` TEXT

### raw_items
Fetched news items, deduplicated by content hash.
- `id` UUID PK, `source_id` UUID FK→sources (CASCADE)
- `title` VARCHAR(1024), `url` VARCHAR(2048), `published_at`, `fetched_at` TIMESTAMPTZ
- `content_text` TEXT, `content_hash` VARCHAR(64) (indexed), `metadata` JSONB

### alerts
Generated alerts with severity, impact, and Persian text.
- `id` UUID PK, `title` VARCHAR(1024), `timestamp_utc` TIMESTAMPTZ
- `source_name` VARCHAR(255), `source_url` VARCHAR(2048)
- `matched_rule_ids` JSONB, `summary_fa` TEXT, `why_important_fa` TEXT
- `expected_impact` JSONB [{asset, direction, mechanism}]
- `severity` VARCHAR(10) [critical/high/medium/low], `time_horizon` VARCHAR(20), `confidence` FLOAT
- `follow_up_questions` JSONB, `dedupe_key` VARCHAR(255) UNIQUE
- `raw_item_id` UUID FK→raw_items (SET NULL), `match_evidence` JSONB
- `price_xauusd_at_alert`, `price_usdirr_at_alert`, `price_coin_at_alert`, `price_18k_at_alert` FLOAT (nullable)
- `news_type` VARCHAR(50) [price_report/causal_event/mixed/commentary]
- `event_category` VARCHAR(50) [fed_policy/geopolitics/iran_forex/...]

### fetch_logs
- `id` UUID PK, `source_id` UUID FK→sources (CASCADE)
- `started_at`, `finished_at` TIMESTAMPTZ, `status` VARCHAR(20), `items_fetched_count` INT, `error_message` TEXT, `duration_ms` INT

### settings
- `key` VARCHAR(255) PK, `value` JSONB, `updated_at` TIMESTAMPTZ

### admin_users
- `id` UUID PK, `email` VARCHAR(320) UNIQUE, `password_hash` VARCHAR(255), `role` VARCHAR(50)

### rules_snapshot
- `id` UUID PK, `version` VARCHAR(100) (SHA-256 prefix), `yaml_content` TEXT, `loaded_at` TIMESTAMPTZ

### sentiment_scores
- `id` UUID PK, `timeframe` VARCHAR(10), `score` INT (0-100), `sentiment` VARCHAR(20), `sentiment_label` VARCHAR(50)
- `alert_count` INT, `created_at` TIMESTAMPTZ. Indexed on (timeframe, created_at)

### economic_events
- `id` UUID PK, `event_name` VARCHAR(512), `event_name_fa` VARCHAR(512)
- `country` VARCHAR(10), `currency` VARCHAR(10), `category` VARCHAR(50)
- `datetime_utc` TIMESTAMPTZ, `impact` VARCHAR(10), `actual`/`forecast`/`previous` VARCHAR(100)
- `source` VARCHAR(50), `affected_assets` JSONB. Unique on (event_name, datetime_utc)

### alert_price_outcomes
- `id` UUID PK, `alert_id` UUID FK→alerts (CASCADE), `check_interval` VARCHAR(10)
- `checked_at` TIMESTAMPTZ, prices + change_pct for xauusd/usdirr/coin/18k (all FLOAT nullable)
- `direction_correct` BOOLEAN (nullable). Unique on (alert_id, check_interval)

### chat_sessions
AI chat conversation sessions.
- `id` UUID PK, `ip_address` VARCHAR(45)
- `messages_count` INTEGER (default 0), `first_message` TEXT (nullable)
- `primary_intent` VARCHAR(50) (nullable), `had_answer_rate` FLOAT (nullable)
- `created_at`, `last_active_at` TIMESTAMPTZ
- Indexes on `created_at`, `last_active_at`

### chat_messages
Individual messages within chat sessions.
- `id` UUID PK, `session_id` UUID FK→chat_sessions (CASCADE)
- `role` VARCHAR(20) [user/assistant], `content` TEXT
- `tool_calls` JSONB (nullable), `tokens_used` INTEGER (nullable)
- `created_at` TIMESTAMPTZ
- Indexes on `session_id`, `created_at`

### chat_analytics
Per-assistant-message analytics extracted from LLM `<chat_meta>` tags.
- `id` UUID PK, `session_id` UUID FK→chat_sessions (CASCADE), `message_id` UUID FK→chat_messages (SET NULL)
- `intent` VARCHAR(50) [news_search/calendar_query/price_check/sentiment_query/comparison/prediction/how_to_use/off_topic/feature_not_available]
- `topics` JSONB (array), `assets_mentioned` JSONB (array)
- `had_answer` BOOLEAN, `missing_feature` TEXT (nullable)
- `suggested_followups` JSONB (array), `created_at` TIMESTAMPTZ

### chat_settings
Key-value configuration for chat widget.
- `key` VARCHAR(255) PK, `value` TEXT (nullable), `updated_at` TIMESTAMPTZ
- Keys: `enabled`, `model`, `rate_limit_ip`, `rate_limit_global`, `welcome_message`, `system_prompt`

## Relationships
- sources → raw_items (1:N, CASCADE)
- sources → fetch_logs (1:N, CASCADE)
- raw_items → alerts (1:1 optional, SET NULL)
- alerts → alert_price_outcomes (1:N, CASCADE)
- chat_sessions → chat_messages (1:N, CASCADE)
- chat_sessions → chat_analytics (1:N, CASCADE)
- chat_messages → chat_analytics (1:1 optional, SET NULL)

## Migrations
- 001: Initial schema (7 tables + seeds)
- 002: Economic events table
- 003: Price tracking columns + outcomes table
- 005: Chat tables (chat_sessions, chat_messages, chat_settings)
- 006: Chat analytics table + session analytics columns
