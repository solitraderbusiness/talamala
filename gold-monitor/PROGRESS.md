# پیشرفت پروژه — پایش طلا (Gold Market Monitor)
# PROJECT PROGRESS TRACKER

> آخرین بروزرسانی: 2026-02-08
> شاخه توسعه: `claude/gold-market-monitor-ui-GRPNX`

---

## فهرست مطالب
1. [مشخصات کامل YAML (ورودی پروژه)](#1-مشخصات-کامل-yaml)
2. [اصول طراحی (غیرقابل مذاکره)](#2-اصول-طراحی)
3. [صفحات و IA](#3-صفحات-و-ia)
4. [سیستم ضد سردرگمی](#4-سیستم-ضد-سردرگمی)
5. [Design System](#5-design-system)
6. [پیاده‌سازی فنی](#6-پیاده‌سازی-فنی)
7. [وضعیت پیاده‌سازی — چک‌لیست جامع](#7-وضعیت-پیاده‌سازی)
8. [فایل‌ها و کامپوننت‌ها](#8-فایلها-و-کامپوننتها)
9. [مراحل بعدی (TODO)](#9-مراحل-بعدی)

---

## 1. مشخصات کامل YAML

### ساختار اصلی
```yaml
version: "1.0"
language: "fa"
purpose: "Market monitoring rules for Gold (global + Iran), Coin, and Gold Funds"
```

### Severity Levels (سطوح اهمیت)
| سطح | توضیح |
|---|---|
| `low` | خبر/داده با اثر احتمالی کم یا کوتاه‌مدت محدود |
| `medium` | خبر/داده با اثر محتمل و قابل توجه، نیازمند توجه |
| `high` | شوک یا تصمیم رسمی/غافلگیرکننده با احتمال اثر قیمتی بالا |

### Time Horizons (افق‌های زمانی)
| افق | توضیح |
|---|---|
| `immediate` | دقایق تا چند ساعت |
| `short` | چند روز تا چند هفته |
| `medium` | چند هفته تا چند ماه |
| `long` | چند ماه تا چند سال |

### Assets (دارایی‌ها)
| ID | کد | نام |
|---|---|---|
| `global_gold` | XAUUSD | طلای جهانی (اونس / XAUUSD) |
| `iran_gold` | IR_GOLD | طلای ایران (۱۸ عیار/مثقال/آبشده) |
| `coin` | IR_COIN | سکه (تمام/نیم/ربع/گرمی) |
| `gold_funds` | IR_GOLDFUNDS | صندوق‌های سرمایه‌گذاری طلا در بورس ایران (ETF طلا) |

### Alert Template (قالب خروجی هر هشدار)
```
فیلدها:
- title                   عنوان
- timestamp_utc           زمان UTC
- source_name             نام منبع
- source_url              لینک منبع
- matched_rule_ids        شناسه قوانین تطبیق‌یافته
- summary_fa              خلاصه فارسی
- why_important_fa        چرا مهم است (فارسی)
- expected_impact          اثر مورد انتظار بر دارایی‌ها
- severity                سطح اهمیت (high/medium/low)
- time_horizon            افق زمانی (immediate/short/medium/long)
- confidence              سطح اطمینان (0-100)
- follow_up_questions     سوالات پیگیری

expected_impact_format:
- asset: global_gold|iran_gold|coin|gold_funds
  direction: bullish|bearish|mixed|unclear
  mechanism: توضیح فارسی ۱-۲ جمله
```

---

### قوانین کامل (Rules) — ۳۰ قانون + ۵ سیگنال تکنیکال

#### بخش ۱: طلای جهانی (GLOBAL GOLD) — ۱۲ قانون

| # | Rule ID | عنوان | افق | وضعیت پیاده‌سازی |
|---|---|---|---|---|
| 1 | `GLOB_RATE_DECISION` | تصمیم نرخ بهره (افزایش/کاهش/تثبیت) | immediate | ✅ در rules.ts + mock alert |
| 2 | `GLOB_QE_QT` | سیاست‌های انبساطی/انقباضی (QE/QT) | short | ✅ در rules.ts |
| 3 | `GLOB_FED_COMM` | سخنرانی‌ها/بیانیه‌ها (Powell/Fed/ECB/BoE/BoJ) | immediate | ✅ در rules.ts + mock alert |
| 4 | `GLOB_US_YIELDS` | بازده اوراق خزانه‌داری آمریکا (2Y/10Y/Real Yield) | immediate | ✅ در rules.ts + mock alert |
| 5 | `GLOB_DOLLAR_DXY` | شاخص دلار (DXY) و اخبار تقویت/تضعیف دلار | immediate | ✅ در rules.ts + mock alert |
| 6 | `GLOB_US_MACRO_DATA` | داده‌های کلان آمریکا (CPI/PCE/NFP/PMI/…) | immediate | ✅ در rules.ts + mock alert |
| 7 | `GLOB_GEOPOL_RISK` | ژئوپلیتیک (جنگ/تشدید/حملات/کودتا/ترور بزرگ) | immediate | ✅ در rules.ts + mock alert |
| 8 | `GLOB_MINING_SUPPLY` | عرضه معدن (تولید/هزینه استخراج/عیار) | medium | ✅ در rules.ts |
| 9 | `GLOB_CB_GOLD_RESERVES` | خرید/فروش طلا توسط بانک‌های مرکزی | short | ✅ در rules.ts + mock alert |
| 10 | `GLOB_ASIA_PHYSICAL_DEMAND` | تقاضای فیزیکی چین/هند (فصلی/واردات/تعرفه) | short | ✅ در rules.ts + mock alert |
| 11 | `GLOB_CRYPTO_SHOCKS` | شوک‌های بزرگ بازار رمزارز (ریزش/جهش شدید) | immediate | ✅ در rules.ts + mock alert |
| 12 | `GLOB_EQUITY_RISK_OFF` | ریزش شدید بورس‌های جهانی / بحران بانکی | immediate | ✅ در rules.ts |

#### بخش ۲: طلای ایران (IRAN GOLD) — ۱۰ قانون

| # | Rule ID | عنوان | افق | وضعیت |
|---|---|---|---|---|
| 13 | `IR_FX_USD` | نرخ دلار آزاد و شکاف نرخ‌ها (آزاد/نیما/مرکز مبادله) | immediate | ✅ در rules.ts + mock alert |
| 14 | `IR_GOV_FX_POLICY` | سیاست‌های ارزی دولت و بانک مرکزی | short | ✅ در rules.ts + mock alert |
| 15 | `IR_RESERVES_SANCTIONS` | ذخایر ارزی، آزادسازی منابع، تحریم‌های ارزی | immediate | ✅ در rules.ts + mock alert |
| 16 | `IR_MACRO_INFLATION_LIQ` | تورم، نقدینگی، پایه پولی، رشد، بیکاری | medium | ✅ در rules.ts + mock alert |
| 17 | `IR_BUDGET_FISCAL` | بودجه، کسری، تامین مالی، اوراق، یارانه‌های نقدی | medium | ✅ در rules.ts |
| 18 | `IR_RATES_CREDIT` | نرخ سود بانکی، نرخ بهره رسمی، سیاست اعتباری | short | ✅ در rules.ts |
| 19 | `IR_INTERNAL_POL_SOCIAL` | ریسک داخلی (بی‌ثباتی سیاسی/اجتماعی) | immediate | ✅ در rules.ts |
| 20 | `IR_FOREIGN_POLICY` | روابط خارجی و مذاکرات (برجام/تحولات منطقه‌ای) | immediate | ✅ در rules.ts + mock alert |
| 21 | `IR_PHYSICAL_SUPPLY_DEMAND` | عرضه/تقاضای فیزیکی طلا (صنف، واردات، بازیافت، مالیات) | short | ✅ در rules.ts |
| 22 | `IR_ECON_MANAGEMENT_CHANGES` | تغییر مدیران اقتصادی (رئیس بانک مرکزی، وزیر اقتصاد) | immediate | ✅ در rules.ts |

#### بخش ۳: سکه (COIN) — ۶ قانون

| # | Rule ID | عنوان | افق | وضعیت |
|---|---|---|---|---|
| 23 | `COIN_PREMIUM_BUBBLE` | حباب سکه (اختلاف قیمت بازار با ارزش ذاتی) | short | ✅ در rules.ts + mock alert |
| 24 | `COIN_CB_AUCTIONS` | حراج/مزایده سکه و پیش‌فروش | immediate | ✅ در rules.ts + mock alert |
| 25 | `COIN_MINT_SUPPLY` | تولید و توزیع سکه (ضرابخانه/ظرفیت ضرب) | short | ✅ در rules.ts |
| 26 | `COIN_SEASONAL_DEMAND` | تقاضای فصلی سکه (نوروز/مهریه/فصل عروسی) | short | ✅ در rules.ts |
| 27 | `COIN_POLICY_TAX_TARIFF` | قوانین/تعرفه/مالیات/معافیت‌های مرتبط با طلا و سکه | medium | ✅ در rules.ts |
| 28 | `COIN_SENTIMENT_SOCIAL` | جو روانی بازار سکه (شبکه‌های اجتماعی/خبرگزاری‌ها) | immediate | ✅ در rules.ts |

#### بخش ۴: صندوق‌های طلا (GOLD FUNDS) — ۴ قانون

| # | Rule ID | عنوان | افق | وضعیت |
|---|---|---|---|---|
| 29 | `FUNDS_NAV_PREMIUM` | NAV صندوق و فاصله قیمت بازار با NAV | short | ✅ در rules.ts + mock alert |
| 30 | `FUNDS_FLOW_VOLUME` | حجم معاملات و ورود/خروج پول به صندوق‌ها | short | ✅ در rules.ts + mock alert |
| 31 | `FUNDS_CAPITAL_MARKET_NEWS` | اخبار بازار سرمایه و مشوق‌های قانونی | medium | ✅ در rules.ts |
| 32 | `FUNDS_CODAL_NOTICES` | اعلانات کدال (افزایش واحدها، تغییر ارکان، توقف) | short | ✅ در rules.ts |

#### سیگنال‌های تکنیکال — ۵ سیگنال

| # | Signal ID | نام | اهمیت | وضعیت |
|---|---|---|---|---|
| 1 | `TECH_SUPPORT_RESIST_BREAK` | شکست حمایت/مقاومت | high | ✅ در rules.ts + mock alert |
| 2 | `TECH_RSI_EXTREMES` | اشباع خرید/فروش و واگرایی RSI | medium | ✅ در rules.ts |
| 3 | `TECH_MACD_CROSS` | کراس MACD | low | ✅ در rules.ts |
| 4 | `TECH_MA_200` | عبور از میانگین متحرک ۲۰۰ | medium | ✅ در rules.ts |
| 5 | `TECH_VOLATILITY_SHOCK` | شوک نوسان | high | ✅ در rules.ts |

### رویدادهای تقویمی (Scheduled Events)
```
us_macro: CPI, Core CPI, PCE, Core PCE, PPI, NFP, GDP, PMI, ISM, Retail Sales
central_banks: FOMC meetings, ECB policy meeting, BoE policy meeting, BoJ policy meeting
```

---

## 2. اصول طراحی

| اصل | وضعیت |
|---|---|
| زبان UI فارسی، راست‌چین (RTL) | ✅ `dir="rtl"` و `lang="fa"` در layout.tsx |
| طراحی مینیمال و خوانا (Bloomberg ساده‌شده) | ✅ Tailwind CSS + فضای سفید زیاد |
| Mobile-first + Desktop عالی | ✅ responsive classes (sm/lg breakpoints) |
| Progressive disclosure | ✅ AlertCard expandable + صفحه جزئیات |
| خلاصه‌سازی و امکان "بیشتر" | ✅ کارت‌ها کوتاه + لینک جزئیات |
| دسته‌بندی و فیلترهای واضح | ✅ FilterBar + Smart Grouping |
| فونت خوانا فارسی | ✅ Vazirmatn از CDN |
| Dark mode و Light mode | ✅ class-based dark mode toggle |
| رنگ‌های معنایی (قرمز/نارنجی/خاکستری) | ✅ SEVERITY_CONFIG + DIRECTION_CONFIG |
| Tooltip برای اصطلاحات تخصصی | ✅ GLOSSARY با ۱۸ اصطلاح |

---

## 3. صفحات و IA

### صفحه ۱: داشبورد (Home / Overview)

| بخش | وضعیت | فایل | یادداشت |
|---|---|---|---|
| **A) نوار بالایی (Top Bar)** | | | |
| → Search | ✅ | FilterBar.tsx | جستجو در فید هشدارها |
| → انتخاب بازار | ✅ | FilterBar.tsx | [همه/طلای جهانی/ایران/سکه/صندوق] |
| → انتخاب بازه زمانی | ✅ | FilterBar.tsx | [امروز/24h/7d/30d] |
| → سوئیچ حالت | ✅ | ModeSwitch.tsx | [کوتاه و سریع / حرفه‌ای] |
| **B) کارت ۳ چیز مهم امروز** | | | |
| → ۳ هشدار severity=high | ✅ | TopAlerts.tsx | با رنگ‌بندی 1/2/3 |
| → تیتر کوتاه | ✅ | | |
| → چرا مهم (۱ جمله) | ✅ | | خلاصه شده |
| → اثر روی ۴ دارایی | ✅ | | icon + direction |
| → افق اثر | ✅ | | HorizonBadge |
| → دکمه مشاهده جزئیات | ✅ | | Link to /alert/[id] |
| **C) Timeline / Feed** | | | |
| → کارت‌ها با Severity/Asset/Horizon/Source | ✅ | TimelineFeed.tsx | |
| → پیش‌فرض فقط medium و high | ✅ | utils.ts | getDefaultFilters() |
| → امکان باز کردن و دیدن توضیحات | ✅ | AlertCard.tsx | Progressive disclosure |
| **D) نقشه علت و معلول** | | | |
| → محرک → مکانیزم → اثر | ✅ | CauseEffect.tsx | ۳ نمونه هاردکد شده |
| **E) ویجت امتیاز ریسک** | | | |
| → عدد 0-100 | ✅ | RiskGauge.tsx | gauge دایره‌ای |
| → محاسبه بر اساس هشدارها | ✅ | utils.ts | calculateRiskScore() |
| → توضیح کوتاه | ✅ | | "شاخص داخلی" |

### صفحه ۲: صفحه هر بازار (Market Page)

| بخش | وضعیت | فایل | یادداشت |
|---|---|---|---|
| هدر: قیمت + تغییرات + روند | ✅ | market/[marketId]/page.tsx | |
| ۵ هشدار مهم این بازار | ✅ | | فیلتر شده بر اساس asset |
| تب اخبار/هشدارها | ✅ | | AlertCard list |
| تب تکنیکال | ✅ | | سطوح حمایت/مقاومت + سیگنال‌ها |
| تب فاندامنتال | ✅ | | قوانین مرتبط با بخش |
| تب داده‌ها (اختیاری) | ⬜ نیاز به بک‌اند | | برای آینده |

### صفحه ۳: جزئیات هشدار (Alert Detail)

| بخش | وضعیت | فایل | یادداشت |
|---|---|---|---|
| عنوان + زمان + منبع | ✅ | alert/[alertId]/page.tsx | |
| خلاصه ۲ خطی | ✅ | | summary_fa |
| Why it matters | ✅ | | why_important_fa با پس‌زمینه زرد |
| اثر بر ۴ دارایی (جدول) | ✅ | ImpactMatrix.tsx | جدول + compact view |
| Confidence | ✅ | | Progress bar + توضیح |
| لینک‌های مرتبط/منابع | ✅ | | source_url |
| Tagها: matched_rule_ids | ✅ | | فقط Professional mode |
| سوالات پیگیری | ✅ | | follow_up_questions |
| Glossary tooltips | ✅ | | GlossaryText + Tooltip |

### صفحه ۴: کتابخانه قوانین (Factor Library)

| بخش | وضعیت | فایل | یادداشت |
|---|---|---|---|
| دسته‌بندی بر اساس بخش‌ها | ✅ | library/page.tsx | جهانی/ایران/سکه/صندوق |
| جستجوی سریع | ✅ | | SearchInput |
| هر Rule یک کارت | ✅ | | expandable cards |
| → چی هست؟ | ✅ | | what_it_is |
| → چه خبرهایی مهم؟ | ✅ | | watch_for.signals |
| → کلمات کلیدی | ✅ | | watch_for.keywords |
| → معیار اهمیت | ✅ | | importance_criteria |
| → Rule ID + افق | ✅ | | metadata |

---

## 4. سیستم ضد سردرگمی

| مکانیزم | وضعیت | فایل‌ها | توضیح |
|---|---|---|---|
| 1. Default filtering | ✅ | utils.ts, AppContext.tsx | فقط medium+high پیش‌فرض |
| 2. Smart grouping | ✅ | TimelineFeed.tsx, utils.ts | گروه‌بندی collapsible |
| 3. Progressive disclosure | ✅ | AlertCard.tsx | expand/collapse + صفحه جزئیات |
| 4. Explainability | ✅ | AlertCard.tsx, CauseEffect.tsx | "چرا مهم" + نقشه علت‌ومعلول |
| 5. Mode switch | ✅ | ModeSwitch.tsx, AppContext.tsx | کوتاه/حرفه‌ای |
| 6. Saved filters / Watchlist | ✅ | AppContext.tsx, FilterBar.tsx | ۲ واچ‌لیست پیش‌فرض |

---

## 5. Design System

| آیتم | وضعیت | فایل | جزئیات |
|---|---|---|---|
| فونت فارسی (Vazirmatn) | ✅ | globals.css | CDN + 4 weights |
| رنگ high: قرمز | ✅ | constants.ts | `text-red-600` / `bg-red-50` |
| رنگ medium: نارنجی | ✅ | constants.ts | `text-amber-600` / `bg-amber-50` |
| رنگ low: خاکستری | ✅ | constants.ts | `text-gray-500` / `bg-gray-50` |
| Bullish: سبز | ✅ | constants.ts | `text-emerald-600` |
| Bearish: قرمز | ✅ | constants.ts | `text-red-600` |
| Dark mode | ✅ | globals.css | class-based via `@custom-variant` |
| Light mode | ✅ | globals.css | پیش‌فرض |
| فاصله‌گذاری و کارت‌های واضح | ✅ | Card.tsx | rounded-xl + border + padding |
| Scrollbar سفارشی | ✅ | globals.css | webkit-scrollbar |
| Selection color | ✅ | globals.css | amber/gold |

---

## 6. پیاده‌سازی فنی

| آیتم | وضعیت | جزئیات |
|---|---|---|
| Next.js + Tailwind (RTL) | ✅ | Next.js 16 + Tailwind v4 |
| Data model برای Alerts | ✅ | types/index.ts → Alert interface |
| صفحات کامل | ✅ | ۴ صفحه + layout |
| State management ساده | ✅ | React Context (AppContext) |
| Mock data (فرمت alert_template) | ✅ | ۱۸ هشدار نمونه در mock-alerts.ts |
| TypeScript types | ✅ | types/index.ts |
| Build موفق | ✅ | `npm run build` بدون خطا |

---

## 7. وضعیت پیاده‌سازی — چک‌لیست جامع

### Deliverables خواسته‌شده

| # | Deliverable | وضعیت | یادداشت |
|---|---|---|---|
| 1 | Repo با ساختار استاندارد | ✅ | Next.js App Router + src dir |
| 2 | Card component | ✅ | `components/ui/Card.tsx` |
| 3 | FilterBar component | ✅ | `components/ui/FilterBar.tsx` |
| 4 | SeverityBadge component | ✅ | `components/ui/SeverityBadge.tsx` |
| 5 | ImpactMatrix component | ✅ | `components/ui/ImpactMatrix.tsx` |
| 6 | TimelineFeed component | ✅ | `components/ui/TimelineFeed.tsx` |
| 7 | README کامل | ✅ | `README.md` |
| 8 | DESIGN_NOTES.md | ✅ | `DESIGN_NOTES.md` |

### Mock Alerts (18 عدد)
| Alert ID | عنوان | Severity | Rule IDs | وضعیت |
|---|---|---|---|---|
| alert-001 | فدرال رزرو نرخ بهره را ۰.۲۵٪ کاهش داد | high | GLOB_RATE_DECISION | ✅ |
| alert-002 | تشدید تنش‌ها در خاورمیانه | high | GLOB_GEOPOL_RISK | ✅ |
| alert-003 | جهش ناگهانی دلار آزاد به بالای ۸۰,۰۰۰ | high | IR_FX_USD | ✅ |
| alert-004 | CPI آمریکا بالاتر از انتظار: ۳.۴٪ | medium | GLOB_US_MACRO_DATA | ✅ |
| alert-005 | بانک مرکزی چین خرید طلا را از سر گرفت | high | GLOB_CB_GOLD_RESERVES | ✅ |
| alert-006 | حباب سکه امامی به ۲۵ درصد رسید | high | COIN_PREMIUM_BUBBLE | ✅ |
| alert-007 | پاول: کاهش‌های بیشتر ممکن | medium | GLOB_FED_COMM | ✅ |
| alert-008 | ورود پول رکوردی به صندوق‌های طلا | medium | FUNDS_FLOW_VOLUME | ✅ |
| alert-009 | شکاف نرخ ارز آزاد و نیما | medium | IR_FX_USD, IR_GOV_FX_POLICY | ✅ |
| alert-010 | بازده اوراق ۱۰ ساله آمریکا سقوط کرد | medium | GLOB_US_YIELDS | ✅ |
| alert-011 | اعلام حراج سکه از سوی مرکز مبادله | medium | COIN_CB_AUCTIONS | ✅ |
| alert-012 | شاخص DXY به زیر ۱۰۰ سقوط کرد | medium | GLOB_DOLLAR_DXY | ✅ |
| alert-013 | پیشرفت در مذاکرات هسته‌ای | high | IR_FOREIGN_POLICY, IR_RESERVES_SANCTIONS | ✅ |
| alert-014 | رشد ۲.۵ درصدی نقدینگی | medium | IR_MACRO_INFLATION_LIQ | ✅ |
| alert-015 | ریزش ۵ درصدی بیت‌کوین | low | GLOB_CRYPTO_SHOCKS | ✅ |
| alert-016 | شکست مقاومت ۲,۷۰۰ دلاری اونس | medium | TECH_SUPPORT_RESIST_BREAK | ✅ |
| alert-017 | افزایش تقاضای طلای هند | low | GLOB_ASIA_PHYSICAL_DEMAND | ✅ |
| alert-018 | فاصله قیمت صندوق زر با NAV | medium | FUNDS_NAV_PREMIUM | ✅ |

### Glossary Terms (18 اصطلاح)
FOMC, CPI, PCE, PPI, NFP, PMI, ISM, DXY, QE, QT, VIX, NAV, ETF, TIPS, GDP, RSI, MACD, MA200

---

## 8. فایل‌ها و کامپوننت‌ها

### ساختار فایل‌ها
```
gold-monitor/
├── README.md
├── DESIGN_NOTES.md
├── PROGRESS.md                          ← این فایل
├── gold_monitor_rules_fa.yaml
├── package.json
├── tsconfig.json
├── next.config.ts
├── postcss.config.mjs
├── eslint.config.mjs
└── src/
    ├── app/
    │   ├── globals.css                  ← استایل‌ها + فونت + dark mode
    │   ├── layout.tsx                   ← Root layout (RTL + AppProvider)
    │   ├── page.tsx                     ← داشبورد اصلی
    │   ├── market/[marketId]/page.tsx   ← صفحه هر بازار
    │   ├── alert/[alertId]/page.tsx     ← جزئیات هشدار
    │   └── library/page.tsx             ← کتابخانه قوانین
    ├── components/
    │   ├── layout/
    │   │   ├── TopBar.tsx               ← نوار بالایی + nav + theme toggle
    │   │   └── MobileNav.tsx            ← منوی موبایل (sidebar)
    │   ├── ui/
    │   │   ├── Card.tsx                 ← کارت پایه
    │   │   ├── AlertCard.tsx            ← کارت هشدار (progressive disclosure)
    │   │   ├── SeverityBadge.tsx        ← نشانگر اهمیت
    │   │   ├── HorizonBadge.tsx         ← نشانگر افق زمانی
    │   │   ├── DirectionIndicator.tsx   ← نشانگر جهت (صعودی/نزولی)
    │   │   ├── ImpactMatrix.tsx         ← ماتریس اثر بر دارایی‌ها
    │   │   ├── FilterBar.tsx            ← نوار فیلتر کامل
    │   │   ├── SearchInput.tsx          ← ورودی جستجو
    │   │   ├── TimelineFeed.tsx         ← فید هشدارها (گروه‌بندی)
    │   │   ├── RiskGauge.tsx            ← نمایشگر ریسک (gauge)
    │   │   ├── CauseEffect.tsx          ← نقشه علت و معلول
    │   │   ├── ModeSwitch.tsx           ← سوئیچ حالت نمایش
    │   │   └── Tooltip.tsx              ← راهنمای اصطلاحات
    │   └── dashboard/
    │       ├── TopAlerts.tsx             ← ۳ هشدار مهم
    │       └── MarketOverview.tsx        ← نوار قیمت‌ها
    ├── context/
    │   └── AppContext.tsx                ← State management مرکزی
    ├── data/
    │   ├── mock-alerts.ts               ← ۱۸ هشدار نمونه
    │   ├── mock-markets.ts              ← ۴ بازار نمونه
    │   └── rules.ts                     ← ۳۲ قانون + ۵ سیگنال تکنیکال
    ├── lib/
    │   ├── constants.ts                 ← تنظیمات ثابت + glossary
    │   └── utils.ts                     ← توابع کمکی
    └── types/
        └── index.ts                     ← TypeScript types
```

---

## 9. مراحل بعدی (TODO)

### فوری — بهبود UI فعلی
- [ ] بهبود responsive design برای تبلت
- [ ] اضافه کردن انیمیشن‌های ساده (transition/fade)
- [ ] بهبود empty states (حالت‌های بدون داده)
- [ ] اضافه کردن loading states / skeletons
- [ ] بهبود accessibility (ARIA labels, keyboard navigation)

### کوتاه‌مدت — قابلیت‌های جدید
- [ ] صفحه تقویم رویدادها (Scheduled Events از YAML)
- [ ] تب "داده‌ها" در صفحه بازار (نمودار قیمت placeholder)
- [ ] امکان ایجاد/ویرایش watchlist سفارشی توسط کاربر
- [ ] ذخیره تنظیمات کاربر در localStorage
- [ ] Push notification / Desktop notification برای هشدارهای high

### میان‌مدت — اتصال به بک‌اند
- [ ] طراحی API endpoints (GET /alerts, GET /markets, GET /rules)
- [ ] جایگزینی mock data با fetch از API
- [ ] Real-time updates (WebSocket یا SSE)
- [ ] نمودار قیمت واقعی (chart library)
- [ ] سیستم احراز هویت

### بلندمدت — توسعه محصول
- [ ] نسخه PWA (قابل نصب روی موبایل)
- [ ] سیستم اعلان تلگرام / ایمیل
- [ ] داشبورد تحلیلی (آمار هشدارها در طول زمان)
- [ ] سیستم امتیازدهی به هشدارها توسط کاربران
- [ ] API برای توسعه‌دهندگان خارجی
- [ ] تست‌های E2E و unit tests
- [ ] CI/CD pipeline

---

## تاریخچه تغییرات

| تاریخ | شرح | کامیت |
|---|---|---|
| 2026-02-08 | ایجاد پروژه کامل — تمام ۴ صفحه + ۱۷ کامپوننت + mock data + مستندات | `c08b370` |
