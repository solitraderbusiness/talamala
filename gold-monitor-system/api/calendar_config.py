"""
Static configuration for the Economic Event Calendar feature.

Contains:
- Persian translations for common economic events
- Event-to-asset impact mappings
- Gold impact notes (how events affect assets)
- Currency-to-asset fallback mapping
"""

from __future__ import annotations

# ── Persian Translations for Economic Events ──────────────────────────

EVENT_TRANSLATIONS: dict[str, str] = {
    # US Employment
    "Non-Farm Payrolls": "اشتغال غیرکشاورزی",
    "Nonfarm Payrolls": "اشتغال غیرکشاورزی",
    "Non-Farm Employment Change": "تغییر اشتغال غیرکشاورزی",
    "Nonfarm Payrolls q/q": "اشتغال غیرکشاورزی (فصلی)",
    "ADP Non-Farm Employment Change": "اشتغال ADP",
    "ADP Nonfarm Employment Change": "اشتغال ADP",
    "Unemployment Rate": "نرخ بیکاری",
    "Initial Jobless Claims": "مدعیان اولیه بیکاری",
    "Continuing Jobless Claims": "مدعیان مستمر بیکاری",
    "Average Hourly Earnings m/m": "متوسط دستمزد ساعتی (ماهانه)",
    "Average Hourly Earnings y/y": "متوسط دستمزد ساعتی (سالانه)",
    "JOLTS Job Openings": "فرصت‌های شغلی JOLTS",

    # US Inflation
    "CPI": "شاخص قیمت مصرف‌کننده",
    "CPI m/m": "شاخص قیمت مصرف‌کننده (ماهانه)",
    "CPI y/y": "شاخص قیمت مصرف‌کننده (سالانه)",
    "Core CPI m/m": "شاخص قیمت مصرف‌کننده هسته‌ای (ماهانه)",
    "Core CPI y/y": "شاخص قیمت مصرف‌کننده هسته‌ای (سالانه)",
    "PPI m/m": "شاخص قیمت تولیدکننده (ماهانه)",
    "PPI y/y": "شاخص قیمت تولیدکننده (سالانه)",
    "Core PPI m/m": "شاخص قیمت تولیدکننده هسته‌ای (ماهانه)",
    "PCE Price Index m/m": "شاخص PCE (ماهانه)",
    "PCE Price Index y/y": "شاخص PCE (سالانه)",
    "Core PCE Price Index m/m": "شاخص PCE هسته‌ای (ماهانه)",
    "Core PCE Price Index y/y": "شاخص PCE هسته‌ای (سالانه)",

    # US Fed & Monetary Policy
    "Federal Funds Rate": "نرخ بهره فدرال رزرو",
    "Fed Interest Rate Decision": "تصمیم نرخ بهره فدرال رزرو",
    "FOMC Statement": "بیانیه کمیته بازار آزاد فدرال",
    "FOMC Minutes": "صورتجلسه کمیته بازار آزاد فدرال",
    "FOMC Press Conference": "کنفرانس مطبوعاتی فدرال رزرو",
    "FOMC Member Speaks": "سخنرانی عضو فدرال رزرو",
    "Fed Chair Powell Speaks": "سخنرانی رئیس فدرال رزرو",
    "Fed Chair Press Conference": "کنفرانس مطبوعاتی رئیس فدرال رزرو",

    # US GDP & Growth
    "GDP q/q": "تولید ناخالص داخلی (فصلی)",
    "GDP y/y": "تولید ناخالص داخلی (سالانه)",
    "Advance GDP q/q": "تولید ناخالص داخلی مقدماتی",
    "Prelim GDP q/q": "تولید ناخالص داخلی اولیه",
    "Final GDP q/q": "تولید ناخالص داخلی نهایی",
    "GDP Price Index q/q": "شاخص قیمت GDP (فصلی)",

    # US Consumer & Retail
    "Retail Sales m/m": "خرده‌فروشی (ماهانه)",
    "Core Retail Sales m/m": "خرده‌فروشی هسته‌ای (ماهانه)",
    "Consumer Confidence": "اعتماد مصرف‌کننده",
    "CB Consumer Confidence": "اعتماد مصرف‌کننده CB",
    "Michigan Consumer Sentiment": "سنتیمنت مصرف‌کننده میشیگان",
    "Prelim UoM Consumer Sentiment": "سنتیمنت مصرف‌کننده میشیگان (اولیه)",
    "Personal Spending m/m": "هزینه‌های شخصی (ماهانه)",
    "Personal Income m/m": "درآمد شخصی (ماهانه)",

    # US Manufacturing & Services
    "ISM Manufacturing PMI": "شاخص مدیران خرید تولیدی ISM",
    "ISM Services PMI": "شاخص مدیران خرید خدماتی ISM",
    "ISM Manufacturing Prices": "قیمت‌های تولیدی ISM",
    "S&P Global Manufacturing PMI": "شاخص PMI تولیدی S&P",
    "S&P Global Services PMI": "شاخص PMI خدماتی S&P",
    "S&P Global Composite PMI": "شاخص PMI ترکیبی S&P",
    "Flash Manufacturing PMI": "شاخص PMI تولیدی فلش",
    "Flash Services PMI": "شاخص PMI خدماتی فلش",
    "Industrial Production m/m": "تولید صنعتی (ماهانه)",
    "Capacity Utilization Rate": "نرخ استفاده از ظرفیت",
    "Durable Goods Orders m/m": "سفارشات کالاهای بادوام (ماهانه)",
    "Core Durable Goods Orders m/m": "سفارشات کالاهای بادوام هسته‌ای (ماهانه)",
    "Factory Orders m/m": "سفارشات کارخانه‌ای (ماهانه)",

    # US Housing
    "Existing Home Sales": "فروش مسکن موجود",
    "New Home Sales": "فروش مسکن نوساز",
    "Building Permits": "مجوزهای ساختمانی",
    "Housing Starts": "شروع ساخت مسکن",

    # US Trade & Dollar
    "Trade Balance": "تراز تجاری",
    "Current Account": "حساب جاری",
    "Treasury Currency Report": "گزارش ارزی خزانه‌داری",

    # US Treasury
    "10-y Bond Auction": "مزایده اوراق ۱۰ ساله",
    "30-y Bond Auction": "مزایده اوراق ۳۰ ساله",
    "2-y Note Auction": "مزایده اوراق ۲ ساله",

    # ECB
    "ECB Interest Rate Decision": "تصمیم نرخ بهره بانک مرکزی اروپا",
    "ECB Rate Decision": "تصمیم نرخ بهره ECB",
    "ECB Press Conference": "کنفرانس مطبوعاتی بانک مرکزی اروپا",
    "ECB Monetary Policy Statement": "بیانیه سیاست پولی ECB",
    "ECB President Lagarde Speaks": "سخنرانی رئیس بانک مرکزی اروپا",

    # BOJ
    "BOJ Policy Rate": "نرخ بهره بانک مرکزی ژاپن",
    "BOJ Interest Rate Decision": "تصمیم نرخ بهره بانک مرکزی ژاپن",
    "BOJ Press Conference": "کنفرانس مطبوعاتی بانک مرکزی ژاپن",
    "BOJ Monetary Policy Statement": "بیانیه سیاست پولی بانک مرکزی ژاپن",

    # BOE
    "BOE Interest Rate Decision": "تصمیم نرخ بهره بانک مرکزی انگلستان",
    "BOE Rate Decision": "تصمیم نرخ بهره BOE",
    "BOE Gov Bailey Speaks": "سخنرانی رئیس بانک مرکزی انگلستان",

    # PBOC
    "PBOC Loan Prime Rate": "نرخ بهره بانک مرکزی چین",
    "PBOC Interest Rate Decision": "تصمیم نرخ بهره بانک مرکزی چین",
    "PBOC MLF Rate": "نرخ MLF بانک مرکزی چین",

    # RBA
    "RBA Interest Rate Decision": "تصمیم نرخ بهره بانک مرکزی استرالیا",
    "RBA Rate Statement": "بیانیه نرخ بهره بانک مرکزی استرالیا",

    # SNB
    "SNB Interest Rate Decision": "تصمیم نرخ بهره بانک مرکزی سوئیس",

    # BOC
    "BOC Interest Rate Decision": "تصمیم نرخ بهره بانک مرکزی کانادا",
    "BOC Rate Statement": "بیانیه نرخ بهره بانک مرکزی کانادا",

    # Oil & Energy
    "Crude Oil Inventories": "ذخایر نفت خام",
    "EIA Crude Oil Stocks Change": "تغییر ذخایر نفت EIA",
    "API Weekly Crude Oil Stock": "ذخایر نفت API",
    "OPEC Meeting": "نشست اوپک",
    "OPEC-JMMC Meetings": "نشست کمیته نظارتی اوپک",
    "Natural Gas Storage": "ذخایر گاز طبیعی",
    "Baker Hughes Oil Rig Count": "تعداد دکل‌های نفتی بیکر هیوز",

    # Gold-specific
    "Gold Reserves": "ذخایر طلا",
    "CFTC Gold Speculative Positions": "موقعیت‌های سفته‌بازی طلا CFTC",
    "Gold ETF Holdings": "دارایی‌های ETF طلا",
    "SPDR Gold Holdings": "دارایی‌های صندوق SPDR طلا",

    # Geopolitical
    "G7 Summit": "نشست جی‌۷",
    "G20 Summit": "نشست جی‌۲۰",
    "UN General Assembly": "مجمع عمومی سازمان ملل",

    # China
    "Chinese GDP q/q": "تولید ناخالص داخلی چین (فصلی)",
    "Chinese GDP y/y": "تولید ناخالص داخلی چین (سالانه)",
    "Chinese CPI y/y": "شاخص قیمت مصرف‌کننده چین",
    "Chinese Trade Balance": "تراز تجاری چین",
    "Chinese Industrial Production y/y": "تولید صنعتی چین",
    "Caixin Manufacturing PMI": "شاخص PMI تولیدی کایکسین چین",
    "Caixin Services PMI": "شاخص PMI خدماتی کایکسین چین",
    "NBS Manufacturing PMI": "شاخص PMI تولیدی NBS چین",

    # Eurozone
    "German CPI m/m": "شاخص قیمت مصرف‌کننده آلمان (ماهانه)",
    "German GDP q/q": "تولید ناخالص داخلی آلمان (فصلی)",
    "German Ifo Business Climate": "شاخص فضای کسب‌وکار آلمان Ifo",
    "German ZEW Economic Sentiment": "سنتیمنت اقتصادی ZEW آلمان",
    "Eurozone CPI y/y": "شاخص قیمت مصرف‌کننده اروپا (سالانه)",
    "Eurozone GDP q/q": "تولید ناخالص داخلی اروپا (فصلی)",
    "Eurozone Unemployment Rate": "نرخ بیکاری منطقه یورو",

    # UK
    "UK CPI y/y": "شاخص قیمت مصرف‌کننده انگلستان (سالانه)",
    "UK GDP m/m": "تولید ناخالص داخلی انگلستان (ماهانه)",
    "UK Unemployment Rate": "نرخ بیکاری انگلستان",
    "UK Retail Sales m/m": "خرده‌فروشی انگلستان (ماهانه)",

    # Japan
    "Japanese GDP q/q": "تولید ناخالص داخلی ژاپن (فصلی)",
    "Japanese CPI y/y": "شاخص قیمت مصرف‌کننده ژاپن (سالانه)",
    "Tankan Manufacturing Index": "شاخص تانکان تولیدی ژاپن",

    # Australia
    "Australian CPI q/q": "شاخص قیمت مصرف‌کننده استرالیا (فصلی)",
    "Australian GDP q/q": "تولید ناخالص داخلی استرالیا (فصلی)",
    "Australian Unemployment Rate": "نرخ بیکاری استرالیا",
}


