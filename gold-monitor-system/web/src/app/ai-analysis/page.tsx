"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import Link from "next/link";
import { timeAgo, cn } from "@/lib/utils";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

/* ════════════════════════════════════════════════════════════════════════
   Type Definitions
   ════════════════════════════════════════════════════════════════════════ */

interface TimeframeConsensus {
  timeframe: string;
  direction: "BUY" | "SELL" | "NEUTRAL";
  strength: number;
  entry_price: number | null;
  stop_loss: number | null;
  take_profit: number | null;
  signal_count: number;
  reasons: string[];
}

interface ConsensusData {
  timestamp: string;
  current_price: number | null;
  timeframes: TimeframeConsensus[];
  alignment: "aligned" | "conflict" | "partial";
  alignment_message: string;
  active_signals: number;
}

interface Signal {
  id: string;
  source_name: string;
  source_accuracy: number;
  direction: "BUY" | "SELL" | "NEUTRAL";
  entry_price: number | null;
  stop_loss: number | null;
  take_profit: number | null;
  timeframe: string;
  status: "active" | "won" | "lost" | "expired";
  created_at: string;
  pips_result: number | null;
}

interface PerformanceSummary {
  total_signals: number;
  win_rate: number;
  net_pips: number;
  profit_factor: number;
  avg_win_pips: number;
  avg_loss_pips: number;
  best_streak: number;
  worst_streak: number;
  sharpe_ratio: number;
  equity_curve: { date: string; cumulative_pips: number }[];
  win_rate_by_timeframe: { timeframe: string; win_rate: number; count: number }[];
}

interface MonthlyPerformance {
  month: string;
  signals: number;
  wins: number;
  losses: number;
  win_rate: number;
  net_pips: number;
}

interface DailyPerformance {
  date: string;
  net_pips: number;
  signals: number;
}

interface SourceLeaderboard {
  rank: number;
  source_name: string;
  source_type: string;
  total_signals: number;
  win_rate: number;
  avg_profit_pips: number;
  avg_loss_pips: number;
  profit_factor: number;
  weight: number;
  status: "active" | "inactive" | "probation";
}

interface JournalEntry {
  date: string;
  signal_count: number;
  wins: number;
  losses: number;
  key_observations: string[];
  cumulative_pips: number;
  summary: string;
}

/* ════════════════════════════════════════════════════════════════════════
   Constants
   ════════════════════════════════════════════════════════════════════════ */

const REFRESH_INTERVAL_MS = 60_000;
const PRICE_REFRESH_MS = 30_000;

const TIMEFRAME_LABELS: Record<string, string> = {
  scalp: "اسکالپ",
  intraday: "روزانه",
  swing: "سویینگ",
  position: "پوزیشن",
};

const TIMEFRAME_ORDER = ["scalp", "intraday", "swing", "position"];

const DIRECTION_CONFIG: Record<string, { label: string; color: string; bg: string; border: string }> = {
  BUY: {
    label: "خرید",
    color: "text-emerald-500",
    bg: "bg-emerald-500/10",
    border: "border-emerald-500/30",
  },
  SELL: {
    label: "فروش",
    color: "text-red-500",
    bg: "bg-red-500/10",
    border: "border-red-500/30",
  },
  NEUTRAL: {
    label: "خنثی",
    color: "text-gray-400",
    bg: "bg-gray-500/10",
    border: "border-gray-500/30",
  },
};

const STATUS_LABELS: Record<string, { label: string; color: string }> = {
  active: { label: "فعال", color: "bg-blue-500/10 text-blue-500 border-blue-500/30" },
  won: { label: "برنده", color: "bg-emerald-500/10 text-emerald-500 border-emerald-500/30" },
  lost: { label: "بازنده", color: "bg-red-500/10 text-red-500 border-red-500/30" },
  expired: { label: "منقضی", color: "bg-gray-500/10 text-gray-400 border-gray-500/30" },
};

const WEIGHT_BADGE: Record<string, string> = {
  high: "bg-emerald-500/10 text-emerald-500 border-emerald-500/30",
  medium: "bg-gold-500/10 text-gold-500 border-gold-500/30",
  low: "bg-gray-500/10 text-gray-400 border-gray-500/30",
};

/* ════════════════════════════════════════════════════════════════════════
   Helper Functions
   ════════════════════════════════════════════════════════════════════════ */

