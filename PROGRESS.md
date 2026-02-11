# Talamala (طلاملا) — Implementation Progress

> Safe checkpoint tag: `safe-checkpoint-2026-02-09`
> To restore: `git checkout safe-checkpoint-2026-02-09`

---

## Phase 1 — Fix What's Broken (اول درست کن)

These are features that already exist in the design/prototype but are broken or dropped in the production system. No new architecture needed.

| # | Feature | Description | Status | Notes |
|---|---------|-------------|--------|-------|
| 1 | **Fix News Source Reliability** | Get stable Persian + English gold news feeds that don't break. This is the heart of the system — everything depends on it. | 🔄 In Progress | Lowered MIN_MATCH_SCORE 0.18→0.10 for English content. Added negative keywords to prevent false positives (gold medal, etc). Added LLM relevance filter for borderline matches. Bumped dedup flush to reprocess items. |
| 2 | **Impact Matrix per Alert** | Each alert should show its effect on all 4 assets (global gold, iran gold, coin, gold funds). Data exists in YAML `impact_hypothesis`, just not displayed. | ⬜ Not Started | Was fully built in `gold-monitor/` prototype as `ImpactMatrix.tsx`. Dropped in `gold-monitor-system/`. |
| 3 | **Glossary Tooltips** | Restore the 18-term glossary (FOMC, CPI, QE, NAV, ETF, RSI, etc.) with hover tooltips so users understand financial terms. | ⬜ Not Started | Was in prototype as `Tooltip.tsx` + `GlossaryText`. 18 terms defined in `constants.ts`. |
| 4 | **Cause-Effect Maps** | Restore visual diagrams: محرک→مکانیزم→اثر (Driver→Mechanism→Effect). Shows users WHY an event matters for gold. | ⬜ Not Started | Was in prototype as `CauseEffect.tsx`. 3 hardcoded examples existed. |
| 5 | **Mode Switch (کوتاه/حرفه‌ای)** | Toggle between beginner and professional view. Beginners get simpler cards, professionals see rule IDs, confidence, match evidence. | ⬜ Not Started | Was in prototype as `ModeSwitch.tsx` + `AppContext.tsx`. |
| 6 | **Event Calendar Page** | Show upcoming scheduled macro events (FOMC, CPI, NFP, ECB, etc.). Data from JBlanked/Finnhub APIs. | ✅ Done | Full economic calendar with event-asset mapping, gold impact notes, Persian translations (~120 events), countdown timer, asset/impact filters, list/week views, dashboard widget. APIs: JBlanked (primary) + Finnhub (fallback). Auto-sync every 6h. |

---

## Phase 1.5 — Data Collection for Analytics (جمع‌آوری داده)

Collecting data now for future monetizable features. Every day without this is lost data.

| # | Feature | Description | Status | Notes |
|---|---------|-------------|--------|-------|
| A | **Price Snapshot at Alert Time** | Stamp 4 market prices (XAUUSD, USD/IRR, Emami coin, 18K gold) on every new alert at creation time. | ✅ Done | `price_snapshot.py` shared module. Worker stamps prices once per cycle. Tries Redis cache → BrsAPI → TGJU fallback. Migration 003. |
| B | **Alert Classification** | Auto-assign `news_type` (price_report/causal_event/mixed/commentary) and `event_category` (fed_policy/geopolitics/iran_forex/etc.) from matched rule IDs. | ✅ Done | `alert_classify.py` maps 30+ rule IDs. Worker stamps on every new alert. Migration 003. |
| C | **Price Outcome Tracking** | Background job checks prices 1h/4h/24h after each alert to verify directional accuracy. | ✅ Done | `price_tracker.py` runs every 15min in API process. `alert_price_outcomes` table with unique constraint on (alert_id, check_interval). Tolerance windows: 1h±15min, 4h±30min, 24h±60min. |
| D | **User Interaction Tracking** | Track clicks, bookmarks, shares on alerts for recommendation engine. | ⬜ Not Started | `user_alert_interactions` table needed. Lower priority — can be added later. |

---

## Phase 2 — Complete the Core (تکمیل هسته)

Features that need some new code but complete the existing product.

| # | Feature | Description | Status | Notes |
|---|---------|-------------|--------|-------|
| 7 | **Per-Market Pages** | Bring back `/market/[marketId]` for each of the 4 assets. Price header, top alerts, tabs for news/technical/fundamental. | ⬜ Not Started | Was fully built in `gold-monitor/` prototype. Dropped in production. |
| 8 | **Coin — Bubble (حباب) Calculation** | Compute سکه intrinsic value vs market price to show حباب percentage. Formula: `حباب = (قیمت بازار - ارزش ذاتی) / ارزش ذاتی × 100`. | ⬜ Not Started | Price data exists (emami_coin from TGJU/BrsAPI). Need intrinsic value formula: `ارزش ذاتی = (وزن طلا × قیمت طلای ۱۸ عیار) + حق ضرب`. |
| 9 | **Coin — Auction (حراج) Tracking** | Monitor and alert on central bank coin auction announcements (بانک کارگشایی, مرکز مبادله). | ⬜ Not Started | Rule `COIN_CB_AUCTIONS` exists in YAML but no data source feeds it. |
| 10 | **Watchlist / Saved Filters** | Let users save custom filter presets and asset watchlists. | ⬜ Not Started | Was in prototype `AppContext.tsx` with 2 default watchlists. |

