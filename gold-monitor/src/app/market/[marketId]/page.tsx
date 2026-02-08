'use client';

import { useMemo, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { AssetId } from '@/types';
import { useApp } from '@/context/AppContext';
import { mockAlerts } from '@/data/mock-alerts';
import { mockMarkets } from '@/data/mock-markets';
import { rules, technicalSignals, getRulesBySection } from '@/data/rules';
import { filterAlerts, sortAlertsBySeverity, cn } from '@/lib/utils';
import { ASSET_CONFIG, SEVERITY_CONFIG } from '@/lib/constants';
import Card from '@/components/ui/Card';
import AlertCard from '@/components/ui/AlertCard';
import SeverityBadge from '@/components/ui/SeverityBadge';
import Tooltip from '@/components/ui/Tooltip';
import { GLOSSARY } from '@/lib/constants';

type Tab = 'alerts' | 'technical' | 'fundamental';

export default function MarketPage() {
  const params = useParams();
  const marketId = params.marketId as AssetId;
  const [activeTab, setActiveTab] = useState<Tab>('alerts');

  const market = mockMarkets.find((m) => m.id === marketId);
  const assetConfig = ASSET_CONFIG[marketId];

  const marketAlerts = useMemo(() => {
    return sortAlertsBySeverity(
      mockAlerts.filter((a) => a.expected_impact.some((i) => i.asset === marketId))
    );
  }, [marketId]);

  const topAlerts = marketAlerts.slice(0, 5);

  const sectionRules = useMemo(() => {
    return getRulesBySection(marketId);
  }, [marketId]);

  if (!market || !assetConfig) {
    return (
      <div className="py-20 text-center">
        <p className="text-gray-500 dark:text-gray-400">بازار مورد نظر یافت نشد.</p>
        <Link href="/" className="mt-4 inline-block text-sm text-amber-600 hover:text-amber-700">
          بازگشت به داشبورد
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-xs text-gray-400 dark:text-gray-500">
        <Link href="/" className="hover:text-gray-600 dark:hover:text-gray-300">داشبورد</Link>
        <span>/</span>
        <span className="text-gray-700 dark:text-gray-200">{market.name}</span>
      </div>

      {/* Market header */}
      <Card padding="lg">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="mb-1 flex items-center gap-2">
              <span className="text-2xl">{assetConfig.icon}</span>
              <h1 className="text-lg font-bold text-gray-900 dark:text-gray-100 sm:text-xl">
                {market.name}
              </h1>
              <span className="text-xs text-gray-400 dark:text-gray-500">({market.nameEn})</span>
            </div>
            <p className="text-sm text-gray-500 dark:text-gray-400">{market.trend}</p>
          </div>
          <div className="text-left sm:text-right">
            <p className="text-2xl font-bold text-gray-900 dark:text-gray-100 sm:text-3xl">
              {market.price}
            </p>
            <div className="mt-1 flex items-center gap-2">
              <span
                className={cn(
                  'text-sm font-medium',
                  market.isPositive ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'
                )}
              >
                {market.change}
              </span>
              <span
                className={cn(
                  'rounded px-1.5 py-0.5 text-xs font-medium',
                  market.isPositive
                    ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-400'
                    : 'bg-red-50 text-red-700 dark:bg-red-950/30 dark:text-red-400'
                )}
              >
                {market.changePercent}
              </span>
            </div>
          </div>
        </div>
      </Card>

      {/* Top 5 alerts for this market */}
      <div>
        <h2 className="mb-3 text-base font-bold text-gray-900 dark:text-gray-100">
          ۵ هشدار مهم {assetConfig.nameShort}
        </h2>
        <div className="space-y-2">
          {topAlerts.map((alert) => (
            <AlertCard key={alert.id} alert={alert} />
          ))}
          {topAlerts.length === 0 && (
            <p className="py-8 text-center text-sm text-gray-400 dark:text-gray-500">هشداری یافت نشد.</p>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200 dark:border-gray-700">
        <nav className="flex gap-1">
          {[
            { id: 'alerts' as Tab, label: 'اخبار / هشدارها' },
            { id: 'technical' as Tab, label: 'تکنیکال' },
            { id: 'fundamental' as Tab, label: 'فاندامنتال' },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                'border-b-2 px-4 py-2.5 text-sm font-medium transition-colors',
                activeTab === tab.id
                  ? 'border-amber-500 text-amber-700 dark:border-amber-400 dark:text-amber-300'
                  : 'border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
              )}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Tab content */}
      {activeTab === 'alerts' && (
        <div className="space-y-2">
          {marketAlerts.map((alert) => (
            <AlertCard key={alert.id} alert={alert} />
          ))}
        </div>
      )}

      {activeTab === 'technical' && (
        <div className="space-y-4">
          <Card>
            <h3 className="mb-3 text-sm font-semibold text-gray-900 dark:text-gray-100">
              سطوح کلیدی
            </h3>
            <div className="overflow-hidden rounded-lg border border-gray-200 dark:border-gray-700">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50 dark:bg-gray-800/50">
                    <th className="px-4 py-2 text-right font-medium text-gray-600 dark:text-gray-300">سطح</th>
                    <th className="px-4 py-2 text-right font-medium text-gray-600 dark:text-gray-300">قیمت</th>
                    <th className="px-4 py-2 text-right font-medium text-gray-600 dark:text-gray-300">وضعیت</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 dark:divide-gray-700/50">
                  <tr>
                    <td className="px-4 py-2 text-gray-800 dark:text-gray-200">مقاومت ۲</td>
                    <td className="px-4 py-2">۲,۸۰۰</td>
                    <td className="px-4 py-2 text-red-500">فعال</td>
                  </tr>
                  <tr>
                    <td className="px-4 py-2 text-gray-800 dark:text-gray-200">مقاومت ۱</td>
                    <td className="px-4 py-2">۲,۷۰۰</td>
                    <td className="px-4 py-2 text-emerald-500">شکسته شده</td>
                  </tr>
                  <tr>
                    <td className="px-4 py-2 text-gray-800 dark:text-gray-200">حمایت ۱</td>
                    <td className="px-4 py-2">۲,۶۵۰</td>
                    <td className="px-4 py-2 text-blue-500">فعال</td>
                  </tr>
                  <tr>
                    <td className="px-4 py-2 text-gray-800 dark:text-gray-200">حمایت ۲</td>
                    <td className="px-4 py-2">۲,۶۰۰</td>
                    <td className="px-4 py-2 text-blue-500">فعال</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </Card>

          <Card>
            <h3 className="mb-3 text-sm font-semibold text-gray-900 dark:text-gray-100">
              سیگنال‌های تکنیکال
            </h3>
            <div className="space-y-2">
              {technicalSignals.map((signal) => (
                <div
                  key={signal.id}
                  className="flex items-center justify-between rounded-lg bg-gray-50 p-3 dark:bg-gray-800/50"
                >
                  <div>
                    <p className="text-sm font-medium text-gray-800 dark:text-gray-200">
                      {signal.name}
                    </p>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      {signal.what_to_compute}
                    </p>
                  </div>
                  <SeverityBadge severity={signal.importance} size="sm" />
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}

      {activeTab === 'fundamental' && (
        <div className="space-y-3">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            عوامل بنیادی تاثیرگذار بر {assetConfig.nameShort}:
          </p>
          {sectionRules.map((rule) => (
            <Card key={rule.id} padding="sm">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                    {rule.title}
                  </h4>
                  <p className="mt-1 text-xs leading-5 text-gray-500 dark:text-gray-400">
                    {rule.what_it_is}
                  </p>
                  <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">
                    {rule.why_important}
                  </p>
                </div>
              </div>
            </Card>
          ))}
          {sectionRules.length === 0 && (
            <p className="py-8 text-center text-sm text-gray-400">
              قوانین مرتبط در بخش
              <Link href="/library" className="mr-1 text-amber-600 hover:text-amber-700 dark:text-amber-400">
                کتابخانه قوانین
              </Link>
              موجود است.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
