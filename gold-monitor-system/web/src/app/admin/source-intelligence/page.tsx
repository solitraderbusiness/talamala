"use client";

import { useEffect, useState, useCallback } from "react";
import { getToken } from "@/lib/auth";
import {
  getSourceOverview,
  getSourceCoverage,
  getDedupeHealth,
  getSourceRecommendations,
  manageSourceTag,
} from "@/lib/api";

/* ── Types ─────────────────────────────────────────────────────────── */

interface SourceRow {
  id: string;
  name: string;
  type: string;
  enabled: boolean;
  raw_count: number;
  alert_count: number;
  match_rate_pct: number | null;
  avg_confidence: number | null;
  severity_breakdown: Record<string, number>;
  error_count: number;
  tags: string[];
}

interface SourceOverviewData {
  sources: SourceRow[];
  total_sources: number;
  enabled_sources: number;
  total_alerts: number;
  total_raw_items: number;
  overall_match_rate_pct: number | null;
  coverage_buckets: Record<string, number>;
}

interface BucketItem {
  label: string;
  count: number;
}

interface CoverageData {
  by_category: BucketItem[];
  by_direction: BucketItem[];
  by_severity: BucketItem[];
  by_source: BucketItem[];
  by_news_type: BucketItem[];
  missing_buckets: string[];
  uncategorized_pct: number | null;
}

interface CollisionItem {
  hash: string;
  sources: string[];
  count: number;
}

interface HighWasteSource {
  source_id: string;
  source_name: string;
  raw_count: number;
  duplicate_count: number;
  waste_pct: number;
}

interface DedupeLayer {
  layer: string;
  description: string;
  duplicates_caught: number;
}

interface DedupeData {
  total_raw_items: number;
  total_alerts: number;
  overall_dedup_rate_pct: number | null;
  cross_source_collisions: CollisionItem[];
  high_waste_sources: HighWasteSource[];
  dedupe_layers: DedupeLayer[];
}

interface Recommendation {
  type: string;
  title: string;
  title_fa?: string;
  description: string;
  description_fa?: string;
  priority: string;
  source_id?: string;
  source_name?: string;
}

interface RecommendationsData {
  recommendations: Recommendation[];
}

/* ── Tab definitions ───────────────────────────────────────────────── */

const TABS = [
  { id: "inventory", label: "موجودی منابع" },
  { id: "coverage", label: "پوشش" },
  { id: "dedupe", label: "تکراری\u200Cها" },
  { id: "recommendations", label: "توصیه\u200Cها" },
] as const;

type TabId = (typeof TABS)[number]["id"];

const DAYS_OPTIONS = [7, 14, 30, 60, 90];

/* ── Helpers ───────────────────────────────────────────────────────── */

function pct(value: number | null | undefined): string {
  if (value == null) return "--";
  return `${value.toFixed(1)}%`;
}

function severityColor(sev: string): string {
  switch (sev) {
    case "critical":
      return "bg-red-600 text-white";
    case "high":
      return "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400";
    case "medium":
      return "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400";
    case "low":
      return "bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400";
    default:
      return "bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400";
  }
}

function typeBadge(type: string): string {
  switch (type) {
    case "add":
    case "enable":
      return "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400";
    case "disable":
    case "remove":
      return "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400";
    case "tune":
    case "adjust":
      return "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400";
    case "investigate":
    case "review":
      return "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400";
    default:
      return "bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400";
  }
}

function priorityBadge(priority: string): string {
  switch (priority) {
    case "high":
      return "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400";
    case "medium":
      return "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400";
    case "low":
      return "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400";
    default:
      return "bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400";
  }
}

function barColor(index: number): string {
  const colors = [
    "bg-gold-500",
    "bg-blue-500",
    "bg-green-500",
    "bg-purple-500",
    "bg-orange-500",
    "bg-teal-500",
    "bg-pink-500",
    "bg-indigo-500",
    "bg-red-400",
    "bg-cyan-500",
  ];
  return colors[index % colors.length];
}

