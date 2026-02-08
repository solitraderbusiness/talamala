'use client';

import { useMemo } from 'react';
import { useApp } from '@/context/AppContext';
import { mockAlerts } from '@/data/mock-alerts';
import { mockMarkets } from '@/data/mock-markets';
import { filterAlerts, getTopAlerts, calculateRiskScore, sortAlertsBySeverity } from '@/lib/utils';
import { CauseEffect as CauseEffectType } from '@/types';
import TopAlerts from '@/components/dashboard/TopAlerts';
import MarketOverview from '@/components/dashboard/MarketOverview';
import FilterBar from '@/components/ui/FilterBar';
import TimelineFeed from '@/components/ui/TimelineFeed';
import RiskGauge from '@/components/ui/RiskGauge';
import CauseEffect from '@/components/ui/CauseEffect';
import Card from '@/components/ui/Card';

const causeEffectExamples: CauseEffectType[] = [
  {
    trigger: 'کاهش نرخ بهره فدرال رزرو',
    mechanism: 'کاهش بازده اوراق + تضعیف دلار',
    effect: 'حمایت از قیمت طلای جهانی',
  },
  {
    trigger: 'جهش دلار آزاد',
    mechanism: 'افزایش قیمت ریالی اونس',
    effect: 'رشد قیمت طلا و سکه در ایران',
  },
  {
    trigger: 'تشدید تنش‌های ژئوپلیتیک',
    mechanism: 'افزایش ریسک‌گریزی جهانی',
    effect: 'هجوم به طلا به عنوان دارایی امن',
  },
];

export default function DashboardPage() {
  const { filters } = useApp();

  const filteredAlerts = useMemo(() => {
    return sortAlertsBySeverity(filterAlerts(mockAlerts, filters));
  }, [filters]);

  const topAlerts = useMemo(() => getTopAlerts(mockAlerts, 3), []);
  const riskScore = useMemo(() => calculateRiskScore(mockAlerts), []);

  return (
    <div className="space-y-6">
      {/* Market prices overview */}
      <MarketOverview markets={mockMarkets} />

      {/* Top 3 alerts */}
      <TopAlerts alerts={topAlerts} />

      {/* Main content grid */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* Left column: Timeline feed */}
        <div className="lg:col-span-2">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-base font-bold text-gray-900 dark:text-gray-100 sm:text-lg">
              فید هشدارها
            </h2>
            <span className="text-xs text-gray-400 dark:text-gray-500">
              {filteredAlerts.length} هشدار
            </span>
          </div>

          <div className="mb-4">
            <FilterBar />
          </div>

          <TimelineFeed alerts={filteredAlerts} grouped />
        </div>

        {/* Right column: Risk score + Cause-Effect */}
        <div className="space-y-4">
          {/* Risk Score */}
          <Card>
            <h3 className="mb-3 text-sm font-semibold text-gray-900 dark:text-gray-100">
              امتیاز ریسک امروز
            </h3>
            <RiskGauge score={riskScore} />
          </Card>

          {/* Cause-Effect Map */}
          <Card>
            <h3 className="mb-3 text-sm font-semibold text-gray-900 dark:text-gray-100">
              نقشه علت و معلول
            </h3>
            <p className="mb-3 text-xs text-gray-500 dark:text-gray-400">
              نمایش ساده مسیر اثرگذاری رویدادهای مهم امروز بر بازار
            </p>
            <CauseEffect items={causeEffectExamples} />
          </Card>
        </div>
      </div>
    </div>
  );
}
