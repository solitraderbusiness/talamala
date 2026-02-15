"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { getToken } from "@/lib/auth";

/* ── Types ── */

interface DataDepthRow {
  table: string;
  label_fa: string;
  rows: number;
  earliest: string | null;
  latest: string | null;
}

interface BackfillStatus {
  status: string;
  job_id?: string;
  phase?: string;
  phase_name?: string;
  phase_total?: string;
  detail?: string;
  updated_at?: string;
}

interface BenchmarkResult {
  name: string;
  start: string;
  end: string;
  expected: string;
  actual: string;
  passed: boolean;
  reason: string;
}

interface BacktestResult {
  run_id: string;
  status: string;
  total_benchmarks: number;
  passed: number;
  failed: number;
  results: {
    regime: BenchmarkResult[];
    correlation: BenchmarkResult[];
    sentiment: BenchmarkResult[];
    events: BenchmarkResult[];
  };
}

interface BacktestHistoryRow {
  id: string;
  run_type: string;
  started_at: string | null;
  finished_at: string | null;
  status: string;
  total_benchmarks: number | null;
  passed_benchmarks: number | null;
  failed_benchmarks: number | null;
  triggered_by: string | null;
  error_message: string | null;
}

/* ── Helpers ── */

const PHASE_LABELS: Record<string, string> = {
  yahoo_prices: "قیمت‌های Yahoo Finance",
  fred_macro: "شاخص‌های FRED",
  cot_history: "آرشیو COT",
  correlations: "همبستگی‌ها",
  regime_scores: "رژیم نقدینگی",
  events: "رویدادها",
  sentiment: "احساسات بازار",
  validation: "اعتبارسنجی",
};

const CATEGORY_LABELS: Record<string, string> = {
  regime: "رژیم",
  correlation: "همبستگی",
  sentiment: "احساسات",
  events: "رویدادها",
};

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

