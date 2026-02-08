'use client';

import Link from 'next/link';
import { MarketInfo } from '@/types';
import { cn } from '@/lib/utils';

interface MarketOverviewProps {
  markets: MarketInfo[];
}

export default function MarketOverview({ markets }: MarketOverviewProps) {
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 sm:gap-3">
      {markets.map((market) => (
        <Link
          key={market.id}
          href={`/market/${market.id}`}
          className={cn(
            'group rounded-xl border border-gray-200 bg-white p-3 transition-all sm:p-4',
            'hover:border-gray-300 hover:shadow-md',
            'dark:border-gray-700/50 dark:bg-gray-900 dark:hover:border-gray-600'
          )}
        >
          <p className="mb-1 text-[11px] text-gray-500 dark:text-gray-400">{market.name}</p>
          <p className="text-base font-bold text-gray-900 dark:text-gray-100 sm:text-lg">
            {market.price}
          </p>
          <div className="mt-1 flex items-center gap-1.5">
            <span
              className={cn(
                'text-xs font-medium',
                market.isPositive
                  ? 'text-emerald-600 dark:text-emerald-400'
                  : 'text-red-600 dark:text-red-400'
              )}
            >
              {market.change}
            </span>
            <span
              className={cn(
                'rounded px-1 py-0.5 text-[10px] font-medium',
                market.isPositive
                  ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-400'
                  : 'bg-red-50 text-red-700 dark:bg-red-950/30 dark:text-red-400'
              )}
            >
              {market.changePercent}
            </span>
          </div>
        </Link>
      ))}
    </div>
  );
}
