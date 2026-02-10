# Talamala (طلاملا) — Implementation Progress

> Safe checkpoint tags:
> - `safe-checkpoint-2026-02-09` — Before formula rewrite
> - `safe-checkpoint-before-formula-rewrite-2026-02-10` — Just before 7-fix rewrite
> To restore: `git checkout <tag-name>`

---

## Phase 1 — Fix What's Broken (اول درست کن)

These are features that already exist in the design/prototype but are broken or dropped in the production system. No new architecture needed.

| # | Feature | Description | Status | Notes |
|---|---------|-------------|--------|-------|
| 1 | **Fix News Source Reliability** | Get stable Persian + English gold news feeds that don't break. This is the heart of the system — everything depends on it. | ✅ Done | Comprehensive formula rewrite (7 fixes): direction detection, severity classification, dedup fingerprinting, per-alert scoring, sentiment formula, confidence blending, MIN_MATCH_SCORE 0.18→0.15. Added news type classification (Fix #8) + background context detection (Fix #9). 162 tests passing. |
| 2 | **Impact Matrix per Alert** | Each alert should show its effect on all 4 assets (global gold, iran gold, coin, gold funds). Data exists in YAML `impact_hypothesis`, just not displayed. | ⬜ Not Started | Was fully built in `gold-monitor/` prototype as `ImpactMatrix.tsx`. Dropped in `gold-monitor-system/`. |
| 3 | **Glossary Tooltips** | Restore the 18-term glossary (FOMC, CPI, QE, NAV, ETF, RSI, etc.) with hover tooltips so users understand financial terms. | ⬜ Not Started | Was in prototype as `Tooltip.tsx` + `GlossaryText`. 18 terms defined in `constants.ts`. |
| 4 | **Cause-Effect Maps** | Restore visual diagrams: محرک→مکانیزم→اثر (Driver→Mechanism→Effect). Shows users WHY an event matters for gold. | ⬜ Not Started | Was in prototype as `CauseEffect.tsx`. 3 hardcoded examples existed. |
| 5 | **Mode Switch (کوتاه/حرفه‌ای)** | Toggle between beginner and professional view. Beginners get simpler cards, professionals see rule IDs, confidence, match evidence. | ⬜ Not Started | Was in prototype as `ModeSwitch.tsx` + `AppContext.tsx`. |
| 6 | **Event Calendar Page** | Show upcoming scheduled macro events (FOMC, CPI, NFP, ECB, etc.). Data from JBlanked/Finnhub APIs. | ✅ Done | Full economic calendar with event-asset mapping, gold impact notes, Persian translations (~120 events), countdown timer, asset/impact filters, list/week views, dashboard widget. APIs: JBlanked (primary) + Finnhub (fallback). Auto-sync every 6h. |

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
| 19 | **CLAUDE.md + README** | Proper project documentation on main branch. | ✅ Done | CLAUDE.md (comprehensive, 800+ lines), SYSTEM_LOGIC.md (all formulas), PROGRESS.md (status tracker). On feature branch `claude/review-project-direction-EsijC`. |
| 20 | **PWA Support** | Installable on mobile as Progressive Web App. | ⬜ Not Started | |

---

## Asset Coverage Summary

| Asset | Price Data | Alerts | Dedicated Page | Special Features | Overall |
|-------|-----------|--------|---------------|-----------------|---------|
| طلای جهانی (XAUUSD) | ✅ BrsAPI/TGJU | ✅ Working (direction + severity + news type) | ⬜ No | ⬜ No technical signals | ✅ Good |
| طلای ایران (18k) | ✅ BrsAPI/TGJU | ✅ Working | ⬜ No | — | ✅ Good |
| دلار (USD/USDT) | ✅ BrsAPI/TGJU | ✅ Working | ⬜ No | — | ✅ Good |
| سکه امامی | ✅ BrsAPI/TGJU | ✅ Working | ⬜ No | ⬜ No حباب calc | ⚠️ Partial |
| صندوق‌های طلا | ❌ None | ❌ None | ⬜ No | ⬜ No NAV/premium | ❌ Missing |

---

## Changelog

| Date | What Changed |
|------|-------------|
| 2026-02-10 | **Documentation update**: CLAUDE.md, SYSTEM_LOGIC.md, PROGRESS.md fully updated to reflect all recent changes. |
| 2026-02-10 | **Fix #9 — Background Context Detection**: Added 4th news type `background_context`. Anniversaries, editorials, status-quo commentary no longer trigger high severity or affect sentiment gauge. Smart override when genuinely new events present. 162 tests passing. |
| 2026-02-10 | **Fix #8 — News Type Classification**: Created `news_type.py` with 3 types (price_report/causal_event/mixed). Price reports forced to score=50, severity=low, excluded from sentiment gauge. Frontend muted styling for non-causal alerts. |
| 2026-02-10 | **7-Fix Formula Rewrite**: Comprehensive rewrite of scoring pipeline. (1) 3-stage direction detection, (2) Event-type severity with "critical" level, (3) Semantic event fingerprinting, (4) Per-alert score formula, (5) Sentiment: neutral=0, directional ratio dampening, (6) Confidence blending, (7) MIN_MATCH_SCORE raised to 0.15. Tagged `safe-checkpoint-before-formula-rewrite-2026-02-10`. |
| 2026-02-10 | **Economic Event Calendar**: Full implementation — new model (`EconomicEvent`), calendar sync worker (JBlanked + Finnhub APIs, 6h interval), `/api/calendar` endpoint with asset/impact filtering, `/calendar` frontend page with list/week views, countdown timer, event-asset mapping with gold impact notes, ~120 Persian translations, dashboard upcoming events widget, navigation updated. |
| 2026-02-09 | Created this progress tracker. Tagged `safe-checkpoint-2026-02-09`. |
