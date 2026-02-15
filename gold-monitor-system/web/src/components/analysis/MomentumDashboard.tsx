"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import DataPending from "./DataPending";
import SkeletonCard from "./SkeletonCard";
import InfoTip from "@/components/InfoTip";

/* ══════════════════════════════════════════════════════════════════════════
   Types
   ══════════════════════════════════════════════════════════════════════════ */

interface Driver {
  id: string;
  label_fa: string;
  score: number;
  direction: string;
  strength: string;
  weight: number;
  raw_value: number | string;
  raw_unit: string;
  explanation_fa: string;
  trend: string;
}

interface DriverMeta {
  normalized_method?: string;
  window_used?: number;
  last_updated_at?: string | null;
  data_age_days?: number | null;
  fallback_used?: boolean;
  zscore?: number | null;
  percentile?: number | null;
  [key: string]: unknown;
}

interface Alignment {
  aligned: boolean;
  bullish_count: number;
  bearish_count: number;
  neutral_count: number;
  divergence_warning: boolean;
  divergence_note_fa: string;
}

interface TechnicalContext {
  gold_rsi_14: number | null;
  gold_rsi_zone: string;
  gold_daily_change_pct: number | null;
  gold_5d_return_pct: number | null;
}

export interface MacroMomentumData {
  composite_score: number | null;
  composite_direction: string;
  composite_direction_fa: string;
  alignment: Alignment;
  drivers: Driver[];
  technical_context: TechnicalContext;
  // v2 fields (optional for backward compat)
  drivers_meta?: Record<string, DriverMeta>;
  weights?: {
    base: Record<string, number>;
    effective: Record<string, number>;
  };
  confidences?: Record<string, number>;
  meta?: {
    run_id: string;
    as_of: string;
    computed_at: string;
    engine_version: string;
    notes: string[];
  };
  warnings?: string[];
}

/* ══════════════════════════════════════════════════════════════════════════
   Config maps
   ══════════════════════════════════════════════════════════════════════════ */

const DIRECTION_COLORS: Record<string, { text: string; bg: string; border: string }> = {
  very_bullish: { text: "text-emerald-500", bg: "bg-emerald-500/10", border: "border-emerald-500/30" },
  bullish:      { text: "text-emerald-500", bg: "bg-emerald-500/10", border: "border-emerald-500/20" },
  neutral:      { text: "text-yellow-500",  bg: "bg-yellow-500/10",  border: "border-yellow-500/20" },
  bearish:      { text: "text-red-500",     bg: "bg-red-500/10",     border: "border-red-500/20" },
  very_bearish: { text: "text-red-500",     bg: "bg-red-500/10",     border: "border-red-500/30" },
  pending:      { text: "text-gray-400",    bg: "bg-gray-500/5",     border: "border-gray-500/20" },
};

const DIRECTION_ARROWS: Record<string, string> = {
  very_bullish: "▲▲",
  bullish: "▲",
  neutral: "●",
  bearish: "▼",
  very_bearish: "▼▼",
};

const TREND_CONFIG: Record<string, { label: string; icon: string }> = {
  accelerating: { label: "شتاب‌دار", icon: "⏫" },
  steady:       { label: "ثابت",     icon: "➡" },
  decelerating: { label: "کُند",     icon: "⏬" },
  reversing:    { label: "برگشت",    icon: "↩" },
};

const RSI_ZONE_LABELS: Record<string, string> = {
  overbought: "اشباع خرید",
  oversold: "اشباع فروش",
  neutral: "خنثی",
  unknown: "—",
};

const NORM_METHOD_LABELS: Record<string, string> = {
  zscore: "z-score",
  percentile: "صدک‌بندی",
  blend: "ترکیبی",
  static_map: "نقشه ثابت",
  fallback: "پیش‌فرض",
};

/* ══════════════════════════════════════════════════════════════════════════
   Helpers
   ══════════════════════════════════════════════════════════════════════════ */

function getScoreBarColor(score: number): string {
  if (score >= 70) return "bg-emerald-500";
  if (score >= 55) return "bg-emerald-400";
  if (score >= 45) return "bg-yellow-400";
  if (score >= 30) return "bg-red-400";
  return "bg-red-500";
}

function getCompositeGradient(direction: string): string {
  switch (direction) {
    case "very_bullish":
    case "bullish":
      return "from-emerald-500/15 to-emerald-500/5";
    case "bearish":
    case "very_bearish":
      return "from-red-500/15 to-red-500/5";
    default:
      return "from-yellow-500/10 to-yellow-500/5";
  }
}

