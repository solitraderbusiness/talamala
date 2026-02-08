"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import {
  getAlerts,
  getAlertStats,
  getPrices,
  type Alert,
  type AlertStats,
  type PricesResponse,
  type PriceItem,
} from "@/lib/api";
import AlertCard from "@/components/AlertCard";
import RiskGauge from "@/components/RiskGauge";
import SeverityBadge from "@/components/SeverityBadge";

const PRICE_KEYS = ["gold_global", "gold_18k", "usd", "emami_coin"] as const;

/** How often to poll for new data (ms) */
const REFRESH_INTERVAL_MS = 60_000;

const PRICE_FALLBACK: Record<string, { label: string; unit: string; icon: string }> = {
  gold_global: { label: "طلای جهانی", unit: "USD/oz", icon: "🌍" },
  gold_18k: { label: "طلای ۱۸ عیار", unit: "تومان/گرم", icon: "💛" },
  usd: { label: "دلار", unit: "تومان", icon: "💵" },
  emami_coin: { label: "سکه امامی", unit: "تومان", icon: "🪙" },
};

export default function DashboardPage() {
  const [stats, setStats] = useState<AlertStats | null>(null);
  const [prices, setPrices] = useState<PricesResponse | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [totalAlerts, setTotalAlerts] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const refreshTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  // Filters
  const [severity, setSeverity] = useState("");
  const [timeHorizon, setTimeHorizon] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const limit = 10;

  const fetchAlerts = useCallback(async () => {
    try {
      const data = await getAlerts({
        severity: severity || undefined,
        time_horizon: timeHorizon || undefined,
        q: search || undefined,
        limit,
        offset: page * limit,
      });
      setAlerts(data.items || []);
      setTotalAlerts(data.total || 0);
    } catch {
      // Alert list may fail independently
    }
  }, [severity, timeHorizon, search, page]);

  /** Silently refresh all dashboard data (no loading spinner). */
  const refreshAll = useCallback(async () => {
    try {
      const [statsData, , pricesData] = await Promise.allSettled([
        getAlertStats(),
        fetchAlerts(),
        getPrices(),
      ]);
      if (statsData.status === "fulfilled") setStats(statsData.value);
      if (pricesData.status === "fulfilled") setPrices(pricesData.value);
      setLastUpdated(new Date());
    } catch {
      // Silent — don't overwrite the page with an error on a background poll
    }
  }, [fetchAlerts]);

  // Initial load (with spinner)
  useEffect(() => {
    async function init() {
      setLoading(true);
      setError(null);
      try {
        await refreshAll();
      } catch (err) {
        setError(err instanceof Error ? err.message : "خطا در بارگذاری");
      } finally {
        setLoading(false);
      }
    }
    init();
  }, [refreshAll]);

  // Re-fetch alerts when filters change
  useEffect(() => {
    fetchAlerts();
  }, [fetchAlerts]);

  // Auto-refresh polling
  useEffect(() => {
    if (refreshTimer.current) {
      clearInterval(refreshTimer.current);
      refreshTimer.current = null;
    }
    if (autoRefresh) {
      refreshTimer.current = setInterval(refreshAll, REFRESH_INTERVAL_MS);
    }
    return () => {
      if (refreshTimer.current) clearInterval(refreshTimer.current);
    };
  }, [autoRefresh, refreshAll]);

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="text-center">
          <div className="mx-auto h-10 w-10 animate-spin rounded-full border-4 border-gold-500 border-t-transparent" />
          <p className="mt-3 text-gray-500">در حال بارگذاری...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page title + refresh controls */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
            داشبورد بازار
          </h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            نمای کلی بازار طلا و ارز
          </p>
        </div>
        <div className="flex items-center gap-3 text-sm">
          {lastUpdated && (
            <span className="text-gray-400">
              آخرین به‌روزرسانی:{" "}
              {lastUpdated.toLocaleTimeString("fa-IR", { hour: "2-digit", minute: "2-digit" })}
            </span>
          )}
          <button
            onClick={() => refreshAll()}
            className="btn-secondary inline-flex items-center gap-1 px-3 py-1.5 text-xs"
            title="به‌روزرسانی"
          >
            &#x21bb; به‌روزرسانی
          </button>
          <label className="inline-flex cursor-pointer items-center gap-1.5">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="h-4 w-4 accent-gold-600"
            />
            <span className="text-gray-500 dark:text-gray-400">خودکار</span>
          </label>
        </div>
      </div>

      {error && (
        <div className="rounded-lg bg-red-50 p-4 text-sm text-red-700 dark:bg-red-900/20 dark:text-red-400">
          {error}
        </div>
      )}

      {/* Market price cards */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {PRICE_KEYS.map((key) => {
          const priceItem: PriceItem | undefined = prices?.prices?.[key];
          const fallback = PRICE_FALLBACK[key];
          return (
            <div key={key} className="card text-center">
              <span className="text-2xl">{priceItem?.icon || fallback.icon}</span>
              <h3 className="mt-2 text-sm font-medium text-gray-600 dark:text-gray-400">
                {priceItem?.label || fallback.label}
              </h3>
              <p className="mt-1 text-lg font-bold text-gray-900 dark:text-gray-100" dir="ltr">
                {priceItem?.formatted || "---"}
              </p>
              <p className="text-xs text-gray-400">{priceItem?.unit || fallback.unit}</p>
            </div>
          );
        })}
      </div>

      {/* Stats + Risk Gauge row */}
      <div className="grid gap-4 md:grid-cols-3">
        {/* Risk gauge */}
        <div className="card flex flex-col items-center justify-center">
          <h3 className="mb-3 text-sm font-medium text-gray-600 dark:text-gray-400">
            شاخص ریسک
          </h3>
          <RiskGauge score={stats?.risk_score ?? 0} />
        </div>

        {/* Alert counts */}
        <div className="card">
          <h3 className="mb-3 text-sm font-medium text-gray-600 dark:text-gray-400">
            هشدارهای امروز
          </h3>
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <SeverityBadge severity="high" />
              <span className="text-xl font-bold text-red-600">
                {stats?.counts?.high ?? 0}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <SeverityBadge severity="medium" />
              <span className="text-xl font-bold text-amber-600">
                {stats?.counts?.medium ?? 0}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <SeverityBadge severity="low" />
              <span className="text-xl font-bold text-gray-600 dark:text-gray-400">
                {stats?.counts?.low ?? 0}
              </span>
            </div>
          </div>
        </div>

        {/* Top alerts */}
        <div className="card">
          <h3 className="mb-3 text-sm font-medium text-gray-600 dark:text-gray-400">
            مهم‌ترین هشدارها
          </h3>
          <div className="space-y-2">
            {stats?.top_alerts && stats.top_alerts.length > 0 ? (
              stats.top_alerts.slice(0, 3).map((alert) => (
                <AlertCard key={alert.id} alert={alert} compact />
              ))
            ) : (
              <p className="py-4 text-center text-sm text-gray-400">
                هشداری موجود نیست
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Alert feed with filters */}
      <div>
        <h2 className="mb-4 text-lg font-bold text-gray-900 dark:text-gray-100">
          فید هشدارها
        </h2>

        {/* Filters */}
        <div className="mb-4 flex flex-wrap gap-3">
          <input
            type="text"
            placeholder="جستجو..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(0);
            }}
            className="input-field max-w-xs"
          />
          <select
            value={severity}
            onChange={(e) => {
              setSeverity(e.target.value);
              setPage(0);
            }}
            className="select-field w-auto"
          >
            <option value="">همه شدت‌ها</option>
            <option value="high">بالا</option>
            <option value="medium">متوسط</option>
            <option value="low">پایین</option>
          </select>
          <select
            value={timeHorizon}
            onChange={(e) => {
              setTimeHorizon(e.target.value);
              setPage(0);
            }}
            className="select-field w-auto"
          >
            <option value="">همه بازه‌ها</option>
            <option value="immediate">فوری</option>
            <option value="short">کوتاه‌مدت</option>
            <option value="medium">میان‌مدت</option>
            <option value="long">بلندمدت</option>
          </select>
        </div>

        {/* Alert list */}
        <div className="space-y-3">
          {alerts.length > 0 ? (
            alerts.map((alert) => <AlertCard key={alert.id} alert={alert} />)
          ) : (
            <div className="card py-12 text-center">
              <p className="text-gray-400">هشداری یافت نشد</p>
            </div>
          )}
        </div>

        {/* Pagination */}
        {totalAlerts > limit && (
          <div className="mt-4 flex items-center justify-center gap-4">
            <button
              onClick={() => setPage(Math.max(0, page - 1))}
              disabled={page === 0}
              className="btn-secondary"
            >
              قبلی
            </button>
            <span className="text-sm text-gray-500">
              صفحه {page + 1} از {Math.ceil(totalAlerts / limit)}
            </span>
            <button
              onClick={() => setPage(page + 1)}
              disabled={(page + 1) * limit >= totalAlerts}
              className="btn-secondary"
            >
              بعدی
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
