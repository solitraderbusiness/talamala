"use client";

import { useEffect, useState } from "react";
import { getToken } from "@/lib/auth";
import { cn } from "@/lib/utils";

interface IndicatorDebug {
  indicator_id: string;
  score: number;
  percentile: number;
  raw_value: number;
  transformed_value: number;
  smoothed_value: number;
  direction: string;
  window_size: number;
  crowded: boolean;
  stale: boolean;
  fallback_used: boolean;
  last_updated_at: string | null;
  source_name: string;
  source_url: string | null;
  winsorize_bounds: number[] | null;
  smoothing_applied: boolean;
  scoring_method: string;
  zscore: number | null;
  label_fa?: string;
  label_en?: string;
  raw_units?: string;
  raw_transform?: string;
  score_semantics?: Record<string, string>;
}

interface DebugResponse {
  run_id: string;
  indicators: Record<string, IndicatorDebug>;
  count: number;
  computed_at: string;
  error?: string;
}

interface AuditLog {
  id: string;
  run_id: string;
  computed_at: string;
  indicator_id: string;
  score: number;
  percentile: number;
  raw_value: number;
  zscore: number | null;
  stale: boolean;
  fallback_used: boolean;
  context: string;
}

function getScoreColor(score: number): string {
  if (score >= 60) return "text-emerald-500";
  if (score > 40) return "text-yellow-500";
  return "text-red-500";
}

function getScoreBg(score: number): string {
  if (score >= 60) return "bg-emerald-500";
  if (score > 40) return "bg-yellow-500";
  return "bg-red-500";
}

