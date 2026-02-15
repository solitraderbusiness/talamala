"use client";

import { useEffect, useState, useCallback } from "react";
import { getToken } from "@/lib/auth";
import {
  getLabelQueue,
  submitLabel,
  getLabelStats,
  getDisagreements,
  getCalibration,
  getOutliers,
  getProvenance,
} from "@/lib/api";

/* ── Types ─────────────────────────────────────────────────────────── */

interface QueueAlert {
  id: string;
  title: string;
  summary_fa: string;
  severity: string;
  direction: string | null;
  direction_confidence: number | null;
  alert_score: number | null;
  created_at: string;
  source_name: string;
  matched_rule_ids: string[];
}

interface LabelQueueResponse {
  queue: QueueAlert[];
  total_unlabeled: number;
  total_labeled: number;
}

interface ConfusionCell {
  actual: string;
  predicted: string;
  count: number;
}

interface DirectionBreakdown {
  direction: string;
  total: number;
  correct: number;
  accuracy_pct: number | null;
}

interface LabelStatsResponse {
  total_labels: number;
  confusion_matrix: ConfusionCell[];
  accuracy: number | null;
  macro_f1: number | null;
  direction_breakdown: DirectionBreakdown[];
  avg_intensity: number | null;
  avg_relevance: number | null;
}

interface DisagreementItem {
  alert_id: string;
  alert_title: string;
  system_direction: string | null;
  ref_direction: string | null;
  ref_reasoning: string | null;
  created_at: string;
}

interface DisagreementsResponse {
  total_scored: number;
  total_disagreements: number;
  disagreement_rate_pct: number | null;
  items: DisagreementItem[];
}

interface CalibrationBin {
  direction: string;
  severity: string;
  count: number;
  avg_return_30min: number | null;
  avg_return_1h: number | null;
  avg_return_4h: number | null;
  avg_return_24h: number | null;
  accuracy_24h: number | null;
}

interface CalibrationResponse {
  total_with_outcomes: number;
  bins: CalibrationBin[];
  overall_accuracy_24h: number | null;
}

interface OutlierItem {
  alert_id: string;
  alert_title: string;
  direction: string | null;
  severity: string | null;
  change_pct_24h: number | null;
  expected_direction: string | null;
  created_at: string;
}

interface OutliersResponse {
  total: number;
  items: OutlierItem[];
}

interface ProvenanceData {
  alert: {
    id: string;
    title: string;
    severity: string;
    direction: string | null;
    direction_confidence: number | null;
    direction_method: string | null;
    alert_score: number | null;
    confidence: number | null;
    matched_rule_ids: string[];
    match_evidence: Record<string, unknown>;
    created_at: string;
    source_name: string;
  } | null;
  raw_item: {
    id: string;
    title: string;
    content_snippet: string | null;
    source_url: string | null;
    fetched_at: string | null;
  } | null;
  human_label: {
    direction_label: string;
    intensity: number;
    relevance: number;
    notes: string | null;
    labeled_at: string | null;
  } | null;
  reference_score: {
    direction: string | null;
    confidence: number | null;
    reasoning: string | null;
    model: string | null;
    scored_at: string | null;
  } | null;
  outcome: {
    status: string;
    change_pct_30min: number | null;
    change_pct_1h: number | null;
    change_pct_4h: number | null;
    change_pct_24h: number | null;
    change_pct_48h: number | null;
    change_pct_7d: number | null;
  } | null;
  market_snapshot: {
    xauusd: number | null;
    dxy: number | null;
    gold_rsi_14: number | null;
    sentiment_composite: number | null;
    snapshot_complete: boolean;
  } | null;
}

/* ── Constants ─────────────────────────────────────────────────────── */

const TABS = [
  { id: "labeling", label: "برچسب\u200Cگذاری" },
  { id: "accuracy", label: "آمار دقت" },
  { id: "disagreements", label: "اختلاف\u200Cنظرها" },
  { id: "calibration", label: "کالیبراسیون" },
  { id: "outliers", label: "پیش\u200Cبینی\u200Cها" },
] as const;

type TabId = (typeof TABS)[number]["id"];

const DIRECTION_OPTIONS = [
  { value: "positive", label: "صعودی (مثبت)", color: "text-green-600 dark:text-green-400", bg: "bg-green-50 dark:bg-green-900/20 border-green-300 dark:border-green-700" },
  { value: "negative", label: "نزولی (منفی)", color: "text-red-600 dark:text-red-400", bg: "bg-red-50 dark:bg-red-900/20 border-red-300 dark:border-red-700" },
  { value: "neutral", label: "خنثی", color: "text-gray-600 dark:text-gray-400", bg: "bg-gray-50 dark:bg-gray-800 border-gray-300 dark:border-gray-600" },
];

const DIRECTIONS_ALL = ["positive", "negative", "neutral"];

/* ── Helpers ───────────────────────────────────────────────────────── */

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

function directionColor(dir: string | null | undefined): string {
  if (!dir) return "text-gray-500";
  if (dir === "positive" || dir === "bullish") return "text-green-600 dark:text-green-400";
  if (dir === "negative" || dir === "bearish") return "text-red-600 dark:text-red-400";
  return "text-gray-500 dark:text-gray-400";
}

function directionBg(dir: string | null | undefined): string {
  if (!dir) return "bg-gray-100 dark:bg-gray-800";
  if (dir === "positive" || dir === "bullish") return "bg-green-100 dark:bg-green-900/30";
  if (dir === "negative" || dir === "bearish") return "bg-red-100 dark:bg-red-900/30";
  return "bg-gray-100 dark:bg-gray-800";
}

function directionLabel(dir: string | null | undefined): string {
  if (!dir) return "نامشخص";
  if (dir === "positive" || dir === "bullish") return "صعودی";
  if (dir === "negative" || dir === "bearish") return "نزولی";
  return "خنثی";
}

function severityBadge(sev: string | null | undefined): string {
  if (!sev) return "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400";
  if (sev === "critical") return "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400";
  if (sev === "high") return "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400";
  if (sev === "medium") return "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400";
  return "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400";
}

function formatPct(val: number | null | undefined): string {
  if (val == null) return "--";
  return `${val >= 0 ? "+" : ""}${val.toFixed(3)}%`;
}

/* ── Main Page ─────────────────────────────────────────────────────── */

