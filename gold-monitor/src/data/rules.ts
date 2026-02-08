import { Rule, TechnicalSignal, RuleSection } from '@/types';

export const rules: Rule[] = [
  // ── GLOBAL GOLD ──
  {
    id: 'GLOB_RATE_DECISION',
    section: 'global_gold',
    title: 'تصمیم نرخ بهره (افزایش/کاهش/تثبیت)',
    what_it_is: 'اعلام رسمی نرخ بهره توسط بانک‌های مرکزی؛ مهم‌تر از همه فدرال رزرو.',
    watch_for: {
      keywords: ['rate hike', 'rate cut', 'hold rates', 'interest rate decision', 'FOMC decision', 'Fed rate', 'ECB rate decision'],
      signals: ['افزایش نرخ بهره یا اشاره به افزایش‌های بیشتر', 'کاهش نرخ بهره یا اشاره به کاهش‌های آینده', 'تغییر مسیر سیاست'],
    },
    why_important: 'نرخ بهره بالاتر معمولاً فشار نزولی بر طلا ایجاد می‌کند؛ نرخ بهره پایین‌تر معمولاً حمایتی است.',
    importance_criteria: {
      high_if: ['تصمیم برخلاف انتظار بازار باشد (Surprise)', 'تغییر مسیر سیاست به‌صورت واضح اعلام شود'],
      medium_if: ['تصمیم مطابق انتظار باشد ولی لحن بیانیه تغییر کند'],
      low_if: ['خبر تکراری بدون اطلاعات جدید'],
    },
    horizon: 'immediate',
  },
  {
    id: 'GLOB_QE_QT',
    section: 'global_gold',
    title: 'سیاست‌های انبساطی/انقباضی (QE/QT)',
    what_it_is: 'تغییر در تزریق یا جمع‌آوری نقدینگی و اندازه ترازنامه بانک مرکزی.',
    watch_for: {
      keywords: ['quantitative easing', 'QE', 'asset purchases', 'balance sheet expansion', 'quantitative tightening', 'QT'],
      signals: ['اعلام برنامه جدید خرید دارایی (QE)', 'کاهش سرعت QT یا توقف QT', 'تشدید QT'],
    },
    why_important: 'QE معمولاً انتظارات تورمی را بالا می‌برد و برای طلا حمایتی است؛ QT برعکس.',
    importance_criteria: {
      high_if: ['شروع QE جدید یا تغییر بزرگ در ترازنامه'],
      medium_if: ['تنها تغییر سرعت QT/QE'],
    },
    horizon: 'short',
  },
  {
    id: 'GLOB_FED_COMM',
    section: 'global_gold',
    title: 'سخنرانی‌ها/بیانیه‌ها (Powell/Fed/ECB/BoE/BoJ)',
    what_it_is: 'راهنمایی کلامی (Forward guidance) که انتظارات نرخ بهره و دلار را تغییر می‌دهد.',
    watch_for: {
      keywords: ['Powell', 'Fed chair', 'Fed minutes', 'forward guidance', 'hawkish', 'dovish', 'Lagarde'],
      signals: ['تغییر لحن از سختگیرانه به نرم یا برعکس', 'اشاره به نگرانی رکود/بحران بانکی'],
    },
    why_important: 'لحن سیاست‌گذار می‌تواند حتی بدون تغییر نرخ بهره، بازار را جابه‌جا کند.',
    importance_criteria: {
      high_if: ['جمله/اشاره کلیدی جدید مسیر آینده نرخ بهره را تغییر دهد'],
      medium_if: ['تکرار مواضع قبلی با جزئیات بیشتر'],
    },
    horizon: 'immediate',
  },
  {
    id: 'GLOB_US_YIELDS',
    section: 'global_gold',
    title: 'بازده اوراق خزانه‌داری آمریکا (2Y/10Y/Real Yield)',
    what_it_is: 'نرخ بازده اوراق که با هزینه فرصت نگهداری طلا مرتبط است.',
    watch_for: {
      keywords: ['10-year yield', '2-year yield', 'Treasury yields', 'real yields', 'TIPS'],
      signals: ['جهش یا سقوط ناگهانی بازده‌ها', 'اخبار بحران بدهی/حراج اوراق بزرگ'],
    },
    why_important: 'بالا رفتن بازده‌ها معمولاً منفی برای طلاست؛ افت بازده‌ها حمایتی است.',
    importance_criteria: {
      high_if: ['حرکت شدید (مثلاً جهش/سقوط غیرعادی در یک روز)'],
    },
    horizon: 'immediate',
  },
  {
    id: 'GLOB_DOLLAR_DXY',
    section: 'global_gold',
    title: 'شاخص دلار (DXY) و اخبار تقویت/تضعیف دلار',
    what_it_is: 'قدرت دلار در برابر سبد ارزها؛ رابطه معکوس رایج با طلا.',
    watch_for: {
      keywords: ['DXY', 'dollar index', 'USD strengthens', 'USD weakens'],
      signals: ['جهش/سقوط شدید DXY', 'دلایل بنیادی تقویت دلار'],
    },
    why_important: 'دلار قوی معمولاً طلا را تحت فشار می‌گذارد.',
    importance_criteria: {
      high_if: ['شکست سطوح کلیدی یا حرکت بسیار سریع'],
    },
    horizon: 'immediate',
  },
  {
    id: 'GLOB_US_MACRO_DATA',
    section: 'global_gold',
    title: 'داده‌های کلان آمریکا (CPI/PCE/NFP/PMI/…)',
    what_it_is: 'گزارش‌هایی که انتظارات نرخ بهره/دلار را تغییر می‌دهند.',
    watch_for: {
      keywords: ['CPI', 'core CPI', 'PCE', 'core PCE', 'PPI', 'NFP', 'GDP', 'PMI', 'ISM'],
      signals: ['عدد بالاتر از انتظار یا پایین‌تر از انتظار', 'بازنگری‌های بزرگ در داده‌ها'],
    },
    why_important: 'غافلگیری داده‌ها می‌تواند مسیر نرخ بهره و دلار را تغییر دهد.',
    importance_criteria: {
      high_if: ['Surprise بزرگ باشد یا بازار واکنش شدید نشان دهد'],
      medium_if: ['Surprise کوچک ولی جهت‌دار باشد'],
    },
    horizon: 'immediate',
  },
  {
    id: 'GLOB_GEOPOL_RISK',
    section: 'global_gold',
    title: 'ژئوپلیتیک (جنگ/تشدید/حملات/کودتا)',
    what_it_is: 'رویدادهای امنیتی-سیاسی که ریسک سیستماتیک و تقاضای دارایی امن را بالا می‌برد.',
    watch_for: {
      keywords: ['war', 'escalation', 'strike', 'missile', 'invasion', 'coup', 'sanctions'],
      signals: ['شروع یا گسترش جنگ', 'حمله به زیرساخت انرژی/کشتیرانی', 'تحریم‌های بزرگ و ناگهانی'],
    },
    why_important: 'افزایش ریسک جهانی غالباً به نفع طلاست.',
    importance_criteria: {
      high_if: ['تشدید رسمی/گسترش درگیری یا تحریم بزرگ'],
    },
    horizon: 'immediate',
  },
  {
    id: 'GLOB_MINING_SUPPLY',
    section: 'global_gold',
    title: 'عرضه معدن (تولید/هزینه استخراج/عیار)',
    what_it_is: 'عوامل سمت عرضه که بیشتر اثر میان‌مدت/بلندمدت دارند.',
    watch_for: {
      keywords: ['gold mine production', 'output cut', 'mine shutdown', 'ore grade', 'all-in sustaining costs'],
      signals: ['افت تولید معنی‌دار یا تعطیلی معدن بزرگ', 'گزارش افت عیار یا رشد هزینه استخراج'],
    },
    why_important: 'محدودیت عرضه و افزایش هزینه می‌تواند از قیمت حمایت کند.',
    importance_criteria: {
      high_if: ['تعطیلی/افت تولید در مقیاس بزرگ گزارش شود'],
      medium_if: ['روند هزینه‌ها/عیار در گزارش‌های معتبر تایید شود'],
    },
    horizon: 'medium',
  },
  {
    id: 'GLOB_CB_GOLD_RESERVES',
    section: 'global_gold',
    title: 'خرید/فروش طلا توسط بانک‌های مرکزی',
    what_it_is: 'تقاضای نهادی بزرگ و سیگنال تنوع ذخایر.',
    watch_for: {
      keywords: ['central bank gold reserves', 'added to gold reserves', 'WGC', 'PBoC gold'],
      signals: ['خرید رکوردی/بزرگ توسط چین/روسیه/هند/ترکیه', 'اعلام فروش یا برنامه فروش ذخایر'],
    },
    why_important: 'خریدهای بزرگ می‌تواند حمایت ساختاری ایجاد کند.',
    importance_criteria: {
      high_if: ['خرید/فروش بزرگ یا تغییر روند چندماهه'],
    },
    horizon: 'short',
  },
  {
    id: 'GLOB_ASIA_PHYSICAL_DEMAND',
    section: 'global_gold',
    title: 'تقاضای فیزیکی چین/هند',
    what_it_is: 'تقاضای جواهرات و سکه، تحت تاثیر فصل‌ها و سیاست‌های تجاری.',
    watch_for: {
      keywords: ['India wedding season', 'Chinese New Year', 'gold imports', 'import duty', 'jewelry demand'],
      signals: ['افزایش غیرعادی تقاضای فصلی', 'کاهش/افزایش تعرفه واردات طلا'],
    },
    why_important: 'این دو کشور سهم بالایی در تقاضای فیزیکی دارند.',
    importance_criteria: {
      high_if: ['تغییر سیاست تعرفه‌ای یا واردات شوک‌آور'],
      medium_if: ['گزارش فصلی قوی/ضعیف'],
    },
    horizon: 'short',
  },
  {
    id: 'GLOB_CRYPTO_SHOCKS',
    section: 'global_gold',
    title: 'شوک‌های بزرگ بازار رمزارز',
    what_it_is: 'جابه‌جایی توجه و نقدینگی بین دارایی‌های جایگزین.',
    watch_for: {
      keywords: ['Bitcoin crash', 'crypto liquidation', 'exchange hack', 'ETF inflows crypto'],
      signals: ['ریزش شدید چندروزه یا لیکوییدیشن بزرگ', 'جهش پرشتاب و موج ریسک‌پذیری'],
    },
    why_important: 'ترس کریپتو می‌تواند پول را به دارایی امن منتقل کند.',
    importance_criteria: {
      high_if: ['ورشکستگی/هک بزرگ/ریزش بسیار شدید'],
    },
    horizon: 'immediate',
  },
  {
    id: 'GLOB_EQUITY_RISK_OFF',
    section: 'global_gold',
    title: 'ریزش شدید بورس‌های جهانی / بحران بانکی',
    what_it_is: 'افزایش ریسک‌گریزی و تقاضا برای دارایی امن.',
    watch_for: {
      keywords: ['stock market selloff', 'bank crisis', 'credit crunch', 'recession fears', 'VIX spike'],
      signals: ['ریزش شدید شاخص‌ها یا جهش VIX', 'خبر ورشکستگی بانک/نهاد بزرگ'],
    },
    why_important: 'Risk-off معمولاً به نفع طلاست.',
    importance_criteria: {
      high_if: ['شوک سیستماتیک/بحران اعتباری'],
    },
    horizon: 'immediate',
  },
  // ── IRAN GOLD ──
  {
    id: 'IR_FX_USD',
    section: 'iran_gold',
    title: 'نرخ دلار آزاد و شکاف نرخ‌ها',
    what_it_is: 'مهم‌ترین محرک ریالی طلا در ایران.',
    watch_for: {
      keywords: ['دلار آزاد', 'نرخ دلار', 'بازار ارز', 'نیما', 'مرکز مبادله', 'درهم'],
      signals: ['جهش/ریزش ناگهانی نرخ ارز', 'تغییر معنادار شکاف نرخ‌ها'],
    },
    why_important: 'قیمت طلا در ایران تقریباً اونس×دلار است.',
    importance_criteria: {
      high_if: ['حرکت شدید یا خبر سیاستی مستقیم'],
    },
    horizon: 'immediate',
  },
  {
    id: 'IR_GOV_FX_POLICY',
    section: 'iran_gold',
    title: 'سیاست‌های ارزی دولت و بانک مرکزی',
    what_it_is: 'قواعد تخصیص/کنترل ارز و مداخلات ارزی.',
    watch_for: {
      keywords: ['سیاست ارزی', 'پیمان ارزی', 'تخصیص ارز', 'تزریق ارز', 'محدودیت صرافی'],
      signals: ['بخشنامه جدید ارزی', 'تزریق/محدودیت بزرگ در بازار ارز'],
    },
    why_important: 'می‌تواند عرضه/تقاضای ارز و انتظارات را جابه‌جا کند.',
    importance_criteria: {
      high_if: ['قانون/بخشنامه جدید با اثر فوری'],
    },
    horizon: 'short',
  },
  {
    id: 'IR_RESERVES_SANCTIONS',
    section: 'iran_gold',
    title: 'ذخایر ارزی، آزادسازی منابع، تحریم‌های ارزی',
    what_it_is: 'توان دسترسی به ارز و فشار/آزادسازی از بیرون.',
    watch_for: {
      keywords: ['آزادسازی منابع', 'پول‌های بلوکه', 'تحریم ارزی', 'تحریم بانکی', 'سوئیفت'],
      signals: ['آزادسازی یا مسدودسازی منابع', 'تحریم جدید علیه بانک‌ها'],
    },
    why_important: 'مستقیماً دلار را تکان می‌دهد و به طلا منتقل می‌شود.',
    importance_criteria: {
      high_if: ['تحریم جدید بزرگ یا آزادسازی بزرگ منابع'],
    },
    horizon: 'immediate',
  },
  {
    id: 'IR_MACRO_INFLATION_LIQ',
    section: 'iran_gold',
    title: 'تورم، نقدینگی، پایه پولی',
    what_it_is: 'پیشران‌های بنیادی ریال و انتظارات تورمی.',
    watch_for: {
      keywords: ['تورم', 'شاخص قیمت', 'نقدینگی', 'پایه پولی', 'رشد اقتصادی', 'بیکاری'],
      signals: ['تورم ماهانه بالا', 'رشد شدید نقدینگی/پایه پولی'],
    },
    why_important: 'تورم/نقدینگی بالا معمولاً تقاضای طلا را تقویت می‌کند.',
    importance_criteria: {
      high_if: ['داده‌ها شوک‌آور یا رکوردی باشد'],
    },
    horizon: 'medium',
  },
  {
    id: 'IR_BUDGET_FISCAL',
    section: 'iran_gold',
    title: 'بودجه، کسری، تامین مالی',
    what_it_is: 'کانال سیاست مالی که انتظارات تورمی و نقدینگی را تغییر می‌دهد.',
    watch_for: {
      keywords: ['بودجه', 'کسری بودجه', 'انتشار اوراق', 'تامین مالی', 'یارانه نقدی'],
      signals: ['کسری بزرگ و روش‌های تامین مالی تورم‌زا'],
    },
    why_important: 'کسری تورم‌زا معمولاً به نفع طلاست.',
    importance_criteria: {
      high_if: ['اعلام سیاست مالی بزرگ یا تغییر ناگهانی'],
    },
    horizon: 'medium',
  },
  {
    id: 'IR_RATES_CREDIT',
    section: 'iran_gold',
    title: 'نرخ سود بانکی، نرخ بهره رسمی',
    what_it_is: 'هزینه پول و جذابیت نگهداری ریال در بانک در برابر طلا.',
    watch_for: {
      keywords: ['نرخ سود', 'سود سپرده', 'شورای پول و اعتبار', 'سود بین بانکی'],
      signals: ['افزایش/کاهش نرخ سود', 'بخشنامه جدید اعتبارات'],
    },
    why_important: 'سود واقعی بالاتر می‌تواند تقاضای طلا را کم کند و بالعکس.',
    importance_criteria: {
      high_if: ['تغییر نرخ سود یا سیاست اعتباری با اثر فوری'],
    },
    horizon: 'short',
  },
  {
    id: 'IR_INTERNAL_POL_SOCIAL',
    section: 'iran_gold',
    title: 'ریسک داخلی (بی‌ثباتی سیاسی/اجتماعی)',
    what_it_is: 'افزایش نااطمینانی داخلی و تقاضای دارایی امن.',
    watch_for: {
      keywords: ['اعتراضات', 'ناآرامی', 'بحران امنیتی', 'ریسک سیاسی'],
      signals: ['گسترش ناآرامی یا رخداد امنیتی مهم'],
    },
    why_important: 'می‌تواند انتظارات ارزی/تورمی را تغییر دهد.',
    importance_criteria: {
      high_if: ['رخداد گسترده یا اثرگذار بر اقتصاد'],
    },
    horizon: 'immediate',
  },
  {
    id: 'IR_FOREIGN_POLICY',
    section: 'iran_gold',
    title: 'روابط خارجی و مذاکرات (برجام/منطقه)',
    what_it_is: 'کانال سیاسی-اقتصادی اصلی برای دلار و انتظارات.',
    watch_for: {
      keywords: ['مذاکرات', 'برجام', 'توافق', 'تحریم جدید', 'قطعنامه'],
      signals: ['پیشرفت/شکست مهم مذاکرات', 'تحریم‌های جدید یا تعلیق تحریم'],
    },
    why_important: 'اثر سریع روی نرخ ارز و در نتیجه طلا.',
    importance_criteria: {
      high_if: ['خبر تاییدشده با اثر فوری بر دسترسی ارزی'],
    },
    horizon: 'immediate',
  },
  {
    id: 'IR_PHYSICAL_SUPPLY_DEMAND',
    section: 'iran_gold',
    title: 'عرضه/تقاضای فیزیکی طلا (واردات، بازیافت، مالیات)',
    what_it_is: 'عوامل بازار فیزیکی که می‌تواند حباب/اختلال ایجاد کند.',
    watch_for: {
      keywords: ['کمبود شمش', 'واردات طلا', 'بازیافت طلا', 'مالیات ارزش افزوده طلا', 'اتحادیه طلافروشان'],
      signals: ['کاهش واردات طلای خام', 'تغییرات مالیاتی/محدودیت‌های معامله'],
    },
    why_important: 'اختلال عرضه یا افزایش هزینه معامله می‌تواند قیمت/حباب را بالا ببرد.',
    importance_criteria: {
      high_if: ['تغییر سیاستی (مالیات/محدودیت) یا کمبود جدی'],
    },
    horizon: 'short',
  },
  {
    id: 'IR_ECON_MANAGEMENT_CHANGES',
    section: 'iran_gold',
    title: 'تغییر مدیران اقتصادی',
    what_it_is: 'شوک انتظارات و احتمال تغییر مسیر سیاست.',
    watch_for: {
      keywords: ['برکناری', 'انتصاب', 'رئیس بانک مرکزی', 'وزیر اقتصاد', 'سازمان برنامه و بودجه'],
      signals: ['تغییرات رسمی در تیم اقتصادی'],
    },
    why_important: 'اثر روانی کوتاه‌مدت و سیگنال سیاستی.',
    importance_criteria: {
      high_if: ['رئیس بانک مرکزی تغییر کند'],
      medium_if: ['تغییرات دیگر تیم اقتصادی'],
    },
    horizon: 'immediate',
  },
  // ── COIN ──
  {
    id: 'COIN_PREMIUM_BUBBLE',
    section: 'coin',
    title: 'حباب سکه (اختلاف قیمت بازار با ارزش ذاتی)',
    what_it_is: 'پریمیوم ناشی از انتظارات تورمی/سفته‌بازی و کمبود عرضه.',
    watch_for: {
      keywords: ['حباب سکه', 'اختلاف ارزش ذاتی', 'پریمیوم سکه'],
      signals: ['افزایش سریع حباب', 'تخلیه سریع حباب', 'رسیدن به سطوح تاریخی'],
    },
    why_important: 'حباب بزرگ ریسک اصلاح را بالا می‌برد.',
    importance_criteria: {
      high_if: ['حباب به سطح غیرعادی/تاریخی برسد'],
    },
    horizon: 'short',
  },
  {
    id: 'COIN_CB_AUCTIONS',
    section: 'coin',
    title: 'حراج/مزایده سکه و پیش‌فروش',
    what_it_is: 'ابزار سیاستی برای افزایش عرضه و کاهش التهاب.',
    watch_for: {
      keywords: ['حراج سکه', 'مزایده سکه', 'پیش فروش سکه', 'بانک کارگشایی', 'مرکز مبادله'],
      signals: ['اعلام تاریخ/حجم/قیمت پایه حراج', 'شرایط پیش‌فروش'],
    },
    why_important: 'عرضه بزرگ می‌تواند حباب را کاهش دهد.',
    importance_criteria: {
      high_if: ['حجم عرضه بزرگ یا شرایط متفاوت از قبل'],
    },
    horizon: 'immediate',
  },
  {
    id: 'COIN_MINT_SUPPLY',
    section: 'coin',
    title: 'تولید و توزیع سکه (ضرابخانه/ظرفیت ضرب)',
    what_it_is: 'سمت عرضه سکه که فقط از کانال رسمی می‌آید.',
    watch_for: {
      keywords: ['ضرابخانه', 'ضرب سکه', 'برنامه ضرب', 'تاخیر توزیع'],
      signals: ['محدود شدن ضرب یا تاخیر توزیع', 'افزایش ظرفیت ضرب'],
    },
    why_important: 'کاهش عرضه سکه می‌تواند قیمت و حباب را بالا ببرد.',
    importance_criteria: {
      high_if: ['کاهش عرضه یا اختلال رسمی تایید شود'],
    },
    horizon: 'short',
  },
  {
    id: 'COIN_SEASONAL_DEMAND',
    section: 'coin',
    title: 'تقاضای فصلی سکه (نوروز/مهریه/عروسی)',
    what_it_is: 'افزایش تقاضای فیزیکی و هدیه/سرمایه‌گذاری در زمان‌های خاص.',
    watch_for: {
      keywords: ['شب عید', 'نوروز', 'محرم', 'صفر', 'مهریه', 'فصل عروسی'],
      signals: ['گزارش افزایش غیرعادی تقاضا یا صف خرید'],
    },
    why_important: 'موج تقاضا می‌تواند قیمت را کوتاه‌مدت بالا ببرد.',
    importance_criteria: {
      medium_if: ['تنها فصلی باشد'],
      high_if: ['همزمان با کمبود عرضه یا شوک ارزی باشد'],
    },
    horizon: 'short',
  },
  {
    id: 'COIN_POLICY_TAX_TARIFF',
    section: 'coin',
    title: 'قوانین/تعرفه/مالیات مرتبط با سکه',
    what_it_is: 'سیاست‌هایی که هزینه معامله و عرضه را تغییر می‌دهند.',
    watch_for: {
      keywords: ['تعرفه گمرکی', 'معافیت مالیاتی', 'بورس کالا', 'گواهی سپرده سکه'],
      signals: ['تعرفه صفر یا تغییر مقررات واردات', 'معافیت مالیاتی یا تغییر کارمزد'],
    },
    why_important: 'می‌تواند عرضه را افزایش یا هزینه‌ها را کاهش دهد.',
    importance_criteria: {
      high_if: ['تغییر قانونی بزرگ تصویب شود'],
    },
    horizon: 'medium',
  },
  {
    id: 'COIN_SENTIMENT_SOCIAL',
    section: 'coin',
    title: 'جو روانی بازار سکه',
    what_it_is: 'موج‌های خبری و شایعات که رفتار جمعی را تحریک می‌کند.',
    watch_for: {
      keywords: ['صف خرید سکه', 'کمبود سکه', 'فروشنده نیست', 'سکه انفجاری'],
      signals: ['ترند شدن واژه‌ها و افزایش ناگهانی حجم گفتگو'],
    },
    why_important: 'می‌تواند حرکت قیمت را تشدید کند.',
    importance_criteria: {
      medium_if: ['بدون تایید از داده/منبع معتبر'],
      high_if: ['همزمان با داده واقعی (دلار/حراج/کمبود)'],
    },
    horizon: 'immediate',
  },
  // ── GOLD FUNDS ──
  {
    id: 'FUNDS_NAV_PREMIUM',
    section: 'gold_funds',
    title: 'NAV صندوق و فاصله قیمت بازار با NAV',
    what_it_is: 'ارزش واقعی دارایی‌ها و انحراف قیمت بازار از آن.',
    watch_for: {
      keywords: ['NAV', 'premium', 'discount', 'ارزش خالص دارایی'],
      signals: ['Premium زیاد', 'Discount زیاد'],
    },
    why_important: 'Premium بالا ریسک اصلاح؛ Discount بالا می‌تواند فرصت باشد.',
    importance_criteria: {
      high_if: ['انحراف شدید یا ناگهانی رخ دهد'],
    },
    horizon: 'short',
  },
  {
    id: 'FUNDS_FLOW_VOLUME',
    section: 'gold_funds',
    title: 'حجم معاملات و ورود/خروج پول به صندوق‌ها',
    what_it_is: 'نشانه ریسک‌گریزی و تقاضای طلا در بازار سرمایه.',
    watch_for: {
      keywords: ['ورود پول', 'خروج پول', 'حجم معاملات', 'صندوق طلا'],
      signals: ['افزایش غیرعادی حجم/ارزش معاملات', 'موج خروج پول'],
    },
    why_important: 'می‌تواند حرکت قیمت صندوق‌ها را تقویت کند.',
    importance_criteria: {
      high_if: ['حجم/ورود پول رکوردی یا غیرعادی باشد'],
    },
    horizon: 'short',
  },
  {
    id: 'FUNDS_CAPITAL_MARKET_NEWS',
    section: 'gold_funds',
    title: 'اخبار بازار سرمایه و مشوق‌های قانونی',
    what_it_is: 'محرک‌های تقاضای صندوق‌ها از مسیر قوانین.',
    watch_for: {
      keywords: ['کارمزد', 'معافیت مالیاتی', 'صندوق جدید طلا', 'قانون جدید بورس'],
      signals: ['مشوق قانونی جدید یا تغییر کارمزد', 'راه‌اندازی صندوق طلا جدید'],
    },
    why_important: 'تغییرات هزینه و دسترسی تقاضا را تغییر می‌دهد.',
    importance_criteria: {
      medium_if: ['خبر جزئی باشد'],
      high_if: ['قانون/مشوق بزرگ باشد'],
    },
    horizon: 'medium',
  },
  {
    id: 'FUNDS_CODAL_NOTICES',
    section: 'gold_funds',
    title: 'اعلانات کدال (افزایش واحدها، تغییر ارکان، توقف/بازگشایی)',
    what_it_is: 'اطلاعیه‌های رسمی که ساختار/نقدشوندگی/قیمت را متاثر می‌کنند.',
    watch_for: {
      keywords: ['کدال', 'افزایش واحد', 'کاهش واحد', 'توقف نماد', 'بازگشایی نماد', 'تغییر امیدنامه'],
      signals: ['Creation/Redemption units', 'توقف یا تغییر ارکان صندوق'],
    },
    why_important: 'می‌تواند Premium را تعدیل کند یا ریسک اجرایی ایجاد کند.',
    importance_criteria: {
      high_if: ['توقف نماد یا تغییرات ساختاری'],
      medium_if: ['افزایش واحدها برای کاهش Premium'],
    },
    horizon: 'short',
  },
];