function formatAge(days: number | null | undefined): string {
  if (days === null || days === undefined) return "";
  if (days < 1) return "امروز";
  if (days === 1) return "۱ روز پیش";
  return `${days} روز پیش`;
}

/** Tooltip showing normalization details for a driver */
function DriverTooltip({ meta, confidence, effWeight, baseWeight }: {
  meta: DriverMeta;
  confidence?: number;
  effWeight?: number;
  baseWeight: number;
}) {
  return (
    <div className="mt-2 rounded-lg border border-gray-200 bg-gray-50 p-3 text-xs dark:border-gray-700 dark:bg-gray-800/50">
      <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
        {/* Normalization method */}
        {meta.normalized_method && (
          <>
            <span className="text-gray-500 dark:text-gray-400">روش نرمال‌سازی:</span>
            <span className="font-medium text-gray-800 dark:text-gray-200">
              {NORM_METHOD_LABELS[meta.normalized_method] ?? meta.normalized_method}
            </span>
          </>
        )}

        {/* Z-score if present */}
        {meta.zscore !== undefined && meta.zscore !== null && (
          <>
            <span className="text-gray-500 dark:text-gray-400">z-score:</span>
            <span className="font-mono font-bold text-gray-800 dark:text-gray-200" dir="ltr">
              {meta.zscore > 0 ? "+" : ""}{meta.zscore.toFixed(2)}σ
            </span>
          </>
        )}

        {/* Percentile if present */}
        {meta.percentile !== undefined && meta.percentile !== null && (
          <>
            <span className="text-gray-500 dark:text-gray-400">صدک:</span>
            <span className="font-mono font-bold text-gray-800 dark:text-gray-200" dir="ltr">
              {(meta.percentile * 100).toFixed(0)}%
            </span>
          </>
        )}

        {/* Window used */}
        {meta.window_used !== undefined && meta.window_used > 0 && (
          <>
            <span className="text-gray-500 dark:text-gray-400">پنجره:</span>
            <span className="text-gray-800 dark:text-gray-200">{meta.window_used} نمونه</span>
          </>
        )}

        {/* Data age */}
        {meta.data_age_days !== undefined && meta.data_age_days !== null && (
          <>
            <span className="text-gray-500 dark:text-gray-400">تازگی داده:</span>
            <span className={cn(
              "text-gray-800 dark:text-gray-200",
              meta.data_age_days > 3 && "text-amber-500",
            )}>
              {formatAge(meta.data_age_days)}
            </span>
          </>
        )}

        {/* Confidence + effective weight */}
        {confidence !== undefined && confidence < 1.0 && (
          <>
            <span className="text-gray-500 dark:text-gray-400">اعتماد:</span>
            <span className="text-amber-500 font-medium" dir="ltr">
              {(confidence * 100).toFixed(0)}%
            </span>
          </>
        )}

        {effWeight !== undefined && effWeight !== baseWeight && (
          <>
            <span className="text-gray-500 dark:text-gray-400">وزن مؤثر:</span>
            <span className="text-gray-800 dark:text-gray-200" dir="ltr">
              <span className="line-through text-gray-400">{baseWeight}%</span>
              {" → "}
              <span className={cn(confidence !== undefined && confidence < 1 ? "text-amber-500" : "")}>
                {effWeight.toFixed(1)}%
              </span>
            </span>
          </>
        )}
      </div>

      {/* Fallback warning */}
      {meta.fallback_used && (
        <p className="mt-2 text-amber-500 text-[10px]">
          از مقدار پیش‌فرض استفاده شد — داده کافی نیست
        </p>
      )}
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════════════
   Component
   ══════════════════════════════════════════════════════════════════════════ */

interface Props {
  data: MacroMomentumData | null;
  loading: boolean;
}

export default function MomentumDashboard({ data, loading }: Props) {
  const hasData = data && data.drivers && data.drivers.length > 0;
  const dc = DIRECTION_COLORS[data?.composite_direction ?? "pending"] ?? DIRECTION_COLORS.pending;
  const [expandedDriver, setExpandedDriver] = useState<string | null>(null);
  const hasV2 = !!data?.drivers_meta;

  return (
    <div className="flex flex-col">
      <div className="mb-4 flex items-center gap-2">
        <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100">
          مومنتوم بنیادی
        </h2>
        <InfoTip term="momentum_dashboard" />
        {data?.meta?.engine_version && (
          <span className="text-[10px] text-gray-400 dark:text-gray-500">
            v{data.meta.engine_version}
          </span>
        )}
      </div>

      {loading ? (
        <SkeletonCard className="h-64 flex-1" />
      ) : !hasData ? (
        <DataPending message="در انتظار داده" />
      ) : (
        <div className="card space-y-4 flex-1">
          {/* ── A. Composite Banner ── */}
          <div
            className={cn(
              "flex items-center gap-4 rounded-lg border p-4 bg-gradient-to-l",
              dc.border,
              getCompositeGradient(data!.composite_direction),
            )}
          >
            {/* Score circle */}
            <div className="flex flex-shrink-0 flex-col items-center">
              <span className={cn("text-3xl font-black tabular-nums", dc.text)} dir="ltr">
                {data!.composite_score ?? "—"}
              </span>
              <span className="text-[10px] text-gray-500 dark:text-gray-400">از ۱۰۰</span>
            </div>

            {/* Direction + alignment */}
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className={cn("text-lg", dc.text)}>
                  {DIRECTION_ARROWS[data!.composite_direction] ?? "●"}
                </span>
                <span className={cn("text-sm font-bold", dc.text)}>
                  {data!.composite_direction_fa}
                </span>
                {data!.alignment.aligned && (
                  <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                    هم‌راستا
                  </span>
                )}
              </div>
              {data!.alignment.divergence_warning && data!.alignment.divergence_note_fa && (
                <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">
                  &#x26A0; {data!.alignment.divergence_note_fa}
                </p>
              )}
              <p className="mt-0.5 text-[11px] text-gray-500 dark:text-gray-400">
                {data!.alignment.bullish_count} صعودی
                {" · "}
                {data!.alignment.bearish_count} نزولی
                {" · "}
                {data!.alignment.neutral_count} خنثی
              </p>
            </div>
          </div>

          {/* ── B. Driver Rows ── */}
          <div className="space-y-2">
            {hasV2 && (
              <p className="text-[10px] text-gray-400 dark:text-gray-500 mb-1">
                (برای جزئیات نرمال‌سازی کلیک کنید)
              </p>
            )}
            {data!.drivers.map((d) => {
              const ddc = DIRECTION_COLORS[d.direction] ?? DIRECTION_COLORS.neutral;
              const trendCfg = TREND_CONFIG[d.trend] ?? TREND_CONFIG.steady;
              const meta = data?.drivers_meta?.[d.id];
              const effWeight = data?.weights?.effective?.[d.id];
              const confidence = data?.confidences?.[d.id];
              const isExpanded = expandedDriver === d.id;

              return (
                <div
                  key={d.id}
                  className={cn(
                    "rounded-lg border p-3 transition-all",
                    ddc.bg,
                    ddc.border,
                  )}
                >
                  {/* Row top: label + weight + arrow + score bar + trend */}
                  <div
                    className={cn(
                      "flex items-center gap-3",
                      hasV2 && "cursor-pointer",
                    )}
                    onClick={() => hasV2 && setExpandedDriver(isExpanded ? null : d.id)}
                  >
                    {/* Driver label + weight badge */}
                    <div className="flex min-w-0 flex-shrink-0 items-center gap-1.5" style={{ width: "110px" }}>
                      <span className="truncate text-sm font-bold text-gray-900 dark:text-gray-100">
                        {d.label_fa}
                      </span>
                      <span className="flex-shrink-0 rounded bg-gray-200 dark:bg-gray-700 px-1 py-0.5 text-[10px] font-medium text-gray-500 dark:text-gray-400" dir="ltr">
                        {effWeight !== undefined && effWeight !== d.weight ? (
                          <span className={cn(confidence !== undefined && confidence < 1 ? "text-amber-500" : "")}>
                            {effWeight.toFixed(0)}%
                          </span>
                        ) : (
                          `${d.weight}%`
                        )}
                      </span>
                    </div>

                    {/* Direction arrow */}
                    <span className={cn("w-6 flex-shrink-0 text-center text-base font-bold", ddc.text)}>
                      {DIRECTION_ARROWS[d.direction] ?? "●"}
                    </span>

                    {/* Score bar */}
                    <div className="flex flex-1 items-center gap-2">
                      <div className="h-2.5 flex-1 rounded-full bg-gray-200 dark:bg-gray-700">
                        <div
                          className={cn(
                            "h-full rounded-full transition-all duration-500",
                            getScoreBarColor(d.score),
                          )}
                          style={{ width: `${d.score}%` }}
                        />
                      </div>
                      <span className={cn("w-8 flex-shrink-0 text-left text-xs font-bold tabular-nums", ddc.text)} dir="ltr">
                        {d.score}
                      </span>
                    </div>

                    {/* Trend indicator */}
                    <span
                      className="flex-shrink-0 text-[11px] text-gray-500 dark:text-gray-400"
                      title={trendCfg.label}
                    >
                      {trendCfg.icon}
                    </span>

                    {/* Expand indicator */}
                    {hasV2 && (
                      <span className="text-[10px] text-gray-300 dark:text-gray-600">
                        {isExpanded ? "▲" : "▼"}
                      </span>
                    )}
                  </div>

                  {/* Row bottom: explanation */}
                  <p className="mt-1.5 text-[11px] leading-relaxed text-gray-600 dark:text-gray-400">
                    {d.explanation_fa}
                  </p>

                  {/* Expandable tooltip */}
                  {isExpanded && meta && (
                    <DriverTooltip
                      meta={meta}
                      confidence={confidence}
                      effWeight={effWeight}
                      baseWeight={d.weight}
                    />
                  )}
                </div>
              );
            })}
          </div>

          {/* ── C. Technical Context (footer) ── */}
          {data!.technical_context && (
            <div className="flex flex-wrap items-center gap-4 rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 px-3 py-2">
              <span className="text-[11px] font-medium text-gray-500 dark:text-gray-400">
                تکنیکال:
              </span>
              {data!.technical_context.gold_rsi_14 != null && (
                <span className="text-[11px] text-gray-500 dark:text-gray-400" dir="ltr">
                  RSI(14):{" "}
                  <span className={cn(
                    "font-bold",
                    data!.technical_context.gold_rsi_14 >= 70
                      ? "text-red-500"
                      : data!.technical_context.gold_rsi_14 <= 30
                        ? "text-emerald-500"
                        : "text-gray-600 dark:text-gray-300",
                  )}>
                    {data!.technical_context.gold_rsi_14}
                  </span>
                  {" "}
                  <span className="text-gray-400">
                    ({RSI_ZONE_LABELS[data!.technical_context.gold_rsi_zone] ?? "—"})
                  </span>
                </span>
              )}
              {data!.technical_context.gold_daily_change_pct != null && (
                <span className="text-[11px] text-gray-500 dark:text-gray-400" dir="ltr">
                  روزانه:{" "}
                  <span className={cn(
                    "font-bold",
                    data!.technical_context.gold_daily_change_pct > 0
                      ? "text-emerald-500"
                      : data!.technical_context.gold_daily_change_pct < 0
                        ? "text-red-500"
                        : "text-gray-400",
                  )}>
                    {data!.technical_context.gold_daily_change_pct > 0 ? "+" : ""}
                    {data!.technical_context.gold_daily_change_pct}%
                  </span>
                </span>
              )}
              {data!.technical_context.gold_5d_return_pct != null && (
                <span className="text-[11px] text-gray-500 dark:text-gray-400" dir="ltr">
                  ۵ روزه:{" "}
                  <span className={cn(
                    "font-bold",
                    data!.technical_context.gold_5d_return_pct > 0
                      ? "text-emerald-500"
                      : data!.technical_context.gold_5d_return_pct < 0
                        ? "text-red-500"
                        : "text-gray-400",
                  )}>
                    {data!.technical_context.gold_5d_return_pct > 0 ? "+" : ""}
                    {data!.technical_context.gold_5d_return_pct}%
                  </span>
                </span>
              )}
            </div>
          )}

          {/* ── Warnings ── */}
          {data?.warnings && data.warnings.length > 0 && (
            <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-2.5">
              {data.warnings.map((w, i) => (
                <p key={i} className="text-xs text-amber-600 dark:text-amber-400">
                  {w}
                </p>
              ))}
            </div>
          )}

          {/* ── D. Info Box ── */}
          <div className="rounded-lg border border-blue-500/20 bg-blue-500/5 p-3">
            <p className="text-xs text-blue-600 dark:text-blue-400">
              <span className="ml-1 font-bold">&#x26A1; مومنتوم بنیادی چیست؟</span>
              ۶ نیروی کلان (جریان ETF، موقعیت COT، نرخ بهره واقعی، قدرت دلار، رژیم کلان و احساسات) را ترکیب می‌کند
              تا نشان دهد کدام عوامل بنیادی طلا را حرکت می‌دهند. هم‌راستایی بالا = روند قوی. واگرایی = احتیاط.
              {hasV2 && " وزن‌ها بر اساس تازگی داده‌ها تعدیل می‌شوند."}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
