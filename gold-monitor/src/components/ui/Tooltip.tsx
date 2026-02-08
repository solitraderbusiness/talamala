'use client';

import { useState, ReactNode } from 'react';
import { cn } from '@/lib/utils';

interface TooltipProps {
  content: string;
  children: ReactNode;
}

export default function Tooltip({ content, children }: TooltipProps) {
  const [show, setShow] = useState(false);

  return (
    <span
      className="relative inline-block"
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
      onTouchStart={() => setShow((s) => !s)}
    >
      <span className="cursor-help border-b border-dashed border-gray-400 dark:border-gray-500">
        {children}
      </span>
      {show && (
        <span
          className={cn(
            'absolute bottom-full right-1/2 z-50 mb-2 w-max max-w-[250px] translate-x-1/2',
            'rounded-lg bg-gray-900 px-3 py-2 text-xs text-white shadow-lg',
            'dark:bg-gray-100 dark:text-gray-900'
          )}
        >
          {content}
          <span
            className={cn(
              'absolute top-full right-1/2 -translate-y-0 translate-x-1/2',
              'border-4 border-transparent border-t-gray-900 dark:border-t-gray-100'
            )}
          />
        </span>
      )}
    </span>
  );
}