# ── Event-to-Asset Impact Mappings ───────────────────────────────────

EVENT_ASSET_IMPACT: dict[str, dict] = {
    "gold_direct": {
        "assets": ["xauusd", "global_gold"],
        "events": [
            "FOMC Rate Decision",
            "Fed Interest Rate Decision",
            "Federal Funds Rate",
            "FOMC Minutes",
            "FOMC Press Conference",
            "FOMC Statement",
            "Fed Chair Powell Speaks",
            "Fed Chair Press Conference",
            "FOMC Member Speaks",
            "Non-Farm Payrolls",
            "Nonfarm Payrolls",
            "CPI", "CPI m/m", "CPI y/y",
            "Core CPI m/m", "Core CPI y/y",
            "PPI m/m", "PPI y/y", "Core PPI m/m",
            "PCE Price Index m/m", "PCE Price Index y/y",
            "Core PCE Price Index m/m", "Core PCE Price Index y/y",
            "GDP q/q", "GDP y/y", "Advance GDP q/q",
            "Prelim GDP q/q", "Final GDP q/q",
            "Initial Jobless Claims",
            "Continuing Jobless Claims",
            "Unemployment Rate",
            "ISM Manufacturing PMI",
            "ISM Services PMI",
            "Retail Sales m/m", "Core Retail Sales m/m",
            "Consumer Confidence", "CB Consumer Confidence",
            "Michigan Consumer Sentiment",
            "Prelim UoM Consumer Sentiment",
            "Durable Goods Orders m/m",
            "Core Durable Goods Orders m/m",
            "ADP Non-Farm Employment Change",
            "ADP Nonfarm Employment Change",
            "Trade Balance",
            "ECB Interest Rate Decision", "ECB Rate Decision",
            "ECB Press Conference",
            "BOJ Policy Rate", "BOJ Interest Rate Decision",
            "BOE Interest Rate Decision", "BOE Rate Decision",
            "PBOC Loan Prime Rate", "PBOC Interest Rate Decision",
            "PBOC MLF Rate",
            "RBA Interest Rate Decision",
            "SNB Interest Rate Decision",
            "BOC Interest Rate Decision",
            "Gold Reserves",
            "CFTC Gold Speculative Positions",
            "Gold ETF Holdings",
            "SPDR Gold Holdings",
            "G7 Summit",
            "G20 Summit",
            "OPEC Meeting", "OPEC-JMMC Meetings",
        ],
    },
    "iran_gold": {
        "assets": ["iran_gold", "usd_irr", "coin"],
        "events": [
            "Iran CPI",
            "Iran Inflation Rate",
            "Iran GDP",
            "Iran Interest Rate",
            "Iran Oil Production",
            "JCPOA",
            "Iran Nuclear Talks",
            "IAEA Report",
            "US Sanctions",
            "UN Security Council",
            "Crude Oil Inventories",
            "EIA Crude Oil Stocks Change",
            "API Weekly Crude Oil Stock",
            "OPEC Meeting", "OPEC-JMMC Meetings",
            "OPEC Production",
            "Baker Hughes Oil Rig Count",
        ],
    },
    "usd_irr": {
        "assets": ["usd_irr", "iran_gold", "coin", "gold_fund"],
        "events": [
            "Iran Central Bank Decision",
            "Iran Budget",
            "Iran Election",
        ],
    },
    "coin": {
        "assets": ["coin"],
        "events": [
            "Iran Mint Production",
            "Central Bank Coin Presale",
        ],
    },
}

