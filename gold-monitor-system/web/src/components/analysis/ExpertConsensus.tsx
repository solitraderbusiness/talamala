"use client";

import { useState, useEffect } from "react";
import { cn } from "@/lib/utils";
import DataPending from "./DataPending";
import SkeletonCard from "./SkeletonCard";
import InfoTip from "@/components/InfoTip";

/* ── Types ── */

interface PeriodCounts {
  bullish: number;
  bearish: number;
  neutral: number;
  mixed: number;
}

interface ExpertConsensusData {
  period_7d: PeriodCounts;
  period_30d: PeriodCounts;
  total_articles: number;
  total_videos: number;
}

/* ── Constants ── */

const OUTLOOK_LABELS: Record<keyof PeriodCounts, { fa: string; color: string; bg: string }> = {
  bullish: { fa: "صعودی", color: "text-emerald-500", bg: "bg-emerald-500" },
  bearish: { fa: "نزولی", color: "text-red-500", bg: "bg-red-500" },
  neutral: { fa: "خنثی", color: "text-gray-400", bg: "bg-gray-400" },
  mixed: { fa: "مختلط", color: "text-amber-500", bg: "bg-amber-500" },
};

/* ── Helpers ── */

function totalOf(p: PeriodCounts): number {
  return p.bullish + p.bearish + p.neutral + p.mixed;
}

function pct(value: number, total: number): number {
  if (total === 0) return 0;
  return Math.round((value / total) * 100);
}

/* ── Component ── */

export default function ExpertConsensus() {
  const [data, setData] = useState<ExpertConsensusData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await fetch("/api/analysis/expert-consensus");
        if (!res.ok) throw new Error("fetch failed");
        const json: ExpertConsensusData = await res.json();
        if (!cancelled) setData(json);
      } catch {
        if (!cancelled) setData(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  const hasData = data && totalOf(data.period_7d) > 0;

  return (
    <div className="flex flex-col">
      <div className="mb-4 flex items-center gap-2">
        <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100">
          &#x1F4CA; اجماع تحلیلگران
        </h2>
        <InfoTip term="expert_consensus" />
      </div>

      {loading ? (
        <SkeletonCard className="h-48 flex-1" />
      ) : !hasData ? (
        <DataPending message="در انتظار داده" />
      ) : (
        <div className="card flex-1">
          {/* ── Main Gauge: 7-day stacked bar ── */}
          {(() => {
            const p = data!.period_7d;
            const total = totalOf(p);
            const bullishPct = pct(p.bullish, total);
            const bearishPct = pct(p.bearish, total);
            const neutralPct = pct(p.neutral + p.mixed, total);

            return (
              <div className="mb-6">
                <div className="mb-2 flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
                  <span>
                    <span className="font-bold text-emerald-500">{bullishPct}%</span>{" "}
                    صعودی
                  </span>
                  <span className="text-gray-400">
                    ۷ روز گذشته ({total} تحلیل)
                  </span>
                  <span>
                    نزولی{" "}
                    <span className="font-bold text-red-500">{bearishPct}%</span>
                  </span>
                </div>
                <div className="flex h-5 w-full overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
                  {bullishPct > 0 && (
                    <div
                      className="bg-emerald-500 transition-all duration-500"
                      style={{ width: `${bullishPct}%` }}
                    />
                  )}
                  {neutralPct > 0 && (
                    <div
                      className="bg-gray-400 transition-all duration-500"
                      style={{ width: `${neutralPct}%` }}
                    />
                  )}
                  {bearishPct > 0 && (
                    <div
                      className="bg-red-500 transition-all duration-500"
                      style={{ width: `${bearishPct}%` }}
                    />
                  )}
                </div>
                <div className="mt-1 flex items-center justify-center gap-4 text-[11px] text-gray-400">
                  <span className="flex items-center gap-1">
                    <span className="inline-block h-2 w-2 rounded-full bg-emerald-500" /> صعودی
                  </span>
                  <span className="flex items-center gap-1">
                    <span className="inline-block h-2 w-2 rounded-full bg-gray-400" /> خنثی/مختلط
                  </span>
                  <span className="flex items-center gap-1">
                    <span className="inline-block h-2 w-2 rounded-full bg-red-500" /> نزولی
                  </span>
                </div>
              </div>
            );
          })()}

          {/* ── Comparison Cards: 7d vs 30d ── */}
          <div className="grid gap-4 sm:grid-cols-2">
            {(["period_7d", "period_30d"] as const).map((periodKey) => {
              const p = data![periodKey];
              const total = totalOf(p);
              const label = periodKey === "period_7d" ? "۷ روز" : "۳۰ روز";

              return (
                <div
                  key={periodKey}
                  className="rounded-lg border border-gray-200 p-4 dark:border-gray-700"
                >
                  <div className="mb-3 flex items-center justify-between">
                    <h3 className="text-sm font-bold text-gray-900 dark:text-gray-100">
                      {label} گذشته
                    </h3>
                    <span className="text-xs text-gray-400">{total} تحلیل</span>
                  </div>
                  <div className="space-y-2">
                    {(Object.keys(OUTLOOK_LABELS) as (keyof PeriodCounts)[]).map((key) => {
                      const count = p[key];
                      const percentage = pct(count, total);
                      const style = OUTLOOK_LABELS[key];
                      return (
                        <div key={key}>
                          <div className="mb-1 flex items-center justify-between">
                            <span className={cn("text-xs font-medium", style.color)}>
                              {style.fa}
                            </span>
                            <span className="text-xs text-gray-500 dark:text-gray-400" dir="ltr">
                              {count} ({percentage}%)
                            </span>
                          </div>
                          <div className="h-2 rounded-full bg-gray-200 dark:bg-gray-700">
                            <div
                              className={cn("h-full rounded-full transition-all duration-500", style.bg)}
                              style={{ width: `${percentage}%` }}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>

          {/* ── Source Counts ── */}
          <div className="mt-4 flex items-center justify-center gap-6 text-xs text-gray-500 dark:text-gray-400">
            <span>
              مقالات:{" "}
              <span className="font-bold text-gray-700 dark:text-gray-200">
                {data!.total_articles}
              </span>
            </span>
            <span>
              ویدئوها:{" "}
              <span className="font-bold text-gray-700 dark:text-gray-200">
                {data!.total_videos}
              </span>
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
