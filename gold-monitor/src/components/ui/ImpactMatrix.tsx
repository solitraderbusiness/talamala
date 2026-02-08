'use client';

import { AssetImpact } from '@/types';
import { ASSET_CONFIG, DIRECTION_CONFIG } from '@/lib/constants';
import { cn } from '@/lib/utils';
import { useApp } from '@/context/AppContext';

interface ImpactMatrixProps {
  impacts: AssetImpact[];
  compact?: boolean;
}

export default function ImpactMatrix({ impacts, compact = false }: ImpactMatrixProps) {
  const { viewMode } = useApp();

  if (compact) {
    return (
      <div className="flex flex-wrap gap-2">
        {impacts.map((impact) => {
          const dirConfig = DIRECTION_CONFIG[impact.direction];
          const assetConfig = ASSET_CONFIG[impact.asset];
          return (
            <span
              key={impact.asset}
              className={cn(
                'inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs',
                'bg-gray-50 dark:bg-gray-800/50'
              )}
              title={impact.mechanism}
            >
              <span>{assetConfig.icon}</span>
              <span className="text-gray-600 dark:text-gray-300">{assetConfig.nameShort}</span>
              <span className={cn('font-medium', dirConfig.color)}>
                {dirConfig.icon} {dirConfig.label}
              </span>
            </span>
          );
        })}
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-lg border border-gray-200 dark:border-gray-700">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-gray-50 dark:bg-gray-800/50">
            <th className="px-3 py-2 text-right font-medium text-gray-600 dark:text-gray-300">دارایی</th>
            <th className="px-3 py-2 text-right font-medium text-gray-600 dark:text-gray-300">جهت</th>
            {viewMode === 'professional' && (
              <th className="px-3 py-2 text-right font-medium text-gray-600 dark:text-gray-300">مکانیزم</th>
            )}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100 dark:divide-gray-700/50">
          {impacts.map((impact) => {
            const dirConfig = DIRECTION_CONFIG[impact.direction];
            const assetConfig = ASSET_CONFIG[impact.asset];
            return (
              <tr key={impact.asset} className="hover:bg-gray-50/50 dark:hover:bg-gray-800/30">
                <td className="px-3 py-2">
                  <span className="flex items-center gap-1.5">
                    <span>{assetConfig.icon}</span>
                    <span className="text-gray-800 dark:text-gray-200">{assetConfig.nameShort}</span>
                  </span>
                </td>
                <td className="px-3 py-2">
                  <span className={cn('flex items-center gap-1 font-medium', dirConfig.color)}>
                    {dirConfig.icon} {dirConfig.label}
                  </span>
                </td>
                {viewMode === 'professional' && (
                  <td className="px-3 py-2 text-xs text-gray-500 dark:text-gray-400">
                    {impact.mechanism}
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
