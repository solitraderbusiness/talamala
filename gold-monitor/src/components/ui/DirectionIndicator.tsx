'use client';

import { Direction } from '@/types';
import { DIRECTION_CONFIG } from '@/lib/constants';
import { cn } from '@/lib/utils';

interface DirectionIndicatorProps {
  direction: Direction;
  size?: 'sm' | 'md';
}

export default function DirectionIndicator({ direction, size = 'md' }: DirectionIndicatorProps) {
  const config = DIRECTION_CONFIG[direction];
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 font-medium',
        config.color,
        size === 'sm' ? 'text-xs' : 'text-sm'
      )}
    >
      <span className={size === 'sm' ? 'text-xs' : 'text-base'}>{config.icon}</span>
      {config.label}
    </span>
  );
}
