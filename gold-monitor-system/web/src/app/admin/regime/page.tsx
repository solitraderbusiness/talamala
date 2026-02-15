"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { getToken } from "@/lib/auth";
import {
  AreaChart,
  Area,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
  ReferenceLine,
} from "recharts";
import InfoTip from "@/components/InfoTip";

/* ── Types ── */

interface RegimeRow {
  ts: string;
  liquidity_stress_index: number | null;
  usd_pressure_index: number | null;
  real_yield_pressure_index: number | null;
  p_expansion: number | null;
  p_tightening: number | null;
  p_stress: number | null;
  p_recovery: number | null;
  smoothed_p_expansion: number | null;
  smoothed_p_tightening: number | null;
  smoothed_p_stress: number | null;
  smoothed_p_recovery: number | null;
  chosen_regime: string | null;
  real_yield_source: string | null;
  credit_proxy_source: string | null;
  days_skipped: number | null;
  metadata: Record<string, unknown> | null;
  created_at: string | null;
  status?: string;
}

interface BenchmarkResult {
  name: string;
  start: string;
  end: string;
  expected: string;
  avg_prob: number;
  pct_days_correct: number;
  passed: boolean;
  reason: string;
}

interface BacktestResult {
  history: Array<{
    date: string;
    lsi: number;
    usdx: number;
    rypi: number;
    smoothed_p_expansion: number;
    smoothed_p_tightening: number;
    smoothed_p_stress: number;
    smoothed_p_recovery: number;
    chosen_regime: string;
  }>;
  benchmarks: BenchmarkResult[];
  summary: { total_days: number; passed: number; failed: number; date_range: string };
}

/* ── Constants ── */

const REGIME_COLORS: Record<string, string> = {
  expansion: "#10B981",
  tightening: "#F59E0B",
  stress: "#EF4444",
  recovery: "#3B82F6",
};

const REGIME_LABELS: Record<string, string> = {
  expansion: "انبساطی",
  tightening: "انقباضی",
  stress: "بحرانی",
  recovery: "بازیابی",
};

const DAY_OPTIONS = [30, 90, 180, 365];

const INPUT_SERIES = [
  { symbol: "DX-Y.NYB", label: "DXY (دلار)", term: "dxy" },
  { symbol: "^VIX", label: "VIX (ترس)", term: "vix" },
  { symbol: "^GSPC", label: "S&P 500", term: "sp500" },
  { symbol: "HYG", label: "HYG (پربازده)", term: "hyg" },
  { symbol: "IEF", label: "IEF (خزانه)", term: "ief" },
  { symbol: "DFII10", label: "DFII10 (بهره واقعی)", term: "dfii10" },
];

const REFRESH_MS = 60_000;

/* ── Helpers ── */

