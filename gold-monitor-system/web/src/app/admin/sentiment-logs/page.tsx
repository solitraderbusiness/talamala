"use client";

import { useCallback, useEffect, useState } from "react";
import { getToken } from "@/lib/auth";
import { cn } from "@/lib/utils";
import type {
  SentimentCalcLogSummary,
  SentimentCalcLogDetail,
  SentimentDiagComponent,
  SentimentDiagnosticsResponse,
} from "@/lib/api";
import {
  getSentimentCalcLogs,
  getSentimentCalcLogDetail,
  getSentimentDiagnostics,
} from "@/lib/api";

/* ── Helpers ───────────────────────────────────────────────────────── */

const COMPONENT_LABELS: Record<string, string> = {
  etf_flows: "جریان ETF",
  cot_positioning: "موقعیت COT",
  real_rates: "نرخ بهره واقعی",
  dollar_strength: "قدرت دلار",
  risk_sentiment: "ریسک بازار",
  price_momentum: "شتاب قیمت",
};

const DIRECTION_LABELS: Record<string, string> = {
  bullish_when_higher: "بالاتر = صعودی",
  inverse: "بالاتر = نزولی",
};

function scoreColor(score: number | null): string {
  if (score == null) return "text-gray-400";
  if (score >= 60) return "text-emerald-500";
  if (score > 40) return "text-gray-400";
  return "text-red-500";
}

function scoreBg(score: number | null): string {
  if (score == null) return "bg-gray-100 dark:bg-gray-800";
  if (score >= 60) return "bg-emerald-50 dark:bg-emerald-900/20";
  if (score > 40) return "bg-gray-50 dark:bg-gray-800/50";
  return "bg-red-50 dark:bg-red-900/20";
}

function saturationBadge(status: string): string {
  if (status === "ok") return "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400";
  if (status === "warning") return "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400";
  return "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400";
}

function timeAgo(ts: string): string {
  const diff = (Date.now() - new Date(ts).getTime()) / 60000;
  if (diff < 1) return "همین الان";
  if (diff < 60) return `${Math.floor(diff)} دقیقه پیش`;
  if (diff < 1440) return `${Math.floor(diff / 60)} ساعت پیش`;
  return `${Math.floor(diff / 1440)} روز پیش`;
}

/* ── Tabs ──────────────────────────────────────────────────────────── */

type Tab = "list" | "diagnostics";

/* ── Component ─────────────────────────────────────────────────────── */

