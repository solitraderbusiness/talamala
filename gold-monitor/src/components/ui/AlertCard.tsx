'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Alert } from '@/types';
import { useApp } from '@/context/AppContext';
import { formatPersianDate } from '@/lib/utils';
import { cn } from '@/lib/utils';
import Card from './Card';
import SeverityBadge from './SeverityBadge';
import HorizonBadge from './HorizonBadge';
import ImpactMatrix from './ImpactMatrix';
import DirectionIndicator from './DirectionIndicator';

interface AlertCardProps {
  alert: Alert;
}

export default function AlertCard({ alert }: AlertCardProps) {
  const [expanded, setExpanded] = useState(false);
  const { viewMode } = useApp();

  const isQuick = viewMode === 'quick';

  return (
    <Card
      className={cn(
        'transition-all',
        alert.severity === 'high' && 'border-r-4 border-r-red-400 dark:border-r-red-500',
        alert.severity === 'medium' && 'border-r-4 border-r-amber-400 dark:border-r-amber-500'
      )}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="mb-1.5 flex flex-wrap items-center gap-2">
            <SeverityBadge severity={alert.severity} size="sm" />
            <HorizonBadge horizon={alert.time_horizon} />
            <span className="text-xs text-gray-400 dark:text-gray-500">
              {formatPersianDate(alert.timestamp_utc)}
            </span>
          </div>
          <h3 className="text-sm font-semibold leading-6 text-gray-900 dark:text-gray-100 sm:text-base">
            {alert.title}
          </h3>
        </div>
      </div>

      {/* Quick mode: just show direction indicators */}
      {isQuick && !expanded && (
        <div className="mt-3">
          <ImpactMatrix impacts={alert.expected_impact} compact />
        </div>
      )}

      {/* Summary (always visible) */}
      {(!isQuick || expanded) && (
        <p className="mt-2 text-sm leading-6 text-gray-600 dark:text-gray-400">
          {alert.summary_fa}
        </p>
      )}

      {/* Why important */}
      {(!isQuick || expanded) && (
        <div className="mt-3 rounded-lg bg-amber-50/50 p-3 dark:bg-amber-950/20">
          <p className="text-xs font-medium text-amber-800 dark:text-amber-300">
            چرا مهم است؟
          </p>
          <p className="mt-1 text-xs leading-5 text-amber-700 dark:text-amber-400">
            {alert.why_important_fa}
          </p>
        </div>
      )}

      {/* Expanded impact matrix */}
      {expanded && (
        <div className="mt-3">
          <ImpactMatrix impacts={alert.expected_impact} />
        </div>
      )}

      {/* Professional mode extras */}
      {expanded && viewMode === 'professional' && (
        <div className="mt-3 space-y-2 border-t border-gray-100 pt-3 dark:border-gray-800">
          <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
            <span>اطمینان:</span>
            <div className="h-1.5 w-20 overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
              <div
                className="h-full rounded-full bg-amber-400"
                style={{ width: `${alert.confidence}%` }}
              />
            </div>
            <span>{alert.confidence}%</span>
          </div>
          <div className="flex flex-wrap gap-1">
            <span className="text-xs text-gray-400">Rule IDs:</span>
            {alert.matched_rule_ids.map((rid) => (
              <span
                key={rid}
                className="rounded bg-gray-100 px-1.5 py-0.5 font-mono text-[10px] text-gray-500 dark:bg-gray-800 dark:text-gray-400"
              >
                {rid}
              </span>
            ))}
          </div>
          <p className="text-xs text-gray-400 dark:text-gray-500">
            منبع: {alert.source_name}
          </p>
        </div>
      )}

      {/* Footer */}
      <div className="mt-3 flex items-center gap-3">
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-xs font-medium text-amber-600 hover:text-amber-700 dark:text-amber-400 dark:hover:text-amber-300"
        >
          {expanded ? 'کمتر' : 'بیشتر'}
        </button>
        <Link
          href={`/alert/${alert.id}`}
          className="text-xs font-medium text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
        >
          مشاهده جزئیات
        </Link>
        {!isQuick && (
          <span className="mr-auto text-xs text-gray-400 dark:text-gray-500">
            {alert.source_name}
          </span>
        )}
      </div>
    </Card>
  );
}
