"use client";

import { useState, useEffect, useCallback } from "react";
import {
  getAlerts,
  getAlertStats,
  getDataFreshness,
  type Alert,
  type AlertStats,
  type DataFreshness,
} from "@/lib/api";
import AlertCard from "@/components/AlertCard";
import RiskGauge from "@/components/RiskGauge";
import SeverityBadge from "@/components/SeverityBadge";
import { timeAgo, cn } from "@/lib/utils";

const marketCards = [
  { label: "طلای جهانی", unit: "USD/oz", icon: "🌍" },
  { label: "طلای ۱۸ عیار", unit: "تومان/گرم", icon: "💛" },
  { label: "دلار", unit: "تومان", icon: "💵" },
  { label: "سکه امامی", unit: "تومان", icon: "🪙" },
];

export default function DashboardPage() {
  const [stats, setStats] = useState<AlertStats | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [totalAlerts, setTotalAlerts] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [freshness, setFreshness] = useState<DataFreshness | null>(null);

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

  useEffect(() => {
    async function init() {
      setLoading(true);
      setError(null);
      try {
        const [statsData, , freshnessData] = await Promise.allSettled([
          getAlertStats(),
          fetchAlerts(),
          getDataFreshness(),
        ]);
        if (statsData.status === "fulfilled") {
          setStats(statsData.value);
        }
        if (freshnessData.status === "fulfilled") {
          setFreshness(freshnessData.value);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "خطا در بارگذاری");
      } finally {
        setLoading(false);
      }
    }
    init();
  }, [fetchAlerts]);

  useEffect(() => {
    fetchAlerts();
  }, [fetchAlerts]);

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
      {/* Page title */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
          داشبورد بازار
        </h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          نمای کلی بازار طلا و ارز
        </p>
      </div>

      {error && (
        <div className="rounded-lg bg-red-50 p-4 text-sm text-red-700 dark:bg-red-900/20 dark:text-red-400">
          {error}
        </div>
      )}

      {/* Market price cards */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {marketCards.map((card) => (
          <div key={card.label} className="card text-center">
            <span className="text-2xl">{card.icon}</span>
            <h3 className="mt-2 text-sm font-medium text-gray-600 dark:text-gray-400">
              {card.label}
            </h3>
            <p className="mt-1 text-lg font-bold text-gray-900 dark:text-gray-100">
              ---
            </p>
            <p className="text-xs text-gray-400">{card.unit}</p>
          </div>
        ))}
      </div>

      {/* Data Freshness Indicators */}
      {freshness && <FreshnessBar freshness={freshness} />}

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

/* ────────────────────────────────────────────────────────────────────── */
/*  Data Freshness Bar                                                    */
/* ────────────────────────────────────────────────────────────────────── */

function FreshnessBar({ freshness }: { freshness: DataFreshness }) {
  const items = [
    { label: "اخبار", timestamp: freshness.last_news_fetch },
    { label: "قیمت", timestamp: freshness.last_price_update },
    { label: "احساسات", timestamp: freshness.last_sentiment_update },
    { label: "ورکر", timestamp: freshness.last_worker_run },
  ].filter((item) => item.timestamp);

  if (items.length === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-4 rounded-lg bg-gray-50 px-4 py-2 text-xs dark:bg-gray-800/50">
      <span className="font-medium text-gray-500 dark:text-gray-400">
        آخرین بروزرسانی:
      </span>
      {items.map((item) => {
        const ageClass = getFreshnessColor(item.timestamp!);
        return (
          <span key={item.label} className="flex items-center gap-1">
            <span
              className={cn(
                "inline-block h-2 w-2 rounded-full",
                ageClass
              )}
            />
            <span className="text-gray-600 dark:text-gray-400">
              {item.label}:
            </span>
            <span className="text-gray-500 dark:text-gray-400">
              {timeAgo(item.timestamp!)}
            </span>
          </span>
        );
      })}
    </div>
  );
}

function getFreshnessColor(timestamp: string): string {
  const now = new Date();
  const ts = new Date(timestamp);
  const diffMinutes = (now.getTime() - ts.getTime()) / 60000;

  if (diffMinutes <= 15) return "bg-emerald-500"; // fresh (green)
  if (diffMinutes <= 60) return "bg-amber-500"; // slightly stale (yellow)
  return "bg-red-500"; // stale (red)
}