function impactColor(label: string): string {
  const lower = label.toLowerCase();
  if (lower === "bullish" || lower.includes("buy")) {
    return "bg-green-500";
  }
  if (lower === "bearish" || lower.includes("sell")) {
    return "bg-red-500";
  }
  return "bg-gray-400";
}

/* ── Card component ────────────────────────────────────────────────── */

function Card({
  title,
  children,
  className = "",
}: {
  title?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={`card p-5 ${className}`}>
      {title && (
        <h3 className="mb-4 text-lg font-semibold text-gray-900 dark:text-gray-100">
          {title}
        </h3>
      )}
      {children}
    </div>
  );
}

function StatBox({
  label,
  value,
  sub,
}: {
  label: string;
  value: string | number;
  sub?: string;
}) {
  return (
    <div className="rounded-lg bg-gray-50 p-3 text-center dark:bg-gray-800">
      <div className="text-xl font-bold text-gray-900 dark:text-gray-100">
        {typeof value === "number" ? value.toLocaleString() : value}
      </div>
      <div className="text-xs text-gray-500 dark:text-gray-400">{label}</div>
      {sub && (
        <div className="mt-0.5 text-[10px] text-gray-400">{sub}</div>
      )}
    </div>
  );
}

/* ── Horizontal bar chart ──────────────────────────────────────────── */