export default function SentimentLogsPage() {
  const [tab, setTab] = useState<Tab>("list");
  const [logs, setLogs] = useState<SentimentCalcLogSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  // Detail drill-down
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<SentimentCalcLogDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // Diagnostics
  const [diag, setDiag] = useState<SentimentDiagnosticsResponse | null>(null);
  const [diagDays, setDiagDays] = useState(60);
  const [diagLoading, setDiagLoading] = useState(false);

  const fetchLogs = useCallback(async () => {
    const token = getToken();
    if (!token) return;
    setLoading(true);
    try {
      const data = await getSentimentCalcLogs(token, 100);
      setLogs(data.items);
      setTotal(data.total);
    } catch { /* ignore */ }
    setLoading(false);
  }, []);

  const fetchDetail = useCallback(async (runId: string) => {
    const token = getToken();
    if (!token) return;
    setDetailLoading(true);
    try {
      const data = await getSentimentCalcLogDetail(token, runId);
      setDetail(data);
    } catch { /* ignore */ }
    setDetailLoading(false);
  }, []);

  const fetchDiag = useCallback(async () => {
    const token = getToken();
    if (!token) return;
    setDiagLoading(true);
    try {
      const data = await getSentimentDiagnostics(token, diagDays);
      setDiag(data);
    } catch { /* ignore */ }
    setDiagLoading(false);
  }, [diagDays]);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  useEffect(() => {
    if (tab === "diagnostics" && !diag) {
      fetchDiag();
    }
  }, [tab, diag, fetchDiag]);

  // Fetch detail when expanding a row
  useEffect(() => {
    if (expandedId) {
      fetchDetail(expandedId);
    } else {
      setDetail(null);
    }
  }, [expandedId, fetchDetail]);

  if (loading && logs.length === 0) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <div className="h-10 w-10 animate-spin rounded-full border-4 border-gold-500 border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {/* Header */}
      <div>
        <h1 className="text-lg font-bold text-gray-900 dark:text-gray-100">
          لاگ محاسبات احساسات
        </h1>
        <p className="text-xs text-gray-500 dark:text-gray-400">
          حسابرسی محاسبات شاخص احساسات — جزئیات هر اجرا، درصدک‌ها، هشدارها و تشخیص کیفیت
        </p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 rounded-lg bg-gray-100 p-1 dark:bg-gray-800">
        <button
          onClick={() => setTab("list")}
          className={cn(
            "rounded-md px-4 py-1.5 text-xs font-bold transition-colors",
            tab === "list"
              ? "bg-white text-gray-900 shadow-sm dark:bg-gray-700 dark:text-gray-100"
              : "text-gray-500 hover:text-gray-700 dark:text-gray-400"
          )}
        >
          تاریخچه اجراها ({total})
        </button>
        <button
          onClick={() => setTab("diagnostics")}
          className={cn(
            "rounded-md px-4 py-1.5 text-xs font-bold transition-colors",
            tab === "diagnostics"
              ? "bg-white text-gray-900 shadow-sm dark:bg-gray-700 dark:text-gray-100"
              : "text-gray-500 hover:text-gray-700 dark:text-gray-400"
          )}
        >
          تشخیص کیفیت
        </button>
      </div>

      {/* Tab content */}
      {tab === "list" ? (
        <RunListView
          logs={logs}
          expandedId={expandedId}
          detail={detail}
          detailLoading={detailLoading}
          onToggle={(id) => setExpandedId(expandedId === id ? null : id)}
        />
      ) : (
        <DiagnosticsView
          diag={diag}
          loading={diagLoading}
          days={diagDays}
          onDaysChange={(d) => { setDiagDays(d); setDiag(null); }}
        />
      )}
    </div>
  );
}

/* ── Run List View ─────────────────────────────────────────────────── */

