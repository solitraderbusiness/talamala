"use client";

import { useEffect, useState, useCallback } from "react";
import { getToken } from "@/lib/auth";
import InfoTip from "@/components/InfoTip";

const API_BASE = "/api/admin/data-reliability";

// ── Types ────────────────────────────────────────────────────────────

interface QASummary {
  pass: number;
  warning: number;
  fail: number;
  no_data: number;
}

interface Overview {
  total_metrics: number;
  qa_summary: QASummary;
  runs_24h: { total: number; success_rate_pct: number; avg_duration_ms: number };
  unresolved_alerts: number;
}

interface MetricLatestRun {
  run_id: string | null;
  status: string | null;
  qa_result: string | null;
  final_value: any;
  started_at: string | null;
  duration_ms: number | null;
  data_timestamp: string | null;
}

interface MetricItem {
  metric_id: string;
  display_name: string;
  unit: string | null;
  update_frequency_minutes: number | null;
  formula_version: string;
  latest_run: MetricLatestRun | null;
}

interface RunItem {
  run_id: string;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  status: string;
  qa_result: string | null;
  final_value: any;
  data_timestamp: string | null;
  formula_version: string | null;
  error_message: string | null;
}

interface RunDetail {
  run: RunItem & { metric_id: string; qa_reasons: any; fallback_used: boolean };
  raw_ingests: any[];
  transform_steps: any[];
  validations: any[];
}

interface AlertItem {
  id: string;
  metric_id: string;
  alert_type: string;
  severity: string;
  message: string | null;
  created_at: string | null;
  resolved_at: string | null;
}

// ── Helpers ──────────────────────────────────────────────────────────

async function apiFetch<T>(path: string, token: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function timeAgo(iso: string | null): string {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "همین الان";
  if (mins < 60) return `${mins} دقیقه پیش`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} ساعت پیش`;
  return `${Math.floor(hours / 24)} روز پیش`;
}

function QABadge({ qa }: { qa: string | null }) {
  if (!qa) return <span className="text-xs text-gray-400">—</span>;
  const styles: Record<string, string> = {
    pass: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400",
    warning: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400",
    fail: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
  };
  const labels: Record<string, string> = { pass: "سالم", warning: "هشدار", fail: "خطا" };
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${styles[qa] || "bg-gray-100 text-gray-600"}`}>
      {labels[qa] || qa}
    </span>
  );
}

function formatValue(value: any, unit: string | null): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") {
    const formatted = Math.abs(value) < 10 ? value.toFixed(4) : value.toLocaleString();
    return unit ? `${formatted} ${unit}` : formatted;
  }
  if (typeof value === "object") return JSON.stringify(value).slice(0, 60);
  return String(value);
}

// ── Main Page ────────────────────────────────────────────────────────

