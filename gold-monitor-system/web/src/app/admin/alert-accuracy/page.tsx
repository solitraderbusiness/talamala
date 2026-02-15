"use client";

import { useState, useEffect, useCallback } from "react";
import { getToken } from "@/lib/auth";
import InfoTip from "@/components/InfoTip";

/* ── Types ─────────────────────────────────────────────────────────── */

interface IntervalAccuracy {
  interval: string;
  total: number;
  correct: number;
  accuracy_pct: number | null;
}

interface OverviewData {
  intervals: IntervalAccuracy[];
  total_outcomes: number;
}

interface CategoryAccuracy {
  category: string;
  total: number;
  correct_24h: number;
  accuracy_24h_pct: number | null;
}

interface SeverityHeatmapRow {
  severity: string;
  intervals: IntervalAccuracy[];
}

interface ImpactCurveRow {
  severity: string;
  avg_changes: { interval: string; avg_change_pct: number | null }[];
}

interface SourceAccuracy {
  source_name: string;
  total: number;
  correct_24h: number;
  accuracy_pct: number | null;
  avg_impact_24h: number | null;
}

/* ── Helpers ───────────────────────────────────────────────────────── */

const INTERVAL_LABELS: Record<string, string> = {
  "30min": "۳۰ دقیقه",
  "1h": "۱ ساعت",
  "4h": "۴ ساعت",
  "24h": "۲۴ ساعت",
  "48h": "۴۸ ساعت",
  "7d": "۷ روز",
};

const SEVERITY_LABELS: Record<string, string> = {
  critical: "بحرانی",
  high: "بالا",
  medium: "متوسط",
  low: "پایین",
};

const SEVERITY_COLORS: Record<string, string> = {
  critical: "bg-red-500",
  high: "bg-orange-500",
  medium: "bg-amber-500",
  low: "bg-blue-500",
};

function accuracyColor(pct: number | null): string {
  if (pct === null) return "text-gray-400";
  if (pct >= 60) return "text-emerald-600 dark:text-emerald-400";
  if (pct >= 45) return "text-amber-600 dark:text-amber-400";
  return "text-red-600 dark:text-red-400";
}

function accuracyBg(pct: number | null): string {
  if (pct === null) return "bg-gray-100 dark:bg-gray-800";
  if (pct >= 60) return "bg-emerald-50 dark:bg-emerald-900/20";
  if (pct >= 45) return "bg-amber-50 dark:bg-amber-900/20";
  return "bg-red-50 dark:bg-red-900/20";
}

/* ── Page Component ───────────────────────────────────────────────── */