# Build a fast lookup: event_name -> set of affected assets
_EVENT_TO_ASSETS: dict[str, set[str]] = {}
for _group in EVENT_ASSET_IMPACT.values():
    for _event_name in _group["events"]:
        _lower = _event_name.lower()
        if _lower not in _EVENT_TO_ASSETS:
            _EVENT_TO_ASSETS[_lower] = set()
        _EVENT_TO_ASSETS[_lower].update(_group["assets"])


def get_affected_assets(event_name: str, currency: str = "") -> list[str]:
    """Return the list of affected assets for a given event name and currency.

    First tries exact match from the static event mapping, then falls
    back to the currency-based mapping.
    """
    lower = event_name.lower()
    assets: set[str] = set()

    # Check exact match
    if lower in _EVENT_TO_ASSETS:
        assets.update(_EVENT_TO_ASSETS[lower])

    # Check partial match (event name contains a known event keyword)
    if not assets:
        for known_event, known_assets in _EVENT_TO_ASSETS.items():
            if known_event in lower or lower in known_event:
                assets.update(known_assets)

    # Fallback to currency mapping
    if not assets and currency:
        currency_assets = CURRENCY_TO_ASSET.get(currency.upper(), [])
        assets.update(currency_assets)

    # Default: if event has USD currency, it affects gold
    if not assets:
        assets.add("xauusd")

    return sorted(assets)


