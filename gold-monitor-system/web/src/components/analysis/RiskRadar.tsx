"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import DataPending from "./DataPending";
import SkeletonCard from "./SkeletonCard";
import InfoTip from "@/components/InfoTip";

export interface RiskRadarComponent {
  name: string;
  name_fa: string;
  score: number;
  weight: number;
}

export interface RiskRadarDetailedComponent extends RiskRadarComponent {
  raw_value: number | string | null;
  raw_units: string;
  source: string;
  last_updated_at: string | null;
  confidence: number;
  explanation_fa: string;
  percentile: number | null;
  window_size: number;
  fallback_used: boolean;
  data_age_days: number | null;
  debug?: {
    indicator_id: string;
    score: number;
    percentile: number;
    zscore: number | null;
    source_name: string;
    source_url: string | null;
    scoring_method: string;
    score_semantics?: Record<string, string>;
  };
}

export interface RiskRadarData {
  composite_score: number | null;
  label: string | null;
  components: RiskRadarComponent[];
  computed_at: string;
  // New v2 fields
  components_detailed?: RiskRadarDetailedComponent[];
  weights?: {
    base: Record<string, number>;
    effective: Record<string, number>;
  };
  confidences?: Record<string, number>;
  warnings?: string[];
  meta?: {
    run_id: string;
    as_of: string;
    engine_version: string;
  };
}

const LABEL_FA: Record<string, string> = {
  high: "ریسک بالا",
  moderate: "ریسک متوسط",
  low: "ریسک پایین",
};

function getRiskColor(score: number): {
  text: string;
  border: string;
  bg: string;
  ring: string;
  bar: string;
  glow: string;
} {
  if (score >= 65)
    return {
      text: "text-red-500",
      border: "border-red-500/50",
      bg: "bg-red-500/10",
      ring: "ring-red-500/30",
      bar: "bg-red-500",
      glow: "shadow-red-500/20",
    };
  if (score >= 40)
    return {
      text: "text-amber-500",
      border: "border-amber-500/50",
      bg: "bg-amber-500/10",
      ring: "ring-amber-500/30",
      bar: "bg-amber-500",
      glow: "shadow-amber-500/20",
    };
  return {
    text: "text-emerald-500",
    border: "border-emerald-500/50",
    bg: "bg-emerald-500/10",
    ring: "ring-emerald-500/30",
    bar: "bg-emerald-500",
    glow: "shadow-emerald-500/20",
  };
}

function getComponentBarColor(score: number): string {
  if (score >= 65) return "bg-red-500";
  if (score >= 40) return "bg-amber-500";
  return "bg-emerald-500";
}

function getComponentTextColor(score: number): string {
  if (score >= 65) return "text-red-500";
  if (score >= 40) return "text-amber-500";
  return "text-emerald-500";
}

const COMPONENT_ICONS: Record<string, string> = {
  volatility: "\u26A0\uFE0F",
  vix: "\u26A0\uFE0F",
  regime: "\uD83C\uDFDB\uFE0F",
  sentiment: "\uD83D\uDCA1",
  cot: "\uD83D\uDCCA",
  etf: "\uD83D\uDCB0",
  correlation: "\uD83D\uDD17",
};

const COMPONENT_HIGHER_MEANS: Record<string, string> = {
  volatility: "نوسان بیشتر = ریسک بالاتر",
  regime: "نوسان بالا در این رژیم = ریسک بالاتر",
  sentiment: "احساسات افراطی = ریسک بازگشت",
  cot: "موقعیت‌های افراطی = ریسک بالاتر",
  etf: "خروج نهادی = ریسک بالاتر",
  correlation: "انحراف از رابطه عادی = ریسک بالاتر",
};

function formatRawValue(value: number | string | null, units: string): string {
  if (value === null || value === undefined) return "N/A";
  if (typeof value === "string") return value;
  if (units === "index") return value.toFixed(1);
  if (units === "% of OI") return `${value.toFixed(1)}%`;
  if (units === "tonnes/day") return `${value >= 0 ? "+" : ""}${value.toFixed(2)} تن`;
  if (units === "coefficient") return value.toFixed(3);
  if (units === "score (0-100)") return `${value.toFixed(0)}/100`;
  return String(value);
}

function formatAge(days: number | null): string {
  if (days === null || days === undefined) return "";
  if (days < 1) return "امروز";
  if (days === 1) return "۱ روز پیش";
  return `${days} روز پیش`;
}