export default function SentimentQAPage() {
  const [activeTab, setActiveTab] = useState<TabId>("labeling");

  // Provenance drawer
  const [provenanceOpen, setProvenanceOpen] = useState(false);
  const [provenanceAlertId, setProvenanceAlertId] = useState<string | null>(null);
  const [provenanceData, setProvenanceData] = useState<ProvenanceData | null>(null);
  const [provenanceLoading, setProvenanceLoading] = useState(false);

  const openProvenance = useCallback(async (alertId: string) => {
    setProvenanceAlertId(alertId);
    setProvenanceOpen(true);
    setProvenanceLoading(true);
    setProvenanceData(null);
    const token = getToken();
    if (!token) return;
    try {
      const data = await getProvenance(token, alertId);
      setProvenanceData(data);
    } catch {
      // silently fail
    } finally {
      setProvenanceLoading(false);
    }
  }, []);

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">
        کنترل کیفیت سنتیمنت
      </h2>

      {/* Tabs */}
      <div className="flex gap-1 overflow-x-auto border-b border-gray-200 dark:border-gray-700">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`whitespace-nowrap px-4 py-2.5 text-sm font-medium transition-colors ${
              activeTab === tab.id
                ? "border-b-2 border-gold-500 text-gold-700 dark:text-gold-400"
                : "text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {activeTab === "labeling" && <LabelingTab onProvenance={openProvenance} />}
      {activeTab === "accuracy" && <AccuracyTab />}
      {activeTab === "disagreements" && <DisagreementsTab onProvenance={openProvenance} />}
      {activeTab === "calibration" && <CalibrationTab />}
      {activeTab === "outliers" && <OutliersTab onProvenance={openProvenance} />}

      {/* Provenance Drawer */}
      <ProvenanceDrawer
        open={provenanceOpen}
        alertId={provenanceAlertId}
        data={provenanceData}
        loading={provenanceLoading}
        onClose={() => setProvenanceOpen(false)}
      />
    </div>
  );
}

/* ── Tab 1: Labeling ───────────────────────────────────────────────── */

function LabelingTab({ onProvenance }: { onProvenance: (id: string) => void }) {
  const [data, setData] = useState<LabelQueueResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState<string | null>(null);
  const [forms, setForms] = useState<
    Record<string, { direction_label: string; intensity: number; relevance: number; notes: string }>
  >({});
  const [submitSuccess, setSubmitSuccess] = useState<string | null>(null);

  const fetchQueue = useCallback(async () => {
    const token = getToken();
    if (!token) return;
    setLoading(true);
    try {
      const result = await getLabelQueue(token, 20);
      setData(result);
      // Initialize forms for each alert
      const newForms: typeof forms = {};
      for (const alert of result.queue) {
        if (!forms[alert.id]) {
          newForms[alert.id] = { direction_label: "", intensity: 3, relevance: 3, notes: "" };
        } else {
          newForms[alert.id] = forms[alert.id];
        }
      }
      setForms((prev) => ({ ...newForms, ...prev }));
    } catch {
      // silently fail
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    fetchQueue();
  }, [fetchQueue]);

  const handleSubmit = async (alertId: string) => {
    const form = forms[alertId];
    if (!form || !form.direction_label) return;
    const token = getToken();
    if (!token) return;

    setSubmitting(alertId);
    try {
      await submitLabel(token, {
        alert_id: alertId,
        direction_label: form.direction_label,
        intensity: form.intensity,
        relevance: form.relevance,
        notes: form.notes || undefined,
      });
      setSubmitSuccess(alertId);
      setTimeout(() => {
        setSubmitSuccess(null);
        fetchQueue();
      }, 1200);
    } catch {
      // silently fail
    } finally {
      setSubmitting(null);
    }
  };

  const updateForm = (alertId: string, field: string, value: string | number) => {
    setForms((prev) => ({
      ...prev,
      [alertId]: { ...prev[alertId], [field]: value },
    }));
  };

  if (loading && !data) {
    return (
      <div className="flex min-h-[30vh] items-center justify-center">
        <div className="h-10 w-10 animate-spin rounded-full border-4 border-gold-500 border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Stats bar */}
      <div className="flex flex-wrap gap-4">
        <div className="card flex items-center gap-3 px-4 py-3">
          <div className="text-2xl font-bold text-gold-600 dark:text-gold-400">
            {data?.total_labeled ?? 0}
          </div>
          <div className="text-sm text-gray-500 dark:text-gray-400">برچسب\u200Cگذاری شده</div>
        </div>
        <div className="card flex items-center gap-3 px-4 py-3">
          <div className="text-2xl font-bold text-gray-900 dark:text-gray-100">
            {data?.total_unlabeled ?? 0}
          </div>
          <div className="text-sm text-gray-500 dark:text-gray-400">در انتظار</div>
        </div>
      </div>

      {/* Queue */}
      {data?.queue.length === 0 ? (
        <div className="card p-8 text-center text-gray-500 dark:text-gray-400">
          همه هشدارها برچسب\u200Cگذاری شده\u200Cاند
        </div>
      ) : (
        <div className="space-y-4">
          {data?.queue.map((alert) => {
            const form = forms[alert.id] || { direction_label: "", intensity: 3, relevance: 3, notes: "" };
            const isSuccess = submitSuccess === alert.id;
            return (
              <div
                key={alert.id}
                className={`card p-5 transition-all ${isSuccess ? "border-green-400 bg-green-50 dark:border-green-700 dark:bg-green-900/20" : ""}`}
              >
                {/* Alert header */}
                <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
                  <div className="flex-1">
                    <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                      {alert.title}
                    </h3>
                    <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                      {alert.source_name}
                      {" \u2022 "}
                      {alert.created_at ? formatTimeAgo(alert.created_at) : ""}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`rounded px-2 py-0.5 text-xs font-medium ${severityBadge(alert.severity)}`}>
                      {alert.severity}
                    </span>
                    {alert.direction && (
                      <span className={`rounded px-2 py-0.5 text-xs font-medium ${directionBg(alert.direction)} ${directionColor(alert.direction)}`}>
                        {directionLabel(alert.direction)}
                      </span>
                    )}
                    <button
                      onClick={() => onProvenance(alert.id)}
                      className="rounded px-2 py-0.5 text-xs text-gold-600 hover:bg-gold-50 dark:text-gold-400 dark:hover:bg-gold-900/20"
                      title="مشاهده زنجیره اثبات"
                    >
                      &#x1F50D;
                    </button>
                  </div>
                </div>

                {alert.summary_fa && (
                  <p className="mb-4 text-sm leading-relaxed text-gray-700 dark:text-gray-300">
                    {alert.summary_fa}
                  </p>
                )}

                {isSuccess ? (
                  <div className="py-3 text-center text-sm font-medium text-green-600 dark:text-green-400">
                    &#10003; ثبت شد
                  </div>
                ) : (
                  <div className="space-y-4 rounded-lg border border-gray-200 bg-gray-50 p-4 dark:border-gray-700 dark:bg-gray-800/50">
                    {/* Direction radio buttons */}
                    <div>
                      <label className="mb-2 block text-xs font-medium text-gray-600 dark:text-gray-400">
                        جهت بازار
                      </label>
                      <div className="flex flex-wrap gap-2">
                        {DIRECTION_OPTIONS.map((opt) => (
                          <button
                            key={opt.value}
                            onClick={() => updateForm(alert.id, "direction_label", opt.value)}
                            className={`rounded-lg border-2 px-4 py-2 text-sm font-medium transition-all ${
                              form.direction_label === opt.value
                                ? `${opt.bg} ring-2 ring-gold-400 dark:ring-gold-600`
                                : "border-gray-200 bg-white hover:border-gray-300 dark:border-gray-700 dark:bg-gray-800 dark:hover:border-gray-600"
                            } ${opt.color}`}
                          >
                            {opt.label}
                          </button>
                        ))}
                      </div>
                    </div>

                    {/* Sliders row */}
                    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                      {/* Intensity */}
                      <div>
                        <label className="mb-1 flex items-center justify-between text-xs font-medium text-gray-600 dark:text-gray-400">
                          <span>شدت تاثیر</span>
                          <span className="font-bold text-gray-900 dark:text-gray-100">{form.intensity}</span>
                        </label>
                        <input
                          type="range"
                          min={1}
                          max={5}
                          step={1}
                          value={form.intensity}
                          onChange={(e) => updateForm(alert.id, "intensity", Number(e.target.value))}
                          className="w-full accent-gold-500"
                        />
                        <div className="flex justify-between text-[10px] text-gray-400">
                          <span>1 - ناچیز</span>
                          <span>5 - بسیار زیاد</span>
                        </div>
                      </div>

                      {/* Relevance */}
                      <div>
                        <label className="mb-1 flex items-center justify-between text-xs font-medium text-gray-600 dark:text-gray-400">
                          <span>ارتباط با طلا</span>
                          <span className="font-bold text-gray-900 dark:text-gray-100">{form.relevance}</span>
                        </label>
                        <input
                          type="range"
                          min={1}
                          max={5}
                          step={1}
                          value={form.relevance}
                          onChange={(e) => updateForm(alert.id, "relevance", Number(e.target.value))}
                          className="w-full accent-gold-500"
                        />
                        <div className="flex justify-between text-[10px] text-gray-400">
                          <span>1 - بی\u200Cربط</span>
                          <span>5 - مستقیم</span>
                        </div>
                      </div>
                    </div>

                    {/* Notes */}
                    <div>
                      <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">
                        یادداشت (اختیاری)
                      </label>
                      <textarea
                        value={form.notes}
                        onChange={(e) => updateForm(alert.id, "notes", e.target.value)}
                        rows={2}
                        className="input-field resize-none text-sm"
                        placeholder="توضیح اضافی..."
                      />
                    </div>

                    {/* Submit */}
                    <div className="flex justify-end">
                      <button
                        onClick={() => handleSubmit(alert.id)}
                        disabled={!form.direction_label || submitting === alert.id}
                        className="btn-primary text-sm disabled:cursor-not-allowed"
                      >
                        {submitting === alert.id ? (
                          <span className="flex items-center gap-2">
                            <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                            ثبت...
                          </span>
                        ) : (
                          "ثبت برچسب"
                        )}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/* ── Tab 2: Accuracy Stats ─────────────────────────────────────────── */

function AccuracyTab() {
  const [data, setData] = useState<LabelStatsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(30);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    setLoading(true);
    getLabelStats(token, days)
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [days]);

  if (loading && !data) {
    return (
      <div className="flex min-h-[30vh] items-center justify-center">
        <div className="h-10 w-10 animate-spin rounded-full border-4 border-gold-500 border-t-transparent" />
      </div>
    );
  }

  if (!data) {
    return <div className="card p-8 text-center text-gray-500 dark:text-gray-400">داده\u200Cای موجود نیست</div>;
  }

  // Build confusion matrix grid
  const matrixMap: Record<string, Record<string, number>> = {};
  for (const dir of DIRECTIONS_ALL) {
    matrixMap[dir] = {};
    for (const dir2 of DIRECTIONS_ALL) {
      matrixMap[dir][dir2] = 0;
    }
  }
  for (const cell of data.confusion_matrix) {
    if (matrixMap[cell.actual] !== undefined) {
      matrixMap[cell.actual][cell.predicted] = cell.count;
    }
  }

  return (
    <div className="space-y-6">
      {/* Period selector */}
      <div className="flex items-center gap-2">
        <span className="text-sm text-gray-500 dark:text-gray-400">بازه:</span>
        {[7, 30, 90].map((d) => (
          <button
            key={d}
            onClick={() => setDays(d)}
            className={`rounded-lg px-3 py-1 text-sm ${
              days === d
                ? "bg-gold-500 text-white"
                : "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400"
            }`}
          >
            {d} روز
          </button>
        ))}
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div className="card p-4 text-center">
          <div className="text-2xl font-bold text-gray-900 dark:text-gray-100">{data.total_labels}</div>
          <div className="text-xs text-gray-500 dark:text-gray-400">کل برچسب\u200Cها</div>
        </div>
        <div className="card p-4 text-center">
          <div className={`text-2xl font-bold ${(data.accuracy ?? 0) >= 70 ? "text-green-600 dark:text-green-400" : (data.accuracy ?? 0) >= 50 ? "text-yellow-600 dark:text-yellow-400" : "text-red-600 dark:text-red-400"}`}>
            {data.accuracy != null ? `${data.accuracy.toFixed(1)}%` : "--"}
          </div>
          <div className="text-xs text-gray-500 dark:text-gray-400">دقت (Accuracy)</div>
        </div>
        <div className="card p-4 text-center">
          <div className="text-2xl font-bold text-gray-900 dark:text-gray-100">
            {data.macro_f1 != null ? `${data.macro_f1.toFixed(1)}%` : "--"}
          </div>
          <div className="text-xs text-gray-500 dark:text-gray-400">Macro F1</div>
        </div>
        <div className="card p-4 text-center">
          <div className="flex justify-center gap-3 text-sm">
            <span className="text-gray-600 dark:text-gray-400">
              شدت: <strong className="text-gray-900 dark:text-gray-100">{data.avg_intensity?.toFixed(1) ?? "--"}</strong>
            </span>
            <span className="text-gray-600 dark:text-gray-400">
              ارتباط: <strong className="text-gray-900 dark:text-gray-100">{data.avg_relevance?.toFixed(1) ?? "--"}</strong>
            </span>
          </div>
          <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">میانگین شدت / ارتباط</div>
        </div>
      </div>

      {/* Confusion Matrix */}
      <div className="card p-5">
        <h3 className="mb-4 text-sm font-semibold text-gray-900 dark:text-gray-100">
          ماتریس اشتباه (سیستم در مقابل انسان)
        </h3>
        <div className="overflow-x-auto">
          <table className="mx-auto text-sm">
            <thead>
              <tr>
                <th className="px-3 py-2 text-xs text-gray-400" />
                <th colSpan={3} className="px-3 py-2 text-center text-xs font-medium text-gray-500 dark:text-gray-400">
                  پیش\u200Cبینی سیستم
                </th>
              </tr>
              <tr>
                <th className="px-3 py-2 text-xs text-gray-400" />
                {DIRECTIONS_ALL.map((d) => (
                  <th key={d} className={`px-3 py-2 text-center text-xs font-medium ${directionColor(d)}`}>
                    {directionLabel(d)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {DIRECTIONS_ALL.map((actual, ri) => (
                <tr key={actual}>
                  <td className={`px-3 py-2 text-xs font-medium ${directionColor(actual)}`}>
                    {ri === 0 && (
                      <span className="absolute -mr-12 rotate-0 text-[10px] text-gray-400">
                      </span>
                    )}
                    {directionLabel(actual)}
                  </td>
                  {DIRECTIONS_ALL.map((predicted) => {
                    const count = matrixMap[actual]?.[predicted] ?? 0;
                    const isDiagonal = actual === predicted;
                    const maxVal = Math.max(
                      1,
                      ...data.confusion_matrix.map((c) => c.count)
                    );
                    const intensity = count / maxVal;
                    let cellBg = "";
                    if (isDiagonal) {
                      cellBg = `rgba(34, 197, 94, ${Math.max(0.1, intensity * 0.6)})`;
                    } else if (count > 0) {
                      cellBg = `rgba(239, 68, 68, ${Math.max(0.1, intensity * 0.5)})`;
                    }
                    return (
                      <td
                        key={predicted}
                        className={`px-3 py-2 text-center font-mono text-sm ${isDiagonal ? "font-bold" : ""}`}
                        style={cellBg ? { backgroundColor: cellBg } : undefined}
                      >
                        {count}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-2 flex justify-center gap-6 text-[10px] text-gray-400">
            <span>ردیف\u200Cها: برچسب انسان</span>
            <span>ستون\u200Cها: پیش\u200Cبینی سیستم</span>
          </div>
        </div>
      </div>

      {/* Direction Breakdown */}
      <div className="card p-5">
        <h3 className="mb-4 text-sm font-semibold text-gray-900 dark:text-gray-100">
          دقت به تفکیک جهت
        </h3>
        <div className="space-y-3">
          {data.direction_breakdown.map((item) => (
            <div key={item.direction} className="flex items-center gap-3">
              <div className={`w-16 text-sm font-medium ${directionColor(item.direction)}`}>
                {directionLabel(item.direction)}
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <div className="h-3 flex-1 rounded-full bg-gray-200 dark:bg-gray-700">
                    <div
                      className={`h-3 rounded-full ${
                        item.direction === "positive" ? "bg-green-500" : item.direction === "negative" ? "bg-red-500" : "bg-gray-400"
                      }`}
                      style={{ width: `${Math.min(item.accuracy_pct ?? 0, 100)}%` }}
                    />
                  </div>
                  <span className="w-14 text-left text-xs font-medium text-gray-700 dark:text-gray-300">
                    {item.accuracy_pct != null ? `${item.accuracy_pct.toFixed(0)}%` : "--"}
                  </span>
                </div>
              </div>
              <div className="text-xs text-gray-500 dark:text-gray-400">
                {item.correct}/{item.total}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ── Tab 3: Disagreements ──────────────────────────────────────────── */

function DisagreementsTab({ onProvenance }: { onProvenance: (id: string) => void }) {
  const [data, setData] = useState<DisagreementsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(7);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    setLoading(true);
    getDisagreements(token, days)
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [days]);

  if (loading && !data) {
    return (
      <div className="flex min-h-[30vh] items-center justify-center">
        <div className="h-10 w-10 animate-spin rounded-full border-4 border-gold-500 border-t-transparent" />
      </div>
    );
  }

  if (!data) {
    return <div className="card p-8 text-center text-gray-500 dark:text-gray-400">داده\u200Cای موجود نیست</div>;
  }

  return (
    <div className="space-y-4">
      {/* Period selector */}
      <div className="flex items-center gap-2">
        <span className="text-sm text-gray-500 dark:text-gray-400">بازه:</span>
        {[3, 7, 14, 30].map((d) => (
          <button
            key={d}
            onClick={() => setDays(d)}
            className={`rounded-lg px-3 py-1 text-sm ${
              days === d
                ? "bg-gold-500 text-white"
                : "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400"
            }`}
          >
            {d} روز
          </button>
        ))}
      </div>

      {/* Summary */}
      <div className="grid grid-cols-3 gap-4">
        <div className="card p-4 text-center">
          <div className="text-2xl font-bold text-gray-900 dark:text-gray-100">{data.total_scored}</div>
          <div className="text-xs text-gray-500 dark:text-gray-400">کل ارزیابی\u200Cشده</div>
        </div>
        <div className="card p-4 text-center">
          <div className="text-2xl font-bold text-red-600 dark:text-red-400">{data.total_disagreements}</div>
          <div className="text-xs text-gray-500 dark:text-gray-400">اختلاف\u200Cنظر</div>
        </div>
        <div className="card p-4 text-center">
          <div className={`text-2xl font-bold ${(data.disagreement_rate_pct ?? 0) > 30 ? "text-red-600 dark:text-red-400" : (data.disagreement_rate_pct ?? 0) > 15 ? "text-yellow-600 dark:text-yellow-400" : "text-green-600 dark:text-green-400"}`}>
            {data.disagreement_rate_pct != null ? `${data.disagreement_rate_pct.toFixed(1)}%` : "--"}
          </div>
          <div className="text-xs text-gray-500 dark:text-gray-400">نرخ اختلاف</div>
        </div>
      </div>

      {/* Table */}
      {data.items.length === 0 ? (
        <div className="card p-8 text-center text-gray-500 dark:text-gray-400">
          اختلاف\u200Cنظری وجود ندارد
        </div>
      ) : (
        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-800">
                  <th className="px-3 py-2.5 text-right text-xs font-medium text-gray-500 dark:text-gray-400">عنوان هشدار</th>
                  <th className="px-3 py-2.5 text-right text-xs font-medium text-gray-500 dark:text-gray-400">سیستم</th>
                  <th className="px-3 py-2.5 text-right text-xs font-medium text-gray-500 dark:text-gray-400">مرجع</th>
                  <th className="px-3 py-2.5 text-right text-xs font-medium text-gray-500 dark:text-gray-400">استدلال مرجع</th>
                  <th className="px-3 py-2.5 text-right text-xs font-medium text-gray-500 dark:text-gray-400">زمان</th>
                  <th className="px-3 py-2.5 text-center text-xs font-medium text-gray-500 dark:text-gray-400">جزئیات</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((item) => (
                  <tr key={item.alert_id} className="border-b border-gray-100 dark:border-gray-800">
                    <td className="max-w-[200px] truncate px-3 py-2.5 text-gray-900 dark:text-gray-100">
                      {item.alert_title}
                    </td>
                    <td className="px-3 py-2.5">
                      <span className={`rounded px-2 py-0.5 text-xs font-medium ${directionBg(item.system_direction)} ${directionColor(item.system_direction)}`}>
                        {directionLabel(item.system_direction)}
                      </span>
                    </td>
                    <td className="px-3 py-2.5">
                      <span className={`rounded px-2 py-0.5 text-xs font-medium ${directionBg(item.ref_direction)} ${directionColor(item.ref_direction)}`}>
                        {directionLabel(item.ref_direction)}
                      </span>
                    </td>
                    <td className="max-w-[250px] truncate px-3 py-2.5 text-xs text-gray-600 dark:text-gray-400">
                      {item.ref_reasoning ?? "--"}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2.5 text-xs text-gray-500 dark:text-gray-400">
                      {item.created_at ? formatTimeAgo(item.created_at) : "--"}
                    </td>
                    <td className="px-3 py-2.5 text-center">
                      <button
                        onClick={() => onProvenance(item.alert_id)}
                        className="rounded px-2 py-1 text-xs text-gold-600 hover:bg-gold-50 dark:text-gold-400 dark:hover:bg-gold-900/20"
                      >
                        &#x1F50D;
                      </button>
                    </td>
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

/* ── Tab 4: Calibration ────────────────────────────────────────────── */

function CalibrationTab() {
  const [data, setData] = useState<CalibrationResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(90);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    setLoading(true);
    getCalibration(token, days)
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [days]);

  if (loading && !data) {
    return (
      <div className="flex min-h-[30vh] items-center justify-center">
        <div className="h-10 w-10 animate-spin rounded-full border-4 border-gold-500 border-t-transparent" />
      </div>
    );
  }

  if (!data) {
    return <div className="card p-8 text-center text-gray-500 dark:text-gray-400">داده\u200Cای موجود نیست</div>;
  }

  return (
    <div className="space-y-4">
      {/* Period selector */}
      <div className="flex items-center gap-2">
        <span className="text-sm text-gray-500 dark:text-gray-400">بازه:</span>
        {[30, 60, 90, 180].map((d) => (
          <button
            key={d}
            onClick={() => setDays(d)}
            className={`rounded-lg px-3 py-1 text-sm ${
              days === d
                ? "bg-gold-500 text-white"
                : "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400"
            }`}
          >
            {d} روز
          </button>
        ))}
      </div>

      {/* Summary */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        <div className="card p-4 text-center">
          <div className="text-2xl font-bold text-gray-900 dark:text-gray-100">{data.total_with_outcomes}</div>
          <div className="text-xs text-gray-500 dark:text-gray-400">هشدار با نتیجه</div>
        </div>
        <div className="card p-4 text-center">
          <div className={`text-2xl font-bold ${(data.overall_accuracy_24h ?? 0) >= 60 ? "text-green-600 dark:text-green-400" : "text-yellow-600 dark:text-yellow-400"}`}>
            {data.overall_accuracy_24h != null ? `${data.overall_accuracy_24h.toFixed(1)}%` : "--"}
          </div>
          <div className="text-xs text-gray-500 dark:text-gray-400">دقت کل ۲۴ ساعته</div>
        </div>
        <div className="card p-4 text-center">
          <div className="text-2xl font-bold text-gray-900 dark:text-gray-100">{data.bins.length}</div>
          <div className="text-xs text-gray-500 dark:text-gray-400">تعداد گروه\u200Cها</div>
        </div>
      </div>

      {/* Bins Table */}
      {data.bins.length === 0 ? (
        <div className="card p-8 text-center text-gray-500 dark:text-gray-400">
          داده\u200Cای کالیبراسیون موجود نیست
        </div>
      ) : (
        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-800">
                  <th className="px-3 py-2.5 text-right text-xs font-medium text-gray-500 dark:text-gray-400">جهت</th>
                  <th className="px-3 py-2.5 text-right text-xs font-medium text-gray-500 dark:text-gray-400">شدت</th>
                  <th className="px-3 py-2.5 text-right text-xs font-medium text-gray-500 dark:text-gray-400">تعداد</th>
                  <th className="px-3 py-2.5 text-center text-xs font-medium text-gray-500 dark:text-gray-400">بازده ۳۰ دقیقه</th>
                  <th className="px-3 py-2.5 text-center text-xs font-medium text-gray-500 dark:text-gray-400">بازده ۱ ساعت</th>
                  <th className="px-3 py-2.5 text-center text-xs font-medium text-gray-500 dark:text-gray-400">بازده ۴ ساعت</th>
                  <th className="px-3 py-2.5 text-center text-xs font-medium text-gray-500 dark:text-gray-400">بازده ۲۴ ساعت</th>
                  <th className="px-3 py-2.5 text-center text-xs font-medium text-gray-500 dark:text-gray-400">دقت ۲۴ ساعته</th>
                </tr>
              </thead>
              <tbody>
                {data.bins.map((bin, i) => (
                  <tr key={i} className="border-b border-gray-100 dark:border-gray-800">
                    <td className="px-3 py-2.5">
                      <span className={`rounded px-2 py-0.5 text-xs font-medium ${directionBg(bin.direction)} ${directionColor(bin.direction)}`}>
                        {directionLabel(bin.direction)}
                      </span>
                    </td>
                    <td className="px-3 py-2.5">
                      <span className={`rounded px-2 py-0.5 text-xs font-medium ${severityBadge(bin.severity)}`}>
                        {bin.severity}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 text-center text-gray-900 dark:text-gray-100">
                      {bin.count}
                    </td>
                    <td className={`px-3 py-2.5 text-center font-mono text-xs ${returnColor(bin.avg_return_30min, bin.direction)}`}>
                      {formatPct(bin.avg_return_30min)}
                    </td>
                    <td className={`px-3 py-2.5 text-center font-mono text-xs ${returnColor(bin.avg_return_1h, bin.direction)}`}>
                      {formatPct(bin.avg_return_1h)}
                    </td>
                    <td className={`px-3 py-2.5 text-center font-mono text-xs ${returnColor(bin.avg_return_4h, bin.direction)}`}>
                      {formatPct(bin.avg_return_4h)}
                    </td>
                    <td className={`px-3 py-2.5 text-center font-mono text-xs ${returnColor(bin.avg_return_24h, bin.direction)}`}>
                      {formatPct(bin.avg_return_24h)}
                    </td>
                    <td className="px-3 py-2.5 text-center">
                      {bin.accuracy_24h != null ? (
                        <span className={`font-medium ${bin.accuracy_24h >= 60 ? "text-green-600 dark:text-green-400" : bin.accuracy_24h >= 40 ? "text-yellow-600 dark:text-yellow-400" : "text-red-600 dark:text-red-400"}`}>
                          {bin.accuracy_24h.toFixed(0)}%
                        </span>
                      ) : (
                        <span className="text-gray-400">--</span>
                      )}
                    </td>
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

function returnColor(val: number | null | undefined, direction: string): string {
  if (val == null) return "text-gray-400";
  // For bullish/positive alerts, positive returns are good (green)
  // For bearish/negative alerts, negative returns are good (green)
  const isAligned =
    (direction === "positive" || direction === "bullish") ? val > 0 :
    (direction === "negative" || direction === "bearish") ? val < 0 :
    false;
  if (isAligned) return "text-green-600 dark:text-green-400";
  if (val === 0) return "text-gray-500";
  return "text-red-600 dark:text-red-400";
}

/* ── Tab 5: Outliers ───────────────────────────────────────────────── */

function OutliersTab({ onProvenance }: { onProvenance: (id: string) => void }) {
  const [data, setData] = useState<OutliersResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    setLoading(true);
    getOutliers(token, 50)
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading && !data) {
    return (
      <div className="flex min-h-[30vh] items-center justify-center">
        <div className="h-10 w-10 animate-spin rounded-full border-4 border-gold-500 border-t-transparent" />
      </div>
    );
  }

  if (!data) {
    return <div className="card p-8 text-center text-gray-500 dark:text-gray-400">داده\u200Cای موجود نیست</div>;
  }

  return (
    <div className="space-y-4">
      {/* Summary */}
      <div className="card flex items-center gap-3 px-4 py-3">
        <div className="text-lg font-bold text-gray-900 dark:text-gray-100">{data.total}</div>
        <div className="text-sm text-gray-500 dark:text-gray-400">بزرگ\u200Cترین اختلاف\u200Cها بین پیش\u200Cبینی و نتیجه</div>
      </div>

      {/* Table */}
      {data.items.length === 0 ? (
        <div className="card p-8 text-center text-gray-500 dark:text-gray-400">
          موردی یافت نشد
        </div>
      ) : (
        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-800">
                  <th className="px-3 py-2.5 text-right text-xs font-medium text-gray-500 dark:text-gray-400">عنوان هشدار</th>
                  <th className="px-3 py-2.5 text-right text-xs font-medium text-gray-500 dark:text-gray-400">جهت پیش\u200Cبینی</th>
                  <th className="px-3 py-2.5 text-right text-xs font-medium text-gray-500 dark:text-gray-400">شدت</th>
                  <th className="px-3 py-2.5 text-center text-xs font-medium text-gray-500 dark:text-gray-400">تغییر ۲۴ ساعته</th>
                  <th className="px-3 py-2.5 text-right text-xs font-medium text-gray-500 dark:text-gray-400">زمان</th>
                  <th className="px-3 py-2.5 text-center text-xs font-medium text-gray-500 dark:text-gray-400">جزئیات</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((item) => (
                  <tr key={item.alert_id} className="border-b border-gray-100 dark:border-gray-800">
                    <td className="max-w-[220px] truncate px-3 py-2.5 text-gray-900 dark:text-gray-100">
                      {item.alert_title}
                    </td>
                    <td className="px-3 py-2.5">
                      <span className={`rounded px-2 py-0.5 text-xs font-medium ${directionBg(item.direction)} ${directionColor(item.direction)}`}>
                        {directionLabel(item.direction)}
                      </span>
                    </td>
                    <td className="px-3 py-2.5">
                      {item.severity && (
                        <span className={`rounded px-2 py-0.5 text-xs font-medium ${severityBadge(item.severity)}`}>
                          {item.severity}
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2.5 text-center">
                      {item.change_pct_24h != null ? (
                        <span className={`font-mono text-sm font-medium ${item.change_pct_24h > 0 ? "text-green-600 dark:text-green-400" : item.change_pct_24h < 0 ? "text-red-600 dark:text-red-400" : "text-gray-500"}`}>
                          {item.change_pct_24h > 0 ? "+" : ""}{item.change_pct_24h.toFixed(3)}%
                        </span>
                      ) : (
                        <span className="text-gray-400">--</span>
                      )}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2.5 text-xs text-gray-500 dark:text-gray-400">
                      {item.created_at ? formatTimeAgo(item.created_at) : "--"}
                    </td>
                    <td className="px-3 py-2.5 text-center">
                      <button
                        onClick={() => onProvenance(item.alert_id)}
                        className="rounded px-2 py-1 text-xs text-gold-600 hover:bg-gold-50 dark:text-gold-400 dark:hover:bg-gold-900/20"
                      >
                        &#x1F50D;
                      </button>
                    </td>
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

/* ── Provenance Drawer ─────────────────────────────────────────────── */

function ProvenanceDrawer({
  open,
  alertId,
  data,
  loading,
  onClose,
}: {
  open: boolean;
  alertId: string | null;
  data: ProvenanceData | null;
  loading: boolean;
  onClose: () => void;
}) {
  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/40 transition-opacity"
        onClick={onClose}
      />

      {/* Slide-over panel from the left */}
      <div className="absolute inset-y-0 right-0 flex max-w-full">
        <div className="w-screen max-w-lg">
          <div className="flex h-full flex-col overflow-y-auto bg-white shadow-xl dark:bg-gray-900">
            {/* Header */}
            <div className="flex items-center justify-between border-b border-gray-200 px-5 py-4 dark:border-gray-700">
              <h3 className="text-sm font-bold text-gray-900 dark:text-gray-100">
                زنجیره اثبات (Provenance)
              </h3>
              <div className="flex items-center gap-3">
                {alertId && (
                  <span className="font-mono text-xs text-gray-400">{alertId.slice(0, 12)}...</span>
                )}
                <button
                  onClick={onClose}
                  className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800"
                >
                  <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                    <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                  </svg>
                </button>
              </div>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-5">
              {loading ? (
                <div className="flex min-h-[30vh] items-center justify-center">
                  <div className="h-8 w-8 animate-spin rounded-full border-4 border-gold-500 border-t-transparent" />
                </div>
              ) : !data ? (
                <div className="py-12 text-center text-sm text-gray-500 dark:text-gray-400">
                  داده\u200Cای موجود نیست
                </div>
              ) : (
                <div className="space-y-5">
                  {/* 1. Alert Info */}
                  {data.alert && (
                    <ProvenanceSection title="هشدار">
                      <div className="space-y-2">
                        <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                          {data.alert.title}
                        </p>
                        <div className="flex flex-wrap gap-2">
                          <span className={`rounded px-2 py-0.5 text-xs font-medium ${severityBadge(data.alert.severity)}`}>
                            {data.alert.severity}
                          </span>
                          <span className={`rounded px-2 py-0.5 text-xs font-medium ${directionBg(data.alert.direction)} ${directionColor(data.alert.direction)}`}>
                            {directionLabel(data.alert.direction)}
                          </span>
                          {data.alert.direction_confidence != null && (
                            <span className="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-600 dark:bg-gray-800 dark:text-gray-400">
                              اعتماد: {(data.alert.direction_confidence * 100).toFixed(0)}%
                            </span>
                          )}
                          {data.alert.direction_method && (
                            <span className="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-600 dark:bg-gray-800 dark:text-gray-400">
                              روش: {data.alert.direction_method}
                            </span>
                          )}
                        </div>
                        <div className="grid grid-cols-2 gap-2 text-xs text-gray-600 dark:text-gray-400">
                          <div>منبع: <span className="text-gray-900 dark:text-gray-100">{data.alert.source_name}</span></div>
                          <div>امتیاز: <span className="text-gray-900 dark:text-gray-100">{data.alert.alert_score ?? "--"}</span></div>
                          <div>اطمینان: <span className="text-gray-900 dark:text-gray-100">{data.alert.confidence ?? "--"}</span></div>
                          <div>زمان: <span className="text-gray-900 dark:text-gray-100">{data.alert.created_at ? formatTimeAgo(data.alert.created_at) : "--"}</span></div>
                        </div>
                        {data.alert.matched_rule_ids.length > 0 && (
                          <div>
                            <span className="text-xs text-gray-500 dark:text-gray-400">قواعد: </span>
                            <div className="mt-1 flex flex-wrap gap-1">
                              {data.alert.matched_rule_ids.map((ruleId) => (
                                <span key={ruleId} className="rounded bg-gold-100 px-2 py-0.5 text-xs font-mono text-gold-800 dark:bg-gold-900/30 dark:text-gold-400">
                                  {ruleId}
                                </span>
                              ))}
                            </div>
                          </div>
                        )}
                        {data.alert.match_evidence && Object.keys(data.alert.match_evidence).length > 0 && (
                          <details className="mt-2">
                            <summary className="cursor-pointer text-xs text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300">
                              شواهد تطبیق (match_evidence)
                            </summary>
                            <pre className="mt-1 max-h-40 overflow-auto rounded bg-gray-50 p-2 text-xs text-gray-700 dark:bg-gray-800 dark:text-gray-300" dir="ltr">
                              {JSON.stringify(data.alert.match_evidence, null, 2)}
                            </pre>
                          </details>
                        )}
                      </div>
                    </ProvenanceSection>
                  )}

                  {/* 2. Raw Item */}
                  {data.raw_item && (
                    <ProvenanceSection title="آیتم خام">
                      <div className="space-y-2 text-xs">
                        <div className="text-gray-600 dark:text-gray-400">
                          <span className="font-medium text-gray-900 dark:text-gray-100">{data.raw_item.title}</span>
                        </div>
                        {data.raw_item.content_snippet && (
                          <p className="leading-relaxed text-gray-600 dark:text-gray-400" dir="auto">
                            {data.raw_item.content_snippet}
                          </p>
                        )}
                        <div className="flex flex-wrap gap-3 text-gray-500 dark:text-gray-400">
                          {data.raw_item.source_url && (
                            <a
                              href={data.raw_item.source_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-gold-600 hover:underline dark:text-gold-400"
                            >
                              لینک اصلی
                            </a>
                          )}
                          {data.raw_item.fetched_at && (
                            <span>دریافت: {formatTimeAgo(data.raw_item.fetched_at)}</span>
                          )}
                        </div>
                      </div>
                    </ProvenanceSection>
                  )}

                  {/* 3. Human Label */}
                  {data.human_label && (
                    <ProvenanceSection title="برچسب انسانی">
                      <div className="space-y-2">
                        <div className="flex items-center gap-3">
                          <span className={`rounded px-2 py-0.5 text-xs font-medium ${directionBg(data.human_label.direction_label)} ${directionColor(data.human_label.direction_label)}`}>
                            {directionLabel(data.human_label.direction_label)}
                          </span>
                          <span className="text-xs text-gray-600 dark:text-gray-400">
                            شدت: <strong className="text-gray-900 dark:text-gray-100">{data.human_label.intensity}</strong>/5
                          </span>
                          <span className="text-xs text-gray-600 dark:text-gray-400">
                            ارتباط: <strong className="text-gray-900 dark:text-gray-100">{data.human_label.relevance}</strong>/5
                          </span>
                        </div>
                        {data.human_label.notes && (
                          <p className="text-xs text-gray-600 dark:text-gray-400">
                            {data.human_label.notes}
                          </p>
                        )}
                        {data.human_label.labeled_at && (
                          <p className="text-[10px] text-gray-400">
                            {formatTimeAgo(data.human_label.labeled_at)}
                          </p>
                        )}
                      </div>
                    </ProvenanceSection>
                  )}

                  {/* 4. Reference Score */}
                  {data.reference_score && (
                    <ProvenanceSection title="امتیاز مرجع (Reference Model)">
                      <div className="space-y-2">
                        <div className="flex items-center gap-3">
                          <span className={`rounded px-2 py-0.5 text-xs font-medium ${directionBg(data.reference_score.direction)} ${directionColor(data.reference_score.direction)}`}>
                            {directionLabel(data.reference_score.direction)}
                          </span>
                          {data.reference_score.confidence != null && (
                            <span className="text-xs text-gray-600 dark:text-gray-400">
                              اعتماد: <strong className="text-gray-900 dark:text-gray-100">{(data.reference_score.confidence * 100).toFixed(0)}%</strong>
                            </span>
                          )}
                          {data.reference_score.model && (
                            <span className="rounded bg-gray-100 px-2 py-0.5 text-[10px] font-mono text-gray-500 dark:bg-gray-800 dark:text-gray-400">
                              {data.reference_score.model}
                            </span>
                          )}
                        </div>
                        {data.reference_score.reasoning && (
                          <p className="text-xs leading-relaxed text-gray-600 dark:text-gray-400">
                            {data.reference_score.reasoning}
                          </p>
                        )}
                        {data.reference_score.scored_at && (
                          <p className="text-[10px] text-gray-400">
                            {formatTimeAgo(data.reference_score.scored_at)}
                          </p>
                        )}
                      </div>
                    </ProvenanceSection>
                  )}

                  {/* 5. Price Outcomes */}
                  {data.outcome && (
                    <ProvenanceSection title="نتایج قیمتی">
                      <div className="space-y-2">
                        <div className="flex items-center gap-2">
                          <span className={`rounded px-2 py-0.5 text-xs font-medium ${
                            data.outcome.status === "complete"
                              ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                              : "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400"
                          }`}>
                            {data.outcome.status}
                          </span>
                        </div>
                        <div className="grid grid-cols-3 gap-2">
                          {[
                            { label: "۳۰ دقیقه", val: data.outcome.change_pct_30min },
                            { label: "۱ ساعت", val: data.outcome.change_pct_1h },
                            { label: "۴ ساعت", val: data.outcome.change_pct_4h },
                            { label: "۲۴ ساعت", val: data.outcome.change_pct_24h },
                            { label: "۴۸ ساعت", val: data.outcome.change_pct_48h },
                            { label: "۷ روز", val: data.outcome.change_pct_7d },
                          ].map((item) => (
                            <div
                              key={item.label}
                              className="rounded-lg bg-gray-50 p-2 text-center dark:bg-gray-800"
                            >
                              <div className={`text-sm font-bold font-mono ${
                                item.val == null ? "text-gray-400" : item.val > 0 ? "text-green-600 dark:text-green-400" : item.val < 0 ? "text-red-600 dark:text-red-400" : "text-gray-500"
                              }`}>
                                {item.val != null ? `${item.val > 0 ? "+" : ""}${item.val.toFixed(3)}%` : "--"}
                              </div>
                              <div className="text-[10px] text-gray-500 dark:text-gray-400">{item.label}</div>
                            </div>
                          ))}
                        </div>
                      </div>
                    </ProvenanceSection>
                  )}

                  {/* 6. Market Snapshot */}
                  {data.market_snapshot && (
                    <ProvenanceSection title="اسنپ\u200Cشات بازار">
                      <div className="space-y-2">
                        <div className="flex items-center gap-2">
                          <span className={`rounded px-2 py-0.5 text-xs font-medium ${
                            data.market_snapshot.snapshot_complete
                              ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                              : "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400"
                          }`}>
                            {data.market_snapshot.snapshot_complete ? "کامل" : "ناقص"}
                          </span>
                        </div>
                        <div className="grid grid-cols-2 gap-2">
                          {[
                            { label: "XAUUSD", val: data.market_snapshot.xauusd, fmt: (v: number) => `$${v.toLocaleString()}` },
                            { label: "DXY", val: data.market_snapshot.dxy, fmt: (v: number) => v.toFixed(2) },
                            { label: "RSI(14)", val: data.market_snapshot.gold_rsi_14, fmt: (v: number) => v.toFixed(1) },
                            { label: "سنتیمنت", val: data.market_snapshot.sentiment_composite, fmt: (v: number) => v.toFixed(0) },
                          ].map((item) => (
                            <div
                              key={item.label}
                              className="rounded-lg bg-gray-50 p-2 dark:bg-gray-800"
                            >
                              <div className="text-[10px] text-gray-500 dark:text-gray-400">{item.label}</div>
                              <div className="text-sm font-medium text-gray-900 dark:text-gray-100">
                                {item.val != null ? item.fmt(item.val) : "--"}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    </ProvenanceSection>
                  )}

                  {/* No data at all */}
                  {!data.alert && !data.raw_item && !data.human_label && !data.reference_score && !data.outcome && !data.market_snapshot && (
                    <div className="py-8 text-center text-sm text-gray-500 dark:text-gray-400">
                      هیچ داده\u200Cای برای این هشدار یافت نشد
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function ProvenanceSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-700">
      <div className="border-b border-gray-200 bg-gray-50 px-4 py-2 dark:border-gray-700 dark:bg-gray-800">
        <h4 className="text-xs font-semibold text-gray-700 dark:text-gray-300">{title}</h4>
      </div>
      <div className="p-4">{children}</div>
    </div>
  );
}
