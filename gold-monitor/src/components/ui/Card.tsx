'use client';

import { ReactNode } from 'react';
import { cn } from '@/lib/utils';

interface CardProps {
  children: ReactNode;
  className?: string;
  onClick?: () => void;
  hover?: boolean;
  padding?: 'sm' | 'md' | 'lg';
}

export default function Card({ children, className, onClick, hover = false, padding = 'md' }: CardProps) {
  return (
    <div
      className={cn(
        'rounded-xl border border-gray-200 bg-white dark:border-gray-700/50 dark:bg-gray-900',
        hover && 'cursor-pointer transition-all hover:border-gray-300 hover:shadow-md dark:hover:border-gray-600',
        padding === 'sm' && 'p-3',
        padding === 'md' && 'p-4 sm:p-5',
        padding === 'lg' && 'p-5 sm:p-6',
        className
      )}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
    >
      {children}
    </div>
  );
}
