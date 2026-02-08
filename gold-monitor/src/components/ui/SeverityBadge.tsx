'use client';

import { Severity } from '@/types';
import { SEVERITY_CONFIG } from '@/lib/constants';
import { cn } from '@/lib/utils';

interface SeverityBadgeProps {
  severity: Severity;
  size?: 'sm' | 'md';
}

export default function SeverityBadge({ severity, size = 'md' }: SeverityBadgeProps) {
  const config = SEVERITY_CONFIG[severity];
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full font-medium',
        config.bgLight,
        config.bgDark,
        config.color,
        size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-3 py-1 text-sm'
      )}
    >
      <span
        className={cn(
          'inline-block rounded-full',
          size === 'sm' ? 'ml-1 h-1.5 w-1.5' : 'ml-1.5 h-2 w-2',
          severity === 'high' && 'bg-red-500',
          severity === 'medium' && 'bg-amber-500',
          severity === 'low' && 'bg-gray-400'
        )}
      />
      {config.label}
    </span>
  );
}