export default function AlertAccuracyPage() {
  const [overview, setOverview] = useState<OverviewData | null>(null);
  const [categories, setCategories] = useState<CategoryAccuracy[]>([]);
  const [heatmap, setHeatmap] = useState<SeverityHeatmapRow[]>([]);
  const [impactCurves, setImpactCurves] = useState<ImpactCurveRow[]>([]);
  const [sources, setSources] = useState<SourceAccuracy[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<"overview" | "sources">("overview");

  const fetchAll = useCallback(async () => {
    const token = getToken();
    if (!token) return;
    const headers = { Authorization: `Bearer ${token}` };

    const [ovRes, catRes, hmRes, icRes, srcRes] = await Promise.allSettled([
      fetch("/api/admin/alert-accuracy/overview", { headers }).then((r) =>
        r.ok ? r.json() : null
      ),
      fetch("/api/admin/alert-accuracy/by-category", { headers }).then((r) =>
        r.ok ? r.json() : null
      ),
      fetch("/api/admin/alert-accuracy/by-severity", { headers }).then((r) =>
        r.ok ? r.json() : null
      ),
      fetch("/api/admin/alert-accuracy/impact-curve", { headers }).then((r) =>
        r.ok ? r.json() : null
      ),
      fetch("/api/admin/alert-accuracy/by-source", { headers }).then((r) =>
        r.ok ? r.json() : null
      ),
    ]);

    if (ovRes.status === "fulfilled" && ovRes.value) setOverview(ovRes.value);
    if (catRes.status === "fulfilled" && catRes.value)
      setCategories(catRes.value.categories || []);
    if (hmRes.status === "fulfilled" && hmRes.value)
      setHeatmap(hmRes.value.heatmap || []);
    if (icRes.status === "fulfilled" && icRes.value)
      setImpactCurves(icRes.value.curves || []);
    if (srcRes.status === "fulfilled" && srcRes.value)
      setSources(srcRes.value.sources || []);

    setLoading(false);
  }, []);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  if (loading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <div className="text-center">
          <div className="mx-auto h-10 w-10 animate-spin rounded-full border-4 border-gold-500 border-t-transparent" />
          <p className="mt-3 text-sm text-gray-500">در حال بارگذاری...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="flex items-center text-xl font-bold text-gray-900 dark:text-gray-100">
          دقت هشدارها
          <InfoTip term="alert_accuracy" />
        </h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          سنجش دقت پیش‌بینی جهت قیمت در هشدارهای تولیدشده — بازخورد حلقه بسته
        </p>
      </div>

      {/* Tab bar */}
      <div className="flex gap-2 border-b border-gray-200 dark:border-gray-700">
        <button
          onClick={() => setActiveTab("overview")}
          className={`px-4 py-2 text-sm font-medium transition-colors ${
            activeTab === "overview"
              ? "border-b-2 border-gold-500 text-gold-700 dark:text-gold-400"
              : "text-gray-500 hover:text-gray-700 dark:text-gray-400"
          }`}
        >
          نمای کلی
        </button>
        <button
          onClick={() => setActiveTab("sources")}
          className={`px-4 py-2 text-sm font-medium transition-colors ${
            activeTab === "sources"
              ? "border-b-2 border-gold-500 text-gold-700 dark:text-gold-400"
              : "text-gray-500 hover:text-gray-700 dark:text-gray-400"
          }`}
        >
          کیفیت منابع
          <InfoTip term="alert_source_quality" />
        </button>
      </div>

      {activeTab === "overview" && (
        <>
          {/* ── Accuracy Cards (6 intervals) ───────────────────────── */}
          {overview && overview.intervals.length > 0 ? (
            <div>
              <h2 className="mb-3 text-sm font-bold text-gray-900 dark:text-gray-100">
                دقت کلی در هر بازه زمانی
              </h2>
              <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
                {overview.intervals.map((iv) => (
                  <div
                    key={iv.interval}
                    className={`rounded-xl border p-4 text-center ${accuracyBg(iv.accuracy_pct)} border-gray-200 dark:border-gray-700`}
                  >
                    <div className="text-xs font-medium text-gray-500 dark:text-gray-400">
                      {INTERVAL_LABELS[iv.interval] || iv.interval}
                    </div>
                    <div
                      className={`mt-1 text-2xl font-bold ${accuracyColor(iv.accuracy_pct)}`}
                    >
                      {iv.accuracy_pct !== null
                        ? `${Math.round(iv.accuracy_pct)}%`
                        : "---"}
                    </div>
                    <div className="mt-1 text-xs text-gray-400">
                      {iv.correct}/{iv.total}
                    </div>
                  </div>
                ))}
              </div>
              <p className="mt-2 text-xs text-gray-400">
                مجموع: {overview.total_outcomes} هشدار دارای داده نتیجه
              </p>
            </div>
          ) : (
            <div className="card py-12 text-center">
              <p className="text-sm text-gray-400">
                هنوز داده کافی برای سنجش دقت جمع‌آوری نشده. هشدارها باید حداقل
                ۳۰ دقیقه عمر داشته باشند.
              </p>
            </div>
          )}

          {/* ── Severity Heatmap ───────────────────────────────────── */}
          {heatmap.length > 0 && (
            <div>
              <h2 className="mb-3 flex items-center text-sm font-bold text-gray-900 dark:text-gray-100">
                دقت بر حسب شدت هشدار
              </h2>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-200 dark:border-gray-700">
                      <th className="px-3 py-2 text-right text-xs font-medium text-gray-500">
                        شدت
                      </th>
                      {Object.entries(INTERVAL_LABELS).map(([key, label]) => (
                        <th
                          key={key}
                          className="px-3 py-2 text-center text-xs font-medium text-gray-500"
                        >
                          {label}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {heatmap.map((row) => (
                      <tr
                        key={row.severity}
                        className="border-b border-gray-100 dark:border-gray-800"
                      >
                        <td className="px-3 py-2">
                          <span className="flex items-center gap-1.5">
                            <span
                              className={`inline-block h-2 w-2 rounded-full ${SEVERITY_COLORS[row.severity] || "bg-gray-400"}`}
                            />
                            <span className="font-medium text-gray-900 dark:text-gray-100">
                              {SEVERITY_LABELS[row.severity] || row.severity}
                            </span>
                          </span>
                        </td>
                        {row.intervals.map((iv) => (
                          <td
                            key={iv.interval}
                            className={`px-3 py-2 text-center font-medium ${accuracyColor(iv.accuracy_pct)}`}
                          >
                            {iv.accuracy_pct !== null
                              ? `${Math.round(iv.accuracy_pct)}%`
                              : "—"}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* ── Category Accuracy ──────────────────────────────────── */}
          {categories.length > 0 && (
            <div>
              <h2 className="mb-3 flex items-center text-sm font-bold text-gray-900 dark:text-gray-100">
                دقت بر حسب دسته‌بندی
                <InfoTip term="alert_accuracy_by_category" />
              </h2>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {categories
                  .sort(
                    (a, b) => (b.accuracy_24h_pct ?? 0) - (a.accuracy_24h_pct ?? 0)
                  )
                  .map((cat) => (
                    <div
                      key={cat.category}
                      className="card flex items-center justify-between"
                    >
                      <div>
                        <div className="text-sm font-medium text-gray-900 dark:text-gray-100">
                          {cat.category}
                        </div>
                        <div className="text-xs text-gray-400">
                          {cat.total} هشدار
                        </div>
                      </div>
                      <div
                        className={`text-lg font-bold ${accuracyColor(cat.accuracy_24h_pct)}`}
                      >
                        {cat.accuracy_24h_pct !== null
                          ? `${Math.round(cat.accuracy_24h_pct)}%`
                          : "---"}
                      </div>
                    </div>
                  ))}
              </div>
            </div>
          )}

          {/* ── Impact Curve ───────────────────────────────────────── */}
          {impactCurves.length > 0 && (
            <div>
              <h2 className="mb-3 flex items-center text-sm font-bold text-gray-900 dark:text-gray-100">
                میانگین تغییر قیمت بعد از هشدار
                <InfoTip term="alert_impact_curve" />
              </h2>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-200 dark:border-gray-700">
                      <th className="px-3 py-2 text-right text-xs font-medium text-gray-500">
                        شدت
                      </th>
                      {Object.entries(INTERVAL_LABELS).map(([key, label]) => (
                        <th
                          key={key}
                          className="px-3 py-2 text-center text-xs font-medium text-gray-500"
                        >
                          {label}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {impactCurves.map((row) => (
                      <tr
                        key={row.severity}
                        className="border-b border-gray-100 dark:border-gray-800"
                      >
                        <td className="px-3 py-2">
                          <span className="flex items-center gap-1.5">
                            <span
                              className={`inline-block h-2 w-2 rounded-full ${SEVERITY_COLORS[row.severity] || "bg-gray-400"}`}
                            />
                            <span className="font-medium">
                              {SEVERITY_LABELS[row.severity] || row.severity}
                            </span>
                          </span>
                        </td>
                        {row.avg_changes.map((ch) => (
                          <td
                            key={ch.interval}
                            className={`px-3 py-2 text-center font-mono text-xs ${
                              ch.avg_change_pct !== null && ch.avg_change_pct > 0
                                ? "text-emerald-600 dark:text-emerald-400"
                                : ch.avg_change_pct !== null &&
                                    ch.avg_change_pct < 0
                                  ? "text-red-600 dark:text-red-400"
                                  : "text-gray-400"
                            }`}
                          >
                            {ch.avg_change_pct !== null
                              ? `${ch.avg_change_pct > 0 ? "+" : ""}${ch.avg_change_pct.toFixed(2)}%`
                              : "—"}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}

      {activeTab === "sources" && (
        <div>
          <h2 className="mb-3 text-sm font-bold text-gray-900 dark:text-gray-100">
            رتبه‌بندی منابع بر اساس دقت
          </h2>
          {sources.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 dark:border-gray-700">
                    <th className="px-3 py-2 text-right text-xs font-medium text-gray-500">
                      منبع
                    </th>
                    <th className="px-3 py-2 text-center text-xs font-medium text-gray-500">
                      تعداد هشدار
                    </th>
                    <th className="px-3 py-2 text-center text-xs font-medium text-gray-500">
                      دقت ۲۴ ساعته
                    </th>
                    <th className="px-3 py-2 text-center text-xs font-medium text-gray-500">
                      میانگین تأثیر
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {sources
                    .sort(
                      (a, b) => (b.accuracy_pct ?? 0) - (a.accuracy_pct ?? 0)
                    )
                    .map((src) => (
                      <tr
                        key={src.source_name}
                        className="border-b border-gray-100 dark:border-gray-800"
                      >
                        <td className="px-3 py-2 font-medium text-gray-900 dark:text-gray-100">
                          {src.source_name}
                        </td>
                        <td className="px-3 py-2 text-center text-gray-500">
                          {src.total}
                        </td>
                        <td
                          className={`px-3 py-2 text-center font-bold ${accuracyColor(src.accuracy_pct)}`}
                        >
                          {src.accuracy_pct !== null
                            ? `${Math.round(src.accuracy_pct)}%`
                            : "---"}
                        </td>
                        <td className="px-3 py-2 text-center font-mono text-xs text-gray-500">
                          {src.avg_impact_24h !== null
                            ? `${src.avg_impact_24h > 0 ? "+" : ""}${src.avg_impact_24h.toFixed(2)}%`
                            : "—"}
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="card py-12 text-center">
              <p className="text-sm text-gray-400">
                هنوز داده کافی برای رتبه‌بندی منابع جمع‌آوری نشده.
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
