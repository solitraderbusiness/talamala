'use client';

import Link from 'next/link';
import { Alert } from '@/types';
import { ASSET_CONFIG, DIRECTION_CONFIG, HORIZON_CONFIG } from '@/lib/constants';
import { cn, formatPersianDate } from '@/lib/utils';
import SeverityBadge from '@/components/ui/SeverityBadge';

interface TopAlertsProps {
  alerts: Alert[];
}

export default function TopAlerts({ alerts }: TopAlertsProps) {
  return (
    <section>
      <div className="mb-4 flex items-center gap-2">
        <h2 className="text-base font-bold text-gray-900 dark:text-gray-100 sm:text-lg">
          ۳ چیز مهم امروز
        </h2>
        <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-700 dark:bg-red-950/40 dark:text-red-400">
          توجه
        </span>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        {alerts.map((alert, idx) => (
          <Link
            key={alert.id}
            href={`/alert/${alert.id}`}
            className={cn(
              'group relative overflow-hidden rounded-xl border p-4 transition-all',
              'hover:shadow-lg',
              idx === 0 && 'border-red-200 bg-red-50/50 dark:border-red-800/50 dark:bg-red-950/20',
              idx === 1 && 'border-amber-200 bg-amber-50/50 dark:border-amber-800/50 dark:bg-amber-950/20',
              idx === 2 && 'border-orange-200 bg-orange-50/50 dark:border-orange-800/50 dark:bg-orange-950/20'
            )}
          >
            {/* Number badge */}
            <div
              className={cn(
                'absolute left-3 top-3 flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold text-white',
                idx === 0 && 'bg-red-500',
                idx === 1 && 'bg-amber-500',
                idx === 2 && 'bg-orange-500'
              )}
            >
              {idx + 1}
            </div>

            <div className="mb-2 flex items-center gap-2">
              <SeverityBadge severity={alert.severity} size="sm" />
              <span className="text-[10px] text-gray-400 dark:text-gray-500">
                {formatPersianDate(alert.timestamp_utc)}
              </span>
            </div>

            <h3 className="mb-2 text-sm font-semibold leading-6 text-gray-900 dark:text-gray-100">
              {alert.title}
            </h3>

            <p className="mb-3 text-xs leading-5 text-gray-600 dark:text-gray-400">
              {alert.why_important_fa.slice(0, 100)}...
            </p>

            {/* Compact impact indicators */}
            <div className="mb-2 flex flex-wrap gap-1.5">
              {alert.expected_impact.map((impact) => {
                const dir = DIRECTION_CONFIG[impact.direction];
                const asset = ASSET_CONFIG[impact.asset];
                return (
                  <span
                    key={impact.asset}
                    className={cn(
                      'inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 text-[10px]',
                      'bg-white/60 dark:bg-gray-900/40'
                    )}
                    title={impact.mechanism}
                  >
                    <span>{asset.icon}</span>
                    <span className={cn('font-medium', dir.color)}>{dir.icon}</span>
                  </span>
                );
              })}
            </div>

            <div className="flex items-center gap-2">
              <span className="rounded bg-blue-100/60 px-1.5 py-0.5 text-[10px] text-blue-700 dark:bg-blue-900/30 dark:text-blue-400">
                {HORIZON_CONFIG[alert.time_horizon].label}
              </span>
              <span className="mr-auto text-[10px] text-gray-400 group-hover:text-amber-600 dark:text-gray-500 dark:group-hover:text-amber-400">
                مشاهده جزئیات ←
              </span>
            </div>
          </Link>
        ))}
      </div>
    </section>
  );
}
