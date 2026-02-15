"use client";

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

  return (
    <div className="flex flex-col">
      <div className="mb-4 flex items-center gap-2">
        <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100">
          مومنتوم بنیادی
        </h2>
        <InfoTip term="momentum_dashboard" />
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
            {data!.drivers.map((d) => {
              const ddc = DIRECTION_COLORS[d.direction] ?? DIRECTION_COLORS.neutral;
              const trendCfg = TREND_CONFIG[d.trend] ?? TREND_CONFIG.steady;

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
                  <div className="flex items-center gap-3">
                    {/* Driver label + weight badge */}
                    <div className="flex min-w-0 flex-shrink-0 items-center gap-1.5" style={{ width: "110px" }}>
                      <span className="truncate text-sm font-bold text-gray-900 dark:text-gray-100">
                        {d.label_fa}
                      </span>
                      <span className="flex-shrink-0 rounded bg-gray-200 dark:bg-gray-700 px-1 py-0.5 text-[10px] font-medium text-gray-500 dark:text-gray-400" dir="ltr">
                        {d.weight}%
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
                  </div>

                  {/* Row bottom: explanation */}
                  <p className="mt-1.5 text-[11px] leading-relaxed text-gray-600 dark:text-gray-400">
                    {d.explanation_fa}
                  </p>
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

          {/* ── D. Info Box ── */}
          <div className="rounded-lg border border-blue-500/20 bg-blue-500/5 p-3">
            <p className="text-xs text-blue-600 dark:text-blue-400">
              <span className="ml-1 font-bold">&#x26A1; مومنتوم بنیادی چیست؟</span>
              ۶ نیروی کلان (جریان ETF، موقعیت COT، نرخ بهره واقعی، قدرت دلار، رژیم کلان و احساسات) را ترکیب می‌کند
              تا نشان دهد کدام عوامل بنیادی طلا را حرکت می‌دهند. هم‌راستایی بالا = روند قوی. واگرایی = احتیاط.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
