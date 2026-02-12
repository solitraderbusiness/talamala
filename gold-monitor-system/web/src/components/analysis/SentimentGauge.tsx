"use client";

import { cn } from "@/lib/utils";
import type { SentimentGaugeResponse } from "@/lib/api";
import DataPending from "./DataPending";
import SkeletonCard from "./SkeletonCard";

const LABEL_STYLES: Record<string, { color: string; bg: string }> = {
  very_bullish: { color: "text-emerald-500", bg: "bg-emerald-500" },
  bullish: { color: "text-emerald-400", bg: "bg-emerald-400" },
  neutral: { color: "text-gray-400", bg: "bg-gray-400" },
  bearish: { color: "text-red-400", bg: "bg-red-400" },
  very_bearish: { color: "text-red-500", bg: "bg-red-500" },
  pending: { color: "text-gray-400", bg: "bg-gray-400" },
};

function getScoreColor(score: number): string {
  if (score >= 70) return "text-emerald-500";
  if (score >= 55) return "text-emerald-400";
  if (score >= 45) return "text-gray-400";
  if (score >= 30) return "text-red-400";
  return "text-red-500";
}

function getBarColor(score: number): string {
  if (score >= 70) return "bg-emerald-500";
  if (score >= 55) return "bg-emerald-400";
  if (score >= 45) return "bg-gray-400";
  if (score >= 30) return "bg-red-400";
  return "bg-red-500";
}

interface Props {
  data: SentimentGaugeResponse | null;
  loading: boolean;
}

export default function SentimentGauge({ data, loading }: Props) {
  const hasData = data && data.composite_score != null;

  return (
    <div>
      <div className="mb-4 flex items-center gap-2">
        <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100">
          &#x1F3AF; سنجش احساسات بازار
        </h2>
      </div>

      {loading ? (
        <SkeletonCard className="h-40" />
      ) : !hasData ? (
        <DataPending message="شاخص احساسات پس از جمع‌آوری داده‌های بنیادی (ETF, COT, نرخ بهره) محاسبه خواهد شد." />
      ) : (
        <div className="card">
          {/* Main gauge */}
          <div className="flex flex-col items-center sm:flex-row sm:items-start sm:gap-8">
            {/* Score circle */}
            <div className="flex flex-col items-center mb-4 sm:mb-0">
              <div
                className={cn(
                  "flex h-28 w-28 items-center justify-center rounded-full border-4",
                  data!.composite_score! >= 55
                    ? "border-emerald-500/40"
                    : data!.composite_score! >= 45
                      ? "border-gray-400/40"
                      : "border-red-500/40"
                )}
              >
                <div className="text-center">
                  <span
                    className={cn("text-3xl font-bold", getScoreColor(data!.composite_score!))}
                  >
                    {data!.composite_score}
                  </span>
                  <span className="block text-[11px] text-gray-400">/100</span>
                </div>
              </div>
              <span
                className={cn(
                  "mt-2 rounded-full px-3 py-1 text-xs font-bold",
                  LABEL_STYLES[data!.label]?.color || "text-gray-400",
                )}
              >
                {data!.label_fa}
              </span>
            </div>

            {/* Component breakdown */}
            <div className="flex-1 w-full space-y-2.5">
              <h3 className="text-sm font-bold text-gray-900 dark:text-gray-100 mb-3">
                اجزای تشکیل‌دهنده ({data!.component_count}/{data!.max_components})
              </h3>
              {data!.components.map((comp) => (
                <div key={comp.name}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs text-gray-600 dark:text-gray-400">
                      {comp.label_fa}
                      <span className="mr-1 text-[10px] text-gray-400">(وزن: {comp.weight}%)</span>
                    </span>
                    <span
                      className={cn("text-xs font-bold", getScoreColor(comp.score))}
                    >
                      {comp.score}
                    </span>
                  </div>
                  <div className="h-2 rounded-full bg-gray-200 dark:bg-gray-700">
                    <div
                      className={cn("h-full rounded-full transition-all duration-700", getBarColor(comp.score))}
                      style={{ width: `${comp.score}%` }}
                    />
                  </div>
                </div>
              ))}

              {data!.component_count < data!.max_components && (
                <p className="text-[11px] text-gray-400 mt-2">
                  {data!.max_components - data!.component_count} جزء در انتظار داده...
                </p>
              )}
            </div>
          </div>

          <div className="mt-4 rounded-lg border border-blue-500/20 bg-blue-500/5 p-3">
            <p className="text-xs text-blue-600 dark:text-blue-400">
              <span className="ml-1 font-bold">&#x26A1; چرا مهم است؟</span>
              این شاخص ترکیبی از ۶ عامل بنیادی (جریان ETF، موقعیت COT، نرخ بهره واقعی، قدرت دلار، ریسک بازار و شتاب قیمت) است.
              امتیاز بالای ۷۰ نشان‌دهنده شرایط بسیار صعودی و زیر ۳۰ نشان‌دهنده شرایط بسیار نزولی برای طلاست.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
