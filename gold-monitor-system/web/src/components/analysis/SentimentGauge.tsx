"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import type { SentimentGaugeResponse } from "@/lib/api";
import DataPending from "./DataPending";
import SkeletonCard from "./SkeletonCard";
import InfoTip from "@/components/InfoTip";

const LABEL_STYLES: Record<string, { color: string; bg: string }> = {
  very_bullish: { color: "text-emerald-500", bg: "bg-emerald-500" },
  bullish: { color: "text-emerald-400", bg: "bg-emerald-400" },
  neutral: { color: "text-gray-400", bg: "bg-gray-400" },
  bearish: { color: "text-red-400", bg: "bg-red-400" },
  very_bearish: { color: "text-red-500", bg: "bg-red-500" },
  pending: { color: "text-gray-400", bg: "bg-gray-400" },
};

function getScoreColor(score: number): string {
  if (score >= 60) return "text-emerald-400";
  if (score > 40) return "text-gray-400";
  return "text-red-400";
}

function getBarColor(score: number): string {
  if (score >= 60) return "bg-emerald-400";
  if (score > 40) return "bg-gray-400";
  return "bg-red-400";
}

function getBorderColor(score: number): string {
  if (score >= 60) return "border-emerald-500/40";
  if (score > 40) return "border-gray-400/40";
  return "border-red-500/40";
}

const COMPONENT_TERM_KEY: Record<string, string> = {
  etf_flows: "sentiment_etf_component",
  cot_positioning: "sentiment_cot_component",
  real_rates: "sentiment_real_rates_component",
  dollar_strength: "sentiment_dollar_component",
  risk_sentiment: "sentiment_risk_component",
  price_momentum: "sentiment_momentum_component",
};

interface Props {
  data: SentimentGaugeResponse | null;
  loading: boolean;
}

export default function SentimentGauge({ data, loading }: Props) {
  const hasData = data && data.composite_score != null;
  const [showExplain, setShowExplain] = useState(false);

  return (
    <div className="flex flex-col">
      <div className="mb-4 flex items-center gap-2">
        <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100">
          &#x1F3AF; سنجش احساسات بازار
        </h2>
        <InfoTip term="sentiment_index" />
      </div>

      {loading ? (
        <SkeletonCard className="h-40 flex-1" />
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
                  getBorderColor(data!.composite_score!),
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
              {data!.scoring_method && (
                <span className="mt-1 text-[9px] text-gray-400">
                  روش: درصدک تاریخی
                </span>
              )}
            </div>

            {/* Component breakdown */}
            <div className="flex-1 w-full space-y-2.5">
              <div className="mb-3 flex items-center justify-between">
                <h3 className="text-sm font-bold text-gray-900 dark:text-gray-100">
                  اجزای تشکیل‌دهنده ({data!.component_count}/{data!.max_components})
                </h3>
                <button
                  onClick={() => setShowExplain(!showExplain)}
                  className={cn(
                    "rounded-lg px-2.5 py-1 text-[10px] font-medium transition-colors",
                    showExplain
                      ? "bg-gold-100 text-gold-700 dark:bg-gold-900/30 dark:text-gold-400"
                      : "bg-gray-100 text-gray-500 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700"
                  )}
                >
                  {showExplain ? "بستن توضیحات" : "توضیح امتیازها"}
                </button>
              </div>
              {data!.components.map((comp) => (
                <div key={comp.name}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs text-gray-600 dark:text-gray-400">
                      {comp.label_fa}
                      <InfoTip term={COMPONENT_TERM_KEY[comp.name] || comp.name} />
                      <span className="mr-1 text-[10px] text-gray-400">(وزن: {comp.weight}%)</span>
                      {comp.stale && (
                        <span className="mr-1 rounded bg-amber-100 px-1 py-0.5 text-[9px] font-bold text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
                          قدیمی
                        </span>
                      )}
                      {comp.crowded && (
                        <span className="mr-1 rounded bg-orange-100 px-1 py-0.5 text-[9px] font-bold text-orange-700 dark:bg-orange-900/30 dark:text-orange-400">
                          اشباع
                        </span>
                      )}
                    </span>
                    <div className="flex items-center gap-1.5">
                      {comp.percentile != null && (
                        <span className="text-[9px] text-gray-400">
                          p{Math.round(comp.percentile * 100)}
                        </span>
                      )}
                      <span
                        className={cn("text-xs font-bold", getScoreColor(comp.score))}
                      >
                        {comp.score}
                      </span>
                    </div>
                  </div>
                  <div className="h-2 rounded-full bg-gray-200 dark:bg-gray-700">
                    <div
                      className={cn("h-full rounded-full transition-all duration-700", getBarColor(comp.score))}
                      style={{ width: `${comp.score}%` }}
                    />
                  </div>
                  {showExplain && comp.explanation && (
                    <div className="mt-1 space-y-1">
                      <p className="whitespace-pre-line rounded bg-gray-50 px-2 py-1.5 text-[10px] leading-relaxed text-gray-500 dark:bg-gray-800/50 dark:text-gray-400">
                        {comp.explanation}
                      </p>
                      {comp.debug?.score_semantics?.sentiment && (
                        <div className="rounded bg-blue-50 dark:bg-blue-900/20 px-2 py-1 text-[10px] text-blue-600 dark:text-blue-400">
                          <span className="font-bold ml-1">این امتیاز چگونه محاسبه شده؟</span>
                          {comp.debug.score_semantics.sentiment}
                          {comp.debug.zscore != null && (
                            <span className="mr-2 font-mono">(z: {comp.debug.zscore.toFixed(2)})</span>
                          )}
                          {comp.debug.source_url && (
                            <a href={comp.debug.source_url} target="_blank" rel="noopener noreferrer"
                               className="mr-2 text-blue-500 hover:underline">منبع</a>
                          )}
                        </div>
                      )}
                    </div>
                  )}
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
              هر عامل بر اساس درصدک تاریخی امتیازدهی می‌شود.
              امتیاز بالای ۶۰ = صعودی، زیر ۴۰ = نزولی، ۴۰-۶۰ = خنثی.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
