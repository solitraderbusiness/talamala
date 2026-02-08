# یادداشت‌های طراحی — پایش طلا

## فلسفه طراحی

### مسئله اصلی
فایل `gold_monitor_rules_fa.yaml` شامل ۳۰+ قانون پایش بازار است. نمایش همه آنها به صورت فلت، کاربر را سردرگم می‌کند. هدف UI این است که اطلاعات زیاد را بدون از دست دادن عمق، **قابل هضم** کند.

### اصول کلیدی
1. **Progressive Disclosure** — اطلاعات مرحله‌ای نمایش داده می‌شود
2. **Severity-first** — همیشه مهم‌ترین‌ها اول هستند
3. **Mobile-first + Desktop excellent** — طراحی ابتدا برای موبایل
4. **RTL-native** — کل UI از ابتدا فارسی/راست‌چین ساخته شده

---

## سیستم ضد سردرگمی (۶ مکانیزم)

### ۱. Default Filtering (فیلتر پیش‌فرض)
- **پیاده‌سازی**: `getDefaultFilters()` در `lib/utils.ts`
- پیش‌فرض فقط `high` و `medium` نمایش داده می‌شود
- کاربر باید آگاهانه `low` را فعال کند
- **فایل**: `context/AppContext.tsx` → state اولیه filters

### ۲. Smart Grouping (گروه‌بندی هوشمند)
- **پیاده‌سازی**: `groupAlertsByTopic()` در `lib/utils.ts`
- هشدارها بر اساس فیلد `group` گروه‌بندی می‌شوند
- هر گروه collapsible است
- گروه‌ها بر اساس بالاترین severity مرتب می‌شوند
- **فایل**: `components/ui/TimelineFeed.tsx`

### ۳. Progressive Disclosure (نمایش مرحله‌ای)
- **پیاده‌سازی**: `AlertCard.tsx` با state داخلی `expanded`
- کارت‌ها ابتدا فقط: تیتر + severity + impact direction نمایش می‌دهند
- با کلیک "بیشتر": خلاصه + چرا مهم + ماتریس اثر باز می‌شود
- لینک "مشاهده جزئیات" به صفحه کامل هدایت می‌کند
- **فایل‌ها**: `components/ui/AlertCard.tsx`, `app/alert/[alertId]/page.tsx`

### ۴. Explainability (توضیح‌پذیری)
- هر هشدار فیلد `why_important_fa` دارد (یک جمله فارسی)
- در کارت: بخش "چرا مهم است؟" با پس‌زمینه زرد
- در صفحه جزئیات: بخش مجزا با توضیح کامل
- **ماژول نقشه علت و معلول**: trigger → mechanism → effect
- **فایل‌ها**: `components/ui/CauseEffect.tsx`, `components/ui/AlertCard.tsx`

### ۵. Mode Switch (سوئیچ حالت)
- **حالت "کوتاه و سریع"**: فقط تیتر + جهت اثر (icon)
- **حالت "حرفه‌ای"**: جزئیات کامل + rule IDs + اطمینان + مکانیزم
- **پیاده‌سازی**: `viewMode` در `AppContext` + شرطی‌سازی در `AlertCard` و `ImpactMatrix`
- **فایل‌ها**: `components/ui/ModeSwitch.tsx`, `context/AppContext.tsx`

### ۶. Watchlist (فیلترهای ذخیره‌شده)
- واچ‌لیست‌های پیش‌فرض: "ژئوپلیتیک و دلار"، "سکه و صندوق‌ها"
- کاربر می‌تواند واچ‌لیست اضافه/حذف کند
- با کلیک روی واچ‌لیست، فیلترها اعمال می‌شود
- **فایل‌ها**: `context/AppContext.tsx` → watchlist state, `components/ui/FilterBar.tsx`

---

## نقشه Rule → UI

### چگونه ruleها به UI تبدیل شده‌اند

| Rule Field | UI Element | محل نمایش |
|---|---|---|
| `id` | Badge (Professional mode) | AlertCard, Alert Detail |
| `title` | عنوان هشدار | AlertCard, TopAlerts |
| `what_it_is` | توضیح در Library | Library Page |
| `watch_for.keywords` | تگ‌ها در Library | Library Page (expanded) |
| `watch_for.signals` | لیست "چه خبرهایی مهم" | Library Page (expanded) |
| `why_important` | بخش "چرا مهم" | AlertCard, Alert Detail |
| `importance_criteria` | معیار severity | Library Page (expanded) |
| `horizon` | HorizonBadge | AlertCard, Alert Detail |

### چگونه alert_template به UI تبدیل شده

| Alert Field | UI Element |
|---|---|
| `title` | تیتر کارت/صفحه |
| `timestamp_utc` | "X دقیقه/ساعت پیش" |
| `source_name` | متن منبع |
| `matched_rule_ids` | Badge‌ها (Professional) |
| `summary_fa` | پاراگراف خلاصه |
| `why_important_fa` | بخش زرد "چرا مهم" |
| `expected_impact` | ImpactMatrix (جدول/badge) |
| `severity` | SeverityBadge (رنگی) |
| `time_horizon` | HorizonBadge |
| `confidence` | Progress bar |
| `follow_up_questions` | لیست سوالات |

---

## ساختار صفحات

### ۱. داشبورد (Home)
- نوار قیمت‌ها (۴ بازار)
- ۳ هشدار مهم امروز (کارت‌های بزرگ)
- فید هشدارها (با فیلتر + گروه‌بندی)
- ویجت ریسک (gauge دایره‌ای)
- نقشه علت و معلول

### ۲. صفحه بازار (Market)
- هدر: قیمت + تغییرات + خلاصه روند
- ۵ هشدار مهم مربوط
- تب‌ها: اخبار | تکنیکال | فاندامنتال

### ۳. جزئیات هشدار (Alert Detail)
- تیتر + metadata
- خلاصه + چرا مهم
- ماتریس اثر (جدول)
- اطمینان + سوالات پیگیری
- قوانین تطبیق‌یافته (Professional)

### ۴. کتابخانه قوانین (Library)
- جستجو + فیلتر بخش
- قوانین گروه‌بندی شده
- هر قانون: expand → جزئیات + keywords + criteria

---

## تصمیمات فنی

- **Next.js App Router**: برای SSR/SSG آینده و routing آسان
- **Tailwind CSS v4**: با `@custom-variant dark` برای class-based dark mode
- **Vazirmatn Font**: بهترین فونت فارسی برای UI
- **React Context**: state management ساده بدون overhead کتابخانه
- **Mock Data**: دقیقاً مطابق `alert_template` از YAML
- **RTL**: `dir="rtl"` و `lang="fa"` در root HTML

---

## Glossary/Tooltip
اصطلاحات تخصصی (FOMC, CPI, PCE, DXY, ...) در صفحه جزئیات هشدار به صورت خودکار شناسایی و با tooltip فارسی نمایش داده می‌شوند.

فایل: `lib/constants.ts` → `GLOSSARY`