export default function AdminBacktestPage() {
  const [dataDepth, setDataDepth] = useState<DataDepthRow[]>([]);
  const [backfillStatus, setBackfillStatus] = useState<BackfillStatus | null>(null);
  const [backfillPolling, setBackfillPolling] = useState(false);
  const [backtestResult, setBacktestResult] = useState<BacktestResult | null>(null);
  const [backtestLoading, setBacktestLoading] = useState(false);
  const [backtestError, setBacktestError] = useState<string | null>(null);
  const [history, setHistory] = useState<BacktestHistoryRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<string>("regime");

  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  // Fetch data depth and history
  const fetchData = useCallback(async () => {
    try {
      const [depthRes, histRes] = await Promise.allSettled([
        authRequest("/api/admin/backtest/data-depth"),
        authRequest("/api/admin/backtest/history?limit=10"),
      ]);

      if (depthRes.status === "fulfilled" && depthRes.value.ok) {
        const d = await depthRes.value.json();
        setDataDepth(d.tables || []);
      }
      if (histRes.status === "fulfilled" && histRes.value.ok) {
        const h = await histRes.value.json();
        if (Array.isArray(h)) setHistory(h);
      }
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Backfill polling
  const startPolling = useCallback(() => {
    if (pollTimer.current) clearInterval(pollTimer.current);
    setBackfillPolling(true);

    const poll = async () => {
      try {
        const res = await authRequest("/api/admin/backtest/backfill/status");
        if (res.ok) {
          const data: BackfillStatus = await res.json();
          setBackfillStatus(data);
          if (data.status === "completed" || data.status === "failed" || data.status === "idle") {
            setBackfillPolling(false);
            if (pollTimer.current) clearInterval(pollTimer.current);
            // Refresh data depth
            fetchData();
          }
        }
      } catch {
        // silent
      }
    };

    poll();
    pollTimer.current = setInterval(poll, 2000);
  }, [fetchData]);

  useEffect(() => {
    return () => {
      if (pollTimer.current) clearInterval(pollTimer.current);
    };
  }, []);

  // Start backfill
  const startBackfill = async () => {
    try {
      const res = await authPost("/api/admin/backtest/backfill?start_date=2014-01-01");
      if (res.ok) {
        const data = await res.json();
        setBackfillStatus({ status: "starting", job_id: data.job_id });
        startPolling();
      }
    } catch (err) {
      setBackfillStatus({
        status: "error",
        detail: err instanceof Error ? err.message : "خطا",
      });
    }
  };

  // Run backtest
  const runBacktest = async () => {
    setBacktestLoading(true);
    setBacktestError(null);
    try {
      const res = await authPost("/api/admin/backtest/run");
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `HTTP ${res.status}`);
      }
      const data: BacktestResult = await res.json();
      setBacktestResult(data);
      // Refresh history
      fetchData();
    } catch (err) {
      setBacktestError(err instanceof Error ? err.message : "خطای ناشناخته");
    } finally {
      setBacktestLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <div className="h-10 w-10 animate-spin rounded-full border-4 border-gold-500 border-t-transparent" />
      </div>
    );
  }

  const phaseNum = backfillStatus?.phase ? parseInt(backfillStatus.phase) : 0;
  const phaseTotal = backfillStatus?.phase_total ? parseInt(backfillStatus.phase_total) : 8;
  const progressPct = phaseTotal > 0 ? Math.round((phaseNum / phaseTotal) * 100) : 0;

  const categories = backtestResult
    ? (["regime", "correlation", "sentiment", "events"] as const)
    : [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100">
          بک‌تست جامع
        </h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          بارگذاری داده‌های ۱۰+ ساله و اعتبارسنجی متریک‌ها با بنچمارک‌های تاریخی
        </p>
      </div>

      {/* ── Section 1: Data Depth ── */}
      <div className="card p-6">
        <h3 className="mb-4 text-lg font-bold text-gray-900 dark:text-gray-100">
          عمق داده‌ها
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 dark:border-gray-700">
                <th className="px-3 py-2 text-right text-xs font-medium text-gray-500">جدول</th>
                <th className="px-3 py-2 text-right text-xs font-medium text-gray-500">تعداد ردیف</th>
                <th className="px-3 py-2 text-right text-xs font-medium text-gray-500">قدیمی‌ترین</th>
                <th className="px-3 py-2 text-right text-xs font-medium text-gray-500">جدیدترین</th>
              </tr>
            </thead>
            <tbody>
              {dataDepth.map((row) => (
                <tr key={row.table} className="border-b border-gray-100 dark:border-gray-800">
                  <td className="px-3 py-2 font-medium text-gray-700 dark:text-gray-300">
                    {row.label_fa}
                  </td>
                  <td className="px-3 py-2 font-mono text-xs text-gray-700 dark:text-gray-300">
                    {row.rows.toLocaleString("fa-IR")}
                  </td>
                  <td className="px-3 py-2 font-mono text-xs text-gray-500">
                    {row.earliest ? row.earliest.slice(0, 10) : "—"}
                  </td>
                  <td className="px-3 py-2 font-mono text-xs text-gray-500">
                    {row.latest ? row.latest.slice(0, 10) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* ── Section 2: Backfill Control ── */}
      <div className="card p-6">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-lg font-bold text-gray-900 dark:text-gray-100">
            بارگذاری داده‌های تاریخی
          </h3>
          <button
            onClick={startBackfill}
            disabled={backfillPolling}
            className="rounded bg-gold-500 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-gold-600 disabled:opacity-50"
          >
            {backfillPolling ? "در حال اجرا..." : "شروع بارگذاری"}
          </button>
        </div>

        {/* Progress */}
        {backfillStatus && backfillStatus.status !== "idle" && (
          <div className="space-y-3">
            {/* Progress bar */}
            <div>
              <div className="mb-1 flex items-center justify-between text-xs text-gray-500">
                <span>
                  فاز {backfillStatus.phase || 0} از {phaseTotal}
                  {backfillStatus.phase_name && (
                    <span className="mr-2 text-gray-700 dark:text-gray-300">
                      — {PHASE_LABELS[backfillStatus.phase_name] || backfillStatus.phase_name}
                    </span>
                  )}
                </span>
                <span>{progressPct}%</span>
              </div>
              <div className="h-3 w-full overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
                <div
                  className="h-full rounded-full bg-gold-500 transition-all duration-500"
                  style={{ width: `${progressPct}%` }}
                />
              </div>
            </div>

            {/* Detail */}
            {backfillStatus.detail && (
              <p className="text-xs text-gray-500 dark:text-gray-400">
                {backfillStatus.detail}
              </p>
            )}

            {/* Phase list */}
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {Object.entries(PHASE_LABELS).map(([key, label], idx) => {
                const phaseIdx = idx + 1;
                const isCurrent = phaseIdx === phaseNum;
                const isDone = phaseNum > phaseIdx;
                const isCompleted = backfillStatus.status === "completed";

                return (
                  <div
                    key={key}
                    className={`rounded-lg border px-3 py-2 text-xs transition-colors ${
                      isCompleted || isDone
                        ? "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-900/20 dark:text-emerald-400"
                        : isCurrent
                          ? "border-gold-300 bg-gold-50 text-gold-700 dark:border-gold-700 dark:bg-gold-900/20 dark:text-gold-400"
                          : "border-gray-200 bg-gray-50 text-gray-400 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-500"
                    }`}
                  >
                    <div className="flex items-center gap-1.5">
                      {(isCompleted || isDone) && <span>&#10003;</span>}
                      {isCurrent && !isCompleted && (
                        <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-gold-500" />
                      )}
                      <span>{label}</span>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Completed message */}
            {backfillStatus.status === "completed" && (
              <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700 dark:border-emerald-800 dark:bg-emerald-900/20 dark:text-emerald-400">
                بارگذاری داده‌ها با موفقیت کامل شد. حالا می‌توانید بک‌تست را اجرا کنید.
              </div>
            )}

            {backfillStatus.status === "failed" && (
              <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-400">
                خطا در بارگذاری: {backfillStatus.detail || "خطای ناشناخته"}
              </div>
            )}
          </div>
        )}

        {(!backfillStatus || backfillStatus.status === "idle") && (
          <p className="text-sm text-gray-500 dark:text-gray-400">
            با کلیک روی دکمه بالا، داده‌های ۱۰+ ساله از Yahoo Finance، FRED، و CFTC بارگذاری
            می‌شود. سپس همبستگی‌ها، رژیم، رویدادها و احساسات محاسبه می‌شوند. این فرایند
            ممکن است چند دقیقه طول بکشد.
          </p>
        )}
      </div>

      {/* ── Section 3: Validation Backtest ── */}
      <div className="card p-6">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-lg font-bold text-gray-900 dark:text-gray-100">
            بک‌تست اعتبارسنجی
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
          <div className="flex items-center gap-3 py-4">
            <div className="h-5 w-5 animate-spin rounded-full border-2 border-gold-500 border-t-transparent" />
            <p className="text-sm text-gray-500 dark:text-gray-400">
              در حال بررسی بنچمارک‌ها...
            </p>
          </div>
        )}

        {backtestError && (
          <div className="rounded-lg border border-red-200 bg-red-50 p-4 dark:border-red-800 dark:bg-red-900/20">
            <p className="text-sm text-red-700 dark:text-red-400">{backtestError}</p>
          </div>
        )}

        {backtestResult && !backtestLoading && (
          <div className="space-y-4">
            {/* Summary */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <div className="rounded-lg bg-gray-50 p-4 dark:bg-gray-800">
                <p className="text-xs text-gray-500 dark:text-gray-400">تعداد بنچمارک</p>
                <p className="mt-1 text-2xl font-bold text-gray-900 dark:text-gray-100">
                  {backtestResult.total_benchmarks}
                </p>
              </div>
              <div className="rounded-lg bg-gray-50 p-4 dark:bg-gray-800">
                <p className="text-xs text-gray-500 dark:text-gray-400">نتیجه</p>
                <p className="mt-1 text-2xl font-bold">
                  <span className="text-emerald-500">{backtestResult.passed}</span>
                  <span className="mx-1 text-gray-400">/</span>
                  <span className="text-gray-900 dark:text-gray-100">
                    {backtestResult.total_benchmarks}
                  </span>
                </p>
              </div>
              <div className="rounded-lg bg-gray-50 p-4 dark:bg-gray-800">
                <p className="text-xs text-gray-500 dark:text-gray-400">درصد موفقیت</p>
                <p className="mt-1 text-2xl font-bold text-gray-900 dark:text-gray-100">
                  {backtestResult.total_benchmarks > 0
                    ? Math.round(
                        (backtestResult.passed / backtestResult.total_benchmarks) * 100
                      )
                    : 0}
                  %
                </p>
              </div>
            </div>

            {/* Tabs */}
            <div className="flex gap-1 border-b border-gray-200 dark:border-gray-700">
              {categories.map((cat) => {
                const results = backtestResult.results[cat] || [];
                const passed = results.filter((r) => r.passed).length;
                return (
                  <button
                    key={cat}
                    onClick={() => setActiveTab(cat)}
                    className={`px-4 py-2 text-sm font-medium transition-colors ${
                      activeTab === cat
                        ? "border-b-2 border-gold-500 text-gold-700 dark:text-gold-400"
                        : "text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300"
                    }`}
                  >
                    {CATEGORY_LABELS[cat]}{" "}
                    <span className="text-xs">
                      ({passed}/{results.length})
                    </span>
                  </button>
                );
              })}
            </div>

            {/* Active tab results */}
            {categories.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-200 dark:border-gray-700">
                      <th className="px-3 py-2 text-right text-xs font-medium text-gray-500">
                        بنچمارک
                      </th>
                      <th className="px-3 py-2 text-right text-xs font-medium text-gray-500">
                        دوره
                      </th>
                      <th className="px-3 py-2 text-right text-xs font-medium text-gray-500">
                        مورد انتظار
                      </th>
                      <th className="px-3 py-2 text-right text-xs font-medium text-gray-500">
                        مقدار واقعی
                      </th>
                      <th className="px-3 py-2 text-center text-xs font-medium text-gray-500">
                        وضعیت
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {(backtestResult.results[activeTab as keyof typeof backtestResult.results] || []).map(
                      (bm) => (
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
                          <td className="px-3 py-2 text-xs text-gray-600 dark:text-gray-400">
                            {bm.expected}
                          </td>
                          <td className="px-3 py-2 font-mono text-xs text-gray-700 dark:text-gray-300">
                            {bm.actual}
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
                      )
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {!backtestResult && !backtestLoading && !backtestError && (
          <p className="text-sm text-gray-500 dark:text-gray-400">
            ابتدا داده‌های تاریخی را بارگذاری کنید، سپس بک‌تست را اجرا کنید. بک‌تست ۱۸
            بنچمارک در ۴ دسته (رژیم، همبستگی، احساسات، رویدادها) را بررسی می‌کند.
          </p>
        )}
      </div>

      {/* ── Section 4: Run History ── */}
      {history.length > 0 && (
        <div className="card p-6">
          <h3 className="mb-4 text-lg font-bold text-gray-900 dark:text-gray-100">
            تاریخچه اجراها
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 dark:border-gray-700">
                  <th className="px-3 py-2 text-right text-xs font-medium text-gray-500">زمان</th>
                  <th className="px-3 py-2 text-right text-xs font-medium text-gray-500">نوع</th>
                  <th className="px-3 py-2 text-right text-xs font-medium text-gray-500">نتیجه</th>
                  <th className="px-3 py-2 text-right text-xs font-medium text-gray-500">وضعیت</th>
                  <th className="px-3 py-2 text-right text-xs font-medium text-gray-500">
                    توسط
                  </th>
                </tr>
              </thead>
              <tbody>
                {history.map((run) => (
                  <tr
                    key={run.id}
                    className="border-b border-gray-100 dark:border-gray-800"
                  >
                    <td className="px-3 py-2 text-xs text-gray-500">
                      {relativeTime(run.started_at)}
                    </td>
                    <td className="px-3 py-2 text-xs text-gray-700 dark:text-gray-300">
                      {run.run_type}
                    </td>
                    <td className="px-3 py-2 font-mono text-xs">
                      {run.passed_benchmarks != null && run.total_benchmarks != null ? (
                        <>
                          <span className="text-emerald-500">{run.passed_benchmarks}</span>
                          <span className="text-gray-400">/{run.total_benchmarks}</span>
                        </>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="px-3 py-2">
                      <span
                        className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${
                          run.status === "completed"
                            ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400"
                            : run.status === "failed"
                              ? "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400"
                              : "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400"
                        }`}
                      >
                        {run.status}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-xs text-gray-500">{run.triggered_by || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
