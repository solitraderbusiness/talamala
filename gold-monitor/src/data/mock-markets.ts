import { MarketInfo } from '@/types';

export const mockMarkets: MarketInfo[] = [
  {
    id: 'global_gold',
    name: 'طلای جهانی (اونس)',
    nameEn: 'XAU/USD',
    price: '۲,۷۱۵',
    change: '+۳۲',
    changePercent: '+۱.۱۹٪',
    trend: 'روند صعودی کوتاه‌مدت. شکست مقاومت ۲,۷۰۰ تایید شده.',
    isPositive: true,
  },
  {
    id: 'iran_gold',
    name: 'طلای ۱۸ عیار (گرم)',
    nameEn: 'IR Gold 18K',
    price: '۵,۸۵۰,۰۰۰',
    change: '+۱۲۰,۰۰۰',
    changePercent: '+۲.۰۹٪',
    trend: 'رشد ناشی از افزایش دلار و اونس. فشار صعودی ادامه‌دار.',
    isPositive: true,
  },
  {
    id: 'coin',
    name: 'سکه تمام بهار آزادی',
    nameEn: 'Bahar Azadi Coin',
    price: '۴۵,۵۰۰,۰۰۰',
    change: '+۱,۲۰۰,۰۰۰',
    changePercent: '+۲.۷۱٪',
    trend: 'حباب ۲۵٪. ریسک اصلاح بالا. احتیاط در خرید توصیه می‌شود.',
    isPositive: true,
  },
  {
    id: 'gold_funds',
    name: 'صندوق طلا (شاخص ترکیبی)',
    nameEn: 'Gold ETF Index',
    price: '۱۲۸,۴۵۰',
    change: '+۲,۱۰۰',
    changePercent: '+۱.۶۶٪',
    trend: 'ورود پول رکوردی. پریمیوم بالا. در صورت اصلاح طلا، اصلاح شدیدتر.',
    isPositive: true,
  },
];