/** Tooltip that shows when user clicks/hovers on a component row */
function ComponentTooltip({ comp }: { comp: RiskRadarDetailedComponent }) {
  return (
    <div className="mt-2 rounded-lg border border-gray-200 bg-gray-50 p-3 text-xs dark:border-gray-700 dark:bg-gray-800/50">
      {/* Raw value + units */}
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-gray-500 dark:text-gray-400">مقدار خام:</span>
        <span className="font-mono font-bold text-gray-800 dark:text-gray-200">
          {formatRawValue(comp.raw_value, comp.raw_units)}
        </span>
      </div>

      {/* What higher/lower means */}
      <div className="mb-1.5 text-gray-500 dark:text-gray-400">
        {COMPONENT_HIGHER_MEANS[comp.name] || ""}
      </div>

      {/* Explanation (Persian) */}
      {comp.explanation_fa && (
        <p className="mb-1.5 text-gray-600 dark:text-gray-300 leading-relaxed">
          {comp.explanation_fa}
        </p>
      )}

      {/* Score semantics */}
      {comp.debug?.score_semantics?.risk && (
        <div className="mb-1.5 rounded bg-blue-50 dark:bg-blue-900/20 px-2 py-1 text-[10px] text-blue-600 dark:text-blue-400">
          <span className="font-bold ml-1">این امتیاز چگونه محاسبه شده؟</span>
          {comp.debug.score_semantics.risk}
          {comp.debug.zscore !== null && comp.debug.zscore !== undefined && (
            <span className="mr-2">(z-score: {comp.debug.zscore.toFixed(2)})</span>
          )}
        </div>
      )}

      {/* Meta row */}
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-gray-400 dark:text-gray-500 mt-2 pt-2 border-t border-gray-200 dark:border-gray-700">
        {comp.source && comp.source !== "N/A" && (
          <span>منبع: {comp.source}</span>
        )}
        {comp.debug?.source_url && (
          <a href={comp.debug.source_url} target="_blank" rel="noopener noreferrer"
             className="text-blue-500 hover:underline">لینک منبع</a>
        )}
        {comp.last_updated_at && (
          <span>آخرین بروزرسانی: {formatAge(comp.data_age_days)}</span>
        )}
        {comp.percentile !== null && comp.percentile !== undefined && (
          <span>صدک: {(comp.percentile * 100).toFixed(0)}%</span>
        )}
        {comp.window_size > 0 && (
          <span>پنجره: {comp.window_size} نمونه</span>
        )}
        {comp.confidence < 1.0 && (
          <span className="text-amber-500">
            اعتماد: {(comp.confidence * 100).toFixed(0)}%
          </span>
        )}
        {comp.fallback_used && (
          <span className="text-amber-500">⚠ از مقدار پیش‌فرض استفاده شد</span>
        )}
      </div>
    </div>
  );
}

interface Props {
  data: RiskRadarData | null;
  loading: boolean;
}

