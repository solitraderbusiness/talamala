'use client';

import { createContext, useContext, useState, useCallback, ReactNode } from 'react';
import { FilterState, ViewMode, ThemeMode, WatchlistItem, Severity, AssetId, TimeHorizon } from '@/types';
import { getDefaultFilters } from '@/lib/utils';

interface AppState {
  viewMode: ViewMode;
  theme: ThemeMode;
  filters: FilterState;
  watchlist: WatchlistItem[];
  sidebarOpen: boolean;
}

interface AppContextType extends AppState {
  setViewMode: (mode: ViewMode) => void;
  toggleTheme: () => void;
  setFilters: (filters: Partial<FilterState>) => void;
  resetFilters: () => void;
  toggleSeverityFilter: (severity: Severity) => void;
  toggleAssetFilter: (asset: AssetId) => void;
  toggleHorizonFilter: (horizon: TimeHorizon) => void;
  setSearchQuery: (query: string) => void;
  setTimeRange: (range: FilterState['timeRange']) => void;
  setSelectedMarket: (market: FilterState['selectedMarket']) => void;
  addToWatchlist: (item: WatchlistItem) => void;
  removeFromWatchlist: (id: string) => void;
  applyWatchlist: (id: string) => void;
  setSidebarOpen: (open: boolean) => void;
}

const AppContext = createContext<AppContextType | undefined>(undefined);

export function AppProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AppState>({
    viewMode: 'quick',
    theme: 'light',
    filters: getDefaultFilters(),
    watchlist: [
      {
        id: 'w1',
        name: 'ژئوپلیتیک و دلار',
        filters: {
          assets: ['global_gold', 'iran_gold'],
          searchQuery: '',
        },
      },
      {
        id: 'w2',
        name: 'سکه و صندوق‌ها',
        filters: {
          assets: ['coin', 'gold_funds'],
          searchQuery: '',
        },
      },
    ],
    sidebarOpen: false,
  });

  const setViewMode = useCallback((mode: ViewMode) => {
    setState((s) => ({ ...s, viewMode: mode }));
  }, []);

  const toggleTheme = useCallback(() => {
    setState((s) => {
      const newTheme = s.theme === 'light' ? 'dark' : 'light';
      if (typeof document !== 'undefined') {
        document.documentElement.classList.toggle('dark', newTheme === 'dark');
      }
      return { ...s, theme: newTheme };
    });
  }, []);

  const setFilters = useCallback((partial: Partial<FilterState>) => {
    setState((s) => ({ ...s, filters: { ...s.filters, ...partial } }));
  }, []);

  const resetFilters = useCallback(() => {
    setState((s) => ({ ...s, filters: getDefaultFilters() }));
  }, []);

  const toggleSeverityFilter = useCallback((severity: Severity) => {
    setState((s) => {
      const current = s.filters.severities;
      const next = current.includes(severity)
        ? current.filter((sv) => sv !== severity)
        : [...current, severity];
      return { ...s, filters: { ...s.filters, severities: next } };
    });
  }, []);

  const toggleAssetFilter = useCallback((asset: AssetId) => {
    setState((s) => {
      const current = s.filters.assets;
      const next = current.includes(asset)
        ? current.filter((a) => a !== asset)
        : [...current, asset];
      return { ...s, filters: { ...s.filters, assets: next } };
    });
  }, []);

  const toggleHorizonFilter = useCallback((horizon: TimeHorizon) => {
    setState((s) => {
      const current = s.filters.horizons;
      const next = current.includes(horizon)
        ? current.filter((h) => h !== horizon)
        : [...current, horizon];
      return { ...s, filters: { ...s.filters, horizons: next } };
    });
  }, []);

  const setSearchQuery = useCallback((query: string) => {
    setState((s) => ({ ...s, filters: { ...s.filters, searchQuery: query } }));
  }, []);

  const setTimeRange = useCallback((range: FilterState['timeRange']) => {
    setState((s) => ({ ...s, filters: { ...s.filters, timeRange: range } }));
  }, []);

  const setSelectedMarket = useCallback((market: FilterState['selectedMarket']) => {
    setState((s) => ({ ...s, filters: { ...s.filters, selectedMarket: market } }));
  }, []);

  const addToWatchlist = useCallback((item: WatchlistItem) => {
    setState((s) => ({ ...s, watchlist: [...s.watchlist, item] }));
  }, []);

  const removeFromWatchlist = useCallback((id: string) => {
    setState((s) => ({ ...s, watchlist: s.watchlist.filter((w) => w.id !== id) }));
  }, []);

  const applyWatchlist = useCallback((id: string) => {
    setState((s) => {
      const item = s.watchlist.find((w) => w.id === id);
      if (!item) return s;
      return { ...s, filters: { ...getDefaultFilters(), ...item.filters } };
    });
  }, []);

  const setSidebarOpen = useCallback((open: boolean) => {
    setState((s) => ({ ...s, sidebarOpen: open }));
  }, []);

  return (
    <AppContext.Provider
      value={{
        ...state,
        setViewMode,
        toggleTheme,
        setFilters,
        resetFilters,
        toggleSeverityFilter,
        toggleAssetFilter,
        toggleHorizonFilter,
        setSearchQuery,
        setTimeRange,
        setSelectedMarket,
        addToWatchlist,
        removeFromWatchlist,
        applyWatchlist,
        setSidebarOpen,
      }}
    >
      {children}
    </AppContext.Provider>
  );
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp must be used within AppProvider');
  return ctx;
}
