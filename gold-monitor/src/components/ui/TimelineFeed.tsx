'use client';

import { useState } from 'react';
import { Alert } from '@/types';
import { groupAlertsByTopic } from '@/lib/utils';
import { cn } from '@/lib/utils';
import AlertCard from './AlertCard';

interface TimelineFeedProps {
  alerts: Alert[];
  grouped?: boolean;
}

export default function TimelineFeed({ alerts, grouped = true }: TimelineFeedProps) {
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());

  const toggleGroup = (group: string) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(group)) next.delete(group);
      else next.add(group);
      return next;
    });
  };

  if (!grouped) {
    return (
      <div className="space-y-3">
        {alerts.map((alert) => (
          <AlertCard key={alert.id} alert={alert} />
        ))}
        {alerts.length === 0 && (
          <div className="py-12 text-center text-sm text-gray-400 dark:text-gray-500">
            هشداری با فیلترهای انتخاب‌شده یافت نشد.
          </div>
        )}
      </div>
    );
  }

  const groups = groupAlertsByTopic(alerts);
  const groupEntries = Object.entries(groups).sort((a, b) => {
    // Sort by highest severity in group
    const getMaxSeverity = (alerts: Alert[]) => {
      if (alerts.some((a) => a.severity === 'high')) return 0;
      if (alerts.some((a) => a.severity === 'medium')) return 1;
      return 2;
    };
    return getMaxSeverity(a[1]) - getMaxSeverity(b[1]);
  });

  return (
    <div className="space-y-4">
      {groupEntries.map(([groupName, groupAlerts]) => {
        const isCollapsed = collapsedGroups.has(groupName);
        const highCount = groupAlerts.filter((a) => a.severity === 'high').length;
        const medCount = groupAlerts.filter((a) => a.severity === 'medium').length;

        return (
          <div key={groupName} className="space-y-2">
            <button
              onClick={() => toggleGroup(groupName)}
              className={cn(
                'flex w-full items-center gap-2 rounded-lg px-3 py-2 text-right transition-colors',
                'hover:bg-gray-100 dark:hover:bg-gray-800'
              )}
            >
              <svg
                className={cn(
                  'h-4 w-4 text-gray-400 transition-transform',
                  isCollapsed && '-rotate-90'
                )}
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
              </svg>
              <span className="text-sm font-semibold text-gray-700 dark:text-gray-200">
                {groupName}
              </span>
              <span className="text-xs text-gray-400 dark:text-gray-500">
                ({groupAlerts.length} هشدار)
              </span>
              {highCount > 0 && (
                <span className="rounded-full bg-red-100 px-1.5 py-0.5 text-[10px] font-medium text-red-600 dark:bg-red-950/40 dark:text-red-400">
                  {highCount} بحرانی
                </span>
              )}
              {medCount > 0 && (
                <span className="rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-600 dark:bg-amber-950/40 dark:text-amber-400">
                  {medCount} مهم
                </span>
              )}
            </button>
            {!isCollapsed && (
              <div className="space-y-2 pr-2 sm:pr-4">
                {groupAlerts.map((alert) => (
                  <AlertCard key={alert.id} alert={alert} />
                ))}
              </div>
            )}
          </div>
        );
      })}
      {alerts.length === 0 && (
        <div className="py-12 text-center text-sm text-gray-400 dark:text-gray-500">
          هشداری با فیلترهای انتخاب‌شده یافت نشد.
        </div>
      )}
    </div>
  );
}