export const technicalSignals: TechnicalSignal[] = [
  {
    id: 'TECH_SUPPORT_RESIST_BREAK',
    name: 'شکست حمایت/مقاومت',
    what_to_compute: 'تشخیص شکست سطوح کلیدی (به‌خصوص سطوح تاریخی/روانی).',
    alert_when: ['شکست سطح کلیدی با تایید (مثلاً بسته شدن کندل بالای سطح)'],
    importance: 'high',
  },
  {
    id: 'TECH_RSI_EXTREMES',
    name: 'اشباع خرید/فروش و واگرایی RSI',
    what_to_compute: 'RSI > 70 یا RSI < 30 و واگرایی‌ها.',
    alert_when: ['همزمان با خبر فاندامنتال یا شکست سطح'],
    importance: 'medium',
  },
  {
    id: 'TECH_MACD_CROSS',
    name: 'کراس MACD',
    what_to_compute: 'کراس‌های مهم MACD در تایم‌فریم روزانه/هفتگی.',
    importance: 'low',
  },
  {
    id: 'TECH_MA_200',
    name: 'عبور از میانگین متحرک ۲۰۰',
    what_to_compute: 'عبور قیمت از MA200 و تثبیت.',
    importance: 'medium',
  },
  {
    id: 'TECH_VOLATILITY_SHOCK',
    name: 'شوک نوسان',
    what_to_compute: 'حرکت‌های بسیار بزرگ نسبت به میانگین نوسان.',
    importance: 'high',
  },
];

export function getRulesBySection(section: RuleSection): Rule[] {
  return rules.filter((r) => r.section === section);
}

export function getRuleById(id: string): Rule | undefined {
  return rules.find((r) => r.id === id);
}