export default function ProvenancePage() {
  const [debugData, setDebugData] = useState<DebugResponse | null>(null);
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(false);
  const [logsLoading, setLogsLoading] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);

  const fetchDebug = async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/analysis/debug");
      const data = await res.json();
      setDebugData(data);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  };

  const fetchLogs = async () => {
    setLogsLoading(true);
    try {
      const res = await fetch("/api/analysis/debug/logs?limit=100");
      const data = await res.json();
      setLogs(data.logs || []);
    } catch {
      /* ignore */
    } finally {
      setLogsLoading(false);
    }
  };

  useEffect(() => {
    fetchDebug();
    fetchLogs();
  }, []);

  const indicators = debugData?.indicators
    ? Object.values(debugData.indicators)
    : [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100">
            شجره‌نامه شاخص‌ها (Provenance)
          </h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            محاسبه کانونیکال ۶ شاخص با جزئیات کامل — مقدار خام، تبدیل، صدک، امتیاز، z-score، منبع
          </p>
        </div>
        <button
          onClick={() => { fetchDebug(); fetchLogs(); }}
          disabled={loading}
          className="rounded-lg bg-gold-600 px-4 py-2 text-sm font-medium text-white hover:bg-gold-700 disabled:opacity-50"
        >
          {loading ? "در حال محاسبه..." : "محاسبه مجدد"}
        </button>
      </div>

      {/* Debug run info */}
      {debugData?.run_id && (
        <div className="rounded-lg border border-gray-200 bg-gray-50 px-4 py-2 text-xs text-gray-500 dark:border-gray-700 dark:bg-gray-800/50 dark:text-gray-400">
          Run ID: <span className="font-mono">{debugData.run_id}</span>
          {" | "}
          محاسبه: {new Date(debugData.computed_at).toLocaleString("fa-IR")}
          {" | "}
          {debugData.count} شاخص
        </div>
      )}

      {/* Indicator cards */}
      {loading ? (
        <div className="text-center text-gray-500 py-10">در حال محاسبه...</div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {indicators.map((ind) => (
            <div
              key={ind.indicator_id}
              className={cn(
                "rounded-xl border p-4 cursor-pointer transition-all",
                expanded === ind.indicator_id
                  ? "border-gold-500/50 bg-gold-50/30 dark:bg-gold-900/10"
                  : "border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600",
              )}
              onClick={() => setExpanded(expanded === ind.indicator_id ? null : ind.indicator_id)}
            >
              {/* Header */}
              <div className="flex items-center justify-between mb-2">
                <div>
                  <h3 className="text-sm font-bold text-gray-900 dark:text-gray-100">
                    {ind.label_fa || ind.indicator_id}
                  </h3>
                  <span className="text-[10px] text-gray-400">{ind.indicator_id}</span>
                </div>
                <div className="text-left">
                  <span className={cn("text-2xl font-bold tabular-nums", getScoreColor(ind.score))}>
                    {ind.score}
                  </span>
                  <span className="block text-[10px] text-gray-400">/100</span>
                </div>
              </div>

              {/* Score bar */}
              <div className="h-2 rounded-full bg-gray-200 dark:bg-gray-700 mb-2">
                <div
                  className={cn("h-full rounded-full transition-all duration-500", getScoreBg(ind.score))}
                  style={{ width: `${ind.score}%` }}
                />
              </div>

              {/* Quick stats */}
              <div className="flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-gray-500 dark:text-gray-400">
                <span>صدک: {(ind.percentile * 100).toFixed(0)}%</span>
                {ind.zscore != null && <span>z: {ind.zscore.toFixed(2)}</span>}
                <span>پنجره: {ind.window_size}</span>
                <span>منبع: {ind.source_name}</span>
                {ind.stale && <span className="text-amber-500 font-bold">قدیمی</span>}
                {ind.crowded && <span className="text-orange-500 font-bold">اشباع</span>}
                {ind.fallback_used && <span className="text-red-500 font-bold">پیش‌فرض</span>}
              </div>

              {/* Expanded details */}
              {expanded === ind.indicator_id && (
                <div className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700 space-y-2">
                  <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
                    <span className="text-gray-500">مقدار خام:</span>
                    <span className="font-mono font-bold">{ind.raw_value?.toFixed(4)}</span>

                    <span className="text-gray-500">تبدیل:</span>
                    <span className="text-gray-700 dark:text-gray-300">{ind.raw_transform}</span>

                    <span className="text-gray-500">واحد:</span>
                    <span>{ind.raw_units}</span>

                    <span className="text-gray-500">مقدار صاف‌شده:</span>
                    <span className="font-mono">{ind.smoothed_value?.toFixed(4)}</span>

                    <span className="text-gray-500">جهت:</span>
                    <span>{ind.direction === "inverse" ? "معکوس ← بالاتر = نزولی" : "مستقیم ← بالاتر = صعودی"}</span>

                    <span className="text-gray-500">روش:</span>
                    <span>{ind.scoring_method}</span>

                    <span className="text-gray-500">صاف‌سازی:</span>
                    <span>{ind.smoothing_applied ? "EMA اعمال شده" : "بدون صاف‌سازی"}</span>

                    {ind.winsorize_bounds && (
                      <>
                        <span className="text-gray-500">محدوده Winsorize:</span>
                        <span className="font-mono">[{ind.winsorize_bounds[0]?.toFixed(3)}, {ind.winsorize_bounds[1]?.toFixed(3)}]</span>
                      </>
                    )}

                    <span className="text-gray-500">آخرین بروزرسانی:</span>
                    <span>{ind.last_updated_at || "—"}</span>

                    {ind.source_url && (
                      <>
                        <span className="text-gray-500">لینک منبع:</span>
                        <a href={ind.source_url} target="_blank" rel="noopener noreferrer"
                           className="text-blue-500 hover:underline truncate">{ind.source_url}</a>
                      </>
                    )}
                  </div>

                  {/* Score semantics */}
                  {ind.score_semantics && Object.keys(ind.score_semantics).length > 0 && (
                    <div className="mt-2 rounded bg-blue-50 dark:bg-blue-900/20 p-2">
                      <h4 className="text-[10px] font-bold text-blue-600 dark:text-blue-400 mb-1">
                        معنای امتیاز در هر زمینه:
                      </h4>
                      {Object.entries(ind.score_semantics).map(([ctx, meaning]) => (
                        <p key={ctx} className="text-[10px] text-blue-600 dark:text-blue-400">
                          <span className="font-bold">{ctx}:</span> {meaning}
                        </p>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Audit logs */}
      <div>
        <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-3">
          لاگ‌های محاسبه اخیر
        </h2>
        {logsLoading ? (
          <div className="text-center text-gray-500 py-6">در حال بارگذاری...</div>
        ) : logs.length === 0 ? (
          <div className="text-center text-gray-500 py-6">هنوز لاگی ثبت نشده. دکمه &quot;محاسبه مجدد&quot; را بزنید.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-gray-200 dark:border-gray-700 text-gray-500">
                  <th className="py-2 px-2 text-right">شاخص</th>
                  <th className="py-2 px-2 text-right">امتیاز</th>
                  <th className="py-2 px-2 text-right">صدک</th>
                  <th className="py-2 px-2 text-right">z-score</th>
                  <th className="py-2 px-2 text-right">قدیمی</th>
                  <th className="py-2 px-2 text-right">زمینه</th>
                  <th className="py-2 px-2 text-right">زمان</th>
                </tr>
              </thead>
              <tbody>
                {logs.slice(0, 50).map((log) => (
                  <tr key={log.id} className="border-b border-gray-100 dark:border-gray-800">
                    <td className="py-1.5 px-2 font-medium">{log.indicator_id}</td>
                    <td className={cn("py-1.5 px-2 font-bold tabular-nums", getScoreColor(log.score))}>
                      {log.score}
                    </td>
                    <td className="py-1.5 px-2 tabular-nums">{(log.percentile * 100).toFixed(0)}%</td>
                    <td className="py-1.5 px-2 tabular-nums font-mono">
                      {log.zscore != null ? log.zscore.toFixed(2) : "—"}
                    </td>
                    <td className="py-1.5 px-2">
                      {log.stale && <span className="text-amber-500">بله</span>}
                      {log.fallback_used && <span className="text-red-500 mr-1">پیش‌فرض</span>}
                    </td>
                    <td className="py-1.5 px-2 text-gray-400">{log.context}</td>
                    <td className="py-1.5 px-2 text-gray-400 tabular-nums" dir="ltr">
                      {log.computed_at ? new Date(log.computed_at).toLocaleTimeString("fa-IR") : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