---

## Phase 3 — Gold Funds (صندوق‌های طلا)

Entirely new vertical. Needs new data sources, new APIs, new UI.

| # | Feature | Description | Status | Notes |
|---|---------|-------------|--------|-------|
| 11 | **Gold Funds — Data Pipeline** | Integrate TSETMC/Codal APIs for real fund data (NAV, price, volume, premium/discount). | ⬜ Not Started | TSETMC source exists in seed but is **disabled** with note "غیرفعال تا تنظیم endpoint". |
| 12 | **Gold Funds — Dashboard Price Card** | Add gold fund prices to the dashboard alongside the existing 4 cards. | ⬜ Not Started | Dashboard only shows: طلای جهانی, طلای ۱۸ عیار, دلار, سکه امامی. No fund prices. |
| 13 | **Gold Funds — Enable FUNDS_* Rules** | Wire up the 4 gold fund alert rules (NAV_PREMIUM, FLOW_VOLUME, CAPITAL_MARKET_NEWS, CODAL_NOTICES) to real data. | ⬜ Not Started | Rules defined in YAML but can never trigger — no data flows into them. |
| 14 | **Codal Integration** | Connect to Codal for gold fund announcements: unit creation/redemption, symbol halt/resume, prospectus changes. | ⬜ Not Started | No Codal connector exists at all. |

---

## Phase 4 — Polish & Growth (توسعه)

Nice-to-have features for future development.

| # | Feature | Description | Status | Notes |
|---|---------|-------------|--------|-------|
| 15 | **Technical Analysis — Basic** | Price history storage + basic indicators (support/resistance, volatility shock). | ⬜ Not Started | 5 technical signals defined in YAML but zero implementation. |
| 16 | **Technical Analysis — Full** | RSI, MACD, MA200 computation and alerts. | ⬜ Not Started | Depends on #15. |
| 17 | **Push/Desktop Notifications** | Browser notifications for high-severity alerts. | ⬜ Not Started | |
| 18 | **Telegram/Email Alerts** | External notification channels. | ⬜ Not Started | |
| 19 | **CLAUDE.md + README** | Proper project documentation on main branch. | ✅ Done | CLAUDE.md, PROGRESS.md, SYSTEM_LOGIC.md, README all updated. |
| 20 | **PWA Support** | Installable on mobile as Progressive Web App. | ⬜ Not Started | |

---

## Asset Coverage Summary

| Asset | Price Data | Alerts | Price Tracking | Dedicated Page | Special Features | Overall |
|-------|-----------|--------|---------------|---------------|-----------------|---------|
| طلای جهانی (XAUUSD) | ✅ BrsAPI/TGJU | ⚠️ Unreliable feeds | ✅ Stamped + outcomes | ⬜ No | ⬜ No technical signals | ⚠️ Partial |
| طلای ایران (18k) | ✅ BrsAPI/TGJU | ⚠️ Unreliable feeds | ✅ Stamped + outcomes | ⬜ No | — | ⚠️ Partial |
| دلار (USD/USDT) | ✅ BrsAPI/TGJU | ⚠️ Unreliable feeds | ✅ Stamped + outcomes | ⬜ No | — | ⚠️ Partial |
| سکه امامی | ✅ BrsAPI/TGJU | ⚠️ Unreliable feeds | ✅ Stamped + outcomes | ⬜ No | ⬜ No حباب calc | ⚠️ Partial |
| صندوق‌های طلا | ❌ None | ❌ None | ❌ None | ⬜ No | ⬜ No NAV/premium | ❌ Missing |

---

## Database Tables (10 total)

| Table | Migration | Purpose |
|-------|-----------|---------|
| `sources` | 001 | Configurable news data sources |
| `raw_items` | 001 | Fetched news items (deduped by SHA-256) |
| `alerts` | 001 + 003 | Generated alerts with prices, classification |
| `fetch_logs` | 001 | Per-source fetch history |
| `settings` | 001 | Key-value config store |
| `admin_users` | 001 | Admin credentials (bcrypt) |
| `rules_snapshot` | 001 | YAML version tracking |
| `sentiment_scores` | lifespan | Historical sentiment scores |
| `economic_events` | 002 | Cached calendar events (JBlanked/Finnhub) |
| `alert_price_outcomes` | 003 | Price changes 1h/4h/24h after alerts |

---

## Changelog

| Date | What Changed |
|------|-------------|
| 2026-02-11 | **Price Tracking & Alert Classification**: 4 price columns on alerts (stamped at creation), `news_type` + `event_category` classification (30+ rule mappings), `alert_price_outcomes` table with 1h/4h/24h tracking, background price tracker job (15min loop), `price_snapshot.py` shared module, `alert_classify.py`, migration 003. Dashboard UI/UX improvements (events widget, price card, alert counts). |
| 2026-02-10 | **Economic Event Calendar**: Full implementation — new model (`EconomicEvent`), calendar sync worker (JBlanked + Finnhub APIs, 6h interval), `/api/calendar` endpoint with asset/impact filtering, `/calendar` frontend page with list/week views, countdown timer, event-asset mapping with gold impact notes, ~120 Persian translations, dashboard upcoming events widget, navigation updated. |
| 2026-02-09 | Created this progress tracker. Tagged `safe-checkpoint-2026-02-09`. |
