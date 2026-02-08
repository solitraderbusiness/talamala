# پایش طلا — Gold Market Monitor

سامانه هوشمند پایش و تحلیل بازار طلا برای کاربران فارسی‌زبان.

## ویژگی‌ها

- **داشبورد**: نمای کلی بازار با ۳ هشدار مهم، فید هشدارها، امتیاز ریسک، نقشه علت و معلول
- **صفحه بازار**: صفحات جداگانه برای طلای جهانی، طلای ایران، سکه، و صندوق‌های طلا
- **جزئیات هشدار**: تحلیل کامل هر هشدار با اثر بر دارایی‌ها و سطح اطمینان
- **کتابخانه قوانین**: دایره‌المعارف ۳۰+ عامل تاثیرگذار بر بازار طلا
- **فیلتر و جستجو**: فیلتر بر اساس اهمیت، افق، بازار، و واچ‌لیست
- **حالت کوتاه/حرفه‌ای**: سوئیچ بین نمای ساده و حرفه‌ای
- **حالت تاریک/روشن**: تم dark و light
- **فارسی و RTL**: طراحی کامل راست‌چین با فونت Vazirmatn

## اجرا

```bash
cd gold-monitor
npm install
npm run dev
```

سپس http://localhost:3000 را باز کنید.

## Build

```bash
npm run build
npm start
```

## ساختار پروژه

```
src/
├── app/                    # صفحات Next.js
│   ├── page.tsx            # داشبورد
│   ├── market/[marketId]/  # صفحه هر بازار
│   ├── alert/[alertId]/    # جزئیات هشدار
│   └── library/            # کتابخانه قوانین
├── components/
│   ├── layout/             # TopBar, MobileNav
│   ├── ui/                 # کامپوننت‌های قابل استفاده مجدد
│   └── dashboard/          # کامپوننت‌های داشبورد
├── context/                # State management (React Context)
├── data/                   # Mock data و قوانین
├── lib/                    # Utilities و Constants
└── types/                  # TypeScript types
```

## کامپوننت‌های اصلی

| کامپوننت | توضیح |
|---|---|
| `Card` | کارت پایه با variants |
| `SeverityBadge` | نشانگر سطح اهمیت (بحرانی/مهم/عادی) |
| `ImpactMatrix` | جدول اثر بر ۴ دارایی |
| `FilterBar` | نوار فیلتر با severity/horizon/market/search |
| `TimelineFeed` | فید هشدارها با گروه‌بندی |
| `AlertCard` | کارت هشدار با progressive disclosure |
| `RiskGauge` | نمایشگر امتیاز ریسک |
| `CauseEffect` | نقشه علت → مکانیزم → معلول |
| `ModeSwitch` | سوئیچ حالت کوتاه/حرفه‌ای |
| `Tooltip` | راهنمای اصطلاحات تخصصی |

## تکنولوژی‌ها

- **Next.js 16** (App Router)
- **React 19**
- **TypeScript**
- **Tailwind CSS v4** (RTL)
- **Vazirmatn Font** (فونت فارسی)

## داده‌ها

فعلاً از mock data استفاده می‌شود. ساختار داده‌ها دقیقاً مطابق `alert_template` فایل `gold_monitor_rules_fa.yaml` است.

برای جزئیات طراحی به [DESIGN_NOTES.md](./DESIGN_NOTES.md) مراجعه کنید.
