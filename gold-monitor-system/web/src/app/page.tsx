"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import Link from "next/link";
import {
  getAlerts,
  getAlertStats,
  getPrices,
  getSentiment,
  getUpcomingEvents,
  type Alert,
  type AlertStats,
  type PricesResponse,
  type PriceItem,
  type SentimentResponse,
  type TimeframeSentiment,
  type SectionSummary,
  type UpcomingEventsResponse,
  type CalendarEvent,
} from "@/lib/api";
import AlertCard from "@/components/AlertCard";
import RiskGauge from "@/components/RiskGauge";
import SentimentChart from "@/components/SentimentChart";

const PRICE_KEYS = ["gold_global", "gold_18k", "usd", "emami_coin"] as const;

/** How often to poll for new data (ms) */
const REFRESH_INTERVAL_MS = 60_000;
/** Fallback sentiment refresh if no new alerts arrive (ms) */
const SENTIMENT_FALLBACK_MS = 120_000;

const PRICE_FALLBACK: Record<string, { label: string; unit: string; icon: string }> = {
  gold_global: { label: "طلای جهانی", unit: "USD/oz", icon: "🌍" },
  gold_18k: { label: "طلای ۱۸ عیار", unit: "تومان/گرم", icon: "💛" },
  usd: { label: "دلار", unit: "تومان", icon: "💵" },
  emami_coin: { label: "سکه امامی", unit: "تومان", icon: "🪙" },
};

const SENTIMENT_COLORS: Record<string, string> = {
  very_bullish: "text-green-500",
  bullish: "text-green-400",
  neutral: "text-gray-400",
  bearish: "text-red-400",
  very_bearish: "text-red-500",
};

const SENTIMENT_BG: Record<string, string> = {
  very_bullish: "bg-green-500/10 border-green-500/30",
  bullish: "bg-green-500/10 border-green-500/20",
  neutral: "bg-gray-500/10 border-gray-500/20",
  bearish: "bg-red-500/10 border-red-500/20",
  very_bearish: "bg-red-500/10 border-red-500/30",
};

const IMPACT_ICON: Record<string, string> = {
  bullish: "▲",
  bearish: "▼",
  neutral: "●",
};

const IMPACT_COLOR: Record<string, string> = {
  bullish: "text-green-500",
  bearish: "text-red-500",
  neutral: "text-gray-400",
};

