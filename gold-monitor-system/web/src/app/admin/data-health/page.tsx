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
  getSnapshotLiveStatus,
  getLiveThroughput,
  getQualityTiers,
  getMissingFields,
  getGuardrails,
  DataHealthOverview,
  SnapshotStats,
  OutcomePipeline,
  SentimentTimelineResponse,
  PriceStatusResponse,
  SentimentCorrelationResponse,
  SnapshotLiveStatusResponse,
  LiveThroughputResponse,
  QualityTiersResponse,
  MissingFieldsResponse,
  GuardrailsResponse,
} from "@/lib/api";
import InfoTip from "@/components/InfoTip";

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
  title: React.ReactNode;
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
  const [liveStatus, setLiveStatus] = useState<SnapshotLiveStatusResponse | null>(null);
  const [throughput, setThroughput] = useState<LiveThroughputResponse | null>(null);
  const [qualityTiers, setQualityTiers] = useState<QualityTiersResponse | null>(null);
  const [missingFields, setMissingFields] = useState<MissingFieldsResponse | null>(null);
  const [guardrails, setGuardrailsData] = useState<GuardrailsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [snapPeriod, setSnapPeriod] = useState("today");

  const fetchAll = useCallback(async () => {
    const token = getToken();
    if (!token) return;

    setLoading(true);
    try {
      const [ov, ss, pl, tl, ps, cr, ls, tp, qt, mf, gr] = await Promise.allSettled([
        getDataHealthOverview(token),
        getSnapshotStats(token, snapPeriod),
        getOutcomePipeline(token),
        getSentimentTimeline(token, 168),
        getPriceStatus(token),
        getSentimentCorrelation(token, 7),
        getSnapshotLiveStatus(token),
        getLiveThroughput(token, 24),
        getQualityTiers(token, 24),
        getMissingFields(token, 7),
        getGuardrails(token),
      ]);

      if (ov.status === "fulfilled") setOverview(ov.value);
      if (ss.status === "fulfilled") setSnapStats(ss.value);
      if (pl.status === "fulfilled") setPipeline(pl.value);
      if (tl.status === "fulfilled") setTimeline(tl.value);
      if (ps.status === "fulfilled") setPriceStatus(ps.value);
      if (cr.status === "fulfilled") setCorrelation(cr.value);
      if (ls.status === "fulfilled") setLiveStatus(ls.value);
      if (tp.status === "fulfilled") setThroughput(tp.value);
      if (qt.status === "fulfilled") setQualityTiers(qt.value);
      if (mf.status === "fulfilled") setMissingFields(mf.value);
      if (gr.status === "fulfilled") setGuardrailsData(gr.value);
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
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <HealthCard
          label={<>اسنپ‌شات زنده (live) <InfoTip term="snapshot_coverage" /></>}
          value={overview?.live_snapshot_coverage_pct != null ? `${overview.live_snapshot_coverage_pct}%` : "—"}
          status={getHealthStatus(overview?.live_snapshot_coverage_pct, 80, 50)}
          detail={`${overview?.live_snapshots_24h ?? 0} زنده از ${overview?.alerts_24h ?? 0} هشدار`}
        />
        <HealthCard
          label="اسنپ‌شات کامل (complete)"
          value={overview?.complete_snapshot_coverage_pct != null ? `${overview.complete_snapshot_coverage_pct}%` : "—"}
          status={getHealthStatus(overview?.complete_snapshot_coverage_pct, 60, 30)}
          detail={`${overview?.complete_snapshots_24h ?? 0} کامل — شامل تکنیکال و سنتیمنت`}
        />
        <HealthCard
          label="پوشش ردیف (seeded)"
          value={overview?.snapshot_coverage_pct != null ? `${overview.snapshot_coverage_pct}%` : "—"}
          status={getHealthStatus(overview?.snapshot_coverage_pct, 95, 80)}
          detail={`${overview?.snapshots_24h ?? 0} ردیف (زنده + بازسازی‌شده)`}
        />
        <HealthCard
          label={<>ردیاب نتایج <InfoTip term="outcome_tracker" /></>}
          value={overview?.outcome_seed_coverage_pct != null ? `${overview.outcome_seed_coverage_pct}% seeded` : "—"}
          status={getHealthStatus(overview?.outcome_seed_coverage_pct, 95, 80)}
          detail={`${overview?.outcomes_seeded_24h ?? 0} seeded — ${overview?.outcomes_complete_pct ?? 0}% complete (all time)`}
        />
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <HealthCard
          label={<>جدول زمانی سنتیمنت <InfoTip term="sentiment_timeline" /></>}
          value={overview?.sentiment_last_recorded ? formatTimeAgo(overview.sentiment_last_recorded) : "—"}
          status={getTimeStatus(overview?.sentiment_last_recorded, 10, 30)}
          detail="هر ۵ دقیقه"
        />
        <HealthCard
          label={<>داده قیمت <InfoTip term="price_data" /></>}
          value={overview?.price_data_last_update ? formatTimeAgo(overview.price_data_last_update) : "—"}
          status={getTimeStatus(overview?.price_data_last_update, 10, 60)}
          detail="۵ دقیقه‌ای + روزانه"
        />
        <HealthCard
          label="شکاف ۷ روزه — اسنپ‌شات"
          value={`${overview?.missing_snapshots_7d ?? "—"}`}
          status={overview?.missing_snapshots_7d === 0 ? "green" : overview?.missing_snapshots_7d != null && overview.missing_snapshots_7d <= 5 ? "yellow" : "red"}
          detail={`از ${overview?.alerts_7d ?? 0} هشدار`}
        />
        <HealthCard
          label="شکاف ۷ روزه — نتایج"
          value={`${overview?.missing_outcomes_7d ?? "—"}`}
          status={overview?.missing_outcomes_7d === 0 ? "green" : overview?.missing_outcomes_7d != null && overview.missing_outcomes_7d <= 5 ? "yellow" : "red"}
          detail={`${overview?.outcome_errors ?? 0} خطا`}
        />
      </div>

      {/* ── Reconciliation Backlog Widget ── */}
      {overview && overview.reconciliation_backlog > 0 && (
        <div className="card flex items-center gap-4 p-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-amber-100 dark:bg-amber-900/30">
            <span className="text-lg">&#x1f504;</span>
          </div>
          <div className="flex-1">
            <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
              بازسازی (Reconciliation)
            </p>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              {overview.reconciliation_backlog} ردیف در صف
              {overview.reconciliation_eta_minutes > 0 && (
                <> — تخمین زمان: {overview.reconciliation_eta_minutes < 60
                  ? `${overview.reconciliation_eta_minutes} دقیقه`
                  : `${Math.round(overview.reconciliation_eta_minutes / 60 * 10) / 10} ساعت`
                }</>
              )}
              <span className="mr-3 text-gray-400">
                (هر {Math.round(overview.reconciliation_interval_seconds / 60)} دقیقه، دسته {overview.reconciliation_batch_size})
              </span>
            </p>
          </div>
        </div>
      )}

      {/* ── Cockpit Widget 1: Guardrails (QA) ── */}
      {guardrails && (
        <Card title="بررسی‌های کیفی (Guardrails QA)">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            {guardrails.checks.map((check) => (
              <div
                key={check.id}
                className={`flex items-start gap-3 rounded-lg border p-4 ${
                  check.verdict === "PASS"
                    ? "border-green-200 bg-green-50 dark:border-green-800 dark:bg-green-900/10"
                    : check.verdict === "WARN"
                      ? "border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-900/10"
                      : "border-red-200 bg-red-50 dark:border-red-800 dark:bg-red-900/10"
                }`}
              >
                <span className="mt-0.5 text-lg">
                  {check.verdict === "PASS" ? "\u2705" : check.verdict === "WARN" ? "\u26a0\ufe0f" : "\u274c"}
                </span>
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span
                      className={`rounded px-1.5 py-0.5 text-xs font-bold ${
                        check.verdict === "PASS"
                          ? "bg-green-200 text-green-800 dark:bg-green-800 dark:text-green-200"
                          : check.verdict === "WARN"
                            ? "bg-amber-200 text-amber-800 dark:bg-amber-800 dark:text-amber-200"
                            : "bg-red-200 text-red-800 dark:bg-red-800 dark:text-red-200"
                      }`}
                    >
                      {check.verdict}
                    </span>
                  </div>
                  <p className="mt-1 text-sm text-gray-700 dark:text-gray-300">
                    {check.label_fa}
                  </p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    {check.id === "live_missing_data"
                      ? `اسنپ‌شات: ${check.missing_snapshot ?? 0} — نتیجه: ${check.missing_outcome ?? 0}`
                      : `تعداد: ${check.count ?? 0}`}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* ── Cockpit Widget 2: Quality Tiers ── */}
      {qualityTiers && (
        <Card title="سطوح کیفیت (Quality Tiers — ۲۴ ساعت)">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <QualityCard
              label="پوشش اسنپ‌شات زنده"
              labelEn="live_snapshot_coverage"
              pct={qualityTiers.live_snapshot_coverage.pct}
              numerator={qualityTiers.live_snapshot_coverage.numerator}
              denominator={qualityTiers.live_snapshot_coverage.denominator}
              goodThreshold={80}
              warnThreshold={50}
            />
            <QualityCard
              label="اسنپ‌شات زنده + کامل"
              labelEn="live_complete_snapshot"
              pct={qualityTiers.live_complete_snapshot_coverage.pct}
              numerator={qualityTiers.live_complete_snapshot_coverage.numerator}
              denominator={qualityTiers.live_complete_snapshot_coverage.denominator}
              goodThreshold={60}
              warnThreshold={30}
            />
            <QualityCard
              label="پوشش ردیاب نتایج"
              labelEn="outcome_seed_coverage"
              pct={qualityTiers.outcome_seed_coverage.pct}
              numerator={qualityTiers.outcome_seed_coverage.numerator}
              denominator={qualityTiers.outcome_seed_coverage.denominator}
              goodThreshold={95}
              warnThreshold={80}
            />
            <QualityCard
              label="نرخ تکمیل نتایج"
              labelEn="outcome_completion"
              pct={qualityTiers.outcome_completion.pct}
              numerator={qualityTiers.outcome_completion.numerator}
              denominator={qualityTiers.outcome_completion.denominator}
              goodThreshold={20}
              warnThreshold={5}
            />
          </div>
        </Card>
      )}

      {/* ── Cockpit Widget 3: Live Snapshot Throughput Chart ── */}
      {throughput && throughput.data.length > 0 && (
        <Card title="عملکرد اسنپ‌شات زنده (Live Snapshot Throughput — ۲۴ ساعت)">
          <div className="space-y-2">
            <div className="flex gap-4 text-xs text-gray-500 dark:text-gray-400">
              <span className="flex items-center gap-1">
                <span className="inline-block h-3 w-3 rounded bg-gold-500" /> هشدارها (alerts)
              </span>
              <span className="flex items-center gap-1">
                <span className="inline-block h-3 w-3 rounded bg-green-500" /> اسنپ‌شات زنده (live)
              </span>
            </div>
            <div className="overflow-x-auto">
              <div className="flex h-44 items-end gap-1" style={{ minWidth: `${throughput.data.length * 28}px` }}>
                {throughput.data.map((point, i) => {
                  const maxVal = Math.max(
                    ...throughput.data.map((d) => Math.max(d.alerts_created, d.live_snapshots_created)),
                    1
                  );
                  const alertH = Math.max(2, (point.alerts_created / maxVal) * 150);
                  const liveH = Math.max(0, (point.live_snapshots_created / maxVal) * 150);
                  const hour = point.hour_bucket
                    ? new Date(point.hour_bucket).getUTCHours().toString().padStart(2, "0")
                    : "";
                  return (
                    <div
                      key={i}
                      className="group relative flex flex-col items-center"
                      style={{ width: "24px" }}
                    >
                      {/* Tooltip */}
                      <div className="pointer-events-none absolute -top-16 z-10 hidden whitespace-nowrap rounded bg-gray-800 px-2 py-1 text-xs text-white shadow-lg group-hover:block">
                        <div>{hour}:00 UTC</div>
                        <div>هشدار: {point.alerts_created}</div>
                        <div>زنده: {point.live_snapshots_created}</div>
                      </div>
                      <div className="flex gap-px items-end">
                        <div
                          className="w-[10px] rounded-t bg-gold-400 dark:bg-gold-600"
                          style={{ height: `${alertH}px` }}
                        />
                        <div
                          className="w-[10px] rounded-t bg-green-500 dark:bg-green-600"
                          style={{ height: `${liveH}px` }}
                        />
                      </div>
                      {(i % 3 === 0 || i === throughput.data.length - 1) && (
                        <span className="mt-1 text-[9px] text-gray-400">{hour}</span>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </Card>
      )}

      {/* ── Cockpit Widget 4: Missing Field Breakdown ── */}
      {missingFields && (
        <Card title="فیلدهای گمشده اسنپ‌شات‌های زنده (Missing Fields — ۷ روز)">
          {missingFields.fields.length === 0 ? (
            <p className="text-sm text-green-600 dark:text-green-400">
              هیچ فیلدی کم نیست &#x2705;
            </p>
          ) : (
            <div className="space-y-2">
              <p className="text-xs text-gray-500 dark:text-gray-400">
                از مجموع {missingFields.total_live_snapshots.toLocaleString()} اسنپ‌شات زنده
              </p>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-200 text-gray-500 dark:border-gray-700 dark:text-gray-400">
                      <th className="px-3 py-2 text-right">فیلد (missing_field)</th>
                      <th className="px-3 py-2 text-right">تعداد (count)</th>
                      <th className="px-3 py-2 text-right">درصد (% of live)</th>
                      <th className="px-3 py-2 text-right">نوار</th>
                    </tr>
                  </thead>
                  <tbody>
                    {missingFields.fields.map((f) => (
                      <tr
                        key={f.field}
                        className="border-b border-gray-100 dark:border-gray-800"
                      >
                        <td className="px-3 py-2 font-mono text-xs text-gray-900 dark:text-gray-100">
                          {f.field}
                        </td>
                        <td className="px-3 py-2 text-gray-700 dark:text-gray-300">
                          {f.count.toLocaleString()}
                        </td>
                        <td className="px-3 py-2 text-gray-700 dark:text-gray-300">
                          {f.pct}%
                        </td>
                        <td className="px-3 py-2">
                          <div className="h-2 w-full rounded bg-gray-200 dark:bg-gray-700">
                            <div
                              className="h-2 rounded bg-red-400 dark:bg-red-500"
                              style={{ width: `${Math.min(f.pct, 100)}%` }}
                            />
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </Card>
      )}

      {/* ── Section: Live vs Reconciled Snapshots ── */}
      {liveStatus && (
        <>
          <Card title="اسنپ‌شات زنده در مقابل بازسازی‌شده (۲۴ ساعت)">
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
              <StatBox label="کل هشدارها" value={liveStatus.summary_24h.total_alerts} />
              <StatBox
                label="زنده (live)"
                value={liveStatus.summary_24h.live_count}
              />
              <StatBox
                label="بازسازی‌شده (reconciled)"
                value={liveStatus.summary_24h.reconciled_count}
              />
              <StatBox
                label="پوشش زنده"
                value={
                  liveStatus.summary_24h.live_snapshot_coverage_pct != null
                    ? `${liveStatus.summary_24h.live_snapshot_coverage_pct}%`
                    : "—"
                }
              />
              <div className="rounded-lg bg-gray-50 p-3 dark:bg-gray-800">
                <div className="text-xs text-gray-500 dark:text-gray-400">آخرین زنده</div>
                <div className="text-sm font-medium text-gray-900 dark:text-gray-100">
                  {liveStatus.summary_24h.last_live_snapshot_at
                    ? formatTimeAgo(liveStatus.summary_24h.last_live_snapshot_at)
                    : "هرگز"}
                </div>
              </div>
              <div className="rounded-lg bg-gray-50 p-3 dark:bg-gray-800">
                <div className="text-xs text-gray-500 dark:text-gray-400">آخرین بازسازی</div>
                <div className="text-sm font-medium text-gray-900 dark:text-gray-100">
                  {liveStatus.summary_24h.last_reconciled_snapshot_at
                    ? formatTimeAgo(liveStatus.summary_24h.last_reconciled_snapshot_at)
                    : "هرگز"}
                </div>
              </div>
            </div>
          </Card>

          <Card title="آخرین ۲۰ اسنپ‌شات">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 text-gray-500 dark:border-gray-700 dark:text-gray-400">
                    <th className="px-2 py-2 text-right">alert_id</th>
                    <th className="px-2 py-2 text-right">زمان</th>
                    <th className="px-2 py-2 text-right">منبع</th>
                    <th className="px-2 py-2 text-right">کامل</th>
                    <th className="px-2 py-2 text-right">XAUUSD</th>
                    <th className="px-2 py-2 text-right">RSI</th>
                    <th className="px-2 py-2 text-right">سنتیمنت</th>
                    <th className="px-2 py-2 text-right">ms</th>
                  </tr>
                </thead>
                <tbody>
                  {liveStatus.recent_snapshots.map((s) => (
                    <tr
                      key={s.alert_id}
                      className={`border-b border-gray-100 dark:border-gray-800 ${
                        s.source === "live"
                          ? "bg-green-50 dark:bg-green-900/10"
                          : ""
                      }`}
                    >
                      <td className="px-2 py-1.5 font-mono text-xs text-gray-600 dark:text-gray-400">
                        {s.alert_id.slice(0, 8)}
                      </td>
                      <td className="px-2 py-1.5 text-xs text-gray-500 dark:text-gray-400">
                        {s.created_at ? formatTimeAgo(s.created_at) : "—"}
                      </td>
                      <td className="px-2 py-1.5">
                        <span
                          className={`rounded px-1.5 py-0.5 text-xs font-medium ${
                            s.source === "live"
                              ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                              : "bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400"
                          }`}
                        >
                          {s.source}
                        </span>
                      </td>
                      <td className="px-2 py-1.5 text-center">
                        {s.snapshot_complete ? (
                          <span className="text-green-600">&#10003;</span>
                        ) : (
                          <span className="text-gray-400">&#10007;</span>
                        )}
                      </td>
                      <td className="px-2 py-1.5 text-xs text-gray-900 dark:text-gray-100">
                        {s.xauusd != null ? s.xauusd.toLocaleString() : "—"}
                      </td>
                      <td className="px-2 py-1.5 text-xs text-gray-900 dark:text-gray-100">
                        {s.gold_rsi_14 ?? "—"}
                      </td>
                      <td className="px-2 py-1.5 text-xs text-gray-900 dark:text-gray-100">
                        {s.sentiment_composite ?? "—"}
                      </td>
                      <td className="px-2 py-1.5 text-xs text-gray-500">
                        {s.fetch_duration_ms ?? "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}

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
      <Card title={<>خط لوله نتایج <InfoTip term="outcome_pipeline" /></>}>
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
  label: React.ReactNode;
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

function QualityCard({
  label,
  labelEn,
  pct,
  numerator,
  denominator,
  goodThreshold,
  warnThreshold,
}: {
  label: string;
  labelEn: string;
  pct: number | null;
  numerator: number;
  denominator: number;
  goodThreshold: number;
  warnThreshold: number;
}) {
  const status = getHealthStatus(pct, goodThreshold, warnThreshold);
  const borderColor =
    status === "green"
      ? "border-green-300 dark:border-green-700"
      : status === "yellow"
        ? "border-amber-300 dark:border-amber-700"
        : status === "red"
          ? "border-red-300 dark:border-red-700"
          : "border-gray-200 dark:border-gray-700";
  return (
    <div className={`rounded-lg border-2 p-4 ${borderColor}`}>
      <div className="flex items-center gap-2">
        <StatusDot status={status} />
        <span className="text-sm text-gray-600 dark:text-gray-400">{label}</span>
      </div>
      <div className="mt-2 text-2xl font-bold text-gray-900 dark:text-gray-100">
        {pct != null ? `${pct}%` : "—"}
      </div>
      <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
        {numerator.toLocaleString()} / {denominator.toLocaleString()}
      </div>
      <div className="mt-0.5 text-[10px] font-mono text-gray-400">
        {labelEn}
      </div>
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
