import { AssetId, Severity, TimeHorizon, RuleSection } from '@/types';

export const SEVERITY_CONFIG: Record<Severity, { label: string; color: string; bgLight: string; bgDark: string }> = {
  high: { label: 'بحرانی', color: 'text-red-600 dark:text-red-400', bgLight: 'bg-red-50', bgDark: 'dark:bg-red-950/30' },
  medium: { label: 'مهم', color: 'text-amber-600 dark:text-amber-400', bgLight: 'bg-amber-50', bgDark: 'dark:bg-amber-950/30' },
  low: { label: 'عادی', color: 'text-gray-500 dark:text-gray-400', bgLight: 'bg-gray-50', bgDark: 'dark:bg-gray-800/30' },
};

export const DIRECTION_CONFIG: Record<string, { label: string; icon: string; color: string }> = {
  bullish: { label: 'صعودی', icon: '▲', color: 'text-emerald-600 dark:text-emerald-400' },
  bearish: { label: 'نزولی', icon: '▼', color: 'text-red-600 dark:text-red-400' },
  mixed: { label: 'مختلط', icon: '◆', color: 'text-amber-600 dark:text-amber-400' },
  unclear: { label: 'نامشخص', icon: '—', color: 'text-gray-500 dark:text-gray-400' },
};

export const HORIZON_CONFIG: Record<TimeHorizon, { label: string; description: string }> = {
  immediate: { label: 'فوری', description: 'دقایق تا چند ساعت' },
  short: { label: 'کوتاه‌مدت', description: 'چند روز تا چند هفته' },
  medium: { label: 'میان‌مدت', description: 'چند هفته تا چند ماه' },
  long: { label: 'بلندمدت', description: 'چند ماه تا چند سال' },
};

export const ASSET_CONFIG: Record<AssetId, { name: string; nameShort: string; icon: string }> = {
  global_gold: { name: 'طلای جهانی (اونس)', nameShort: 'طلای جهانی', icon: '🌍' },
  iran_gold: { name: 'طلای ایران (۱۸ عیار)', nameShort: 'طلای ایران', icon: '🇮🇷' },
  coin: { name: 'سکه', nameShort: 'سکه', icon: '🪙' },
  gold_funds: { name: 'صندوق‌های طلا', nameShort: 'صندوق طلا', icon: '📊' },
};

export const SECTION_CONFIG: Record<RuleSection, { title: string; categories: { id: string; title: string }[] }> = {
  global_gold: {
    title: 'عوامل جهانی',
    categories: [
      { id: 'rates', title: 'نرخ بهره و سیاست پولی' },
      { id: 'dollar', title: 'دلار و ارزها' },
      { id: 'geopolitics', title: 'ژئوپلیتیک و ریسک' },
      { id: 'supply', title: 'عرضه معدن و بانک‌های مرکزی' },
      { id: 'demand', title: 'تقاضای فیزیکی (چین/هند)' },
      { id: 'alternative', title: 'کریپتو و بورس' },
    ],
  },
  iran_gold: {
    title: 'عوامل ایران',
    categories: [
      { id: 'fx', title: 'دلار و سیاست ارزی' },
      { id: 'macro', title: 'تورم و نقدینگی' },
      { id: 'fiscal', title: 'بودجه و سود بانکی' },
      { id: 'politics', title: 'تحریم و مذاکرات' },
      { id: 'physical', title: 'عرضه فیزیکی و مالیات' },
      { id: 'management', title: 'مدیران اقتصادی' },
    ],
  },
  coin: {
    title: 'عوامل سکه',
    categories: [
      { id: 'premium', title: 'حباب و پریمیوم' },
      { id: 'supply', title: 'حراج و ضرب' },
      { id: 'demand', title: 'تقاضای فصلی' },
      { id: 'policy', title: 'قوانین و مالیات' },
      { id: 'sentiment', title: 'جو روانی' },
    ],
  },
  gold_funds: {
    title: 'عوامل صندوق‌ها',
    categories: [
      { id: 'nav', title: 'NAV و پریمیوم' },
      { id: 'flow', title: 'جریان پول' },
      { id: 'regulation', title: 'قوانین بازار سرمایه' },
      { id: 'codal', title: 'اعلانات کدال' },
    ],
  },
};

export const GLOSSARY: Record<string, string> = {
  'FOMC': 'کمیته بازار آزاد فدرال رزرو (تصمیم‌گیرنده نرخ بهره آمریکا)',
  'CPI': 'شاخص قیمت مصرف‌کننده (معیار اصلی تورم)',
  'PCE': 'شاخص هزینه مصرف شخصی (معیار تورم مورد علاقه فدرال رزرو)',
  'PPI': 'شاخص قیمت تولیدکننده',
  'NFP': 'آمار اشتغال غیرکشاورزی آمریکا',
  'PMI': 'شاخص مدیران خرید (سنجش سلامت اقتصاد)',
  'ISM': 'موسسه مدیریت عرضه (آمارهای اقتصادی)',
  'DXY': 'شاخص دلار آمریکا در برابر سبد ارزها',
  'QE': 'تسهیل کمّی (تزریق پول توسط بانک مرکزی)',
  'QT': 'انقباض کمّی (جمع‌آوری پول توسط بانک مرکزی)',
  'VIX': 'شاخص ترس بازار سهام',
  'NAV': 'ارزش خالص دارایی صندوق',
  'ETF': 'صندوق قابل معامله در بورس',
  'TIPS': 'اوراق خزانه محافظت‌شده در برابر تورم',
  'GDP': 'تولید ناخالص داخلی',
  'RSI': 'شاخص قدرت نسبی (اندیکاتور تکنیکال)',
  'MACD': 'میانگین متحرک همگرا واگرا (اندیکاتور تکنیکال)',
  'MA200': 'میانگین متحرک ۲۰۰ روزه',
};

export const TIME_RANGES = [
  { id: 'today' as const, label: 'امروز' },
  { id: '24h' as const, label: '۲۴ ساعت' },
  { id: '7d' as const, label: '۷ روز' },
  { id: '30d' as const, label: '۳۰ روز' },
];

export const MARKET_OPTIONS = [
  { id: 'all' as const, label: 'همه بازارها' },
  { id: 'global_gold' as const, label: 'طلای جهانی' },
  { id: 'iran_gold' as const, label: 'طلای ایران' },
  { id: 'coin' as const, label: 'سکه' },
  { id: 'gold_funds' as const, label: 'صندوق طلا' },
];
