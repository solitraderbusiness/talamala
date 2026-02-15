"use client";

import { useState, useEffect } from "react";
import { cn } from "@/lib/utils";
import InfoTip from "@/components/InfoTip";
import DataPending from "./DataPending";

/* -- Types --------------------------------------------------------- */

interface RegimeStats {
  regime: string;
  avg_daily_return_pct: number;
  win_rate: number;
  max_drawdown_pct: number;
  best_day_pct: number;
  worst_day_pct: number;
  total_days: number;
}

interface TransitionImpact {
  from_regime: string;
  to_regime: string;
  count: number;
  avg_change_5d_pct: number | null;
  avg_change_10d_pct: number | null;
  avg_change_20d_pct: number | null;
}

interface GoldPerformanceData {
  regimes: RegimeStats[];
}

interface TransitionsData {
  transitions: TransitionImpact[];
}

/* -- Helpers -------------------------------------------------------- */

const REGIME_LABELS: Record<string, string> = {
  expansion: "توسعه",
  recovery: "بازیابی",
  tightening: "انقباض",
  stress: "بحران",
};

const REGIME_DESCRIPTIONS: Record<string, string> = {
  expansion: "نقدینگی بالا، نرخ بهره پایین، رشد اقتصادی",
  recovery: "خروج از بحران، بهبود رشد",
  tightening: "نرخ بهره در حال افزایش، سیاست انقباضی",
  stress: "تنش اعتباری، فرار به سمت امنیت",
};

const REGIME_ICONS: Record<string, string> = {
  expansion: "🟢",
  recovery: "🔵",
  tightening: "🟡",
  stress: "🔴",
};

const REGIME_COLORS: Record<string, string> = {
  expansion: "border-emerald-500/40 bg-emerald-500/5",
  recovery: "border-blue-500/40 bg-blue-500/5",
  tightening: "border-amber-500/40 bg-amber-500/5",
  stress: "border-red-500/40 bg-red-500/5",
};

const REGIME_BADGE_COLORS: Record<string, string> = {
  expansion: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
  recovery: "bg-blue-500/10 text-blue-600 dark:text-blue-400",
  tightening: "bg-amber-500/10 text-amber-600 dark:text-amber-400",
  stress: "bg-red-500/10 text-red-600 dark:text-red-400",
};

function pctColor(val: number): string {
  if (val > 0) return "text-emerald-500";
  if (val < 0) return "text-red-500";
  return "text-gray-400";
}

function formatPct(val: number | null, digits = 2): string {
  if (val == null) return "—";
  const sign = val > 0 ? "+" : "";
  return `${sign}${val.toFixed(digits)}%`;
}

/* -- Component ------------------------------------------------------ */