function RunListView({
  logs,
  expandedId,
  detail,
  detailLoading,
  onToggle,
}: {
  logs: SentimentCalcLogSummary[];
  expandedId: string | null;
  detail: SentimentCalcLogDetail | null;
  detailLoading: boolean;
  onToggle: (id: string) => void;
}) {
  if (logs.length === 0) {
    return (
      <div className="card text-center text-sm text-gray-400 py-12">
        هنوز هیچ محاسبه‌ای ثبت نشده
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-gray-200 dark:border-gray-800">
      <table className="w-full text-xs">
        <thead className="bg-gray-50 dark:bg-gray-800/50">
          <tr>
            <th className="px-3 py-2 text-right font-bold text-gray-500 dark:text-gray-400">زمان</th>
            <th className="px-3 py-2 text-right font-bold text-gray-500 dark:text-gray-400">امتیاز</th>
            <th className="px-3 py-2 text-right font-bold text-gray-500 dark:text-gray-400">برچسب</th>
            <th className="px-3 py-2 text-right font-bold text-gray-500 dark:text-gray-400">هشدارها</th>
            <th className="px-3 py-2 text-right font-bold text-gray-500 dark:text-gray-400">وضعیت</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
          {logs.map((log) => (
            <RunRow
              key={log.id}
              log={log}
              expanded={expandedId === log.id}
              detail={expandedId === log.id ? detail : null}
              detailLoading={expandedId === log.id && detailLoading}
              onToggle={() => onToggle(log.id)}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ── Single Run Row ────────────────────────────────────────────────── */

function RunRow({
  log,
  expanded,
  detail,
  detailLoading,
  onToggle,
}: {
  log: SentimentCalcLogSummary;
  expanded: boolean;
  detail: SentimentCalcLogDetail | null;
  detailLoading: boolean;
  onToggle: () => void;
}) {
  return (
    <>
      <tr
        className="cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/30"
        onClick={onToggle}
      >
        <td className="whitespace-nowrap px-3 py-2.5 text-gray-500 dark:text-gray-400">
          {log.run_at ? timeAgo(log.run_at) : "—"}
          <div className="text-[10px] text-gray-400">
            {log.run_at ? new Date(log.run_at).toLocaleString("fa-IR") : ""}
          </div>
        </td>
        <td className="whitespace-nowrap px-3 py-2.5">
          <span className={cn("text-lg font-bold", scoreColor(log.overall_score))}>
            {log.overall_score ?? "—"}
          </span>
          <span className="text-[10px] text-gray-400">/100</span>
        </td>
        <td className="whitespace-nowrap px-3 py-2.5">
          <span className={cn(
            "rounded-full px-2.5 py-0.5 text-[11px] font-bold",
            scoreColor(log.overall_score),
          )}>
            {log.overall_label_fa || log.overall_label || "—"}
          </span>
        </td>
        <td className="whitespace-nowrap px-3 py-2.5">
          <div className="flex items-center gap-1.5">
            {log.warning_count > 0 && (
              <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-bold text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
                {log.warning_count} هشدار
              </span>
            )}
            {log.has_stale && (
              <span className="rounded bg-orange-100 px-1.5 py-0.5 text-[10px] font-bold text-orange-700 dark:bg-orange-900/30 dark:text-orange-400">
                قدیمی
              </span>
            )}
            {log.has_fallback && (
              <span className="rounded bg-purple-100 px-1.5 py-0.5 text-[10px] font-bold text-purple-700 dark:bg-purple-900/30 dark:text-purple-400">
                پیش‌فرض
              </span>
            )}
          </div>
        </td>
        <td className="px-3 py-2.5">
          <svg
            className={cn("h-4 w-4 text-gray-400 transition-transform", expanded && "rotate-90")}
            viewBox="0 0 20 20"
            fill="currentColor"
          >
            <path fillRule="evenodd" d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z" clipRule="evenodd" />
          </svg>
        </td>
      </tr>
      {expanded && (
        <tr className="bg-gray-50/80 dark:bg-gray-800/20">
          <td colSpan={5} className="px-4 py-4">
            {detailLoading ? (
              <div className="flex items-center justify-center py-6">
                <div className="h-6 w-6 animate-spin rounded-full border-2 border-gold-500 border-t-transparent" />
              </div>
            ) : detail ? (
              <RunDetail detail={detail} />
            ) : (
              <p className="text-center text-xs text-gray-400">خطا در بارگذاری جزئیات</p>
            )}
          </td>
        </tr>
      )}
    </>
  );
}

/* ── Run Detail (expanded) ─────────────────────────────────────────── */

function RunDetail({ detail }: { detail: SentimentCalcLogDetail }) {
  return (
    <div className="space-y-4">
      {/* Meta */}
      <div className="flex flex-wrap gap-4 text-[11px] text-gray-500">
        <span>
          شناسه: <code className="font-mono text-gray-600 dark:text-gray-400">{detail.id.slice(0, 12)}</code>
        </span>
        {detail.app_version && (
          <span>
            نسخه: <code className="font-mono text-gray-600 dark:text-gray-400">{detail.app_version}</code>
          </span>
        )}
        <span>
          زمان: {detail.run_at ? new Date(detail.run_at).toLocaleString("fa-IR") : "—"}
        </span>
      </div>

      {/* Components grid */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {detail.components.map((comp: Record<string, unknown>, idx) => {
          const name = comp.name as string;
          const score = comp.score as number | null;
          const percentile = comp.percentile as number | null;
          const rawValue = comp.raw_value as number | string | null;
          const rawUnits = comp.raw_units as string | null;
          const direction = comp.direction as string | null;
          const windowSize = comp.window_size as number | null;
          const crowded = comp.crowded as boolean | undefined;
          const stale = comp.stale as boolean | undefined;
          const fallbackUsed = comp.fallback_used as boolean | undefined;
          const weight = comp.weight as number | null;
          const explanation = comp.explanation as string | null;
          const smoothedValue = comp.smoothed_value as number | null;
          const winBounds = comp.winsorize_bounds as [number, number] | null;

          return (
            <div
              key={idx}
              className={cn(
                "rounded-lg border p-3",
                stale
                  ? "border-orange-300 dark:border-orange-700"
                  : fallbackUsed
                    ? "border-purple-300 dark:border-purple-700"
                    : "border-gray-200 dark:border-gray-700",
                scoreBg(score),
              )}
            >
              {/* Header */}
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-bold text-gray-900 dark:text-gray-100">
                  {COMPONENT_LABELS[name] || name}
                </span>
                <div className="flex items-center gap-1.5">
                  {stale && (
                    <span className="rounded bg-orange-100 px-1 py-0.5 text-[9px] font-bold text-orange-700 dark:bg-orange-900/30 dark:text-orange-400">
                      قدیمی
                    </span>
                  )}
                  {crowded && (
                    <span className="rounded bg-red-100 px-1 py-0.5 text-[9px] font-bold text-red-700 dark:bg-red-900/30 dark:text-red-400">
                      اشباع
                    </span>
                  )}
                  {fallbackUsed && (
                    <span className="rounded bg-purple-100 px-1 py-0.5 text-[9px] font-bold text-purple-700 dark:bg-purple-900/30 dark:text-purple-400">
                      پیش‌فرض
                    </span>
                  )}
                </div>
              </div>

              {/* Score + percentile */}
              <div className="flex items-baseline gap-2 mb-2">
                <span className={cn("text-2xl font-bold", scoreColor(score))}>
                  {score ?? "—"}
                </span>
                {percentile != null && (
                  <span className="text-[10px] text-gray-400">
                    p{Math.round(percentile * 100)}
                  </span>
                )}
                {weight != null && (
                  <span className="text-[10px] text-gray-400">
                    (وزن: {weight}%)
                  </span>
                )}
              </div>

              {/* Details grid */}
              <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[10px]">
                {rawValue != null && (
                  <>
                    <span className="text-gray-400">مقدار خام:</span>
                    <span className="font-mono text-gray-600 dark:text-gray-300">
                      {typeof rawValue === "number" ? rawValue.toFixed(4) : rawValue}
                      {rawUnits && <span className="mr-0.5 text-gray-400"> {rawUnits}</span>}
                    </span>
                  </>
                )}
                {smoothedValue != null && (
                  <>
                    <span className="text-gray-400">مقدار صاف‌شده:</span>
                    <span className="font-mono text-gray-600 dark:text-gray-300">
                      {smoothedValue.toFixed(4)}
                    </span>
                  </>
                )}
                {direction && (
                  <>
                    <span className="text-gray-400">جهت:</span>
                    <span className="text-gray-600 dark:text-gray-300">
                      {DIRECTION_LABELS[direction] || direction}
                    </span>
                  </>
                )}
                {windowSize != null && (
                  <>
                    <span className="text-gray-400">پنجره:</span>
                    <span className="text-gray-600 dark:text-gray-300">
                      {windowSize} نقطه داده
                    </span>
                  </>
                )}
                {winBounds && (
                  <>
                    <span className="text-gray-400">حدود Winsorize:</span>
                    <span className="font-mono text-gray-600 dark:text-gray-300">
                      [{winBounds[0]?.toFixed(2)}, {winBounds[1]?.toFixed(2)}]
                    </span>
                  </>
                )}
              </div>

              {/* Explanation */}
              {explanation && (
                <p className="mt-2 whitespace-pre-line rounded bg-white/60 px-2 py-1.5 text-[10px] leading-relaxed text-gray-500 dark:bg-gray-900/40 dark:text-gray-400">
                  {explanation}
                </p>
              )}
            </div>
          );
        })}
      </div>

      {/* Warnings */}
      {detail.warnings.length > 0 && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 dark:border-amber-800 dark:bg-amber-900/10">
          <div className="mb-1.5 text-[11px] font-bold text-amber-700 dark:text-amber-400">
            هشدارها ({detail.warnings.length})
          </div>
          <ul className="space-y-1">
            {detail.warnings.map((w, i) => (
              <li key={i} className="text-[10px] text-amber-600 dark:text-amber-300">
                {w}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

/* ── Diagnostics View ──────────────────────────────────────────────── */

function DiagnosticsView({
  diag,
  loading,
  days,
  onDaysChange,
}: {
  diag: SentimentDiagnosticsResponse | null;
  loading: boolean;
  days: number;
  onDaysChange: (d: number) => void;
}) {
  return (
    <div className="space-y-4">
      {/* Period selector */}
      <div className="flex items-center gap-3">
        <label className="text-xs font-bold text-gray-500 dark:text-gray-400">
          دوره تحلیل:
        </label>
        <select
          value={days}
          onChange={(e) => onDaysChange(Number(e.target.value))}
          className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-xs dark:border-gray-700 dark:bg-gray-900"
        >
          <option value={7}>۷ روز</option>
          <option value={30}>۳۰ روز</option>
          <option value={60}>۶۰ روز</option>
          <option value={180}>۶ ماه</option>
          <option value={365}>۱ سال</option>
        </select>
      </div>

      {loading ? (
        <div className="flex min-h-[20vh] items-center justify-center">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-gold-500 border-t-transparent" />
        </div>
      ) : !diag ? (
        <div className="card text-center text-sm text-gray-400 py-12">
          خطا در بارگذاری تشخیص‌ها
        </div>
      ) : (
        <>
          {/* Summary cards */}
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="card">
              <div className="text-xs font-bold text-gray-500 dark:text-gray-400">تعداد اجراها</div>
              <div className="mt-1 text-2xl font-bold text-gray-900 dark:text-gray-100">
                {diag.total_runs.toLocaleString("fa-IR")}
              </div>
              <div className="text-[10px] text-gray-400">در {days} روز گذشته</div>
            </div>
            <div className="card">
              <div className="text-xs font-bold text-gray-500 dark:text-gray-400">اجزای فعال</div>
              <div className="mt-1 text-2xl font-bold text-gray-900 dark:text-gray-100">
                {diag.components.length}
              </div>
            </div>
            <div className="card">
              <div className="text-xs font-bold text-gray-500 dark:text-gray-400">هشدارهای کیفیت</div>
              <div className={cn(
                "mt-1 text-2xl font-bold",
                diag.quality_warnings.length > 0 ? "text-amber-600" : "text-emerald-600"
              )}>
                {diag.quality_warnings.length}
              </div>
            </div>
          </div>

          {/* Quality warnings */}
          {diag.quality_warnings.length > 0 && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 dark:border-amber-800 dark:bg-amber-900/10">
              <div className="mb-1.5 text-[11px] font-bold text-amber-700 dark:text-amber-400">
                هشدارهای کیفیت
              </div>
              <ul className="space-y-1">
                {diag.quality_warnings.map((w, i) => (
                  <li key={i} className="text-[10px] text-amber-600 dark:text-amber-300">
                    {w}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Per-component diagnostics */}
          <div className="overflow-x-auto rounded-xl border border-gray-200 dark:border-gray-800">
            <table className="w-full text-xs">
              <thead className="bg-gray-50 dark:bg-gray-800/50">
                <tr>
                  <th className="px-3 py-2 text-right font-bold text-gray-500 dark:text-gray-400">جزء</th>
                  <th className="px-3 py-2 text-right font-bold text-gray-500 dark:text-gray-400">اشباع</th>
                  <th className="px-3 py-2 text-right font-bold text-gray-500 dark:text-gray-400">میانگین</th>
                  <th className="px-3 py-2 text-right font-bold text-gray-500 dark:text-gray-400">میانه</th>
                  <th className="px-3 py-2 text-right font-bold text-gray-500 dark:text-gray-400">بازه</th>
                  <th className="px-3 py-2 text-right font-bold text-gray-500 dark:text-gray-400">انحراف</th>
                  <th className="px-3 py-2 text-right font-bold text-gray-500 dark:text-gray-400">قدیمی%</th>
                  <th className="px-3 py-2 text-right font-bold text-gray-500 dark:text-gray-400">پیش‌فرض%</th>
                  <th className="px-3 py-2 text-right font-bold text-gray-500 dark:text-gray-400">ازدحام%</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                {diag.components.map((comp) => (
                  <DiagRow key={comp.component} comp={comp} />
                ))}
                {diag.components.length === 0 && (
                  <tr>
                    <td colSpan={9} className="px-4 py-8 text-center text-gray-400">
                      داده‌ای موجود نیست
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Legend */}
          <div className="flex flex-wrap gap-4 text-[10px] text-gray-400">
            <span>
              <span className="inline-block h-2 w-2 rounded-full bg-emerald-400 ml-1" />
              اشباع &lt; 5%
            </span>
            <span>
              <span className="inline-block h-2 w-2 rounded-full bg-amber-400 ml-1" />
              اشباع 5-10%
            </span>
            <span>
              <span className="inline-block h-2 w-2 rounded-full bg-red-400 ml-1" />
              اشباع &gt; 10%
            </span>
            <span>هدف میانه: ≈50 (انحراف &lt; 15 نرمال)</span>
          </div>
        </>
      )}
    </div>
  );
}

/* ── Diagnostics Row ───────────────────────────────────────────────── */

function DiagRow({ comp }: { comp: SentimentDiagComponent }) {
  return (
    <tr className="hover:bg-gray-50 dark:hover:bg-gray-800/30">
      <td className="whitespace-nowrap px-3 py-2.5 font-bold text-gray-900 dark:text-gray-100">
        {COMPONENT_LABELS[comp.component] || comp.component}
        <div className="text-[10px] font-normal text-gray-400">
          {comp.run_count} اجرا
        </div>
      </td>
      <td className="whitespace-nowrap px-3 py-2.5">
        <span className={cn(
          "rounded-full px-2 py-0.5 text-[10px] font-bold",
          saturationBadge(comp.saturation_status),
        )}>
          {comp.saturation_pct}%
        </span>
      </td>
      <td className={cn("whitespace-nowrap px-3 py-2.5 font-mono", scoreColor(comp.mean_score))}>
        {comp.mean_score}
      </td>
      <td className={cn(
        "whitespace-nowrap px-3 py-2.5 font-mono font-bold",
        Math.abs(comp.median_score - 50) > 15 ? "text-amber-600" : "text-gray-700 dark:text-gray-300"
      )}>
        {comp.median_score}
      </td>
      <td className="whitespace-nowrap px-3 py-2.5 font-mono text-gray-500">
        {comp.min_score}–{comp.max_score}
      </td>
      <td className="whitespace-nowrap px-3 py-2.5 font-mono text-gray-500">
        {comp.std_dev}
      </td>
      <td className={cn(
        "whitespace-nowrap px-3 py-2.5",
        comp.stale_pct > 20 ? "font-bold text-orange-600" : "text-gray-500"
      )}>
        {comp.stale_pct}%
      </td>
      <td className={cn(
        "whitespace-nowrap px-3 py-2.5",
        comp.fallback_pct > 10 ? "font-bold text-purple-600" : "text-gray-500"
      )}>
        {comp.fallback_pct}%
      </td>
      <td className={cn(
        "whitespace-nowrap px-3 py-2.5",
        comp.crowded_pct > 20 ? "font-bold text-red-600" : "text-gray-500"
      )}>
        {comp.crowded_pct}%
      </td>
    </tr>
  );
}