# ── Currency-to-Asset Fallback Mapping ────────────────────────────────

CURRENCY_TO_ASSET: dict[str, list[str]] = {
    "USD": ["xauusd", "global_gold", "usd_irr"],
    "EUR": ["xauusd", "global_gold"],
    "CNY": ["xauusd", "global_gold"],
    "JPY": ["xauusd"],
    "GBP": ["xauusd"],
    "CHF": ["xauusd"],
    "AUD": ["xauusd"],
    "CAD": ["xauusd"],
    "NZD": ["xauusd"],
    "IRR": ["iran_gold", "usd_irr", "coin", "gold_fund"],
}


# ── Gold Impact Notes ────────────────────────────────────────────────

EVENT_GOLD_NOTES: dict[str, dict[str, dict[str, str]]] = {
    "Non-Farm Payrolls": {
        "xauusd": {
            "above_forecast": "نزولی — اشتغال قوی = انتظار سختگیری فدرال رزرو = تقویت دلار = فشار بر طلا",
            "below_forecast": "صعودی — اشتغال ضعیف = انتظار کاهش نرخ بهره = تضعیف دلار = حمایت از طلا",
        },
        "usd_irr": {
            "above_forecast": "صعودی دلار — تقویت دلار جهانی معمولاً به افزایش نرخ دلار در ایران منجر می‌شود",
            "below_forecast": "نزولی دلار — تضعیف دلار ممکن است فشار نزولی بر نرخ ارز در ایران ایجاد کند",
        },
    },
    "Nonfarm Payrolls": {
        "xauusd": {
            "above_forecast": "نزولی — اشتغال قوی = انتظار سختگیری فدرال رزرو = تقویت دلار = فشار بر طلا",
            "below_forecast": "صعودی — اشتغال ضعیف = انتظار کاهش نرخ بهره = تضعیف دلار = حمایت از طلا",
        },
    },
    "CPI m/m": {
        "xauusd": {
            "above_forecast": "کوتاه‌مدت نزولی، بلندمدت صعودی — تورم بالا = فدرال رزرو سختگیرتر (نزولی) اما تورم = تقاضای پناهگاهی (صعودی)",
            "below_forecast": "صعودی — تورم پایین = انتظار سیاست انبساطی = حمایت از طلا",
        },
    },
    "CPI y/y": {
        "xauusd": {
            "above_forecast": "کوتاه‌مدت نزولی، بلندمدت صعودی — تورم بالا = فدرال رزرو سختگیرتر (نزولی) اما تورم = تقاضای پناهگاهی (صعودی)",
            "below_forecast": "صعودی — تورم پایین = انتظار سیاست انبساطی = حمایت از طلا",
        },
    },
    "Core CPI m/m": {
        "xauusd": {
            "above_forecast": "نزولی — تورم هسته‌ای بالا = احتمال افزایش نرخ بهره = فشار بر طلا",
            "below_forecast": "صعودی — تورم هسته‌ای پایین = احتمال کاهش نرخ بهره = حمایت از طلا",
        },
    },
    "Federal Funds Rate": {
        "xauusd": {
            "above_forecast": "نزولی — نرخ بهره بالاتر = هزینه فرصت نگهداری طلا افزایش = فشار فروش",
            "below_forecast": "صعودی — کاهش نرخ بهره = تضعیف دلار و کاهش هزینه فرصت = حمایت قوی از طلا",
        },
    },
    "FOMC Statement": {
        "xauusd": {
            "above_forecast": "نزولی — لحن سختگیرانه = انتظار افزایش یا حفظ نرخ بهره بالا = فشار بر طلا",
            "below_forecast": "صعودی — لحن انبساطی = انتظار کاهش نرخ بهره = حمایت از طلا",
        },
    },
    "ECB Interest Rate Decision": {
        "xauusd": {
            "above_forecast": "پیچیده — تقویت یورو = تضعیف نسبی دلار = حمایت از طلا",
            "below_forecast": "پیچیده — تضعیف یورو = تقویت نسبی دلار = فشار بر طلا",
        },
    },
    "Crude Oil Inventories": {
        "iran_gold": {
            "above_forecast": "نزولی نفت → کاهش درآمد ارزی ایران → فشار بر ریال",
            "below_forecast": "صعودی نفت → افزایش درآمد ارزی ایران → حمایت از ریال",
        },
    },
    "GDP q/q": {
        "xauusd": {
            "above_forecast": "نزولی — رشد اقتصادی قوی = ریسک‌پذیری بالا = کاهش تقاضای پناهگاهی طلا",
            "below_forecast": "صعودی — رشد ضعیف = نگرانی اقتصادی = افزایش تقاضای پناهگاهی طلا",
        },
    },
    "Initial Jobless Claims": {
        "xauusd": {
            "above_forecast": "صعودی — افزایش بیکاری = اقتصاد ضعیف‌تر = انتظار سیاست انبساطی",
            "below_forecast": "نزولی — بازار کار قوی = فدرال رزرو سختگیرانه‌تر",
        },
    },
    "Consumer Confidence": {
        "xauusd": {
            "above_forecast": "نزولی — اعتماد بالا = ریسک‌پذیری = خروج سرمایه از طلا",
            "below_forecast": "صعودی — اعتماد پایین = نگرانی = پناه به طلا",
        },
    },
    "ISM Manufacturing PMI": {
        "xauusd": {
            "above_forecast": "نزولی — فعالیت تولیدی قوی = اقتصاد سالم = کمتر نیاز به طلا",
            "below_forecast": "صعودی — ضعف تولیدی = نگرانی رکود = افزایش تقاضای طلا",
        },
    },
    "Retail Sales m/m": {
        "xauusd": {
            "above_forecast": "نزولی — مصرف قوی = اقتصاد سالم = فدرال رزرو سختگیرتر",
            "below_forecast": "صعودی — مصرف ضعیف = نگرانی رشد اقتصادی = حمایت از طلا",
        },
    },
    "Michigan Consumer Sentiment": {
        "xauusd": {
            "above_forecast": "نزولی — سنتیمنت بالا = ریسک‌پذیری بیشتر = فشار بر طلا",
            "below_forecast": "صعودی — سنتیمنت پایین = نگرانی مصرف‌کننده = پناه به طلا",
        },
    },
    "PCE Price Index m/m": {
        "xauusd": {
            "above_forecast": "نزولی — شاخص مورد علاقه فد بالا = سیاست سختگیرانه = فشار بر طلا",
            "below_forecast": "صعودی — تورم پایین = احتمال کاهش نرخ بهره = حمایت از طلا",
        },
    },
    "Core PCE Price Index m/m": {
        "xauusd": {
            "above_forecast": "نزولی — شاخص هسته‌ای PCE بالا = سیاست سختگیرانه‌تر فدرال رزرو",
            "below_forecast": "صعودی — تورم هسته‌ای کنترل شده = احتمال انعطاف فدرال رزرو",
        },
    },
    "Durable Goods Orders m/m": {
        "xauusd": {
            "above_forecast": "نزولی — سفارشات قوی = اقتصاد سالم = کاهش تقاضای طلا",
            "below_forecast": "صعودی — سفارشات ضعیف = نگرانی تولیدی = افزایش تقاضای طلا",
        },
    },
    "ADP Non-Farm Employment Change": {
        "xauusd": {
            "above_forecast": "نزولی — پیش‌نمایش اشتغال قوی = انتظار NFP قوی = فشار بر طلا",
            "below_forecast": "صعودی — پیش‌نمایش اشتغال ضعیف = حمایت از طلا",
        },
    },
    "OPEC Meeting": {
        "iran_gold": {
            "above_forecast": "افزایش تولید → کاهش قیمت نفت → فشار بر درآمد ارزی ایران",
            "below_forecast": "کاهش تولید → افزایش قیمت نفت → حمایت از درآمد ارزی ایران",
        },
    },
    "BOJ Policy Rate": {
        "xauusd": {
            "above_forecast": "صعودی طلا — افزایش نرخ بهره ژاپن = تقویت ین = تضعیف دلار = حمایت از طلا",
            "below_forecast": "نزولی طلا — حفظ نرخ پایین = ین ضعیف = دلار قوی = فشار بر طلا",
        },
    },
}


def get_gold_impact_note(event_name: str, asset: str = "xauusd") -> dict[str, str] | None:
    """Return impact notes for a given event and asset, or None if not available."""
    notes = EVENT_GOLD_NOTES.get(event_name)
    if notes and asset in notes:
        return notes[asset]
    return None


def translate_event_name(name: str) -> str:
    """Translate an event name to Persian. Returns original name if no translation exists."""
    if name in EVENT_TRANSLATIONS:
        return EVENT_TRANSLATIONS[name]

    # Try case-insensitive partial matching
    name_lower = name.lower()
    for en_name, fa_name in EVENT_TRANSLATIONS.items():
        if en_name.lower() == name_lower:
            return fa_name

    return name
