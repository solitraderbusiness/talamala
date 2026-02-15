"use client";

import { useCallback, useEffect, useState } from "react";
import { getToken } from "@/lib/auth";
import { cn } from "@/lib/utils";

/* ── Types ─────────────────────────────────────────────────────────── */

interface AuditEntry {
  id: string;
  trace_id: string;
  parent_trace_id: string | null;
  event_type: string;
  actor: string;
  entity_type: string | null;
  entity_id: string | null;
  action: string;
  details: Record<string, unknown> | null;
  duration_ms: number | null;
  status: string;
  error_message: string | null;
  code_version: string | null;
  created_at: string;
}

interface AuditOverview {
  total_24h: number;
  total_7d: number;
  failure_rate_24h: number;
  failures_24h: number;
  by_event_type: { event_type: string; count: number; failures: number }[];
  top_actors: { actor: string; count: number }[];
}

/* ── Helpers ───────────────────────────────────────────────────────── */

const EVENT_TYPE_LABELS: Record<string, string> = {
  job_run: "اجرای جاب",
  data_ingest: "دریافت داده",
  metric_compute: "محاسبه متریک",
  alert_generate: "تولید هشدار",
  admin_action: "عملیات ادمین",
  api_call: "فراخوانی API",
};

const STATUS_COLORS: Record<string, string> = {
  success: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
  failure: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  warning: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
};

function timeAgo(ts: string): string {
  const diff = (Date.now() - new Date(ts).getTime()) / 60000;
  if (diff < 1) return "همین الان";
  if (diff < 60) return `${Math.floor(diff)} دقیقه پیش`;
  if (diff < 1440) return `${Math.floor(diff / 60)} ساعت پیش`;
  return `${Math.floor(diff / 1440)} روز پیش`;
}

/* ── Component ─────────────────────────────────────────────────────── */

