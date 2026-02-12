"use client";

import { useEffect, useState, useCallback } from "react";
import { getToken } from "@/lib/auth";
import {
  getDataHealthOverview,
  getSnapshotStats,
  getOutcomePipeline,
  getSentimentTimeline,
  getPriceStatus,
  getSentimentCorrelation,
  DataHealthOverview,
  SnapshotStats,
  OutcomePipeline,
  SentimentTimelineResponse,
  PriceStatusResponse,
  SentimentCorrelationResponse,
} from "@/lib/api";

function StatusDot({ status }: { status: "green" | "yellow" | "red" | "gray" }) {
  const colors = {
    green: "bg-green-500",
    yellow: "bg-yellow-500",
    red: "bg-red-500",
    gray: "bg-gray-400",
  };
  return (
    <span
      className={`inline-block h-3 w-3 rounded-full ${colors[status]}`}
    />
  );
}

function Card({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="card p-5">
      <h3 className="mb-4 text-lg font-semibold text-gray-900 dark:text-gray-100">
        {title}
      </h3>
      {children}
    </div>
  );
}

export default function DataHealthPage() {
  const [overview, setOverview] = useState<DataHealthOverview | null>(null);
  const [snapStats, setSnapStats] = useState<SnapshotStats | null>(null);
  const [pipeline, setPipeline] = useState<OutcomePipeline | null>(null);
  const [timeline, setTimeline] = useState<SentimentTimelineResponse | null>(null);
  const [priceStatus, setPriceStatus] = useState<PriceStatusResponse | null>(null);
  const [correlation, setCorrelation] = useState<SentimentCorrelationResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [snapPeriod, setSnapPeriod] = useState("today");

  const fetchAll = useCallback(async () => {
    const token = getToken();
    if (!token) return;

    setLoading(true);
    try {
      const [ov, ss, pl, tl, ps, cr] = await Promise.allSettled([
        getDataHealthOverview(token),
        getSnapshotStats(token, snapPeriod),
        getOutcomePipeline(token),
        getSentimentTimeline(token, 168),
        getPriceStatus(token),
        getSentimentCorrelation(token, 7),
      ]);

      if (ov.status === "fulfilled") setOverview(ov.value);
      if (ss.status === "fulfilled") setSnapStats(ss.value);
      if (pl.status === "fulfilled") setPipeline(pl.value);
      if (tl.status === "fulfilled") setTimeline(tl.value);
      if (ps.status === "fulfilled") setPriceStatus(ps.value);
      if (cr.status === "fulfilled") setCorrelation(cr.value);
    } finally {
      setLoading(false);
    }
  }, [snapPeriod]);

  useEffect(() => {
    fetchAll();
    const interval = setInterval(fetchAll, 60000);
    return () => clearInterval(interval);
  }, [fetchAll]);

  // Refetch snapshot stats when period changes
  useEffect(() => {
    const token = getToken();
    if (!token) return;
    getSnapshotStats(token, snapPeriod)
      .then(setSnapStats)
      .catch(() => {});
  }, [snapPeriod]);

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
        سلامت داده
      </h2>

      {/* ── Section 1: Health Status Cards ── */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <HealthCard
          label="پوشش اسنپ‌شات"
          value={overview?.snapshot_coverage_pct != null ? `${overview.snapshot_coverage_pct}%` : "—"}
          status={getHealthStatus(overview?.snapshot_coverage_pct, 80, 50)}
          detail={`${overview?.snapshots_24h ?? 0} از ${overview?.alerts_24h ?? 0} هشدار`}
        />
        <HealthCard
          label="ردیاب نتایج"
          value={`${overview?.outcome_pipeline?.complete ?? 0} تکمیل`}
          status={overview?.outcome_errors === 0 ? "green" : overview?.outcome_errors && overview.outcome_errors > 5 ? "red" : "yellow"}
          detail={`${overview?.outcome_errors ?? 0} خطا`}
        />
        <HealthCard
          label="جدول زمانی سنتیمنت"
          value={overview?.sentiment_last_recorded ? formatTimeAgo(overview.sentiment_last_recorded) : "—"}
          status={getTimeStatus(overview?.sentiment_last_recorded, 10, 30)}
          detail="هر ۵ دقیقه"
        />
        <HealthCard
          label="داده قیمت"
          value={overview?.price_data_last_update ? formatTimeAgo(overview.price_data_last_update) : "—"}
          status={getTimeStatus(overview?.price_data_last_update, 10, 60)}
          detail="۵ دقیقه‌ای + روزانه"
        />
        <HealthCard
          label="اسنپ‌شات کامل"
          value={`${overview?.complete_snapshots_24h ?? 0}`}
          status={overview?.complete_snapshots_24h && overview.complete_snapshots_24h > 0 ? "green" : "yellow"}
          detail="۲۴ ساعت اخیر"
        />
      </div>

      {/* ── Section 2: Snapshot Completeness ── */}
      <Card title="کامل بودن اسنپ‌شات">
        <div className="mb-3 flex gap-2">
          {(["today", "week", "month"] as const).map((p) => (
            <button
              key={p}
              onClick={() => setSnapPeriod(p)}
              className={`rounded-lg px-3 py-1 text-sm ${
                snapPeriod === p
                  ? "bg-gold-500 text-white"
                  : "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400"
              }`}
            >
              {p === "today" ? "امروز" : p === "week" ? "هفته" : "ماه"}
            </button>
          ))}
        </div>
        {snapStats && (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <StatBox label="هشدارها" value={snapStats.alerts_count} />
              <StatBox label="اسنپ‌شات‌ها" value={snapStats.snapshots_count} />
              <StatBox label="کامل" value={snapStats.complete_count} />
              <StatBox
                label="پوشش"
                value={snapStats.completeness_pct != null ? `${snapStats.completeness_pct}%` : "—"}
              />
            </div>
            {snapStats.top_missing_fields.length > 0 && (
              <div>
                <p className="mb-2 text-sm font-medium text-gray-600 dark:text-gray-400">
                  فیلدهای گمشده
                </p>
                <div className="flex flex-wrap gap-2">
                  {snapStats.top_missing_fields.map((f) => (
                    <span
                      key={f.field}
                      className="rounded bg-red-100 px-2 py-1 text-xs text-red-700 dark:bg-red-900/30 dark:text-red-400"
                    >
                      {f.field} ({f.count})
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </Card>

      {/* ── Section 3: Outcome Pipeline ── */}
      <Card title="خط لوله نتایج">
        {pipeline && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-8">
              {Object.entries(pipeline.counts).map(([status, count]) => (
                <div
                  key={status}
                  className="rounded-lg bg-gray-50 p-3 text-center dark:bg-gray-800"
                >
                  <div className="text-lg font-bold text-gray-900 dark:text-gray-100">
                    {count}
                  </div>
                  <div className="text-xs text-gray-500 dark:text-gray-400">
                    {statusLabel(status)}
                  </div>
                </div>
              ))}
            </div>
            <div className="flex items-center gap-4 text-sm text-gray-600 dark:text-gray-400">
              <span>
                مجموع: <strong>{pipeline.total}</strong>
              </span>
              <span>
                تکمیل‌شده: <strong>{pipeline.completed}</strong>
              </span>
              {pipeline.completion_rate != null && (
                <span>
                  نرخ تکمیل: <strong>{pipeline.completion_rate}%</strong>
                </span>
              )}
            </div>
            {pipeline.recent_errors.length > 0 && (
              <div>
                <p className="mb-2 text-sm font-medium text-red-600 dark:text-red-400">
                  خطاهای اخیر
                </p>
                <div className="max-h-40 overflow-y-auto rounded bg-red-50 p-3 text-xs dark:bg-red-900/20">
                  {pipeline.recent_errors.map((e, i) => (
                    <div key={i} className="mb-1">
                      <span className="font-mono text-red-700 dark:text-red-400">
                        {e.alert_id.slice(0, 8)}
                      </span>
                      {" — "}
                      {e.status}
                      {e.updated_at && ` — ${formatTimeAgo(e.updated_at)}`}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </Card>

      {/* ── Section 4: Sentiment vs Price ── */}
      <Card title="سنتیمنت در مقابل قیمت">
        {timeline && timeline.data.length > 0 ? (
          <div className="space-y-4">
            <div className="overflow-x-auto">
              <div className="flex h-40 items-end gap-px">
                {timeline.data.slice(-200).map((point, i) => {
                  const score = point.composite_score ?? 50;
                  const height = Math.max(4, score * 1.4);
                  const color =
                    score >= 70
                      ? "bg-green-500"
                      : score >= 55
                        ? "bg-green-300"
                        : score >= 45
                          ? "bg-gray-400"
                          : score >= 30
                            ? "bg-red-300"
                            : "bg-red-500";
                  return (
                    <div
                      key={i}
                      className={`w-1 rounded-t ${color}`}
                      style={{ height: `${height}px` }}
                      title={`${point.recorded_at}: ${score}`}
                    />
                  );
                })}
              </div>
              <div className="mt-1 flex justify-between text-xs text-gray-400">
                <span>۷ روز پیش</span>
                <span>الان</span>
              </div>
            </div>
            {correlation && correlation.correlations.length > 0 && (
              <div>
                <p className="mb-2 text-sm font-medium text-gray-600 dark:text-gray-400">
                  همبستگی سنتیمنت—قیمت
                </p>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                  {correlation.correlations.map((c) => (
                    <div
                      key={c.lag}
                      className="rounded-lg bg-gray-50 p-2 text-center dark:bg-gray-800"
                    >
                      <div
                        className={`text-lg font-bold ${
                          c.correlation > 0.3
                            ? "text-green-600"
                            : c.correlation < -0.3
                              ? "text-red-600"
                              : "text-gray-500"
                        }`}
                      >
                        {c.correlation > 0 ? "+" : ""}
                        {c.correlation}
                      </div>
                      <div className="text-xs text-gray-500 dark:text-gray-400">
                        تاخیر {c.lag}
                      </div>
                      <div className="mt-1 text-[10px] text-gray-400">
                        {c.interpretation}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          <p className="text-sm text-gray-500 dark:text-gray-400">
            هنوز داده‌ای ثبت نشده است
          </p>
        )}
      </Card>

      {/* ── Section 5: Price Data Status ── */}
      <Card title="وضعیت داده قیمت">
        {priceStatus && priceStatus.symbols.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 text-gray-500 dark:border-gray-700 dark:text-gray-400">
                  <th className="px-3 py-2 text-right">نماد</th>
                  <th className="px-3 py-2 text-right">تایم‌فریم</th>
                  <th className="px-3 py-2 text-right">آخرین قیمت</th>
                  <th className="px-3 py-2 text-right">آخرین بروزرسانی</th>
                  <th className="px-3 py-2 text-right">تعداد رکورد</th>
                </tr>
              </thead>
              <tbody>
                {priceStatus.symbols.map((s, i) => (
                  <tr
                    key={i}
                    className="border-b border-gray-100 dark:border-gray-800"
                  >
                    <td className="px-3 py-2 font-mono text-gray-900 dark:text-gray-100">
                      {s.symbol}
                    </td>
                    <td className="px-3 py-2 text-gray-600 dark:text-gray-400">
                      {s.timeframe}
                    </td>
                    <td className="px-3 py-2 text-gray-900 dark:text-gray-100">
                      {s.last_price != null ? s.last_price.toLocaleString() : "—"}
                    </td>
                    <td className="px-3 py-2 text-gray-500 dark:text-gray-400">
                      {s.last_update ? formatTimeAgo(s.last_update) : "—"}
                    </td>
                    <td className="px-3 py-2 text-gray-600 dark:text-gray-400">
                      {s.record_count.toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-gray-500 dark:text-gray-400">
            هنوز داده قیمتی ثبت نشده است
          </p>
        )}
      </Card>
    </div>
  );
}

/* ── Helper Components ── */

function HealthCard({
  label,
  value,
  status,
  detail,
}: {
  label: string;
  value: string;
  status: "green" | "yellow" | "red" | "gray";
  detail: string;
}) {
  return (
    <div className="card flex items-start gap-3 p-4">
      <StatusDot status={status} />
      <div>
        <p className="text-sm text-gray-500 dark:text-gray-400">{label}</p>
        <p className="text-lg font-bold text-gray-900 dark:text-gray-100">
          {value}
        </p>
        <p className="text-xs text-gray-400">{detail}</p>
      </div>
    </div>
  );
}

function StatBox({
  label,
  value,
}: {
  label: string;
  value: number | string;
}) {
  return (
    <div className="rounded-lg bg-gray-50 p-3 text-center dark:bg-gray-800">
      <div className="text-xl font-bold text-gray-900 dark:text-gray-100">
        {typeof value === "number" ? value.toLocaleString() : value}
      </div>
      <div className="text-xs text-gray-500 dark:text-gray-400">{label}</div>
    </div>
  );
}

/* ── Helper Functions ── */

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    pending_30min: "۳۰ دقیقه",
    pending_1h: "۱ ساعت",
    pending_4h: "۴ ساعت",
    pending_24h: "۲۴ ساعت",
    pending_48h: "۴۸ ساعت",
    pending_7d: "۷ روز",
    complete: "تکمیل",
  };
  return labels[status] ?? status;
}

function formatTimeAgo(isoDate: string): string {
  const diff = Date.now() - new Date(isoDate).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "الان";
  if (mins < 60) return `${mins} دقیقه پیش`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} ساعت پیش`;
  const days = Math.floor(hours / 24);
  return `${days} روز پیش`;
}

function getHealthStatus(
  value: number | null | undefined,
  good: number,
  warning: number
): "green" | "yellow" | "red" | "gray" {
  if (value == null) return "gray";
  if (value >= good) return "green";
  if (value >= warning) return "yellow";
  return "red";
}

function getTimeStatus(
  isoDate: string | null | undefined,
  goodMinutes: number,
  warnMinutes: number
): "green" | "yellow" | "red" | "gray" {
  if (!isoDate) return "gray";
  const mins = (Date.now() - new Date(isoDate).getTime()) / 60000;
  if (mins <= goodMinutes) return "green";
  if (mins <= warnMinutes) return "yellow";
  return "red";
}