export default function DataReliabilityPage() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [metrics, setMetrics] = useState<MetricItem[]>([]);
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedMetric, setSelectedMetric] = useState<string | null>(null);
  const [runs, setRuns] = useState<RunItem[]>([]);
  const [runDetail, setRunDetail] = useState<RunDetail | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>("all");

  const fetchData = useCallback(async () => {
    const token = getToken();
    if (!token) return;
    setLoading(true);
    try {
      const [ov, mt, al] = await Promise.allSettled([
        apiFetch<Overview>("/overview", token),
        apiFetch<{ metrics: MetricItem[] }>("/metrics", token),
        apiFetch<{ alerts: AlertItem[] }>("/alerts?limit=50&unresolved_only=false", token),
      ]);
      if (ov.status === "fulfilled") setOverview(ov.value);
      if (mt.status === "fulfilled") setMetrics(mt.value.metrics);
      if (al.status === "fulfilled") setAlerts(al.value.alerts);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 60000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const loadRuns = async (metricId: string) => {
    const token = getToken();
    if (!token) return;
    setSelectedMetric(metricId);
    setRunDetail(null);
    try {
      const data = await apiFetch<{ runs: RunItem[] }>(`/metrics/${metricId}/runs?limit=30`, token);
      setRuns(data.runs);
    } catch {
      setRuns([]);
    }
  };

  const loadRunDetail = async (metricId: string, runId: string) => {
    const token = getToken();
    if (!token) return;
    try {
      const data = await apiFetch<RunDetail>(`/metrics/${metricId}/runs/${runId}`, token);
      setRunDetail(data);
    } catch {
      setRunDetail(null);
    }
  };

  const resolveAlert = async (alertId: string) => {
    const token = getToken();
    if (!token) return;
    try {
      await fetch(`${API_BASE}/alerts/${alertId}/resolve`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      fetchData();
    } catch {}
  };

  const filteredMetrics = statusFilter === "all"
    ? metrics
    : metrics.filter((m) => {
        const qa = m.latest_run?.qa_result;
        if (statusFilter === "no_data") return !m.latest_run;
        return qa === statusFilter;
      });

  if (loading && !overview) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <div className="h-10 w-10 animate-spin rounded-full border-4 border-gold-500 border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">
        اعتبار داده‌ها
        <InfoTip term="qa_status" />
      </h2>

      {/* ── Section 1: Overview Dashboard ────────────────────────── */}
      {overview && (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <StatCard label="کل متریک‌ها" value={overview.total_metrics} color="gray" />
          <StatCard label="سالم" value={overview.qa_summary.pass} color="green" />
          <StatCard label="هشدار" value={overview.qa_summary.warning} color="yellow" />
          <StatCard label="خطا" value={overview.qa_summary.fail} color="red" />
          <StatCard label="بدون داده" value={overview.qa_summary.no_data} color="gray" />
          <StatCard label="اجراهای ۲۴ ساعته" value={overview.runs_24h.total} color="gray" />
          <StatCard label={<>نرخ موفقیت <InfoTip term="success_rate" /></>} value={`${overview.runs_24h.success_rate_pct}%`} color="green" />
          <StatCard
            label="هشدارهای فعال"
            value={overview.unresolved_alerts}
            color={overview.unresolved_alerts > 0 ? "red" : "green"}
          />
        </div>
      )}

      {/* ── Section 2: Metric Explorer ───────────────────────────── */}
      <div className="card p-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            متریک‌ها
          </h3>
          <div className="flex gap-1">
            {[
              { key: "all", label: "همه" },
              { key: "pass", label: "سالم" },
              { key: "warning", label: "هشدار" },
              { key: "fail", label: "خطا" },
              { key: "no_data", label: "بدون داده" },
            ].map((f) => (
              <button
                key={f.key}
                onClick={() => setStatusFilter(f.key)}
                className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                  statusFilter === f.key
                    ? "bg-gold-500 text-white"
                    : "bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400"
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-right text-sm">
            <thead>
              <tr className="border-b border-gray-200 text-xs text-gray-500 dark:border-gray-700 dark:text-gray-400">
                <th className="pb-2 pe-4 font-medium">متریک</th>
                <th className="pb-2 pe-4 font-medium">آخرین مقدار</th>
                <th className="pb-2 pe-4 font-medium">وضعیت QA</th>
                <th className="pb-2 pe-4 font-medium">آخرین به‌روزرسانی</th>
                <th className="pb-2 font-medium">مدت (ms)</th>
              </tr>
            </thead>
            <tbody>
              {filteredMetrics.map((m) => (
                <tr
                  key={m.metric_id}
                  onClick={() => loadRuns(m.metric_id)}
                  className={`cursor-pointer border-b border-gray-100 transition-colors hover:bg-gold-50/50 dark:border-gray-800 dark:hover:bg-gray-800/50 ${
                    selectedMetric === m.metric_id ? "bg-gold-50 dark:bg-gray-800" : ""
                  }`}
                >
                  <td className="py-2.5 pe-4">
                    <div className="font-medium text-gray-900 dark:text-gray-100">
                      {m.display_name}
                    </div>
                    <div className="text-xs text-gray-400">{m.metric_id}</div>
                  </td>
                  <td className="py-2.5 pe-4 font-mono text-xs">
                    {formatValue(m.latest_run?.final_value, m.unit)}
                  </td>
                  <td className="py-2.5 pe-4">
                    <QABadge qa={m.latest_run?.qa_result || null} />
                  </td>
                  <td className="py-2.5 pe-4 text-xs text-gray-500">
                    {timeAgo(m.latest_run?.started_at || null)}
                  </td>
                  <td className="py-2.5 text-xs text-gray-400">
                    {m.latest_run?.duration_ms ?? "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* ── Section 3: Run Detail View ───────────────────────────── */}
      {selectedMetric && (
        <div className="card p-5">
          <h3 className="mb-4 text-lg font-semibold text-gray-900 dark:text-gray-100">
            تاریخچه اجرا: {metrics.find((m) => m.metric_id === selectedMetric)?.display_name}
          </h3>

          {runs.length === 0 ? (
            <p className="text-sm text-gray-400">هنوز اجرایی ثبت نشده است.</p>
          ) : (
            <div className="space-y-2">
              <div className="overflow-x-auto">
                <table className="w-full text-right text-sm">
                  <thead>
                    <tr className="border-b border-gray-200 text-xs text-gray-500 dark:border-gray-700">
                      <th className="pb-2 pe-3 font-medium">شناسه</th>
                      <th className="pb-2 pe-3 font-medium">زمان شروع</th>
                      <th className="pb-2 pe-3 font-medium">مدت</th>
                      <th className="pb-2 pe-3 font-medium">وضعیت</th>
                      <th className="pb-2 pe-3 font-medium">QA</th>
                      <th className="pb-2 font-medium">مقدار</th>
                    </tr>
                  </thead>
                  <tbody>
                    {runs.map((r) => (
                      <tr
                        key={r.run_id}
                        onClick={() => loadRunDetail(selectedMetric, r.run_id)}
                        className={`cursor-pointer border-b border-gray-100 transition-colors hover:bg-gray-50 dark:border-gray-800 dark:hover:bg-gray-800/50 ${
                          runDetail?.run?.run_id === r.run_id ? "bg-blue-50 dark:bg-blue-900/20" : ""
                        }`}
                      >
                        <td className="py-2 pe-3 font-mono text-xs text-gray-400">
                          {r.run_id.slice(0, 8)}
                        </td>
                        <td className="py-2 pe-3 text-xs">{timeAgo(r.started_at)}</td>
                        <td className="py-2 pe-3 text-xs">{r.duration_ms ?? "—"} ms</td>
                        <td className="py-2 pe-3 text-xs">
                          <span className={r.status === "success" ? "text-green-600" : r.status === "failed" ? "text-red-600" : "text-gray-500"}>
                            {r.status}
                          </span>
                        </td>
                        <td className="py-2 pe-3"><QABadge qa={r.qa_result} /></td>
                        <td className="py-2 font-mono text-xs">{formatValue(r.final_value, null)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Run drill-down */}
          {runDetail && (
            <div className="mt-6 space-y-4 border-t border-gray-200 pt-4 dark:border-gray-700">
              <h4 className="font-semibold text-gray-900 dark:text-gray-100">
                جزئیات اجرا: {runDetail.run.run_id.slice(0, 8)}...
              </h4>

              {/* Raw Ingests */}
              {runDetail.raw_ingests.length > 0 && (
                <div>
                  <h5 className="mb-2 text-sm font-medium text-gray-700 dark:text-gray-300">
                    دریافت داده خام
                  </h5>
                  <div className="space-y-2">
                    {runDetail.raw_ingests.map((ing, i) => (
                      <div key={i} className="rounded-lg bg-gray-50 p-3 text-xs dark:bg-gray-800">
                        <div className="flex flex-wrap gap-4">
                          <span><strong>منبع:</strong> {ing.source_id}</span>
                          <span><strong>وضعیت:</strong> {ing.response_status}</span>
                          <span><strong>تاخیر:</strong> {ing.latency_ms} ms</span>
                          <span><strong>زمان:</strong> {timeAgo(ing.retrieved_at)}</span>
                        </div>
                        {ing.request_url && (
                          <div className="mt-1 text-gray-400 break-all">{ing.request_url}</div>
                        )}
                        {ing.payload_sample && (
                          <details className="mt-2">
                            <summary className="cursor-pointer text-gold-600">نمونه پاسخ</summary>
                            <pre className="mt-1 max-h-40 overflow-auto rounded bg-gray-900 p-2 text-green-400 ltr">
                              {JSON.stringify(ing.payload_sample, null, 2)}
                            </pre>
                          </details>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Transform Steps */}
              {runDetail.transform_steps.length > 0 && (
                <div>
                  <h5 className="mb-2 text-sm font-medium text-gray-700 dark:text-gray-300">
                    مراحل محاسبه
                  </h5>
                  <div className="space-y-1">
                    {runDetail.transform_steps.map((step, i) => (
                      <div key={i} className="flex items-start gap-3 rounded-lg bg-gray-50 p-3 text-xs dark:bg-gray-800">
                        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-gold-500 text-white font-bold">
                          {step.step_order}
                        </span>
                        <div>
                          <div className="font-medium">{step.step_name}</div>
                          {step.output_value !== null && (
                            <div className="mt-1 font-mono text-gray-500 ltr">
                              {typeof step.output_value === "object"
                                ? JSON.stringify(step.output_value)
                                : String(step.output_value)}
                            </div>
                          )}
                          {step.normalization_method && (
                            <div className="mt-1 text-gold-600">
                              نرمال‌سازی: {step.normalization_method}
                              {step.normalization_params && (
                                <span className="ltr"> {JSON.stringify(step.normalization_params)}</span>
                              )}
                            </div>
                          )}
                          {step.notes && <div className="mt-1 text-gray-400">{step.notes}</div>}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Validation Results */}
              {runDetail.validations.length > 0 && (
                <div>
                  <h5 className="mb-2 text-sm font-medium text-gray-700 dark:text-gray-300">
                    نتایج اعتبارسنجی
                  </h5>
                  <div className="space-y-1">
                    {runDetail.validations.map((v, i) => (
                      <div key={i} className="flex items-center gap-3 rounded-lg bg-gray-50 p-3 text-xs dark:bg-gray-800">
                        <QABadge qa={v.result} />
                        <span className="font-medium">{v.check_name}</span>
                        <span className="text-gray-500">{v.reason}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Final Output */}
              <div>
                <h5 className="mb-2 text-sm font-medium text-gray-700 dark:text-gray-300">
                  خروجی نهایی
                </h5>
                <pre className="max-h-40 overflow-auto rounded-lg bg-gray-900 p-3 text-xs text-green-400 ltr">
                  {JSON.stringify(runDetail.run.final_value, null, 2)}
                </pre>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Section 4: Alerts Monitor ────────────────────────────── */}
      <div className="card p-5">
        <h3 className="mb-4 text-lg font-semibold text-gray-900 dark:text-gray-100">
          هشدارها
        </h3>
        {alerts.length === 0 ? (
          <p className="text-sm text-gray-400">هشداری ثبت نشده است.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-right text-sm">
              <thead>
                <tr className="border-b border-gray-200 text-xs text-gray-500 dark:border-gray-700">
                  <th className="pb-2 pe-3 font-medium">متریک</th>
                  <th className="pb-2 pe-3 font-medium">نوع</th>
                  <th className="pb-2 pe-3 font-medium">شدت</th>
                  <th className="pb-2 pe-3 font-medium">پیام</th>
                  <th className="pb-2 pe-3 font-medium">زمان</th>
                  <th className="pb-2 font-medium">وضعیت</th>
                </tr>
              </thead>
              <tbody>
                {alerts.map((a) => (
                  <tr key={a.id} className="border-b border-gray-100 dark:border-gray-800">
                    <td className="py-2 pe-3 text-xs font-medium">{a.metric_id}</td>
                    <td className="py-2 pe-3 text-xs">{a.alert_type}</td>
                    <td className="py-2 pe-3">
                      <span className={`text-xs font-medium ${a.severity === "critical" ? "text-red-600" : "text-yellow-600"}`}>
                        {a.severity === "critical" ? "بحرانی" : "هشدار"}
                      </span>
                    </td>
                    <td className="py-2 pe-3 text-xs text-gray-500 max-w-xs truncate">{a.message}</td>
                    <td className="py-2 pe-3 text-xs text-gray-400">{timeAgo(a.created_at)}</td>
                    <td className="py-2">
                      {a.resolved_at ? (
                        <span className="text-xs text-green-600">حل شده</span>
                      ) : (
                        <button
                          onClick={() => resolveAlert(a.id)}
                          className="rounded bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700 hover:bg-green-200 dark:bg-green-900/30 dark:text-green-400"
                        >
                          حل کردن
                        </button>
                      )}
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

// ── Stat Card Component ──────────────────────────────────────────────

function StatCard({
  label,
  value,
  color,
}: {
  label: React.ReactNode;
  value: number | string;
  color: "green" | "yellow" | "red" | "gray";
}) {
  const borderColors: Record<string, string> = {
    green: "border-green-200 dark:border-green-800",
    yellow: "border-yellow-200 dark:border-yellow-800",
    red: "border-red-200 dark:border-red-800",
    gray: "border-gray-200 dark:border-gray-700",
  };
  const textColors: Record<string, string> = {
    green: "text-green-700 dark:text-green-400",
    yellow: "text-yellow-700 dark:text-yellow-400",
    red: "text-red-700 dark:text-red-400",
    gray: "text-gray-700 dark:text-gray-300",
  };

  return (
    <div className={`rounded-xl border p-4 ${borderColors[color]}`}>
      <div className={`text-2xl font-bold ${textColors[color]}`}>{value}</div>
      <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">{label}</div>
    </div>
  );
}
