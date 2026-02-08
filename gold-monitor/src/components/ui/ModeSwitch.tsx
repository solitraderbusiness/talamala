'use client';

import { useApp } from '@/context/AppContext';
import { cn } from '@/lib/utils';

export default function ModeSwitch() {
  const { viewMode, setViewMode } = useApp();

  return (
    <div className="flex items-center gap-1 rounded-lg border border-gray-200 p-1 dark:border-gray-700">
      <button
        onClick={() => setViewMode('quick')}
        className={cn(
          'rounded-md px-3 py-1 text-xs font-medium transition-colors',
          viewMode === 'quick'
            ? 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300'
            : 'text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800'
        )}
      >
        کوتاه و سریع
      </button>
      <button
        onClick={() => setViewMode('professional')}
        className={cn(
          'rounded-md px-3 py-1 text-xs font-medium transition-colors',
          viewMode === 'professional'
            ? 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300'
            : 'text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800'
        )}
      >
        حرفه‌ای
      </button>
    </div>
  );
}