function HorizontalBarChart({
  items,
  colorFn,
}: {
  items: BucketItem[];
  colorFn?: (label: string, index: number) => string;
}) {
  const maxCount = Math.max(...items.map((i) => i.count), 1);
  return (
    <div className="space-y-2">
      {items.map((item, idx) => {
        const widthPct = Math.max(2, (item.count / maxCount) * 100);
        const color = colorFn
          ? colorFn(item.label, idx)
          : barColor(idx);
        return (
          <div key={item.label} className="flex items-center gap-3">
            <div className="w-28 shrink-0 truncate text-sm text-gray-700 dark:text-gray-300">
              {item.label || "(empty)"}
            </div>
            <div className="flex-1">
              <div className="h-5 w-full rounded bg-gray-100 dark:bg-gray-800">
                <div
                  className={`h-5 rounded ${color}`}
                  style={{ width: `${widthPct}%` }}
                />
              </div>
            </div>
            <div className="w-12 shrink-0 text-left text-sm font-medium text-gray-900 dark:text-gray-100">
              {item.count.toLocaleString()}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/* ── Main page component ───────────────────────────────────────────── */

export default function SourceIntelligencePage() {
  const [activeTab, setActiveTab] = useState<TabId>("inventory");
  const [days, setDays] = useState(7);
  const [loading, setLoading] = useState(true);

  const [overview, setOverview] = useState<SourceOverviewData | null>(null);
  const [coverage, setCoverage] = useState<CoverageData | null>(null);
  const [dedupe, setDedupe] = useState<DedupeData | null>(null);
  const [recommendations, setRecommendations] = useState<RecommendationsData | null>(null);

  const [tagLoading, setTagLoading] = useState<string | null>(null);

  const fetchAll = useCallback(async () => {
    const token = getToken();
    if (!token) return;

    setLoading(true);
    try {
      const [ov, cv, dd, rc] = await Promise.allSettled([
        getSourceOverview(token, days),
        getSourceCoverage(token, days),
        getDedupeHealth(token, days),
        getSourceRecommendations(token, days),
      ]);

      if (ov.status === "fulfilled") setOverview(ov.value);
      if (cv.status === "fulfilled") setCoverage(cv.value);
      if (dd.status === "fulfilled") setDedupe(dd.value);
      if (rc.status === "fulfilled") setRecommendations(rc.value);
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  async function handleRemoveTag(sourceId: string, tag: string) {
    const token = getToken();
    if (!token) return;
    const key = `${sourceId}_${tag}`;
    setTagLoading(key);
    try {
      await manageSourceTag(token, { source_id: sourceId, tag, action: "remove" });
      await fetchAll();
    } catch {
      // silent
    } finally {
      setTagLoading(null);
    }
  }

  if (loading && !overview) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <div className="h-10 w-10 animate-spin rounded-full border-4 border-gold-500 border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header + days selector */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">
          هوش منابع
        </h2>
        <div className="flex items-center gap-2">
          <label className="text-sm text-gray-500 dark:text-gray-400">
            بازه:
          </label>
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-900 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100"
          >
            {DAYS_OPTIONS.map((d) => (
              <option key={d} value={d}>
                {d} روز
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 overflow-x-auto rounded-lg border border-gray-200 bg-gray-50 p-1 dark:border-gray-800 dark:bg-gray-900">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`whitespace-nowrap rounded-md px-4 py-2 text-sm font-medium transition-colors ${
              activeTab === tab.id
                ? "bg-gold-500 text-white shadow-sm"
                : "text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === "inventory" && (
        <InventoryTab
          overview={overview}
          tagLoading={tagLoading}
          onRemoveTag={handleRemoveTag}
        />
      )}
      {activeTab === "coverage" && <CoverageTab coverage={coverage} />}
      {activeTab === "dedupe" && <DedupeTab dedupe={dedupe} />}
      {activeTab === "recommendations" && (
        <RecommendationsTab recommendations={recommendations} />
      )}
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════════
   Tab 1: Inventory (موجودی منابع)
   ══════════════════════════════════════════════════════════════════════ */

function InventoryTab({
  overview,
  tagLoading,
  onRemoveTag,
}: {
  overview: SourceOverviewData | null;
  tagLoading: string | null;
  onRemoveTag: (sourceId: string, tag: string) => void;
}) {
  const [sortField, setSortField] = useState<keyof SourceRow>("match_rate_pct");
  const [sortAsc, setSortAsc] = useState(false);

  if (!overview) {
    return (
      <p className="text-sm text-gray-500 dark:text-gray-400">
        داده‌ای دریافت نشد
      </p>
    );
  }

  function handleSort(field: keyof SourceRow) {
    if (sortField === field) {
      setSortAsc(!sortAsc);
    } else {
      setSortField(field);
      setSortAsc(false);
    }
  }

  const sorted = [...overview.sources].sort((a, b) => {
    const av = a[sortField];
    const bv = b[sortField];
    const an = typeof av === "number" ? av : av == null ? -Infinity : 0;
    const bn = typeof bv === "number" ? bv : bv == null ? -Infinity : 0;
    return sortAsc ? an - bn : bn - an;
  });

  const sortIndicator = (field: keyof SourceRow) =>
    sortField === field ? (sortAsc ? " \u25B2" : " \u25BC") : "";

  return (
    <div className="space-y-4">
      {/* Summary cards */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <StatBox label="کل منابع" value={overview.total_sources} />
        <StatBox label="فعال" value={overview.enabled_sources} />
        <StatBox label="آیتم خام" value={overview.total_raw_items} />
        <StatBox label="هشدارها" value={overview.total_alerts} />
        <StatBox
          label="نرخ تطبیق"
          value={pct(overview.overall_match_rate_pct)}
        />
        <StatBox
          label="غیرفعال"
          value={overview.total_sources - overview.enabled_sources}
        />
      </div>

      {/* Sources table */}
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 text-gray-500 dark:border-gray-700 dark:text-gray-400">
                <th className="px-2 py-2 text-right">نام</th>
                <th className="px-2 py-2 text-right">نوع</th>
                <th className="px-2 py-2 text-center">وضعیت</th>
                <th
                  className="cursor-pointer px-2 py-2 text-right hover:text-gold-600"
                  onClick={() => handleSort("raw_count")}
                >
                  خام{sortIndicator("raw_count")}
                </th>
                <th
                  className="cursor-pointer px-2 py-2 text-right hover:text-gold-600"
                  onClick={() => handleSort("alert_count")}
                >
                  هشدار{sortIndicator("alert_count")}
                </th>
                <th
                  className="cursor-pointer px-2 py-2 text-right hover:text-gold-600"
                  onClick={() => handleSort("match_rate_pct")}
                >
                  نرخ تطبیق{sortIndicator("match_rate_pct")}
                </th>
                <th
                  className="cursor-pointer px-2 py-2 text-right hover:text-gold-600"
                  onClick={() => handleSort("avg_confidence")}
                >
                  اطمینان{sortIndicator("avg_confidence")}
                </th>
                <th className="px-2 py-2 text-right">شدت‌ها</th>
                <th
                  className="cursor-pointer px-2 py-2 text-right hover:text-gold-600"
                  onClick={() => handleSort("error_count")}
                >
                  خطا{sortIndicator("error_count")}
                </th>
                <th className="px-2 py-2 text-right">برچسب‌ها</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((src) => (
                <tr
                  key={src.id}
                  className="border-b border-gray-100 dark:border-gray-800"
                >
                  {/* Name */}
                  <td className="max-w-[160px] truncate px-2 py-2 font-medium text-gray-900 dark:text-gray-100">
                    {src.name}
                  </td>

                  {/* Type */}
                  <td className="px-2 py-2">
                    <span className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-600 dark:bg-gray-700 dark:text-gray-400">
                      {src.type}
                    </span>
                  </td>

                  {/* Enabled */}
                  <td className="px-2 py-2 text-center">
                    {src.enabled ? (
                      <span className="inline-block h-2.5 w-2.5 rounded-full bg-green-500" />
                    ) : (
                      <span className="inline-block h-2.5 w-2.5 rounded-full bg-gray-300 dark:bg-gray-600" />
                    )}
                  </td>

                  {/* Raw count */}
                  <td className="px-2 py-2 text-gray-700 dark:text-gray-300">
                    {src.raw_count.toLocaleString()}
                  </td>

                  {/* Alert count */}
                  <td className="px-2 py-2 text-gray-700 dark:text-gray-300">
                    {src.alert_count.toLocaleString()}
                  </td>

                  {/* Match rate */}
                  <td className="px-2 py-2">
                    <div className="flex items-center gap-2">
                      <div className="h-1.5 w-16 rounded bg-gray-200 dark:bg-gray-700">
                        <div
                          className={`h-1.5 rounded ${
                            (src.match_rate_pct ?? 0) >= 10
                              ? "bg-green-500"
                              : (src.match_rate_pct ?? 0) >= 3
                                ? "bg-yellow-500"
                                : "bg-red-400"
                          }`}
                          style={{
                            width: `${Math.min(src.match_rate_pct ?? 0, 100)}%`,
                          }}
                        />
                      </div>
                      <span className="text-xs text-gray-600 dark:text-gray-400">
                        {pct(src.match_rate_pct)}
                      </span>
                    </div>
                  </td>

                  {/* Avg confidence */}
                  <td className="px-2 py-2 text-gray-700 dark:text-gray-300">
                    {src.avg_confidence != null
                      ? src.avg_confidence.toFixed(2)
                      : "--"}
                  </td>

                  {/* Severity breakdown */}
                  <td className="px-2 py-2">
                    <div className="flex flex-wrap gap-1">
                      {Object.entries(src.severity_breakdown || {}).map(
                        ([sev, count]) =>
                          count > 0 ? (
                            <span
                              key={sev}
                              className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${severityColor(
                                sev
                              )}`}
                            >
                              {sev[0].toUpperCase()}:{count}
                            </span>
                          ) : null
                      )}
                    </div>
                  </td>

                  {/* Error count */}
                  <td className="px-2 py-2">
                    {src.error_count > 0 ? (
                      <span className="rounded bg-red-100 px-1.5 py-0.5 text-xs font-medium text-red-700 dark:bg-red-900/30 dark:text-red-400">
                        {src.error_count}
                      </span>
                    ) : (
                      <span className="text-xs text-gray-400">0</span>
                    )}
                  </td>

                  {/* Tags */}
                  <td className="px-2 py-2">
                    <div className="flex flex-wrap gap-1">
                      {(src.tags || []).map((tag) => (
                        <span
                          key={tag}
                          className="group inline-flex items-center gap-0.5 rounded bg-gold-100 px-1.5 py-0.5 text-[10px] font-medium text-gold-800 dark:bg-gold-900/30 dark:text-gold-300"
                        >
                          {tag}
                          <button
                            onClick={() => onRemoveTag(src.id, tag)}
                            disabled={tagLoading === `${src.id}_${tag}`}
                            className="mr-0.5 hidden text-gold-600 hover:text-red-500 group-hover:inline dark:text-gold-400"
                            title="حذف برچسب"
                          >
                            {tagLoading === `${src.id}_${tag}` ? "..." : "\u00D7"}
                          </button>
                        </span>
                      ))}
                    </div>
                  </td>
                </tr>
              ))}
              {sorted.length === 0 && (
                <tr>
                  <td
                    colSpan={10}
                    className="px-4 py-8 text-center text-sm text-gray-400"
                  >
                    منبعی یافت نشد
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════════
   Tab 2: Coverage (پوشش)
   ══════════════════════════════════════════════════════════════════════ */

function CoverageTab({ coverage }: { coverage: CoverageData | null }) {
  if (!coverage) {
    return (
      <p className="text-sm text-gray-500 dark:text-gray-400">
        داده‌ای دریافت نشد
      </p>
    );
  }

  return (
    <div className="space-y-6">
      {/* Uncategorized warning */}
      {coverage.uncategorized_pct != null && coverage.uncategorized_pct > 5 && (
        <div className="flex items-center gap-3 rounded-lg border border-yellow-300 bg-yellow-50 p-4 dark:border-yellow-700 dark:bg-yellow-900/20">
          <span className="text-lg text-yellow-600 dark:text-yellow-400">
            &#x26A0;
          </span>
          <div>
            <p className="text-sm font-medium text-yellow-800 dark:text-yellow-300">
              {coverage.uncategorized_pct.toFixed(1)}% از هشدارها بدون دسته‌بندی
              هستند
            </p>
            <p className="text-xs text-yellow-600 dark:text-yellow-400">
              دسته‌بندی قوانین YAML را بررسی کنید
            </p>
          </div>
        </div>
      )}

      {/* Missing buckets */}
      {coverage.missing_buckets && coverage.missing_buckets.length > 0 && (
        <Card title="حوزه‌های بدون پوشش">
          <div className="flex flex-wrap gap-2">
            {coverage.missing_buckets.map((bucket) => (
              <span
                key={bucket}
                className="rounded-lg border border-red-200 bg-red-50 px-3 py-1.5 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-400"
              >
                {bucket}
              </span>
            ))}
          </div>
        </Card>
      )}

      {/* Charts grid */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* By category */}
        {coverage.by_category && coverage.by_category.length > 0 && (
          <Card title="بر اساس دسته‌بندی">
            <HorizontalBarChart items={coverage.by_category} />
          </Card>
        )}

        {/* By direction */}
        {coverage.by_direction && coverage.by_direction.length > 0 && (
          <Card title="بر اساس جهت">
            <HorizontalBarChart
              items={coverage.by_direction}
              colorFn={(label) => impactColor(label)}
            />
          </Card>
        )}

        {/* By severity */}
        {coverage.by_severity && coverage.by_severity.length > 0 && (
          <Card title="بر اساس شدت">
            <HorizontalBarChart
              items={coverage.by_severity}
              colorFn={(label) => {
                switch (label) {
                  case "critical":
                    return "bg-red-600";
                  case "high":
                    return "bg-red-400";
                  case "medium":
                    return "bg-yellow-500";
                  case "low":
                    return "bg-gray-400";
                  default:
                    return "bg-gray-400";
                }
              }}
            />
          </Card>
        )}

        {/* By news type */}
        {coverage.by_news_type && coverage.by_news_type.length > 0 && (
          <Card title="بر اساس نوع خبر">
            <HorizontalBarChart items={coverage.by_news_type} />
          </Card>
        )}
      </div>

      {/* By source (full width) */}
      {coverage.by_source && coverage.by_source.length > 0 && (
        <Card title="بر اساس منبع">
          <HorizontalBarChart items={coverage.by_source} />
        </Card>
      )}
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════════
   Tab 3: Dedupe (تکراری‌ها)
   ══════════════════════════════════════════════════════════════════════ */

function DedupeTab({ dedupe }: { dedupe: DedupeData | null }) {
  if (!dedupe) {
    return (
      <p className="text-sm text-gray-500 dark:text-gray-400">
        داده‌ای دریافت نشد
      </p>
    );
  }

  const dedupeRatePct = dedupe.overall_dedup_rate_pct ?? 0;
  const dedupeColor =
    dedupeRatePct > 70
      ? "text-red-600 dark:text-red-400"
      : dedupeRatePct > 40
        ? "text-yellow-600 dark:text-yellow-400"
        : "text-green-600 dark:text-green-400";

  return (
    <div className="space-y-6">
      {/* Summary */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatBox label="آیتم خام" value={dedupe.total_raw_items} />
        <StatBox label="هشدار نهایی" value={dedupe.total_alerts} />
        <div className="rounded-lg bg-gray-50 p-3 text-center dark:bg-gray-800">
          <div className={`text-xl font-bold ${dedupeColor}`}>
            {pct(dedupe.overall_dedup_rate_pct)}
          </div>
          <div className="text-xs text-gray-500 dark:text-gray-400">
            نرخ حذف تکراری
          </div>
        </div>
        <StatBox
          label="برخورد بین‌منبعی"
          value={dedupe.cross_source_collisions?.length ?? 0}
        />
      </div>

      {/* Overall dedup rate bar */}
      <Card title="نرخ کلی حذف تکراری">
        <div className="space-y-2">
          <div className="h-6 w-full rounded-lg bg-gray-200 dark:bg-gray-700">
            <div
              className={`flex h-6 items-center justify-center rounded-lg text-xs font-bold text-white ${
                dedupeRatePct > 70
                  ? "bg-red-500"
                  : dedupeRatePct > 40
                    ? "bg-yellow-500"
                    : "bg-green-500"
              }`}
              style={{ width: `${Math.max(dedupeRatePct, 3)}%` }}
            >
              {dedupeRatePct > 10 ? pct(dedupe.overall_dedup_rate_pct) : ""}
            </div>
          </div>
          <div className="flex justify-between text-xs text-gray-400">
            <span>0% (بدون تکرار)</span>
            <span>100% (همه تکراری)</span>
          </div>
        </div>
      </Card>

      {/* Dedupe layers */}
      {dedupe.dedupe_layers && dedupe.dedupe_layers.length > 0 && (
        <Card title="لایه‌های حذف تکراری">
          <div className="space-y-3">
            {dedupe.dedupe_layers.map((layer, idx) => (
              <div
                key={idx}
                className="flex items-center justify-between rounded-lg border border-gray-200 p-3 dark:border-gray-700"
              >
                <div className="flex-1">
                  <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                    {layer.layer}
                  </p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    {layer.description}
                  </p>
                </div>
                <div className="mr-3 text-left">
                  <span className="rounded bg-blue-100 px-2 py-1 text-sm font-bold text-blue-700 dark:bg-blue-900/30 dark:text-blue-400">
                    {layer.duplicates_caught.toLocaleString()}
                  </span>
                  <div className="mt-0.5 text-[10px] text-gray-400">
                    تکراری
                  </div>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Cross-source collisions */}
        {dedupe.cross_source_collisions &&
          dedupe.cross_source_collisions.length > 0 && (
            <Card title="برخوردهای بین‌منبعی">
              <div className="max-h-72 overflow-y-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-200 text-gray-500 dark:border-gray-700 dark:text-gray-400">
                      <th className="px-2 py-2 text-right">هش</th>
                      <th className="px-2 py-2 text-right">منابع</th>
                      <th className="px-2 py-2 text-right">تعداد</th>
                    </tr>
                  </thead>
                  <tbody>
                    {dedupe.cross_source_collisions.map((col, idx) => (
                      <tr
                        key={idx}
                        className="border-b border-gray-100 dark:border-gray-800"
                      >
                        <td className="px-2 py-1.5 font-mono text-xs text-gray-600 dark:text-gray-400">
                          {col.hash?.slice(0, 12) ?? "--"}...
                        </td>
                        <td className="px-2 py-1.5">
                          <div className="flex flex-wrap gap-1">
                            {col.sources.map((s) => (
                              <span
                                key={s}
                                className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] dark:bg-gray-700"
                              >
                                {s}
                              </span>
                            ))}
                          </div>
                        </td>
                        <td className="px-2 py-1.5 font-medium text-gray-900 dark:text-gray-100">
                          {col.count}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}

        {/* High waste sources */}
        {dedupe.high_waste_sources && dedupe.high_waste_sources.length > 0 && (
          <Card title="منابع پر اتلاف">
            <div className="space-y-3">
              {dedupe.high_waste_sources.map((src) => (
                <div
                  key={src.source_id}
                  className="rounded-lg border border-red-200 p-3 dark:border-red-800"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                      {src.source_name}
                    </span>
                    <span className="rounded bg-red-100 px-2 py-0.5 text-xs font-bold text-red-700 dark:bg-red-900/30 dark:text-red-400">
                      {src.waste_pct.toFixed(1)}% اتلاف
                    </span>
                  </div>
                  <div className="mt-2 h-2 w-full rounded bg-gray-200 dark:bg-gray-700">
                    <div
                      className="h-2 rounded bg-red-400"
                      style={{
                        width: `${Math.min(src.waste_pct, 100)}%`,
                      }}
                    />
                  </div>
                  <div className="mt-1 flex justify-between text-xs text-gray-500 dark:text-gray-400">
                    <span>
                      خام: {src.raw_count.toLocaleString()}
                    </span>
                    <span>
                      تکراری: {src.duplicate_count.toLocaleString()}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════════
   Tab 4: Recommendations (توصیه‌ها)
   ══════════════════════════════════════════════════════════════════════ */

function RecommendationsTab({
  recommendations,
}: {
  recommendations: RecommendationsData | null;
}) {
  if (!recommendations) {
    return (
      <p className="text-sm text-gray-500 dark:text-gray-400">
        داده‌ای دریافت نشد
      </p>
    );
  }

  const items = recommendations.recommendations ?? [];

  if (items.length === 0) {
    return (
      <Card>
        <div className="py-8 text-center">
          <p className="text-lg font-medium text-green-600 dark:text-green-400">
            همه چیز خوب به نظر می‌رسد!
          </p>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            در حال حاضر توصیه‌ای برای بهبود وجود ندارد
          </p>
        </div>
      </Card>
    );
  }

  return (
    <div className="space-y-3">
      {items.map((rec, idx) => (
        <div
          key={idx}
          className="card flex gap-4 p-4"
        >
          {/* Number */}
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gold-100 text-sm font-bold text-gold-800 dark:bg-gold-900/30 dark:text-gold-300">
            {idx + 1}
          </div>

          {/* Content */}
          <div className="min-w-0 flex-1">
            {/* Badges row */}
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <span
                className={`rounded px-2 py-0.5 text-xs font-medium ${typeBadge(
                  rec.type
                )}`}
              >
                {rec.type}
              </span>
              <span
                className={`rounded px-2 py-0.5 text-xs font-medium ${priorityBadge(
                  rec.priority
                )}`}
              >
                {rec.priority === "high"
                  ? "اولویت بالا"
                  : rec.priority === "medium"
                    ? "اولویت متوسط"
                    : "اولویت پایین"}
              </span>
              {rec.source_name && (
                <span className="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-600 dark:bg-gray-700 dark:text-gray-400">
                  {rec.source_name}
                </span>
              )}
            </div>

            {/* Title */}
            <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              {rec.title_fa || rec.title}
            </h4>

            {/* Description */}
            <p className="mt-1 text-sm leading-relaxed text-gray-600 dark:text-gray-400">
              {rec.description_fa || rec.description}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}