export default function RiskRadar({ data, loading }: Props) {
  const hasData = data && data.composite_score != null;
  const [expandedComp, setExpandedComp] = useState<string | null>(null);

  // Build a map from component name → detailed data
  const detailedMap: Record<string, RiskRadarDetailedComponent> = {};
  if (data?.components_detailed) {
    for (const c of data.components_detailed) {
      detailedMap[c.name] = c;
    }
  }

  const hasDetailed = Object.keys(detailedMap).length > 0;

  return (
    <div className="flex flex-col">
      <div className="mb-4 flex items-center gap-2">
        <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100">
          &#x1F6E1;&#xFE0F; رادار ریسک
        </h2>
        <InfoTip term="risk_radar" />
        {data?.meta?.engine_version && (
          <span className="text-[10px] text-gray-400 dark:text-gray-500">
            v{data.meta.engine_version}
          </span>
        )}
      </div>

      {loading ? (
        <SkeletonCard className="h-64 flex-1" />
      ) : !hasData ? (
        <DataPending message="داده‌های رادار ریسک پس از جمع‌آوری شاخص‌های بازار محاسبه خواهد شد." />
      ) : (
        (() => {
          const score = data!.composite_score!;
          const label = data!.label || "moderate";
          const colors = getRiskColor(score);
          const circumference = 2 * Math.PI * 54;
          const strokeOffset = circumference - (score / 100) * circumference;
          const effectiveWeights = data?.weights?.effective;

          return (
            <div className={cn("card border-2 transition-all flex-1", colors.border)}>
              <div className="flex flex-col items-center gap-6 sm:flex-row sm:items-start sm:gap-10">
                {/* Central gauge */}
                <div className="flex flex-col items-center flex-shrink-0">
                  <div className={cn("relative flex h-36 w-36 items-center justify-center")}>
                    {/* Background ring */}
                    <svg
                      className="absolute inset-0 h-full w-full -rotate-90"
                      viewBox="0 0 120 120"
                    >
                      <circle
                        cx="60"
                        cy="60"
                        r="54"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="8"
                        className="text-gray-200 dark:text-gray-700"
                      />
                      <circle
                        cx="60"
                        cy="60"
                        r="54"
                        fill="none"
                        strokeWidth="8"
                        strokeLinecap="round"
                        strokeDasharray={circumference}
                        strokeDashoffset={strokeOffset}
                        className={cn(
                          "transition-all duration-1000 ease-out",
                          score >= 65
                            ? "stroke-red-500"
                            : score >= 40
                              ? "stroke-amber-500"
                              : "stroke-emerald-500"
                        )}
                      />
                    </svg>
                    {/* Score number */}
                    <div className="relative z-10 text-center">
                      <span
                        className={cn("text-4xl font-extrabold tabular-nums", colors.text)}
                      >
                        {Math.round(score)}
                      </span>
                      <span className="block text-[11px] text-gray-400 dark:text-gray-500">
                        از ۱۰۰
                      </span>
                    </div>
                  </div>
                  {/* Label badge */}
                  <span
                    className={cn(
                      "mt-3 rounded-full border px-4 py-1 text-sm font-bold",
                      colors.bg,
                      colors.border,
                      colors.text
                    )}
                  >
                    {LABEL_FA[label] || label}
                  </span>
                </div>

                {/* Component breakdown */}
                <div className="flex-1 w-full">
                  <h3 className="text-sm font-bold text-gray-900 dark:text-gray-100 mb-4">
                    اجزای ریسک
                    {hasDetailed && (
                      <span className="mr-2 text-[10px] font-normal text-gray-400">
                        (برای جزئیات بیشتر کلیک کنید)
                      </span>
                    )}
                  </h3>
                  <div className="space-y-3">
                    {data!.components.map((comp) => {
                      const barColor = getComponentBarColor(comp.score);
                      const textColor = getComponentTextColor(comp.score);
                      const icon = COMPONENT_ICONS[comp.name] || "\uD83D\uDD39";
                      const detailed = detailedMap[comp.name];
                      const isExpanded = expandedComp === comp.name;
                      const effWeight = effectiveWeights?.[comp.name];
                      const confidence = data?.confidences?.[comp.name];

                      return (
                        <div key={comp.name}>
                          <div
                            className={cn(
                              "flex items-center justify-between mb-1",
                              hasDetailed && "cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/50 -mx-1 px-1 rounded"
                            )}
                            onClick={() => {
                              if (hasDetailed) {
                                setExpandedComp(isExpanded ? null : comp.name);
                              }
                            }}
                          >
                            <span className="flex items-center gap-1.5 text-xs text-gray-700 dark:text-gray-300">
                              <span className="text-sm">{icon}</span>
                              <span className="font-medium">{comp.name_fa}</span>
                              <span className="text-[10px] text-gray-400 dark:text-gray-500">
                                {effWeight !== undefined && effWeight !== comp.weight ? (
                                  <>
                                    (وزن: <span className="line-through">{comp.weight}</span>
                                    {" → "}
                                    <span className={confidence !== undefined && confidence < 1 ? "text-amber-500" : ""}>
                                      {effWeight.toFixed(0)}%
                                    </span>)
                                  </>
                                ) : (
                                  `(وزن: ${comp.weight}%)`
                                )}
                              </span>
                              {hasDetailed && (
                                <span className="text-[10px] text-gray-300 dark:text-gray-600">
                                  {isExpanded ? "▲" : "▼"}
                                </span>
                              )}
                            </span>
                            <span
                              className={cn("text-xs font-bold tabular-nums", textColor)}
                            >
                              {comp.score}
                            </span>
                          </div>
                          <div className="h-2.5 rounded-full bg-gray-200 dark:bg-gray-700 overflow-hidden">
                            <div
                              className={cn(
                                "h-full rounded-full transition-all duration-700 ease-out",
                                barColor
                              )}
                              style={{ width: `${Math.min(comp.score, 100)}%` }}
                            />
                          </div>
                          {/* Expandable tooltip */}
                          {isExpanded && detailed && (
                            <ComponentTooltip comp={detailed} />
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>

              {/* Warnings */}
              {data?.warnings && data.warnings.length > 0 && (
                <div className="mt-4 rounded-lg border border-amber-500/20 bg-amber-500/5 p-2.5">
                  {data.warnings.map((w, i) => (
                    <p key={i} className="text-xs text-amber-600 dark:text-amber-400">
                      ⚠ {w}
                    </p>
                  ))}
                </div>
              )}

              {/* Explanatory footer */}
              <div className="mt-5 rounded-lg border border-blue-500/20 bg-blue-500/5 p-3">
                <p className="text-xs text-blue-600 dark:text-blue-400">
                  <span className="ml-1 font-bold">&#x26A1; چرا مهم است؟</span>
                  رادار ریسک از ترکیب ۶ عامل (شاخص ترس VIX، رژیم بازار، احساسات، موقعیت معامله‌گران
                  COT، جریان صندوق‌های ETF و همبستگی دلار-طلا) محاسبه می‌شود. امتیاز بالای ۶۵ نشانه
                  ریسک بالا، ۴۰ تا ۶۴ متوسط و زیر ۴۰ نشانه شرایط کم‌ریسک برای بازار طلاست.
                  {hasDetailed && " وزن‌ها بر اساس تازگی داده‌ها تعدیل می‌شوند."}
                </p>
              </div>
            </div>
          );
        })()
      )}
    </div>
  );
}
