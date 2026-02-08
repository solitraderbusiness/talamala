'use client';

import { CauseEffect as CauseEffectType } from '@/types';
import { cn } from '@/lib/utils';

interface CauseEffectProps {
  items: CauseEffectType[];
}

export default function CauseEffect({ items }: CauseEffectProps) {
  return (
    <div className="space-y-3">
      {items.map((item, idx) => (
        <div
          key={idx}
          className="flex items-center gap-2 overflow-x-auto rounded-lg bg-gray-50 p-3 text-sm dark:bg-gray-800/50"
        >
          <span className="shrink-0 rounded-md bg-blue-100 px-2 py-1 text-xs font-medium text-blue-800 dark:bg-blue-900/40 dark:text-blue-300">
            {item.trigger}
          </span>
          <svg className="h-4 w-4 shrink-0 rotate-180 text-gray-400 rtl:rotate-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M10 19l-7-7m0 0l7-7m-7 7h18" />
          </svg>
          <span className="shrink-0 rounded-md bg-purple-100 px-2 py-1 text-xs font-medium text-purple-800 dark:bg-purple-900/40 dark:text-purple-300">
            {item.mechanism}
          </span>
          <svg className="h-4 w-4 shrink-0 rotate-180 text-gray-400 rtl:rotate-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M10 19l-7-7m0 0l7-7m-7 7h18" />
          </svg>
          <span className="shrink-0 rounded-md bg-amber-100 px-2 py-1 text-xs font-medium text-amber-800 dark:bg-amber-900/40 dark:text-amber-300">
            {item.effect}
          </span>
        </div>
      ))}
    </div>
  );
}