export default function AuditLogsPage() {
  const [overview, setOverview] = useState<AuditOverview | null>(null);
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);

  // Filters
  const [filterType, setFilterType] = useState<string>("");
  const [filterStatus, setFilterStatus] = useState<string>("");
  const [filterHours, setFilterHours] = useState<string>("24");
  const [filterAction, setFilterAction] = useState<string>("");
  const [traceId, setTraceId] = useState<string>("");

  // Expanded row
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const perPage = 50;

  const fetchOverview = useCallback(async () => {
    const token = getToken();
    if (!token) return;
    try {
      const res = await fetch("/api/admin/audit-logs/overview", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setOverview(await res.json());
    } catch { /* ignore */ }
  }, []);

  const fetchLogs = useCallback(async () => {
    const token = getToken();
    if (!token) return;

    const params = new URLSearchParams();
    params.set("page", String(page));
    params.set("per_page", String(perPage));
    if (filterType) params.set("event_type", filterType);
    if (filterStatus) params.set("status", filterStatus);
    if (filterHours) params.set("hours", filterHours);
    if (filterAction) params.set("action", filterAction);
    if (traceId) params.set("trace_id", traceId);

    try {
      const res = await fetch(`/api/admin/audit-logs?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setEntries(data.items);
        setTotal(data.total);
      }
    } catch { /* ignore */ }
    setLoading(false);
  }, [page, filterType, filterStatus, filterHours, filterAction, traceId]);

  useEffect(() => {
    fetchOverview();
  }, [fetchOverview]);

  useEffect(() => {
    setLoading(true);
    fetchLogs();
  }, [fetchLogs]);

  const totalPages = Math.ceil(total / perPage);

  if (loading && !overview) {
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
          لاگ حسابرسی
        </h1>
        <p className="text-xs text-gray-500 dark:text-gray-400">
          ردیابی عملیات سیستم — جاب‌ها، محاسبات، هشدارها و اقدامات ادمین
        </p>
      </div>

      {/* Overview Cards */}
      {overview && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="card">
            <div className="text-xs font-bold text-gray-500 dark:text-gray-400">
              رویداد ۲۴ ساعته
            </div>
            <div className="mt-1 text-2xl font-bold text-gray-900 dark:text-gray-100">
              {overview.total_24h.toLocaleString("fa-IR")}
            </div>
          </div>
          <div className="card">
            <div className="text-xs font-bold text-gray-500 dark:text-gray-400">
              رویداد ۷ روزه
            </div>
            <div className="mt-1 text-2xl font-bold text-gray-900 dark:text-gray-100">
              {overview.total_7d.toLocaleString("fa-IR")}
            </div>
          </div>
          <div className="card">
            <div className="text-xs font-bold text-gray-500 dark:text-gray-400">
              خطاهای ۲۴ ساعته
            </div>
            <div className="mt-1 flex items-baseline gap-2">
              <span className={cn(
                "text-2xl font-bold",
                overview.failures_24h > 0 ? "text-red-600" : "text-emerald-600"
              )}>
                {overview.failures_24h}
              </span>
              <span className="text-xs text-gray-400">
                ({overview.failure_rate_24h}%)
              </span>
            </div>
          </div>
          <div className="card">
            <div className="text-xs font-bold text-gray-500 dark:text-gray-400">
              انواع رویداد
            </div>
            <div className="mt-2 flex flex-wrap gap-1">
              {overview.by_event_type.map((t) => (
                <button
                  key={t.event_type}
                  onClick={() => {
                    setFilterType(t.event_type);
                    setPage(1);
                  }}
                  className="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-medium text-gray-600 hover:bg-gold-100 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gold-900/30"
                >
                  {EVENT_TYPE_LABELS[t.event_type] || t.event_type} ({t.count})
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap gap-2">
        <select
          value={filterType}
          onChange={(e) => { setFilterType(e.target.value); setPage(1); }}
          className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-xs dark:border-gray-700 dark:bg-gray-900"
        >
          <option value="">همه انواع</option>
          <option value="job_run">اجرای جاب</option>
          <option value="data_ingest">دریافت داده</option>
          <option value="metric_compute">محاسبه متریک</option>
          <option value="alert_generate">تولید هشدار</option>
          <option value="admin_action">عملیات ادمین</option>
          <option value="api_call">فراخوانی API</option>
        </select>

        <select
          value={filterStatus}
          onChange={(e) => { setFilterStatus(e.target.value); setPage(1); }}
          className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-xs dark:border-gray-700 dark:bg-gray-900"
        >
          <option value="">همه وضعیت‌ها</option>
          <option value="success">موفق</option>
          <option value="failure">خطا</option>
        </select>

        <select
          value={filterHours}
          onChange={(e) => { setFilterHours(e.target.value); setPage(1); }}
          className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-xs dark:border-gray-700 dark:bg-gray-900"
        >
          <option value="1">۱ ساعت</option>
          <option value="6">۶ ساعت</option>
          <option value="24">۲۴ ساعت</option>
          <option value="72">۳ روز</option>
          <option value="168">۷ روز</option>
          <option value="">همه</option>
        </select>

        <input
          type="text"
          placeholder="جستجوی عملیات..."
          value={filterAction}
          onChange={(e) => { setFilterAction(e.target.value); setPage(1); }}
          className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-xs dark:border-gray-700 dark:bg-gray-900"
        />

        <input
          type="text"
          placeholder="Trace ID..."
          value={traceId}
          onChange={(e) => { setTraceId(e.target.value); setPage(1); }}
          className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-xs font-mono dark:border-gray-700 dark:bg-gray-900"
        />

        {(filterType || filterStatus || filterAction || traceId) && (
          <button
            onClick={() => {
              setFilterType("");
              setFilterStatus("");
              setFilterAction("");
              setTraceId("");
              setPage(1);
            }}
            className="rounded-lg bg-red-50 px-3 py-1.5 text-xs text-red-600 hover:bg-red-100 dark:bg-red-900/20 dark:text-red-400"
          >
            پاک کردن فیلترها
          </button>
        )}
      </div>

      {/* Results count */}
      <div className="text-xs text-gray-500">
        {total.toLocaleString("fa-IR")} رکورد یافت شد
        {totalPages > 1 && ` — صفحه ${page} از ${totalPages}`}
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-xl border border-gray-200 dark:border-gray-800">
        <table className="w-full text-xs">
          <thead className="bg-gray-50 dark:bg-gray-800/50">
            <tr>
              <th className="px-3 py-2 text-right font-bold text-gray-500 dark:text-gray-400">زمان</th>
              <th className="px-3 py-2 text-right font-bold text-gray-500 dark:text-gray-400">نوع</th>
              <th className="px-3 py-2 text-right font-bold text-gray-500 dark:text-gray-400">عملیات</th>
              <th className="px-3 py-2 text-right font-bold text-gray-500 dark:text-gray-400">موجودیت</th>
              <th className="px-3 py-2 text-right font-bold text-gray-500 dark:text-gray-400">وضعیت</th>
              <th className="px-3 py-2 text-right font-bold text-gray-500 dark:text-gray-400">مدت</th>
              <th className="px-3 py-2 text-right font-bold text-gray-500 dark:text-gray-400">Trace</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
            {entries.map((entry) => (
              <LogRow
                key={entry.id}
                entry={entry}
                expanded={expandedId === entry.id}
                onToggle={() => setExpandedId(expandedId === entry.id ? null : entry.id)}
                onTraceClick={(tid) => { setTraceId(tid); setPage(1); }}
              />
            ))}
            {entries.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-gray-400">
                  {loading ? "در حال بارگذاری..." : "رکوردی یافت نشد"}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2">
          <button
            disabled={page <= 1}
            onClick={() => setPage(page - 1)}
            className="rounded-lg border px-3 py-1 text-xs disabled:opacity-30 dark:border-gray-700"
          >
            قبلی
          </button>
          <span className="text-xs text-gray-500">
            {page} / {totalPages}
          </span>
          <button
            disabled={page >= totalPages}
            onClick={() => setPage(page + 1)}
            className="rounded-lg border px-3 py-1 text-xs disabled:opacity-30 dark:border-gray-700"
          >
            بعدی
          </button>
        </div>
      )}
    </div>
  );
}

/* ── Row component ──────────────────────────────────────────────────── */

function LogRow({
  entry,
  expanded,
  onToggle,
  onTraceClick,
}: {
  entry: AuditEntry;
  expanded: boolean;
  onToggle: () => void;
  onTraceClick: (tid: string) => void;
}) {
  return (
    <>
      <tr
        className="cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/30"
        onClick={onToggle}
      >
        <td className="whitespace-nowrap px-3 py-2 text-gray-500 dark:text-gray-400">
          {timeAgo(entry.created_at)}
        </td>
        <td className="whitespace-nowrap px-3 py-2">
          <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-medium text-gray-600 dark:bg-gray-800 dark:text-gray-400">
            {EVENT_TYPE_LABELS[entry.event_type] || entry.event_type}
          </span>
        </td>
        <td className="px-3 py-2 font-mono text-gray-900 dark:text-gray-100">
          {entry.action}
        </td>
        <td className="whitespace-nowrap px-3 py-2 text-gray-500">
          {entry.entity_type && (
            <span>
              {entry.entity_type}
              {entry.entity_id && (
                <span className="text-gray-400">:{entry.entity_id.slice(0, 12)}</span>
              )}
            </span>
          )}
        </td>
        <td className="whitespace-nowrap px-3 py-2">
          <span className={cn(
            "rounded-full px-2 py-0.5 text-[10px] font-medium",
            STATUS_COLORS[entry.status] || "bg-gray-100 text-gray-600"
          )}>
            {entry.status === "success" ? "موفق" : entry.status === "failure" ? "خطا" : entry.status}
          </span>
        </td>
        <td className="whitespace-nowrap px-3 py-2 text-gray-500">
          {entry.duration_ms != null ? `${entry.duration_ms}ms` : "—"}
        </td>
        <td className="whitespace-nowrap px-3 py-2">
          <button
            onClick={(e) => {
              e.stopPropagation();
              onTraceClick(entry.trace_id);
            }}
            className="font-mono text-[10px] text-blue-600 hover:underline dark:text-blue-400"
          >
            {entry.trace_id.slice(0, 8)}
          </button>
        </td>
      </tr>
      {expanded && (
        <tr className="bg-gray-50 dark:bg-gray-800/30">
          <td colSpan={7} className="px-4 py-3">
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <div className="text-[10px] font-bold text-gray-400">Trace ID</div>
                <div className="mt-0.5 font-mono text-xs text-gray-700 dark:text-gray-300">
                  {entry.trace_id}
                </div>
              </div>
              <div>
                <div className="text-[10px] font-bold text-gray-400">Actor</div>
                <div className="mt-0.5 text-xs text-gray-700 dark:text-gray-300">
                  {entry.actor}
                </div>
              </div>
              {entry.error_message && (
                <div className="sm:col-span-2">
                  <div className="text-[10px] font-bold text-red-500">خطا</div>
                  <pre className="mt-0.5 max-h-32 overflow-auto whitespace-pre-wrap rounded bg-red-50 p-2 text-[10px] text-red-700 dark:bg-red-900/20 dark:text-red-300">
                    {entry.error_message}
                  </pre>
                </div>
              )}
              {entry.details && Object.keys(entry.details).length > 0 && (
                <div className="sm:col-span-2">
                  <div className="text-[10px] font-bold text-gray-400">جزئیات</div>
                  <pre className="mt-0.5 max-h-48 overflow-auto whitespace-pre-wrap rounded bg-gray-100 p-2 text-[10px] text-gray-700 dark:bg-gray-800 dark:text-gray-300">
                    {JSON.stringify(entry.details, null, 2)}
                  </pre>
                </div>
              )}
              <div>
                <div className="text-[10px] font-bold text-gray-400">زمان دقیق</div>
                <div className="mt-0.5 text-xs text-gray-700 dark:text-gray-300">
                  {new Date(entry.created_at).toLocaleString("fa-IR")}
                </div>
              </div>
              {entry.code_version && (
                <div>
                  <div className="text-[10px] font-bold text-gray-400">نسخه کد</div>
                  <div className="mt-0.5 font-mono text-xs text-gray-700 dark:text-gray-300">
                    {entry.code_version}
                  </div>
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
