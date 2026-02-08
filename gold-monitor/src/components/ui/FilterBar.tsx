'use client';

import { useApp } from '@/context/AppContext';
import { SEVERITY_CONFIG, ASSET_CONFIG, HORIZON_CONFIG, TIME_RANGES, MARKET_OPTIONS } from '@/lib/constants';
import { Severity, AssetId, TimeHorizon } from '@/types';
import { cn } from '@/lib/utils';
import SearchInput from './SearchInput';

interface FilterBarProps {
  showMarketFilter?: boolean;
  showTimeRange?: boolean;
  compact?: boolean;
}

export default function FilterBar({ showMarketFilter = true, showTimeRange = true, compact = false }: FilterBarProps) {
  const {
    filters,
    toggleSeverityFilter,
    toggleAssetFilter,
    toggleHorizonFilter,
    setSearchQuery,
    setTimeRange,
    setSelectedMarket,
    resetFilters,
    watchlist,
    applyWatchlist,
  } = useApp();

  return (
    <div className={cn('space-y-3', compact && 'space-y-2')}>
      {/* Search */}
      <SearchInput
        value={filters.searchQuery}
        onChange={setSearchQuery}
        placeholder="جستجو در هشدارها..."
      />

      <div className="flex flex-wrap items-center gap-2">
        {/* Time range */}
        {showTimeRange && (
          <div className="flex items-center gap-1 rounded-lg border border-gray-200 p-1 dark:border-gray-700">
            {TIME_RANGES.map((tr) => (
              <button
                key={tr.id}
                onClick={() => setTimeRange(tr.id)}
                className={cn(
                  'rounded-md px-2.5 py-1 text-xs font-medium transition-colors',
                  filters.timeRange === tr.id
                    ? 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300'
                    : 'text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800'
                )}
              >
                {tr.label}
              </button>
            ))}
          </div>
        )}

        {/* Market filter */}
        {showMarketFilter && (
          <div className="flex items-center gap-1 rounded-lg border border-gray-200 p-1 dark:border-gray-700">
            {MARKET_OPTIONS.map((m) => (
              <button
                key={m.id}
                onClick={() => setSelectedMarket(m.id)}
                className={cn(
                  'rounded-md px-2.5 py-1 text-xs font-medium transition-colors',
                  filters.selectedMarket === m.id
                    ? 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300'
                    : 'text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800'
                )}
              >
                {m.label}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {/* Severity filters */}
        <span className="text-xs text-gray-400 dark:text-gray-500">اهمیت:</span>
        {(Object.keys(SEVERITY_CONFIG) as Severity[]).map((sev) => (
          <button
            key={sev}
            onClick={() => toggleSeverityFilter(sev)}
            className={cn(
              'rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors',
              filters.severities.includes(sev)
                ? cn(
                    SEVERITY_CONFIG[sev].bgLight,
                    SEVERITY_CONFIG[sev].bgDark,
                    SEVERITY_CONFIG[sev].color,
                    'border-current'
                  )
                : 'border-gray-200 text-gray-400 hover:border-gray-300 dark:border-gray-700 dark:text-gray-500'
            )}
          >
            {SEVERITY_CONFIG[sev].label}
          </button>
        ))}

        <span className="mr-2 text-xs text-gray-400 dark:text-gray-500">افق:</span>
        {(Object.keys(HORIZON_CONFIG) as TimeHorizon[]).map((hz) => (
          <button
            key={hz}
            onClick={() => toggleHorizonFilter(hz)}
            className={cn(
              'rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors',
              filters.horizons.includes(hz)
                ? 'border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-600 dark:bg-blue-950/30 dark:text-blue-400'
                : 'border-gray-200 text-gray-400 hover:border-gray-300 dark:border-gray-700 dark:text-gray-500'
            )}
          >
            {HORIZON_CONFIG[hz].label}
          </button>
        ))}

        {/* Reset */}
        <button
          onClick={resetFilters}
          className="mr-auto text-xs text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300"
        >
          پاکسازی فیلتر
        </button>
      </div>

      {/* Watchlist quick access */}
      {watchlist.length > 0 && (
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-400 dark:text-gray-500">واچ‌لیست:</span>
          {watchlist.map((w) => (
            <button
              key={w.id}
              onClick={() => applyWatchlist(w.id)}
              className={cn(
                'rounded-full border border-gray-200 px-2.5 py-0.5 text-xs font-medium',
                'text-gray-600 transition-colors hover:border-amber-300 hover:bg-amber-50',
                'dark:border-gray-700 dark:text-gray-400 dark:hover:border-amber-600 dark:hover:bg-amber-950/20'
              )}
            >
              {w.name}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
