'use client';

import { TimeHorizon } from '@/types';
import { HORIZON_CONFIG } from '@/lib/constants';
import { cn } from '@/lib/utils';

interface HorizonBadgeProps {
  horizon: TimeHorizon;
  showDescription?: boolean;
}

export default function HorizonBadge({ horizon, showDescription = false }: HorizonBadgeProps) {
  const config = HORIZON_CONFIG[horizon];
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium',
        'bg-blue-50 text-blue-700 dark:bg-blue-950/30 dark:text-blue-400'
      )}
      title={config.description}
    >
      <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
      {config.label}
      {showDescription && <span className="text-blue-500 dark:text-blue-300">({config.description})</span>}
    </span>
  );
}