function formatPrice(price: number | null | undefined): string {
  if (price == null) return "---";
  return price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function getWeightCategory(weight: number): string {
  if (weight >= 0.7) return "high";
  if (weight >= 0.4) return "medium";
  return "low";
}

function getPipsColor(pips: number): string {
  if (pips > 0) return "text-emerald-500";
  if (pips < 0) return "text-red-500";
  return "text-gray-400";
}

function getHeatmapColor(pips: number): string {
  if (pips >= 50) return "bg-emerald-500";
  if (pips >= 20) return "bg-emerald-400";
  if (pips > 0) return "bg-emerald-300/60";
  if (pips === 0) return "bg-gray-600";
  if (pips > -20) return "bg-red-300/60";
  if (pips > -50) return "bg-red-400";
  return "bg-red-500";
}

/* ════════════════════════════════════════════════════════════════════════
   Skeleton Components
   ════════════════════════════════════════════════════════════════════════ */

function SkeletonCard({ className = "" }: { className?: string }) {
  return (
    <div className={cn("card animate-pulse", className)}>
      <div className="h-4 w-1/3 rounded bg-gray-200 dark:bg-gray-700" />
      <div className="mt-3 h-8 w-1/2 rounded bg-gray-200 dark:bg-gray-700" />
      <div className="mt-2 h-3 w-2/3 rounded bg-gray-200 dark:bg-gray-700" />
      <div className="mt-2 h-3 w-1/2 rounded bg-gray-200 dark:bg-gray-700" />
    </div>
  );
}

function SkeletonRow() {
  return (
    <div className="flex animate-pulse items-center gap-4 rounded-lg border border-gray-200 p-3 dark:border-gray-800">
      <div className="h-10 w-10 rounded-full bg-gray-200 dark:bg-gray-700" />
      <div className="flex-1 space-y-2">
        <div className="h-3 w-1/3 rounded bg-gray-200 dark:bg-gray-700" />
        <div className="h-3 w-1/2 rounded bg-gray-200 dark:bg-gray-700" />
      </div>
      <div className="h-6 w-16 rounded bg-gray-200 dark:bg-gray-700" />
    </div>
  );
}

/* ════════════════════════════════════════════════════════════════════════
   Warming Up State
   ════════════════════════════════════════════════════════════════════════ */

function WarmingUpMessage() {
  return (
    <div className="card flex flex-col items-center justify-center py-16 text-center">
      <div className="mb-4 text-5xl">&#x1F9E0;</div>
      <h3 className="text-lg font-bold text-gray-900 dark:text-gray-100">
        سیستم هوش مصنوعی در حال آماده‌سازی است
      </h3>
      <p className="mt-2 max-w-md text-sm text-gray-500 dark:text-gray-400">
        سیستم تحلیل هوشمند در حال جمع‌آوری و پردازش سیگنال‌ها از منابع مختلف است.
        لطفا چند دقیقه صبر کنید تا اولین تحلیل‌ها آماده شوند.
      </p>
      <div className="mt-6 flex items-center gap-2">
        <div className="h-2 w-2 animate-pulse rounded-full bg-gold-500" />
        <span className="text-sm text-gold-600 dark:text-gold-400">در حال پردازش...</span>
      </div>
    </div>
  );
}

/* ════════════════════════════════════════════════════════════════════════
   Main Page Component
   ════════════════════════════════════════════════════════════════════════ */

export default function AIAnalysisPage() {
  // ── Section 1: Consensus & Price ──
  const [currentPrice, setCurrentPrice] = useState<number | null>(null);
  const [consensus, setConsensus] = useState<ConsensusData | null>(null);
  const [consensusLoading, setConsensusLoading] = useState(true);

  // ── Section 2: Signals ──
  const [signals, setSignals] = useState<Signal[]>([]);
  const [signalsLoading, setSignalsLoading] = useState(true);
  const [signalTimeframe, setSignalTimeframe] = useState("all");
  const [signalStatus, setSignalStatus] = useState("all");
  const [signalOffset, setSignalOffset] = useState(0);
  const [hasMoreSignals, setHasMoreSignals] = useState(true);

  // ── Section 3: Performance ──
  const [performance, setPerformance] = useState<PerformanceSummary | null>(null);
  const [monthly, setMonthly] = useState<MonthlyPerformance[]>([]);
  const [daily, setDaily] = useState<DailyPerformance[]>([]);
  const [performanceLoading, setPerformanceLoading] = useState(true);

  // ── Section 4: Sources ──
  const [sources, setSources] = useState<SourceLeaderboard[]>([]);
  const [sourcesLoading, setSourcesLoading] = useState(true);

  // ── Section 5: Journal ──
  const [journal, setJournal] = useState<JournalEntry[]>([]);
  const [journalLoading, setJournalLoading] = useState(true);

  // ── Global ──
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const refreshTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const priceTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  /* ────────────────────────────────────────────────────────────────────
     Data Fetching
     ──────────────────────────────────────────────────────────────────── */

  const fetchCurrentPrice = useCallback(async () => {
    try {
      const res = await fetch("/api/ai-analysis/price/current");
      if (res.ok) {
        const data = await res.json();
        setCurrentPrice(data.price ?? data.current_price ?? null);
      }
    } catch {
      // Silent fail for price polling
    }
  }, []);

  const fetchConsensus = useCallback(async () => {
    try {
      const res = await fetch("/api/ai-analysis/consensus/latest");
      if (res.ok) {
        const data = await res.json();
        setConsensus(data);
        if (data.current_price) {
          setCurrentPrice(data.current_price);
        }
      }
    } catch {
      // Silent
    } finally {
      setConsensusLoading(false);
    }
  }, []);

  const fetchSignals = useCallback(
    async (reset = false) => {
      try {
        const offset = reset ? 0 : signalOffset;
        const params = new URLSearchParams({
          limit: "50",
          offset: String(offset),
        });
        if (signalTimeframe !== "all") params.set("timeframe", signalTimeframe);
        if (signalStatus !== "all") params.set("status", signalStatus);

        const res = await fetch(`/api/ai-analysis/signals/recent?${params}`);
        if (res.ok) {
          const data = await res.json();
          const items: Signal[] = data.signals || data.items || [];
          if (reset) {
            setSignals(items);
            setSignalOffset(items.length);
          } else {
            setSignals((prev) => [...prev, ...items]);
            setSignalOffset((prev) => prev + items.length);
          }
          setHasMoreSignals(items.length >= 50);
        }
      } catch {
        // Silent
      } finally {
        setSignalsLoading(false);
      }
    },
    [signalTimeframe, signalStatus, signalOffset]
  );

  const fetchPerformance = useCallback(async () => {
    try {
      const [summaryRes, monthlyRes, dailyRes] = await Promise.allSettled([
        fetch("/api/ai-analysis/performance/summary"),
        fetch("/api/ai-analysis/performance/monthly"),
        fetch("/api/ai-analysis/performance/daily"),
      ]);

      if (summaryRes.status === "fulfilled" && summaryRes.value.ok) {
        const data = await summaryRes.value.json();
        setPerformance(data);
      }
      if (monthlyRes.status === "fulfilled" && monthlyRes.value.ok) {
        const data = await monthlyRes.value.json();
        setMonthly(data.months || data || []);
      }
      if (dailyRes.status === "fulfilled" && dailyRes.value.ok) {
        const data = await dailyRes.value.json();
        setDaily(data.days || data || []);
      }
    } catch {
      // Silent
    } finally {
      setPerformanceLoading(false);
    }
  }, []);

  const fetchSources = useCallback(async () => {
    try {
      const res = await fetch("/api/ai-analysis/sources/leaderboard");
      if (res.ok) {
        const data = await res.json();
        setSources(data.sources || data || []);
      }
    } catch {
      // Silent
    } finally {
      setSourcesLoading(false);
    }
  }, []);

  const fetchJournal = useCallback(async () => {
    try {
      const res = await fetch("/api/ai-analysis/journal/recent");
      if (res.ok) {
        const data = await res.json();
        setJournal(data.entries || data || []);
      }
    } catch {
      // Silent
    } finally {
      setJournalLoading(false);
    }
  }, []);

  const refreshAll = useCallback(async () => {
    try {
      await Promise.allSettled([
        fetchConsensus(),
        fetchSignals(true),
        fetchPerformance(),
        fetchSources(),
        fetchJournal(),
      ]);
      setLastUpdated(new Date());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "خطا در بارگذاری داده‌ها");
    }
  }, [fetchConsensus, fetchSignals, fetchPerformance, fetchSources, fetchJournal]);

  /* ────────────────────────────────────────────────────────────────────
     Effects
     ──────────────────────────────────────────────────────────────────── */

  // Initial load
  const refreshAllRef = useRef(refreshAll);
  refreshAllRef.current = refreshAll;

  useEffect(() => {
    refreshAllRef.current();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Price polling (30s)
  useEffect(() => {
    fetchCurrentPrice();
    priceTimer.current = setInterval(fetchCurrentPrice, PRICE_REFRESH_MS);
    return () => {
      if (priceTimer.current) clearInterval(priceTimer.current);
    };
  }, [fetchCurrentPrice]);

  // Auto-refresh (60s)
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

  // Re-fetch signals when filters change
  useEffect(() => {
    setSignalsLoading(true);
    setSignalOffset(0);
    const timeout = setTimeout(() => {
      fetchSignals(true);
    }, 0);
    return () => clearTimeout(timeout);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signalTimeframe, signalStatus]);

  /* ════════════════════════════════════════════════════════════════════════
     Render
     ════════════════════════════════════════════════════════════════════════ */

  const sortedTimeframes = consensus?.timeframes
    ? [...consensus.timeframes].sort(
        (a, b) =>
          TIMEFRAME_ORDER.indexOf(a.timeframe) - TIMEFRAME_ORDER.indexOf(b.timeframe)
      )
    : [];

  return (
    <div className="space-y-8">
      {/* ── Page Header ── */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Link
              href="/"
              className="text-gray-400 transition-colors hover:text-gray-600 dark:hover:text-gray-300"
            >
              داشبورد
            </Link>
            <span className="text-gray-300 dark:text-gray-600">/</span>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
              تحلیل هوش مصنوعی
            </h1>
          </div>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            تحلیل لحظه‌ای بازار طلا توسط هوش مصنوعی
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

      {/* ╔══════════════════════════════════════════════════════════════════╗
         ║  SECTION 1: Live AI Analysis (Hero)                              ║
         ╚══════════════════════════════════════════════════════════════════╝ */}
      <section id="live-analysis">
        {/* Hero Header */}
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">
            تحلیل زنده
          </h2>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/10 px-3 py-1 text-xs font-medium text-emerald-500 border border-emerald-500/30">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
            </span>
            زنده
          </span>
          {consensus && (
            <span className="rounded-full bg-gold-500/10 px-3 py-1 text-xs font-medium text-gold-600 border border-gold-500/30 dark:text-gold-400">
              {consensus.active_signals} سیگنال فعال
            </span>
          )}
        </div>

        {/* Current Price */}
        <div className="mb-4 card flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className="text-3xl">&#x1F4B0;</span>
            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400">قیمت لحظه‌ای طلای جهانی</p>
              <p className="text-2xl font-bold text-gray-900 dark:text-gray-100" dir="ltr">
                {currentPrice != null ? (
                  <>
                    <span className="text-gold-500">$</span>
                    {formatPrice(currentPrice)}
                  </>
                ) : (
                  <span className="text-gray-400">---</span>
                )}
              </p>
            </div>
          </div>
          <div className="text-xs text-gray-400">
            به‌روزرسانی هر ۳۰ ثانیه
          </div>
        </div>

        {consensusLoading ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {[1, 2, 3, 4].map((i) => (
              <SkeletonCard key={i} />
            ))}
          </div>
        ) : !consensus || sortedTimeframes.length === 0 ? (
          <WarmingUpMessage />
        ) : (
          <>
            {/* Timeframe Cards */}
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {sortedTimeframes.map((tf) => {
                const dir = DIRECTION_CONFIG[tf.direction] || DIRECTION_CONFIG.NEUTRAL;
                return (
                  <div
                    key={tf.timeframe}
                    className={cn(
                      "card border transition-all duration-300",
                      dir.border
                    )}
                  >
                    {/* Header */}
                    <div className="mb-3 flex items-center justify-between">
                      <h3 className="text-sm font-bold text-gray-900 dark:text-gray-100">
                        {TIMEFRAME_LABELS[tf.timeframe] || tf.timeframe}
                      </h3>
                      <span
                        className={cn(
                          "rounded-full border px-2.5 py-0.5 text-xs font-bold",
                          dir.bg,
                          dir.border,
                          dir.color
                        )}
                      >
                        {dir.label}
                      </span>
                    </div>

                    {/* Strength Meter */}
                    <div className="mb-3">
                      <div className="mb-1 flex items-center justify-between">
                        <span className="text-xs text-gray-500 dark:text-gray-400">قدرت سیگنال</span>
                        <span className="text-xs font-bold text-gray-700 dark:text-gray-300">
                          {tf.strength}%
                        </span>
                      </div>
                      <div className="h-2 rounded-full bg-gray-200 dark:bg-gray-700">
                        <div
                          className={cn(
                            "h-full rounded-full transition-all duration-700",
                            tf.direction === "BUY"
                              ? "bg-emerald-500"
                              : tf.direction === "SELL"
                                ? "bg-red-500"
                                : "bg-gray-400"
                          )}
                          style={{ width: `${Math.min(tf.strength, 100)}%` }}
                        />
                      </div>
                    </div>

                    {/* Entry / SL / TP */}
                    <div className="mb-3 space-y-1.5 text-xs">
                      <div className="flex justify-between">
                        <span className="text-gray-500 dark:text-gray-400">ورود</span>
                        <span className="font-mono font-medium text-gray-900 dark:text-gray-100" dir="ltr">
                          {formatPrice(tf.entry_price)}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-500 dark:text-gray-400">حد ضرر</span>
                        <span className="font-mono font-medium text-red-500" dir="ltr">
                          {formatPrice(tf.stop_loss)}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-500 dark:text-gray-400">حد سود</span>
                        <span className="font-mono font-medium text-emerald-500" dir="ltr">
                          {formatPrice(tf.take_profit)}
                        </span>
                      </div>
                    </div>

                    {/* Signal Count */}
                    <div className="mb-2 flex items-center justify-between text-xs">
                      <span className="text-gray-500 dark:text-gray-400">تعداد سیگنال</span>
                      <span className="font-medium text-gray-700 dark:text-gray-300">
                        {tf.signal_count}
                      </span>
                    </div>

                    {/* Top 2 Reasons */}
                    {tf.reasons && tf.reasons.length > 0 && (
                      <div className="mt-2 border-t border-gray-100 pt-2 dark:border-gray-800">
                        {tf.reasons.slice(0, 2).map((reason, i) => (
                          <p key={i} className="mt-1 text-[11px] leading-relaxed text-gray-500 dark:text-gray-400">
                            <span className="ml-1 text-gold-500">&#x25CF;</span>
                            {reason}
                          </p>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {/* Alignment Alert */}
            {consensus.alignment && (
              <div
                className={cn(
                  "mt-4 rounded-lg border p-3 text-sm",
                  consensus.alignment === "aligned"
                    ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                    : consensus.alignment === "conflict"
                      ? "border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-400"
                      : "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400"
                )}
              >
                <div className="flex items-center gap-2">
                  <span className="text-lg">
                    {consensus.alignment === "aligned"
                      ? "\u2705"
                      : consensus.alignment === "conflict"
                        ? "\u26A0\uFE0F"
                        : "\u26A1"}
                  </span>
                  <span className="font-medium">
                    {consensus.alignment === "aligned"
                      ? "هم‌راستایی کامل تایم‌فریم‌ها"
                      : consensus.alignment === "conflict"
                        ? "تناقض بین تایم‌فریم‌ها"
                        : "هم‌راستایی جزئی تایم‌فریم‌ها"}
                  </span>
                </div>
                {consensus.alignment_message && (
                  <p className="mt-1 text-xs opacity-80">{consensus.alignment_message}</p>
                )}
              </div>
            )}
          </>
        )}
      </section>

      {/* ╔══════════════════════════════════════════════════════════════════╗
         ║  SECTION 2: Recent Signals Feed                                  ║
         ╚══════════════════════════════════════════════════════════════════╝ */}
      <section id="signals-feed">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">
            سیگنال‌های اخیر
          </h2>
          <span className="text-xs text-gray-400">
            {signals.length} سیگنال نمایش داده شده
          </span>
        </div>

        {/* Filters */}
        <div className="mb-4 flex flex-wrap gap-3">
          {/* Timeframe filter */}
          <div className="flex gap-1">
            {[
              { value: "all", label: "همه" },
              { value: "scalp", label: "اسکالپ" },
              { value: "intraday", label: "روزانه" },
              { value: "swing", label: "سویینگ" },
              { value: "position", label: "پوزیشن" },
            ].map((opt) => (
              <button
                key={opt.value}
                onClick={() => setSignalTimeframe(opt.value)}
                className={cn(
                  "rounded-lg px-3 py-1.5 text-xs font-medium transition-colors",
                  signalTimeframe === opt.value
                    ? "bg-gold-600 text-white"
                    : "bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700"
                )}
              >
                {opt.label}
              </button>
            ))}
          </div>

          {/* Status filter */}
          <div className="flex gap-1">
            {[
              { value: "all", label: "همه" },
              { value: "active", label: "فعال" },
              { value: "won", label: "برنده" },
              { value: "lost", label: "بازنده" },
            ].map((opt) => (
              <button
                key={opt.value}
                onClick={() => setSignalStatus(opt.value)}
                className={cn(
                  "rounded-lg px-3 py-1.5 text-xs font-medium transition-colors",
                  signalStatus === opt.value
                    ? "bg-gold-600 text-white"
                    : "bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700"
                )}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        {/* Signal Cards */}
        {signalsLoading && signals.length === 0 ? (
          <div className="space-y-3">
            {[1, 2, 3, 4, 5].map((i) => (
              <SkeletonRow key={i} />
            ))}
          </div>
        ) : signals.length === 0 ? (
          <div className="card py-12 text-center">
            <p className="text-gray-400">
              {signalTimeframe !== "all" || signalStatus !== "all"
                ? "سیگنالی با این فیلترها یافت نشد"
                : "هنوز سیگنالی ثبت نشده است"}
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {signals.map((signal) => {
              const dir = DIRECTION_CONFIG[signal.direction] || DIRECTION_CONFIG.NEUTRAL;
              const statusCfg = STATUS_LABELS[signal.status] || STATUS_LABELS.active;
              return (
                <div
                  key={signal.id}
                  className="card flex flex-wrap items-center gap-3 px-4 py-3 sm:flex-nowrap"
                >
                  {/* Source + Accuracy */}
                  <div className="flex min-w-0 items-center gap-2">
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gray-100 text-sm font-bold text-gray-600 dark:bg-gray-800 dark:text-gray-300">
                      {signal.source_name?.charAt(0)?.toUpperCase() || "?"}
                    </div>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-gray-900 dark:text-gray-100">
                        {signal.source_name}
                      </p>
                      <p className="text-[11px] text-gray-400">
                        دقت: <span dir="ltr">{(signal.source_accuracy * 100).toFixed(0)}%</span>
                      </p>
                    </div>
                  </div>

                  {/* Direction Badge */}
                  <span
                    className={cn(
                      "shrink-0 rounded-full border px-2.5 py-0.5 text-xs font-bold",
                      dir.bg,
                      dir.border,
                      dir.color
                    )}
                  >
                    {dir.label}
                  </span>

                  {/* Entry / SL / TP */}
                  <div className="hidden shrink-0 gap-3 text-xs sm:flex" dir="ltr">
                    <span className="text-gray-500 dark:text-gray-400">
                      E: <span className="font-mono font-medium text-gray-700 dark:text-gray-300">{formatPrice(signal.entry_price)}</span>
                    </span>
                    <span className="text-gray-500 dark:text-gray-400">
                      SL: <span className="font-mono font-medium text-red-500">{formatPrice(signal.stop_loss)}</span>
                    </span>
                    <span className="text-gray-500 dark:text-gray-400">
                      TP: <span className="font-mono font-medium text-emerald-500">{formatPrice(signal.take_profit)}</span>
                    </span>
                  </div>

                  {/* Timeframe Tag */}
                  <span className="shrink-0 rounded-md bg-gray-100 px-2 py-0.5 text-[11px] font-medium text-gray-600 dark:bg-gray-800 dark:text-gray-400">
                    {TIMEFRAME_LABELS[signal.timeframe] || signal.timeframe}
                  </span>

                  {/* Time ago */}
                  <span className="shrink-0 text-[11px] text-gray-400">
                    {timeAgo(signal.created_at)}
                  </span>

                  {/* Status badge */}
                  <span
                    className={cn(
                      "shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-medium",
                      statusCfg.color
                    )}
                  >
                    {statusCfg.label}
                  </span>

                  {/* Pips result if resolved */}
                  {signal.pips_result != null && (
                    <span
                      className={cn(
                        "shrink-0 text-xs font-bold",
                        getPipsColor(signal.pips_result)
                      )}
                      dir="ltr"
                    >
                      {signal.pips_result > 0 ? "+" : ""}
                      {signal.pips_result.toFixed(1)} pips
                    </span>
                  )}
                </div>
              );
            })}

            {/* Load More */}
            {hasMoreSignals && (
              <div className="mt-3 text-center">
                <button
                  onClick={() => fetchSignals(false)}
                  className="btn-secondary inline-flex items-center gap-1 px-4 py-2 text-xs"
                >
                  بارگذاری بیشتر
                </button>
              </div>
            )}
          </div>
        )}
      </section>

      {/* ╔══════════════════════════════════════════════════════════════════╗
         ║  SECTION 3: Performance Dashboard                                ║
         ╚══════════════════════════════════════════════════════════════════╝ */}
      <section id="performance">
        <h2 className="mb-4 text-xl font-bold text-gray-900 dark:text-gray-100">
          عملکرد سیستم
        </h2>

        {performanceLoading ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {[1, 2, 3, 4, 5, 6, 7, 8].map((i) => (
              <SkeletonCard key={i} className="py-3" />
            ))}
          </div>
        ) : !performance ? (
          <WarmingUpMessage />
        ) : (
          <>
            {/* Key Metrics Row */}
            <div className="mb-6 grid gap-3 grid-cols-2 sm:grid-cols-3 lg:grid-cols-5">
              {[
                {
                  label: "کل سیگنال‌ها",
                  value: performance.total_signals.toLocaleString("fa-IR"),
                  icon: "&#x1F4CA;",
                },
                {
                  label: "نرخ برد",
                  value: `${performance.win_rate.toFixed(1)}%`,
                  icon: "&#x1F3AF;",
                  color: performance.win_rate >= 55 ? "text-emerald-500" : performance.win_rate >= 45 ? "text-gold-500" : "text-red-500",
                },
                {
                  label: "مجموع پیپ",
                  value: `${performance.net_pips > 0 ? "+" : ""}${performance.net_pips.toFixed(1)}`,
                  icon: "&#x1F4B9;",
                  color: getPipsColor(performance.net_pips),
                },
                {
                  label: "عامل سود",
                  value: performance.profit_factor.toFixed(2),
                  icon: "&#x2696;&#xFE0F;",
                  color: performance.profit_factor >= 1.5 ? "text-emerald-500" : performance.profit_factor >= 1 ? "text-gold-500" : "text-red-500",
                },
                {
                  label: "میانگین سود",
                  value: `+${performance.avg_win_pips.toFixed(1)}`,
                  icon: "&#x2705;",
                  color: "text-emerald-500",
                },
                {
                  label: "میانگین ضرر",
                  value: `-${performance.avg_loss_pips.toFixed(1)}`,
                  icon: "&#x274C;",
                  color: "text-red-500",
                },
                {
                  label: "بهترین رشته",
                  value: `${performance.best_streak} برد`,
                  icon: "&#x1F525;",
                  color: "text-emerald-500",
                },
                {
                  label: "بدترین رشته",
                  value: `${performance.worst_streak} باخت`,
                  icon: "&#x1F4A5;",
                  color: "text-red-500",
                },
                {
                  label: "نسبت شارپ",
                  value: performance.sharpe_ratio.toFixed(2),
                  icon: "&#x1F4C8;",
                  color: performance.sharpe_ratio >= 1.5 ? "text-emerald-500" : performance.sharpe_ratio >= 0.5 ? "text-gold-500" : "text-red-500",
                },
              ].map((metric) => (
                <div key={metric.label} className="card py-3 text-center">
                  <span
                    className="text-xl"
                    dangerouslySetInnerHTML={{ __html: metric.icon }}
                  />
                  <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    {metric.label}
                  </p>
                  <p
                    className={cn(
                      "mt-1 text-lg font-bold",
                      metric.color || "text-gray-900 dark:text-gray-100"
                    )}
                    dir="ltr"
                  >
                    {metric.value}
                  </p>
                </div>
              ))}
            </div>

            {/* Equity Curve Chart */}
            {performance.equity_curve && performance.equity_curve.length > 0 && (
              <div className="card mb-6">
                <h3 className="mb-4 text-sm font-bold text-gray-900 dark:text-gray-100">
                  منحنی سرمایه (پیپ تجمعی)
                </h3>
                <div className="h-64" dir="ltr">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={performance.equity_curve}>
                      <CartesianGrid
                        strokeDasharray="3 3"
                        stroke="#374151"
                        opacity={0.3}
                      />
                      <XAxis
                        dataKey="date"
                        tick={{ fontSize: 10, fill: "#9CA3AF" }}
                        tickFormatter={(val: string) => {
                          const d = new Date(val);
                          return `${d.getMonth() + 1}/${d.getDate()}`;
                        }}
                      />
                      <YAxis
                        tick={{ fontSize: 10, fill: "#9CA3AF" }}
                        tickFormatter={(val: number) => `${val}`}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: "#1F2937",
                          border: "1px solid #374151",
                          borderRadius: "8px",
                          color: "#F3F4F6",
                          fontSize: "12px",
                        }}
                        labelFormatter={(label) => {
                          try {
                            return new Date(String(label)).toLocaleDateString("fa-IR");
                          } catch {
                            return String(label);
                          }
                        }}
                        formatter={(value) => [`${Number(value).toFixed(1)} pips`, "پیپ تجمعی"]}
                      />
                      <Line
                        type="monotone"
                        dataKey="cumulative_pips"
                        stroke="#F59E0B"
                        strokeWidth={2}
                        dot={false}
                        activeDot={{ r: 4, fill: "#F59E0B" }}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}

            {/* Two columns: Monthly Table + Win Rate by Timeframe */}
            <div className="grid gap-4 md:grid-cols-2">
              {/* Monthly Performance Table */}
              {monthly.length > 0 && (
                <div className="card overflow-x-auto">
                  <h3 className="mb-3 text-sm font-bold text-gray-900 dark:text-gray-100">
                    عملکرد ماهانه
                  </h3>
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-gray-200 dark:border-gray-700">
                        <th className="py-2 text-right font-medium text-gray-500 dark:text-gray-400">ماه</th>
                        <th className="py-2 text-center font-medium text-gray-500 dark:text-gray-400">سیگنال</th>
                        <th className="py-2 text-center font-medium text-gray-500 dark:text-gray-400">برد</th>
                        <th className="py-2 text-center font-medium text-gray-500 dark:text-gray-400">باخت</th>
                        <th className="py-2 text-center font-medium text-gray-500 dark:text-gray-400">نرخ برد</th>
                        <th className="py-2 text-left font-medium text-gray-500 dark:text-gray-400">پیپ خالص</th>
                      </tr>
                    </thead>
                    <tbody>
                      {monthly.map((m) => (
                        <tr key={m.month} className="border-b border-gray-100 dark:border-gray-800">
                          <td className="py-2 font-medium text-gray-900 dark:text-gray-100" dir="ltr">
                            {m.month}
                          </td>
                          <td className="py-2 text-center text-gray-600 dark:text-gray-400">
                            {m.signals}
                          </td>
                          <td className="py-2 text-center text-emerald-500">{m.wins}</td>
                          <td className="py-2 text-center text-red-500">{m.losses}</td>
                          <td className="py-2 text-center text-gray-700 dark:text-gray-300" dir="ltr">
                            {m.win_rate.toFixed(1)}%
                          </td>
                          <td
                            className={cn("py-2 text-left font-bold", getPipsColor(m.net_pips))}
                            dir="ltr"
                          >
                            {m.net_pips > 0 ? "+" : ""}
                            {m.net_pips.toFixed(1)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {/* Win Rate by Timeframe Bar Chart */}
              {performance.win_rate_by_timeframe && performance.win_rate_by_timeframe.length > 0 && (
                <div className="card">
                  <h3 className="mb-3 text-sm font-bold text-gray-900 dark:text-gray-100">
                    نرخ برد به تفکیک تایم‌فریم
                  </h3>
                  <div className="h-56" dir="ltr">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart
                        data={performance.win_rate_by_timeframe.map((item) => ({
                          ...item,
                          label: TIMEFRAME_LABELS[item.timeframe] || item.timeframe,
                        }))}
                      >
                        <CartesianGrid
                          strokeDasharray="3 3"
                          stroke="#374151"
                          opacity={0.3}
                        />
                        <XAxis
                          dataKey="label"
                          tick={{ fontSize: 11, fill: "#9CA3AF" }}
                        />
                        <YAxis
                          domain={[0, 100]}
                          tick={{ fontSize: 10, fill: "#9CA3AF" }}
                          tickFormatter={(val: number) => `${val}%`}
                        />
                        <Tooltip
                          contentStyle={{
                            backgroundColor: "#1F2937",
                            border: "1px solid #374151",
                            borderRadius: "8px",
                            color: "#F3F4F6",
                            fontSize: "12px",
                          }}
                          formatter={(value, _name, props) => {
                            const count = (props as { payload?: { count?: number } })?.payload?.count ?? 0;
                            return [
                              `${Number(value).toFixed(1)}% (${count} سیگنال)`,
                              "نرخ برد",
                            ];
                          }}
                        />
                        <Bar
                          dataKey="win_rate"
                          fill="#F59E0B"
                          radius={[4, 4, 0, 0]}
                          maxBarSize={50}
                        />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              )}
            </div>

            {/* Daily Performance Heatmap */}
            {daily.length > 0 && (
              <div className="card mt-6">
                <h3 className="mb-3 text-sm font-bold text-gray-900 dark:text-gray-100">
                  نقشه حرارتی عملکرد روزانه
                </h3>
                <p className="mb-3 text-[11px] text-gray-500 dark:text-gray-400">
                  هر خانه نشان‌دهنده عملکرد یک روز (بر حسب پیپ) است
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {daily.slice(-60).map((d) => (
                    <div
                      key={d.date}
                      className={cn(
                        "h-6 w-6 rounded-sm transition-colors",
                        getHeatmapColor(d.net_pips)
                      )}
                      title={`${d.date}: ${d.net_pips > 0 ? "+" : ""}${d.net_pips.toFixed(1)} pips (${d.signals} سیگنال)`}
                    />
                  ))}
                </div>
                {/* Legend */}
                <div className="mt-3 flex items-center gap-3 text-[10px] text-gray-500 dark:text-gray-400">
                  <span>ضرر</span>
                  <div className="flex gap-0.5">
                    <div className="h-3 w-3 rounded-sm bg-red-500" />
                    <div className="h-3 w-3 rounded-sm bg-red-400" />
                    <div className="h-3 w-3 rounded-sm bg-red-300/60" />
                    <div className="h-3 w-3 rounded-sm bg-gray-600" />
                    <div className="h-3 w-3 rounded-sm bg-emerald-300/60" />
                    <div className="h-3 w-3 rounded-sm bg-emerald-400" />
                    <div className="h-3 w-3 rounded-sm bg-emerald-500" />
                  </div>
                  <span>سود</span>
                </div>
              </div>
            )}
          </>
        )}
      </section>

      {/* ╔══════════════════════════════════════════════════════════════════╗
         ║  SECTION 4: Source Leaderboard                                   ║
         ╚══════════════════════════════════════════════════════════════════╝ */}
      <section id="source-leaderboard">
        <h2 className="mb-4 text-xl font-bold text-gray-900 dark:text-gray-100">
          رتبه‌بندی منابع سیگنال
        </h2>

        {sourcesLoading ? (
          <div className="space-y-3">
            {[1, 2, 3, 4].map((i) => (
              <SkeletonRow key={i} />
            ))}
          </div>
        ) : sources.length === 0 ? (
          <div className="card py-12 text-center">
            <p className="text-gray-400">هنوز منبعی ثبت نشده است</p>
          </div>
        ) : (
          <div className="card overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-gray-200 dark:border-gray-700">
                  <th className="py-2.5 text-right font-medium text-gray-500 dark:text-gray-400">رتبه</th>
                  <th className="py-2.5 text-right font-medium text-gray-500 dark:text-gray-400">منبع</th>
                  <th className="py-2.5 text-center font-medium text-gray-500 dark:text-gray-400">نوع</th>
                  <th className="py-2.5 text-center font-medium text-gray-500 dark:text-gray-400">سیگنال‌ها</th>
                  <th className="py-2.5 text-center font-medium text-gray-500 dark:text-gray-400">نرخ برد</th>
                  <th className="py-2.5 text-center font-medium text-gray-500 dark:text-gray-400">م. سود</th>
                  <th className="py-2.5 text-center font-medium text-gray-500 dark:text-gray-400">م. ضرر</th>
                  <th className="py-2.5 text-center font-medium text-gray-500 dark:text-gray-400">ع. سود</th>
                  <th className="py-2.5 text-center font-medium text-gray-500 dark:text-gray-400">وزن</th>
                  <th className="py-2.5 text-center font-medium text-gray-500 dark:text-gray-400">وضعیت</th>
                </tr>
              </thead>
              <tbody>
                {sources.map((source) => {
                  const weightCat = getWeightCategory(source.weight);
                  return (
                    <tr
                      key={source.rank}
                      className="border-b border-gray-100 transition-colors hover:bg-gray-50 dark:border-gray-800 dark:hover:bg-gray-800/50"
                    >
                      {/* Rank */}
                      <td className="py-2.5">
                        <span
                          className={cn(
                            "inline-flex h-6 w-6 items-center justify-center rounded-full text-[11px] font-bold",
                            source.rank <= 3
                              ? "bg-gold-500/20 text-gold-600 dark:text-gold-400"
                              : "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400"
                          )}
                        >
                          {source.rank}
                        </span>
                      </td>

                      {/* Source Name */}
                      <td className="py-2.5 font-medium text-gray-900 dark:text-gray-100">
                        {source.source_name}
                      </td>

                      {/* Type */}
                      <td className="py-2.5 text-center">
                        <span className="rounded-md bg-gray-100 px-2 py-0.5 text-[11px] text-gray-600 dark:bg-gray-800 dark:text-gray-400">
                          {source.source_type}
                        </span>
                      </td>

                      {/* Signals count */}
                      <td className="py-2.5 text-center text-gray-700 dark:text-gray-300">
                        {source.total_signals}
                      </td>

                      {/* Win Rate */}
                      <td className="py-2.5 text-center" dir="ltr">
                        <span
                          className={cn(
                            "font-medium",
                            source.win_rate >= 55
                              ? "text-emerald-500"
                              : source.win_rate >= 45
                                ? "text-gold-500"
                                : "text-red-500"
                          )}
                        >
                          {source.win_rate.toFixed(1)}%
                        </span>
                      </td>

                      {/* Avg Profit */}
                      <td className="py-2.5 text-center text-emerald-500" dir="ltr">
                        +{source.avg_profit_pips.toFixed(1)}
                      </td>

                      {/* Avg Loss */}
                      <td className="py-2.5 text-center text-red-500" dir="ltr">
                        -{source.avg_loss_pips.toFixed(1)}
                      </td>

                      {/* Profit Factor */}
                      <td className="py-2.5 text-center font-medium text-gray-700 dark:text-gray-300" dir="ltr">
                        {source.profit_factor.toFixed(2)}
                      </td>

                      {/* Weight Badge */}
                      <td className="py-2.5 text-center">
                        <span
                          className={cn(
                            "rounded-full border px-2 py-0.5 text-[11px] font-medium",
                            WEIGHT_BADGE[weightCat]
                          )}
                          dir="ltr"
                        >
                          {(source.weight * 100).toFixed(0)}%
                        </span>
                      </td>

                      {/* Status */}
                      <td className="py-2.5 text-center">
                        <span
                          className={cn(
                            "rounded-full px-2 py-0.5 text-[11px] font-medium",
                            source.status === "active"
                              ? "bg-emerald-500/10 text-emerald-500"
                              : source.status === "probation"
                                ? "bg-amber-500/10 text-amber-500"
                                : "bg-gray-500/10 text-gray-400"
                          )}
                        >
                          {source.status === "active"
                            ? "فعال"
                            : source.status === "probation"
                              ? "آزمایشی"
                              : "غیرفعال"}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* ╔══════════════════════════════════════════════════════════════════╗
         ║  SECTION 5: AI Analysis Journal                                  ║
         ╚══════════════════════════════════════════════════════════════════╝ */}
      <section id="journal">
        <h2 className="mb-4 text-xl font-bold text-gray-900 dark:text-gray-100">
          ژورنال تحلیل هوش مصنوعی
        </h2>

        {journalLoading ? (
          <div className="space-y-4">
            {[1, 2, 3].map((i) => (
              <SkeletonCard key={i} className="py-6" />
            ))}
          </div>
        ) : journal.length === 0 ? (
          <div className="card py-12 text-center">
            <p className="text-gray-400">هنوز گزارشی در ژورنال ثبت نشده است</p>
          </div>
        ) : (
          <div className="relative">
            {/* Timeline line */}
            <div className="absolute right-4 top-0 bottom-0 w-0.5 bg-gray-200 dark:bg-gray-700 sm:right-6" />

            <div className="space-y-6">
              {journal.map((entry, idx) => (
                <div key={entry.date} className="relative pr-10 sm:pr-14">
                  {/* Timeline dot */}
                  <div
                    className={cn(
                      "absolute right-2.5 top-4 h-3 w-3 rounded-full border-2 border-white dark:border-gray-900 sm:right-4.5",
                      idx === 0
                        ? "bg-gold-500"
                        : "bg-gray-300 dark:bg-gray-600"
                    )}
                    style={{ right: "10px" }}
                  />

                  <div className="card">
                    {/* Date Header */}
                    <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-3">
                        <h3 className="text-sm font-bold text-gray-900 dark:text-gray-100" dir="ltr">
                          {(() => {
                            try {
                              return new Date(entry.date).toLocaleDateString("fa-IR", {
                                weekday: "long",
                                year: "numeric",
                                month: "long",
                                day: "numeric",
                              });
                            } catch {
                              return entry.date;
                            }
                          })()}
                        </h3>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="rounded-md bg-gray-100 px-2 py-0.5 text-[11px] font-medium text-gray-600 dark:bg-gray-800 dark:text-gray-400">
                          {entry.signal_count} سیگنال
                        </span>
                        <span className="rounded-md bg-emerald-500/10 px-2 py-0.5 text-[11px] font-medium text-emerald-500">
                          {entry.wins} برد
                        </span>
                        <span className="rounded-md bg-red-500/10 px-2 py-0.5 text-[11px] font-medium text-red-500">
                          {entry.losses} باخت
                        </span>
                      </div>
                    </div>

                    {/* Summary */}
                    {entry.summary && (
                      <p className="mb-3 text-sm text-gray-700 dark:text-gray-300 leading-relaxed">
                        {entry.summary}
                      </p>
                    )}

                    {/* Key Observations */}
                    {entry.key_observations && entry.key_observations.length > 0 && (
                      <div className="mb-3 space-y-1">
                        {entry.key_observations.map((obs, i) => (
                          <p key={i} className="text-xs text-gray-500 dark:text-gray-400 leading-relaxed">
                            <span className="ml-1 text-gold-500">&#x25CF;</span>
                            {obs}
                          </p>
                        ))}
                      </div>
                    )}

                    {/* Cumulative Pips */}
                    <div className="flex items-center justify-between border-t border-gray-100 pt-2 dark:border-gray-800">
                      <span className="text-xs text-gray-500 dark:text-gray-400">
                        پیپ تجمعی تا این تاریخ
                      </span>
                      <span
                        className={cn(
                          "text-sm font-bold",
                          getPipsColor(entry.cumulative_pips)
                        )}
                        dir="ltr"
                      >
                        {entry.cumulative_pips > 0 ? "+" : ""}
                        {entry.cumulative_pips.toFixed(1)} pips
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </section>

      {/* ── Footer Attribution ── */}
      <div className="pb-4 text-center text-xs text-gray-400">
        تحلیل‌ها توسط سیستم هوش مصنوعی طلاملا تولید شده‌اند و جایگزین مشاوره مالی نیستند.
      </div>
    </div>
  );
}