export default function DashboardPage() {
  const [stats, setStats] = useState<AlertStats | null>(null);
  const [prices, setPrices] = useState<PricesResponse | null>(null);
  const [sentiment, setSentiment] = useState<SentimentResponse | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [totalAlerts, setTotalAlerts] = useState(0);
  const [upcomingEvents, setUpcomingEvents] = useState<CalendarEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const refreshTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const sentimentTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  /** Track previous alert total to detect new arrivals */
  const prevAlertTotal = useRef<number>(-1);

  // Filters
  const [directionFilter, setDirectionFilter] = useState("");
  const [timeHorizon, setTimeHorizon] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const [activeSection, setActiveSection] = useState<string | null>(null);
  const [sentimentTab, setSentimentTab] = useState<"1h" | "4h" | "24h">("4h");
  const [gaugeView, setGaugeView] = useState<"gauge" | "chart">("gauge");
  const limit = 10;

  const fetchAlerts = useCallback(async () => {
    try {
      const params: Record<string, string | number | undefined> = {
        time_horizon: timeHorizon || undefined,
        q: search || undefined,
        limit,
        offset: page * limit,
      };
      const data = await getAlerts(params);
      let items = data.items || [];
      // Client-side direction filter
      if (directionFilter) {
        items = items.filter((a) => (a.direction || "neutral") === directionFilter);
      }
      setAlerts(items);
      setTotalAlerts(directionFilter ? items.length : data.total || 0);
    } catch {
      // Alert list may fail independently
    }
  }, [directionFilter, timeHorizon, search, page]);

  const fetchSentiment = useCallback(async () => {
    try {
      const data = await getSentiment();
      setSentiment(data);
    } catch {
      // Sentiment may fail independently
    }
  }, []);

  /** Silently refresh all dashboard data (no loading spinner).
   *  Also detects new alerts and triggers sentiment refresh. */
  const refreshAll = useCallback(async () => {
    try {
      const [statsData, , pricesData, upcomingData] = await Promise.allSettled([
        getAlertStats(),
        fetchAlerts(),
        getPrices(),
        getUpcomingEvents(5, "high"),
      ]);
      if (statsData.status === "fulfilled") {
        const newStats = statsData.value;
        const newTotal =
          (newStats?.counts?.high ?? 0) +
          (newStats?.counts?.medium ?? 0) +
          (newStats?.counts?.low ?? 0);

        // If new alerts arrived, refresh sentiment immediately
        if (prevAlertTotal.current >= 0 && newTotal > prevAlertTotal.current) {
          fetchSentiment();
        }
        prevAlertTotal.current = newTotal;
        setStats(newStats);
      }
      if (pricesData.status === "fulfilled") setPrices(pricesData.value);
      if (upcomingData.status === "fulfilled") setUpcomingEvents(upcomingData.value.events || []);
      setLastUpdated(new Date());
    } catch {
      // Silent — don't overwrite the page with an error on a background poll
    }
  }, [fetchAlerts, fetchSentiment]);

  // Initial load (with spinner) — sentiment loads separately to avoid blocking
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

  // Sentiment loads independently (non-blocking) since it may be slow (LLM call)
  useEffect(() => {
    fetchSentiment();
  }, [fetchSentiment]);

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
    if (sentimentTimer.current) {
      clearInterval(sentimentTimer.current);
      sentimentTimer.current = null;
    }
    if (autoRefresh) {
      refreshTimer.current = setInterval(refreshAll, REFRESH_INTERVAL_MS);
      sentimentTimer.current = setInterval(fetchSentiment, SENTIMENT_FALLBACK_MS);
    }
    return () => {
      if (refreshTimer.current) clearInterval(refreshTimer.current);
      if (sentimentTimer.current) clearInterval(sentimentTimer.current);
    };
  }, [autoRefresh, refreshAll, fetchSentiment]);

  const activeSentiment: TimeframeSentiment | undefined =
    sentiment?.timeframes?.[sentimentTab];

  // Get sections from stats, filtered if a section is active
  const sections: SectionSummary[] = stats?.sections || [];
  const displayedSections = activeSection
    ? sections.filter((s) => s.id === activeSection)
    : sections;

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
            onClick={() => { refreshAll(); fetchSentiment(); }}
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

      {/* ─── Sentiment Analysis Panel ─── */}
      <div className="card">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-bold text-gray-900 dark:text-gray-100">
            تحلیل احساسات بازار
          </h2>
          {sentiment && (
            <div className="flex gap-1">
              {(["1h", "4h", "24h"] as const).map((tf) => (
                <button
                  key={tf}
                  onClick={() => setSentimentTab(tf)}
                  className={`rounded-md px-3 py-1 text-xs font-medium transition-colors ${
                    sentimentTab === tf
                      ? "bg-gold-600 text-white"
                      : "text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800"
                  }`}
                >
                  {sentiment.timeframes[tf]?.label || tf}
                </button>
              ))}
            </div>
          )}
        </div>

        {!sentiment ? (
          <div className="flex items-center justify-center gap-2 py-4">
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-gold-500 border-t-transparent" />
            <span className="text-sm text-gray-400">در حال بارگذاری تحلیل...</span>
          </div>
        ) : activeSentiment ? (
          <div className="space-y-3">
            {/* Sentiment badge + summary */}
            <div className={`flex items-start gap-4 rounded-lg border p-3 transition-colors duration-500 ${SENTIMENT_BG[activeSentiment.sentiment] || SENTIMENT_BG.neutral}`}>
              <div className="text-center">
                <div className={`text-2xl font-bold transition-colors duration-500 ${SENTIMENT_COLORS[activeSentiment.sentiment] || ""}`}>
                  {activeSentiment.sentiment_label}
                </div>
                {activeSentiment.score !== undefined && (
                  <div className={`mt-0.5 text-lg font-bold transition-colors duration-500 ${SENTIMENT_COLORS[activeSentiment.sentiment] || ""}`}>
                    {activeSentiment.score}
                  </div>
                )}
                <div className="mt-0.5 text-xs text-gray-500">
                  {activeSentiment.alert_count} خبر
                </div>
              </div>
              <div className="flex-1 text-sm text-gray-700 dark:text-gray-300">
                <p>{activeSentiment.summary}</p>
                {activeSentiment.outlook && (
                  <p className="mt-1.5 text-xs text-gray-500 dark:text-gray-400">
                    چشم‌انداز: {activeSentiment.outlook}
                  </p>
                )}
              </div>
            </div>

            {/* Key drivers */}
            {activeSentiment.key_drivers && activeSentiment.key_drivers.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {activeSentiment.key_drivers.map((d, i) => (
                  <div
                    key={i}
                    className="inline-flex items-center gap-1.5 rounded-full bg-gray-100 px-3 py-1 text-xs dark:bg-gray-800"
                  >
                    <span className={IMPACT_COLOR[d.impact] || ""}>
                      {IMPACT_ICON[d.impact] || "●"}
                    </span>
                    <span className="text-gray-700 dark:text-gray-300">{d.title}</span>
                    {d.weight === "high" && (
                      <span className="text-[10px] font-bold text-amber-500">!</span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : (
          <p className="py-4 text-center text-sm text-gray-400">
            داده‌ای موجود نیست
          </p>
        )}
      </div>

      {/* ─── Market Price Cards ─── */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
        {PRICE_KEYS.map((key) => {
          const priceItem: PriceItem | undefined = prices?.prices?.[key];
          const fallback = PRICE_FALLBACK[key];
          const changeColor = priceItem?.direction === "up"
            ? "text-green-500"
            : priceItem?.direction === "down"
              ? "text-red-500"
              : "text-gray-400";
          return (
            <div key={key} className="card text-center">
              <span className="text-2xl">{priceItem?.icon || fallback.icon}</span>
              <h3 className="mt-2 text-sm font-medium text-gray-600 dark:text-gray-400">
                {priceItem?.label || fallback.label}
              </h3>
              <p className="mt-1 text-lg font-bold text-gray-900 dark:text-gray-100" dir="ltr">
                {priceItem?.formatted || "---"}
              </p>
              {priceItem?.change_pct ? (
                <p className={`text-xs font-medium ${changeColor}`} dir="ltr">
                  {priceItem.change_pct}
                </p>
              ) : (
                <p className="text-xs text-gray-400">{priceItem?.unit || fallback.unit}</p>
              )}
            </div>
          );
        })}
        <Link
          href="/prices"
          className="card flex flex-col items-center justify-center text-center transition-colors hover:border-gold-500 hover:bg-gold-50 dark:hover:border-gold-600 dark:hover:bg-gold-900/20"
        >
          <span className="text-2xl">📊</span>
          <span className="mt-2 text-sm font-medium text-gold-600 dark:text-gold-400">
            بیشتر
          </span>
          <span className="mt-0.5 text-xs text-gray-400">
            طلا، ارز، رمزارز
          </span>
        </Link>
      </div>

      {/* ─── Upcoming Economic Events Widget ─── */}
      {upcomingEvents.length > 0 && (
        <div className="card">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-bold text-gray-900 dark:text-gray-100">
              رویدادهای مهم پیش‌رو
            </h2>
            <Link
              href="/calendar"
              className="text-xs text-gold-600 hover:text-gold-700 dark:text-gold-400 dark:hover:text-gold-300"
            >
              مشاهده تقویم کامل &#8592;
            </Link>
          </div>
          <div className="space-y-2">
            {upcomingEvents.slice(0, 5).map((event) => {
              const impactColor = event.impact === "high"
                ? "bg-red-500"
                : event.impact === "medium"
                  ? "bg-orange-500"
                  : "bg-green-500";
              const flagMap: Record<string, string> = {
                US: "\u{1F1FA}\u{1F1F8}", EU: "\u{1F1EA}\u{1F1FA}",
                GB: "\u{1F1EC}\u{1F1E7}", JP: "\u{1F1EF}\u{1F1F5}",
                CN: "\u{1F1E8}\u{1F1F3}", AU: "\u{1F1E6}\u{1F1FA}",
                IR: "\u{1F1EE}\u{1F1F7}",
              };
              return (
                <div
                  key={event.id}
                  className="flex items-center gap-3 rounded-lg px-2 py-1.5 hover:bg-gray-50 dark:hover:bg-gray-800/50"
                >
                  <div className={`h-2.5 w-2.5 shrink-0 rounded-full ${impactColor}`} />
                  <span className="text-xs text-gold-600 dark:text-gold-400 w-20 shrink-0">
                    {event.time_until}
                  </span>
                  <span className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                    {event.event_name_fa !== event.event_name
                      ? event.event_name_fa
                      : event.event_name}
                  </span>
                  <span className="text-base shrink-0">
                    {flagMap[event.country] || event.country}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ─── Sentiment Score + Stats Row ─── */}
      <div className="grid gap-4 md:grid-cols-3">
        {/* Sentiment score gauge / chart */}
        <div className="card flex flex-col">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-sm font-medium text-gray-600 dark:text-gray-400">
              شاخص احساسات
            </h3>
            <button
              onClick={() => setGaugeView(gaugeView === "gauge" ? "chart" : "gauge")}
              className="rounded-md p-1 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800"
              title={gaugeView === "gauge" ? "نمودار" : "گیج"}
            >
              {gaugeView === "gauge" ? (
                <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                  <path d="M2 11a1 1 0 011-1h2a1 1 0 011 1v5a1 1 0 01-1 1H3a1 1 0 01-1-1v-5zm6-4a1 1 0 011-1h2a1 1 0 011 1v9a1 1 0 01-1 1H9a1 1 0 01-1-1V7zm6-3a1 1 0 011-1h2a1 1 0 011 1v12a1 1 0 01-1 1h-2a1 1 0 01-1-1V4z" />
                </svg>
              ) : (
                <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z" clipRule="evenodd" />
                </svg>
              )}
            </button>
          </div>
          {/* Timeframe buttons */}
          <div className="mb-2 flex justify-center gap-1">
            {(["1h", "4h", "24h"] as const).map((tf) => (
              <button
                key={tf}
                onClick={() => setSentimentTab(tf)}
                className={`rounded-md px-2.5 py-0.5 text-[11px] font-medium transition-colors ${
                  sentimentTab === tf
                    ? "bg-gold-600 text-white"
                    : "text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800"
                }`}
              >
                {tf === "24h" ? "روزانه" : tf}
              </button>
            ))}
          </div>
          {/* Gauge or Chart view */}
          <div className="flex flex-1 items-center justify-center">
            {gaugeView === "gauge" ? (
              <RiskGauge
                score={
                  sentiment?.timeframes?.[sentimentTab]?.score ??
                  stats?.risk_score ??
                  50
                }
              />
            ) : (
              <SentimentChart timeframe={sentimentTab} hours={48} height={130} />
            )}
          </div>
        </div>

        {/* News counts */}
        <div className="card">
          <h3 className="mb-3 text-sm font-medium text-gray-600 dark:text-gray-400">
            خبرهای امروز
          </h3>
          <div className="flex flex-col items-center justify-center gap-2">
            <span className="text-4xl font-bold text-gray-900 dark:text-gray-100">
              {(stats?.counts?.high ?? 0) + (stats?.counts?.medium ?? 0) + (stats?.counts?.low ?? 0)}
            </span>
            <span className="text-sm text-gray-500 dark:text-gray-400">خبر</span>
          </div>
        </div>

        {/* Top alerts (most important) */}
        <div className="card">
          <h3 className="mb-3 text-sm font-medium text-gray-600 dark:text-gray-400">
            مهم‌ترین خبرها
          </h3>
          <div className="space-y-2">
            {stats?.top_alerts && stats.top_alerts.length > 0 ? (
              stats.top_alerts.slice(0, 3).map((alert) => (
                <AlertCard key={alert.id} alert={alert} compact />
              ))
            ) : (
              <p className="py-4 text-center text-sm text-gray-400">
                خبری موجود نیست
              </p>
            )}
          </div>
        </div>
      </div>

      {/* ─── Categorized Alert Sections ─── */}
      {sections.length > 0 && (
        <div>
          <h2 className="mb-3 text-lg font-bold text-gray-900 dark:text-gray-100">
            دسته‌بندی خبرها
          </h2>
          {/* Section filter tabs */}
          <div className="mb-4 flex flex-wrap gap-2">
            <button
              onClick={() => setActiveSection(null)}
              className={`rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${
                activeSection === null
                  ? "bg-gold-600 text-white shadow-sm"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400"
              }`}
            >
              همه
            </button>
            {sections.map((sec) => (
              <button
                key={sec.id}
                onClick={() => setActiveSection(sec.id === activeSection ? null : sec.id)}
                className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${
                  activeSection === sec.id
                    ? "bg-gold-600 text-white shadow-sm"
                    : "bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400"
                }`}
              >
                <span>{sec.icon}</span>
                <span>{sec.label}</span>
                <span className="rounded-full bg-black/10 px-1.5 text-[10px] dark:bg-white/10">
                  {sec.total}
                </span>
              </button>
            ))}
          </div>

          {/* Section grid — 2 columns on desktop */}
          <div className="grid gap-4 md:grid-cols-2">
            {displayedSections.map((sec) => {
              const visibleAlerts = sec.alerts.slice(0, 4);
              return (
                <div
                  key={sec.id}
                  className="rounded-xl border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900"
                >
                  {/* Section header */}
                  <div className="flex items-center justify-between border-b border-gray-100 px-4 py-3 dark:border-gray-800">
                    <h3 className="flex items-center gap-2 text-sm font-bold text-gray-900 dark:text-gray-100">
                      <span>{sec.icon}</span>
                      {sec.label}
                    </h3>
                    <span className="text-[10px] text-gray-400">
                      {sec.total} خبر
                    </span>
                  </div>
                  {/* Alert rows */}
                  <div className="divide-y divide-gray-50 dark:divide-gray-800/50">
                    {visibleAlerts.length > 0 ? (
                      visibleAlerts.map((alert) => (
                        <AlertCard key={alert.id} alert={alert} compact />
                      ))
                    ) : (
                      <p className="py-6 text-center text-xs text-gray-400">
                        خبری در این دسته نیست
                      </p>
                    )}
                  </div>
                  {/* "See all" footer */}
                  {sec.total > 4 && (
                    <div className="border-t border-gray-100 px-4 py-2 text-center dark:border-gray-800">
                      <button
                        onClick={() => {
                          setActiveSection(sec.id);
                          setDirectionFilter("");
                          setPage(0);
                          // Scroll to the feed section
                          document.getElementById("alert-feed")?.scrollIntoView({ behavior: "smooth" });
                        }}
                        className="text-xs font-medium text-gold-600 hover:text-gold-700 dark:text-gold-400"
                      >
                        مشاهده همه {sec.total} خبر ←
                      </button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ─── Full Alert Feed ─── */}
      <div id="alert-feed">
        <h2 className="mb-4 text-lg font-bold text-gray-900 dark:text-gray-100">
          فید خبرها
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
            value={directionFilter}
            onChange={(e) => {
              setDirectionFilter(e.target.value);
              setPage(0);
            }}
            className="select-field w-auto"
          >
            <option value="">همه جهت‌ها</option>
            <option value="bullish">صعودی</option>
            <option value="bearish">نزولی</option>
            <option value="neutral">خنثی</option>
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
              <p className="text-gray-400">خبری یافت نشد</p>
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