export default function RegimeGoldPerformance() {
  const [perfData, setPerfData] = useState<GoldPerformanceData | null>(null);
  const [transData, setTransData] = useState<TransitionsData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchData() {
      try {
        const [perfRes, transRes] = await Promise.allSettled([
          fetch("/api/regime/gold-performance"),
          fetch("/api/regime/transitions"),
        ]);

        if (perfRes.status === "fulfilled" && perfRes.value.ok) {
          setPerfData(await perfRes.value.json());
        }
        if (transRes.status === "fulfilled" && transRes.value.ok) {
          setTransData(await transRes.value.json());
        }
      } catch {
        // silent
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, []);

  const header = (
    <div className="mb-4 flex items-center gap-2">
      <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100">
        عملکرد طلا در رژیم‌ها
      </h2>
      <InfoTip term="regime_gold_performance" />
    </div>
  );

  if (loading) {
    return (
      <div className="flex flex-col">
        {header}
        <div className="card space-y-4 flex-1">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {[...Array(4)].map((_, i) => (
              <div
                key={i}
                className="h-32 animate-pulse rounded-xl bg-gray-100 dark:bg-gray-800"
              />
            ))}
          </div>
        </div>
      </div>
    );
  }

  const hasPerf = perfData && perfData.regimes.length > 0;
  const hasTrans = transData && transData.transitions.length > 0;

  if (!hasPerf && !hasTrans) {
    return (
      <div className="flex flex-col">
        {header}
        <DataPending message="در انتظار داده..." />
      </div>
    );
  }

  // Find the best regime for gold (highest avg return)
  const bestRegime = hasPerf
    ? perfData.regimes.reduce((best, r) =>
        r.avg_daily_return_pct > best.avg_daily_return_pct ? r : best
      )
    : null;

  // Find best transition (highest 20d avg change)
  const bestTransition = hasTrans
    ? transData.transitions
        .filter((t) => t.avg_change_20d_pct != null)
        .reduce(
          (best, t) =>
            (t.avg_change_20d_pct ?? 0) > (best?.avg_change_20d_pct ?? -Infinity)
              ? t
              : best,
          null as TransitionImpact | null
        )
    : null;

  return (
    <div className="flex flex-col">
      {header}

      <div className="card space-y-5 flex-1">
      {/* Key Takeaway */}
      {bestRegime && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4">
          <p className="text-sm text-gray-700 dark:text-gray-300">
            <span className="ml-1 font-bold text-amber-600 dark:text-amber-400">
              نتیجه کلیدی:
            </span>
            بهترین عملکرد طلا در رژیم{" "}
            <span className="font-bold">
              {REGIME_ICONS[bestRegime.regime]}{" "}
              {REGIME_LABELS[bestRegime.regime]}
            </span>{" "}
            بوده با میانگین بازده روزانه{" "}
            <span className={cn("font-bold", pctColor(bestRegime.avg_daily_return_pct))} dir="ltr">
              {formatPct(bestRegime.avg_daily_return_pct, 3)}
            </span>{" "}
            و نرخ برد{" "}
            <span className="font-bold" dir="ltr">{bestRegime.win_rate.toFixed(0)}%</span>.
          </p>
        </div>
      )}

      {/* Regime Cards */}
      {hasPerf && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {perfData.regimes.map((r) => {
            const isBest = bestRegime?.regime === r.regime;
            return (
              <div
                key={r.regime}
                className={cn(
                  "relative rounded-xl border p-4 transition-all",
                  REGIME_COLORS[r.regime] ?? "border-gray-200 bg-gray-50",
                  isBest && "ring-2 ring-amber-400/50"
                )}
              >
                {isBest && (
                  <div className="absolute -top-2.5 left-3 rounded-full bg-amber-500 px-2 py-0.5 text-[10px] font-bold text-white">
                    بهترین برای طلا
                  </div>
                )}

                <div className="mb-1 text-base font-bold">
                  {REGIME_ICONS[r.regime]} {REGIME_LABELS[r.regime] ?? r.regime}
                </div>
                <p className="mb-3 text-[11px] leading-relaxed text-gray-500 dark:text-gray-400">
                  {REGIME_DESCRIPTIONS[r.regime]}
                </p>

                <div className="space-y-2 text-xs">
                  {/* Average daily return */}
                  <div className="flex items-center justify-between">
                    <span className="text-gray-500 dark:text-gray-400">بازده روزانه</span>
                    <span className={cn("font-mono font-bold", pctColor(r.avg_daily_return_pct))} dir="ltr">
                      {formatPct(r.avg_daily_return_pct, 3)}
                    </span>
                  </div>

                  {/* Win rate with visual bar */}
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-gray-500 dark:text-gray-400">نرخ برد</span>
                      <span className="font-mono font-bold" dir="ltr">
                        {r.win_rate.toFixed(0)}%
                      </span>
                    </div>
                    <div className="h-1.5 rounded-full bg-gray-200 dark:bg-gray-700">
                      <div
                        className={cn(
                          "h-full rounded-full",
                          r.win_rate >= 55 ? "bg-emerald-400" : r.win_rate >= 45 ? "bg-gray-400" : "bg-red-400"
                        )}
                        style={{ width: `${Math.min(r.win_rate, 100)}%` }}
                      />
                    </div>
                  </div>

                  {/* Max drawdown */}
                  <div className="flex items-center justify-between">
                    <span className="text-gray-500 dark:text-gray-400">حداکثر افت</span>
                    <span className="font-mono font-bold text-red-500" dir="ltr">
                      -{r.max_drawdown_pct.toFixed(1)}%
                    </span>
                  </div>

                  {/* Trading days */}
                  <div className="flex items-center justify-between pt-1 border-t border-gray-200/50 dark:border-gray-700/50">
                    <span className="text-gray-400">{r.total_days} روز</span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Transitions */}
      {hasTrans && (
        <div>
          <h3 className="mb-1 text-sm font-bold text-gray-700 dark:text-gray-300">
            وقتی رژیم عوض می‌شود، طلا چه می‌کند؟
            <InfoTip term="regime_transition" />
          </h3>
          <p className="mb-3 text-[11px] text-gray-400">
            میانگین تغییر قیمت طلا بعد از هر تغییر رژیم (بر اساس داده‌های تاریخی)
          </p>

          <div className="space-y-2">
            {transData.transitions.map((t, i) => {
              const change20d = t.avg_change_20d_pct;
              const isBestTrans = bestTransition && t.from_regime === bestTransition.from_regime && t.to_regime === bestTransition.to_regime;
              return (
                <div
                  key={i}
                  className={cn(
                    "flex flex-wrap items-center gap-3 rounded-lg px-3 py-2.5",
                    isBestTrans
                      ? "bg-amber-500/5 ring-1 ring-amber-500/20"
                      : "bg-gray-50 dark:bg-gray-800/50"
                  )}
                >
                  {/* Transition badge */}
                  <div className="flex items-center gap-1.5 min-w-[140px]">
                    <span className={cn("rounded-full px-2 py-0.5 text-[11px] font-bold", REGIME_BADGE_COLORS[t.from_regime])}>
                      {REGIME_LABELS[t.from_regime] ?? t.from_regime}
                    </span>
                    <span className="text-gray-400">→</span>
                    <span className={cn("rounded-full px-2 py-0.5 text-[11px] font-bold", REGIME_BADGE_COLORS[t.to_regime])}>
                      {REGIME_LABELS[t.to_regime] ?? t.to_regime}
                    </span>
                  </div>

                  {/* Count */}
                  <span className="text-[11px] text-gray-400">
                    {t.count}x
                  </span>

                  {/* Changes at different horizons */}
                  <div className="flex items-center gap-4 mr-auto" dir="ltr">
                    <div className="text-center">
                      <span className="block text-[9px] text-gray-400">۵ روز</span>
                      <span className={cn("block text-xs font-bold", t.avg_change_5d_pct != null ? pctColor(t.avg_change_5d_pct) : "text-gray-400")}>
                        {formatPct(t.avg_change_5d_pct)}
                      </span>
                    </div>
                    <div className="text-center">
                      <span className="block text-[9px] text-gray-400">۱۰ روز</span>
                      <span className={cn("block text-xs font-bold", t.avg_change_10d_pct != null ? pctColor(t.avg_change_10d_pct) : "text-gray-400")}>
                        {formatPct(t.avg_change_10d_pct)}
                      </span>
                    </div>
                    <div className="text-center">
                      <span className="block text-[9px] text-gray-400">۲۰ روز</span>
                      <span className={cn("block text-xs font-bold", change20d != null ? pctColor(change20d) : "text-gray-400")}>
                        {formatPct(change20d)}
                      </span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {bestTransition && bestTransition.avg_change_20d_pct != null && (
            <div className="mt-3 rounded-lg border border-blue-500/20 bg-blue-500/5 p-3">
              <p className="text-xs text-blue-600 dark:text-blue-400">
                <span className="ml-1 font-bold">نتیجه:</span>
                بیشترین بازده ۲۰ روزه بعد از تغییر از{" "}
                <span className="font-bold">{REGIME_LABELS[bestTransition.from_regime]}</span>
                {" "}به{" "}
                <span className="font-bold">{REGIME_LABELS[bestTransition.to_regime]}</span>
                {" "}بوده ({" "}
                <span className={cn("font-bold", pctColor(bestTransition.avg_change_20d_pct))} dir="ltr">
                  {formatPct(bestTransition.avg_change_20d_pct)}
                </span>
                {" "}در ۲۰ روز).
              </p>
            </div>
          )}
        </div>
      )}
      </div>
    </div>
  );
}