function authRequest(url: string) {
  const token = getToken();
  return fetch(url, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
}

function authPost(url: string) {
  const token = getToken();
  return fetch(url, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
}

function relativeTime(iso: string | null): string {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "همین الان";
  if (mins < 60) return `${mins} دقیقه پیش`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} ساعت پیش`;
  const days = Math.floor(hours / 24);
  return `${days} روز پیش`;
}

/* ── Component ── */

export default function AdminRegimePage() {
  const [latest, setLatest] = useState<RegimeRow | null>(null);
  const [history, setHistory] = useState<RegimeRow[]>([]);
  const [days, setDays] = useState(90);
  const [loading, setLoading] = useState(true);
  const [backtestData, setBacktestData] = useState<BacktestResult | null>(null);
  const [backtestLoading, setBacktestLoading] = useState(false);
  const [backtestError, setBacktestError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const [latestRes, histRes] = await Promise.all([
        authRequest("/api/regime/latest"),
        authRequest(`/api/regime/history?days=${days}`),
      ]);
      if (latestRes.ok) {
        const d = await latestRes.json();
        if (!d.status || d.status !== "pending") setLatest(d);
      }
      if (histRes.ok) {
        const d = await histRes.json();
        if (Array.isArray(d)) setHistory(d.reverse()); // oldest first for chart
      }
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [days]);

  const fetchRef = useRef(fetchData);
  fetchRef.current = fetchData;

  useEffect(() => {
    setLoading(true);
    fetchRef.current();
  }, [days]);

  useEffect(() => {
    if (timer.current) clearInterval(timer.current);
    timer.current = setInterval(() => fetchRef.current(), REFRESH_MS);
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, []);

  // Backtest handler
  const runBacktest = async () => {
    setBacktestLoading(true);
    setBacktestError(null);
    try {
      const res = await authPost("/api/regime/backtest");
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `HTTP ${res.status}`);
      }
      const data: BacktestResult = await res.json();
      setBacktestData(data);
    } catch (err) {
      setBacktestError(err instanceof Error ? err.message : "خطای ناشناخته");
    } finally {
      setBacktestLoading(false);
    }
  };

  // Backtest chart data
  const backtestChartData = backtestData?.history.map((r) => ({
    date: r.date,
    expansion: Math.round(r.smoothed_p_expansion * 100),
    tightening: Math.round(r.smoothed_p_tightening * 100),
    stress: Math.round(r.smoothed_p_stress * 100),
    recovery: Math.round(r.smoothed_p_recovery * 100),
    lsi: r.lsi,
    usdx: r.usdx,
    rypi: r.rypi,
  })) ?? [];

  // Benchmark event markers for the chart
  const benchmarkMarkers = backtestData?.benchmarks.map((b) => ({
    date: b.start,
    label: b.name,
  })) ?? [];

  // Chart data
  const chartData = history.map((r) => ({
    date: r.ts,
    expansion: Math.round((r.smoothed_p_expansion ?? 0) * 100),
    tightening: Math.round((r.smoothed_p_tightening ?? 0) * 100),
    stress: Math.round((r.smoothed_p_stress ?? 0) * 100),
    recovery: Math.round((r.smoothed_p_recovery ?? 0) * 100),
    lsi: r.liquidity_stress_index,
    usdx: r.usd_pressure_index,
    rypi: r.real_yield_pressure_index,
  }));

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="card animate-pulse p-4">
              <div className="h-4 w-24 rounded bg-gray-200 dark:bg-gray-700" />
              <div className="mt-3 h-8 w-16 rounded bg-gray-200 dark:bg-gray-700" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (!latest || latest.status === "pending") {
    return (
      <div className="card p-8 text-center">
        <p className="text-gray-500 dark:text-gray-400">
          هنوز داده‌ای محاسبه نشده است. منتظر اولین اجرای موتور رژیم باشید.
        </p>
      </div>
    );
  }

  const regime = latest.chosen_regime || "expansion";
  const dominantProb =
    regime === "expansion"
      ? latest.smoothed_p_expansion
      : regime === "tightening"
        ? latest.smoothed_p_tightening
        : regime === "stress"
          ? latest.smoothed_p_stress
          : latest.smoothed_p_recovery;

  return (
    <div className="space-y-6">
      {/* ── Section 1: Status Cards ── */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {/* Current regime */}
        <div className="card p-4">
          <p className="text-xs text-gray-500 dark:text-gray-400">رژیم فعلی <InfoTip term="regime" /></p>
          <div className="mt-1 flex items-center gap-2">
            <span
              className="inline-block h-3 w-3 rounded-full"
              style={{ backgroundColor: REGIME_COLORS[regime] }}
            />
            <span className="text-lg font-bold text-gray-900 dark:text-gray-100">
              {REGIME_LABELS[regime] || regime}
            </span>
            <span className="text-sm font-medium" style={{ color: REGIME_COLORS[regime] }}>
              {dominantProb != null ? `${Math.round(dominantProb * 100)}%` : "—"}
            </span>
          </div>
        </div>

        {/* Data sources */}
        <div className="card p-4">
          <p className="text-xs text-gray-500 dark:text-gray-400">منابع داده</p>
          <div className="mt-1 space-y-1">
            <p className="text-sm text-gray-700 dark:text-gray-300">
              بهره واقعی:{" "}
              <span className="font-mono text-xs">{latest.real_yield_source || "—"}</span>
            </p>
            <p className="text-sm text-gray-700 dark:text-gray-300">
              پراکسی اعتباری:{" "}
              <span className="font-mono text-xs">{latest.credit_proxy_source || "—"}</span>
            </p>
          </div>
        </div>

        {/* Last computation */}
        <div className="card p-4">
          <p className="text-xs text-gray-500 dark:text-gray-400">آخرین محاسبه</p>
          <p className="mt-1 text-lg font-bold text-gray-900 dark:text-gray-100">
            {relativeTime(latest.created_at)}
          </p>
          <p className="text-xs text-gray-400">{latest.ts}</p>
        </div>

        {/* Data coverage */}
        <div className="card p-4">
          <p className="text-xs text-gray-500 dark:text-gray-400">پوشش داده</p>
          <p className="mt-1 text-lg font-bold text-gray-900 dark:text-gray-100">
            {history.length} روز
          </p>
          <p className="text-xs text-gray-400">
            {latest.days_skipped ?? 0} روز حذف شده
          </p>
        </div>
      </div>

      {/* ── Section 2: History Chart ── */}
      <div className="card p-6">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-lg font-bold text-gray-900 dark:text-gray-100">
            تاریخچه رژیم
          </h3>
          <div className="flex gap-1">
            {DAY_OPTIONS.map((d) => (
              <button
                key={d}
                onClick={() => setDays(d)}
                className={`rounded px-3 py-1 text-xs font-medium transition-colors ${
                  days === d
                    ? "bg-gold-500 text-white"
                    : "bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700"
                }`}
              >
                {d} روز
              </button>
            ))}
          </div>
        </div>

        {chartData.length > 0 ? (
          <div className="space-y-6">
            {/* Stacked area chart */}
            <div>
              <p className="mb-2 text-xs text-gray-500 dark:text-gray-400">
                احتمال رژیم‌ها (%)
              </p>
              <ResponsiveContainer width="100%" height={280}>
                <AreaChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 10 }}
                    tickFormatter={(v) => v.slice(5)}
                  />
                  <YAxis domain={[0, 100]} tick={{ fontSize: 10 }} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "#1f2937",
                      border: "none",
                      borderRadius: 8,
                      fontSize: 12,
                    }}
                    formatter={(value, name) => [
                      `${value}%`,
                      REGIME_LABELS[name as string] || name,
                    ]}
                  />
                  <Legend
                    formatter={(value) => REGIME_LABELS[value] || value}
                    wrapperStyle={{ fontSize: 11 }}
                  />
                  <Area
                    type="monotone"
                    dataKey="expansion"
                    stackId="1"
                    fill={REGIME_COLORS.expansion}
                    stroke={REGIME_COLORS.expansion}
                    fillOpacity={0.6}
                  />
                  <Area
                    type="monotone"
                    dataKey="tightening"
                    stackId="1"
                    fill={REGIME_COLORS.tightening}
                    stroke={REGIME_COLORS.tightening}
                    fillOpacity={0.6}
                  />
                  <Area
                    type="monotone"
                    dataKey="stress"
                    stackId="1"
                    fill={REGIME_COLORS.stress}
                    stroke={REGIME_COLORS.stress}
                    fillOpacity={0.6}
                  />
                  <Area
                    type="monotone"
                    dataKey="recovery"
                    stackId="1"
                    fill={REGIME_COLORS.recovery}
                    stroke={REGIME_COLORS.recovery}
                    fillOpacity={0.6}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>

            {/* Index line chart */}
            <div>
              <p className="mb-2 text-xs text-gray-500 dark:text-gray-400">
                شاخص‌های ورودی <InfoTip term="regime" />
              </p>
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 10 }}
                    tickFormatter={(v) => v.slice(5)}
                  />
                  <YAxis domain={[-3, 3]} tick={{ fontSize: 10 }} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "#1f2937",
                      border: "none",
                      borderRadius: 8,
                      fontSize: 12,
                    }}
                    formatter={(value, name) => {
                      const labels: Record<string, string> = {
                        lsi: "فشار نقدینگی",
                        usdx: "فشار دلار",
                        rypi: "فشار بهره واقعی",
                      };
                      const v = typeof value === "number" ? value.toFixed(2) : "—";
                      return [v, labels[name as string] || name];
                    }}
                  />
                  <Legend
                    formatter={(value) => {
                      const labels: Record<string, string> = {
                        lsi: "LSI",
                        usdx: "USDX",
                        rypi: "RYPI",
                      };
                      return labels[value] || value;
                    }}
                    wrapperStyle={{ fontSize: 11 }}
                  />
                  <Line type="monotone" dataKey="lsi" stroke="#EF4444" dot={false} strokeWidth={1.5} />
                  <Line type="monotone" dataKey="usdx" stroke="#3B82F6" dot={false} strokeWidth={1.5} />
                  <Line type="monotone" dataKey="rypi" stroke="#F59E0B" dot={false} strokeWidth={1.5} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        ) : (
          <p className="py-8 text-center text-sm text-gray-400">
            داده‌ای برای نمایش وجود ندارد
          </p>
        )}
      </div>

      {/* ── Section 3: Data Pipeline Health ── */}
      <div className="card p-6">
        <h3 className="mb-4 text-lg font-bold text-gray-900 dark:text-gray-100">
          سلامت خط لوله داده
          <InfoTip term="job_health" />
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 dark:border-gray-700">
                <th className="px-3 py-2 text-right text-xs font-medium text-gray-500">سری</th>
                <th className="px-3 py-2 text-right text-xs font-medium text-gray-500">
                  آخرین داده
                </th>
                <th className="px-3 py-2 text-right text-xs font-medium text-gray-500">
                  تعداد رکورد
                </th>
                <th className="px-3 py-2 text-center text-xs font-medium text-gray-500">
                  وضعیت
                </th>
              </tr>
            </thead>
            <tbody>
              {INPUT_SERIES.map((s) => {
                // Find the last date for this series in the regime data
                const lastRow = history.length > 0 ? history[history.length - 1] : null;
                const lastDate = lastRow?.ts || "—";
                return (
                  <tr
                    key={s.symbol}
                    className="border-b border-gray-100 dark:border-gray-800"
                  >
                    <td className="px-3 py-2 font-medium text-gray-700 dark:text-gray-300">
                      {s.label}
                      <InfoTip term={s.term} />
                    </td>
                    <td className="px-3 py-2 font-mono text-xs text-gray-500">{lastDate}</td>
                    <td className="px-3 py-2 text-gray-500">{history.length}</td>
                    <td className="px-3 py-2 text-center">
                      <span
                        className={`inline-block h-2.5 w-2.5 rounded-full ${
                          history.length > 0 ? "bg-emerald-500" : "bg-red-500"
                        }`}
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Source info */}
        <div className="mt-4 flex flex-wrap gap-4 text-xs text-gray-500">
          <div>
            منبع بهره واقعی:{" "}
            <span className="font-mono text-gray-700 dark:text-gray-300">
              {latest.real_yield_source || "—"}
            </span>
          </div>
          <div>
            منبع اعتباری:{" "}
            <span className="font-mono text-gray-700 dark:text-gray-300">
              {latest.credit_proxy_source || "—"}
            </span>
          </div>
          <div>
            روزهای حذف شده:{" "}
            <span className="font-mono text-gray-700 dark:text-gray-300">
              {latest.days_skipped ?? 0}
            </span>
          </div>
        </div>
      </div>

      {/* ── Section 4: Historical Backtest ── */}
      <div className="card p-6">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-lg font-bold text-gray-900 dark:text-gray-100">
            بک‌تست تاریخی
            <InfoTip term="backtest" />
          </h3>
          <button
            onClick={runBacktest}
            disabled={backtestLoading}
            className="rounded bg-gold-500 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-gold-600 disabled:opacity-50"
          >
            {backtestLoading ? "در حال اجرا..." : "اجرای بک‌تست"}
          </button>
        </div>

        {backtestLoading && (
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              <div className="h-5 w-5 animate-spin rounded-full border-2 border-gold-500 border-t-transparent" />
              <p className="text-sm text-gray-500 dark:text-gray-400">
                در حال بارگذاری داده‌های تاریخی... (حدود ۳۰-۶۰ ثانیه)
              </p>
            </div>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="animate-pulse rounded-lg bg-gray-100 p-4 dark:bg-gray-800">
                  <div className="h-4 w-20 rounded bg-gray-200 dark:bg-gray-700" />
                  <div className="mt-2 h-8 w-16 rounded bg-gray-200 dark:bg-gray-700" />
                </div>
              ))}
            </div>
          </div>
        )}

        {backtestError && (
          <div className="rounded-lg border border-red-200 bg-red-50 p-4 dark:border-red-800 dark:bg-red-900/20">
            <p className="text-sm text-red-700 dark:text-red-400">{backtestError}</p>
          </div>
        )}

        {backtestData && !backtestLoading && (
          <div className="space-y-6">
            {/* Summary cards */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <div className="rounded-lg bg-gray-50 p-4 dark:bg-gray-800">
                <p className="text-xs text-gray-500 dark:text-gray-400">روزهای محاسبه شده</p>
                <p className="mt-1 text-2xl font-bold text-gray-900 dark:text-gray-100">
                  {backtestData.summary.total_days.toLocaleString("fa-IR")}
                </p>
              </div>
              <div className="rounded-lg bg-gray-50 p-4 dark:bg-gray-800">
                <p className="text-xs text-gray-500 dark:text-gray-400">نتیجه بنچمارک</p>
                <p className="mt-1 text-2xl font-bold">
                  <span className="text-emerald-500">{backtestData.summary.passed}</span>
                  <span className="mx-1 text-gray-400">/</span>
                  <span className="text-gray-900 dark:text-gray-100">
                    {backtestData.summary.passed + backtestData.summary.failed}
                  </span>
                </p>
              </div>
              <div className="rounded-lg bg-gray-50 p-4 dark:bg-gray-800">
                <p className="text-xs text-gray-500 dark:text-gray-400">بازه زمانی</p>
                <p className="mt-1 text-sm font-medium text-gray-700 dark:text-gray-300">
                  {backtestData.summary.date_range}
                </p>
              </div>
            </div>

            {/* Benchmark table */}
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 dark:border-gray-700">
                    <th className="px-3 py-2 text-right text-xs font-medium text-gray-500">رویداد</th>
                    <th className="px-3 py-2 text-right text-xs font-medium text-gray-500">دوره</th>
                    <th className="px-3 py-2 text-right text-xs font-medium text-gray-500">رژیم مورد انتظار</th>
                    <th className="px-3 py-2 text-right text-xs font-medium text-gray-500">میانگین احتمال</th>
                    <th className="px-3 py-2 text-right text-xs font-medium text-gray-500">روزهای صحیح</th>
                    <th className="px-3 py-2 text-center text-xs font-medium text-gray-500">وضعیت</th>
                  </tr>
                </thead>
                <tbody>
                  {backtestData.benchmarks.map((bm) => (
                    <tr
                      key={bm.name}
                      className="border-b border-gray-100 dark:border-gray-800"
                    >
                      <td className="px-3 py-2 font-medium text-gray-700 dark:text-gray-300">
                        {bm.name}
                      </td>
                      <td className="px-3 py-2 font-mono text-xs text-gray-500">
                        {bm.start} — {bm.end}
                      </td>
                      <td className="px-3 py-2">
                        <span
                          className="inline-block rounded px-2 py-0.5 text-xs font-medium text-white"
                          style={{
                            backgroundColor: REGIME_COLORS[bm.expected.split(",")[0].trim()] || "#6B7280",
                          }}
                        >
                          {bm.expected.split(",").map((r) => REGIME_LABELS[r.trim()] || r.trim()).join("، ")}
                        </span>
                      </td>
                      <td className="px-3 py-2 font-mono text-xs text-gray-700 dark:text-gray-300">
                        {(bm.avg_prob * 100).toFixed(1)}%
                      </td>
                      <td className="px-3 py-2 font-mono text-xs text-gray-700 dark:text-gray-300">
                        {(bm.pct_days_correct * 100).toFixed(0)}%
                      </td>
                      <td className="px-3 py-2 text-center">
                        <span
                          className={`inline-block rounded px-2 py-0.5 text-xs font-bold ${
                            bm.passed
                              ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400"
                              : "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400"
                          }`}
                        >
                          {bm.passed ? "PASS" : "FAIL"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* 10-year regime chart */}
            {backtestChartData.length > 0 && (
              <div className="space-y-6">
                <div>
                  <p className="mb-2 text-xs text-gray-500 dark:text-gray-400">
                    تاریخچه رژیم (بک‌تست ۱۰+ ساله)
                  </p>
                  <ResponsiveContainer width="100%" height={300}>
                    <AreaChart data={backtestChartData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
                      <XAxis
                        dataKey="date"
                        tick={{ fontSize: 9 }}
                        tickFormatter={(v) => v.slice(0, 7)}
                        interval="preserveStartEnd"
                      />
                      <YAxis domain={[0, 100]} tick={{ fontSize: 10 }} />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: "#1f2937",
                          border: "none",
                          borderRadius: 8,
                          fontSize: 12,
                        }}
                        formatter={(value, name) => [
                          `${value}%`,
                          REGIME_LABELS[name as string] || name,
                        ]}
                      />
                      <Legend
                        formatter={(value) => REGIME_LABELS[value] || value}
                        wrapperStyle={{ fontSize: 11 }}
                      />
                      {benchmarkMarkers.map((m) => (
                        <ReferenceLine
                          key={m.date}
                          x={m.date}
                          stroke="#9CA3AF"
                          strokeDasharray="4 4"
                          label={{
                            value: m.label,
                            position: "top",
                            fontSize: 9,
                            fill: "#9CA3AF",
                          }}
                        />
                      ))}
                      <Area
                        type="monotone"
                        dataKey="expansion"
                        stackId="1"
                        fill={REGIME_COLORS.expansion}
                        stroke={REGIME_COLORS.expansion}
                        fillOpacity={0.6}
                      />
                      <Area
                        type="monotone"
                        dataKey="tightening"
                        stackId="1"
                        fill={REGIME_COLORS.tightening}
                        stroke={REGIME_COLORS.tightening}
                        fillOpacity={0.6}
                      />
                      <Area
                        type="monotone"
                        dataKey="stress"
                        stackId="1"
                        fill={REGIME_COLORS.stress}
                        stroke={REGIME_COLORS.stress}
                        fillOpacity={0.6}
                      />
                      <Area
                        type="monotone"
                        dataKey="recovery"
                        stackId="1"
                        fill={REGIME_COLORS.recovery}
                        stroke={REGIME_COLORS.recovery}
                        fillOpacity={0.6}
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>

                {/* 10-year index chart */}
                <div>
                  <p className="mb-2 text-xs text-gray-500 dark:text-gray-400">
                    شاخص‌های ورودی (بک‌تست)
                  </p>
                  <ResponsiveContainer width="100%" height={220}>
                    <LineChart data={backtestChartData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
                      <XAxis
                        dataKey="date"
                        tick={{ fontSize: 9 }}
                        tickFormatter={(v) => v.slice(0, 7)}
                        interval="preserveStartEnd"
                      />
                      <YAxis domain={[-3, 3]} tick={{ fontSize: 10 }} />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: "#1f2937",
                          border: "none",
                          borderRadius: 8,
                          fontSize: 12,
                        }}
                        formatter={(value, name) => {
                          const labels: Record<string, string> = {
                            lsi: "فشار نقدینگی",
                            usdx: "فشار دلار",
                            rypi: "فشار بهره واقعی",
                          };
                          const v = typeof value === "number" ? value.toFixed(2) : "—";
                          return [v, labels[name as string] || name];
                        }}
                      />
                      <Legend
                        formatter={(value) => {
                          const labels: Record<string, string> = {
                            lsi: "LSI",
                            usdx: "USDX",
                            rypi: "RYPI",
                          };
                          return labels[value] || value;
                        }}
                        wrapperStyle={{ fontSize: 11 }}
                      />
                      {benchmarkMarkers.map((m) => (
                        <ReferenceLine
                          key={m.date}
                          x={m.date}
                          stroke="#9CA3AF"
                          strokeDasharray="4 4"
                        />
                      ))}
                      <Line type="monotone" dataKey="lsi" stroke="#EF4444" dot={false} strokeWidth={1.5} />
                      <Line type="monotone" dataKey="usdx" stroke="#3B82F6" dot={false} strokeWidth={1.5} />
                      <Line type="monotone" dataKey="rypi" stroke="#F59E0B" dot={false} strokeWidth={1.5} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
