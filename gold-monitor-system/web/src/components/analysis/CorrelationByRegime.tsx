"use client";

import { useState, useEffect } from "react";
import { cn } from "@/lib/utils";
import DataPending from "./DataPending";
import SkeletonCard from "./SkeletonCard";
import InfoTip from "@/components/InfoTip";

/* ── Types ── */

interface CorrelationPairByRegime {
  pair_b: string;
  label_fa: string;
  avg_correlation: number;
  sample_count: number;
}

interface RegimeCorrelation {
  regime: string;
  pairs: CorrelationPairByRegime[];
}

interface CorrelationByRegimeData {
  regimes: RegimeCorrelation[];
}

/* ── Constants ── */

const REGIME_TABS: { key: string; label: string }[] = [
  { key: "expansion", label: "توسعه" },
  { key: "recovery", label: "بازیابی" },
  { key: "tightening", label: "انقباض" },
  { key: "stress", label: "بحران" },
];

const REGIME_COLORS: Record<string, { active: string; border: string; ring: string }> = {
  expansion: {
    active: "bg-emerald-500 text-white",
    border: "border-emerald-500",
    ring: "ring-emerald-500/20",
  },
  recovery: {
    active: "bg-blue-500 text-white",
    border: "border-blue-500",
    ring: "ring-blue-500/20",
  },
  tightening: {
    active: "bg-amber-500 text-white",
    border: "border-amber-500",
    ring: "ring-amber-500/20",
  },
  stress: {
    active: "bg-red-500 text-white",
    border: "border-red-500",
    ring: "ring-red-500/20",
  },
};

/* ── Helpers ── */

function getBarColor(corr: number): string {
  if (corr >= 0) return "bg-red-500";
  return "bg-blue-500";
}

function getTextColor(corr: number): string {
  if (corr >= 0) return "text-red-500";
  return "text-blue-500";
}

function getStrengthLabel(corr: number): string {
  const abs = Math.abs(corr);
  if (abs >= 0.7) return "قوی";
  if (abs >= 0.3) return "متوسط";
  return "ضعیف";
}

/* ── Component ── */

export default function CorrelationByRegime() {
  const [data, setData] = useState<CorrelationByRegimeData | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("expansion");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await fetch("/api/analysis/correlation-by-regime");
        if (!res.ok) throw new Error("fetch failed");
        const json: CorrelationByRegimeData = await res.json();
        if (!cancelled) {
          setData(json);
          // Default to first available regime
          if (json.regimes.length > 0) {
            setActiveTab(json.regimes[0].regime);
          }
        }
      } catch {
        if (!cancelled) setData(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  const hasData = data && data.regimes.length > 0;

  const activeRegime = data?.regimes.find((r) => r.regime === activeTab);
  const tabColors = REGIME_COLORS[activeTab] || REGIME_COLORS.expansion;

  return (
    <div className="flex flex-col">
      <div className="mb-4 flex items-center gap-2">
        <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100">
          &#x1F504; همبستگی بر اساس رژیم
        </h2>
        <InfoTip term="correlation_by_regime" />
      </div>

      {loading ? (
        <div className="space-y-3 flex-1">
          <SkeletonCard className="h-10" />
          <div className="grid gap-3 sm:grid-cols-2">
            {[1, 2, 3, 4].map((i) => (
              <SkeletonCard key={i} className="h-20" />
            ))}
          </div>
        </div>
      ) : !hasData ? (
        <DataPending message="در انتظار داده" />
      ) : (
        <div className="card flex-1">
          {/* ── Tabs ── */}
          <div className="mb-5 flex gap-2 overflow-x-auto">
            {REGIME_TABS.map((tab) => {
              const isActive = activeTab === tab.key;
              const colors = REGIME_COLORS[tab.key] || REGIME_COLORS.expansion;
              const regimeExists = data!.regimes.some((r) => r.regime === tab.key);

              return (
                <button
                  key={tab.key}
                  type="button"
                  disabled={!regimeExists}
                  onClick={() => setActiveTab(tab.key)}
                  className={cn(
                    "rounded-lg px-4 py-2 text-sm font-medium transition-all whitespace-nowrap",
                    isActive
                      ? cn(colors.active, "shadow-sm ring-2", colors.ring)
                      : regimeExists
                        ? "bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
                        : "bg-gray-50 text-gray-300 cursor-not-allowed dark:bg-gray-900 dark:text-gray-600",
                  )}
                >
                  {tab.label}
                </button>
              );
            })}
          </div>

          {/* ── Correlation Pairs for Active Tab ── */}
          {activeRegime && activeRegime.pairs.length > 0 ? (
            <div className="space-y-3">
              {activeRegime.pairs.map((pair) => (
                <div
                  key={pair.pair_b}
                  className="rounded-lg border border-gray-200 p-3 dark:border-gray-700"
                >
                  <div className="mb-2 flex items-center justify-between">
                    <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                      {pair.label_fa}
                    </span>
                    <div className="flex items-center gap-2">
                      <span className="text-[11px] text-gray-400">
                        {pair.sample_count} نمونه
                      </span>
                      <span
                        className={cn("text-sm font-bold", getTextColor(pair.avg_correlation))}
                        dir="ltr"
                      >
                        {pair.avg_correlation > 0 ? "+" : ""}
                        {pair.avg_correlation.toFixed(2)}
                      </span>
                    </div>
                  </div>

                  {/* Visual bar: center-based like CorrelationMatrix */}
                  <div className="relative h-3 rounded-full bg-gray-200 dark:bg-gray-700">
                    {/* Center line */}
                    <div className="absolute right-1/2 top-0 h-full w-0.5 bg-gray-400 dark:bg-gray-500" />
                    {/* Correlation bar */}
                    <div
                      className={cn(
                        "absolute top-0 h-full rounded-full transition-all duration-500",
                        getBarColor(pair.avg_correlation),
                      )}
                      style={{
                        width: `${Math.abs(pair.avg_correlation) * 50}%`,
                        ...(pair.avg_correlation >= 0
                          ? { right: "50%", borderTopRightRadius: 0, borderBottomRightRadius: 0 }
                          : { left: "50%", borderTopLeftRadius: 0, borderBottomLeftRadius: 0 }),
                      }}
                    />
                  </div>

                  <div className="mt-1 flex items-center justify-between text-[11px] text-gray-400">
                    <span>{getStrengthLabel(pair.avg_correlation)}</span>
                    <span className={getTextColor(pair.avg_correlation)}>
                      {pair.avg_correlation >= 0 ? "مثبت" : "منفی"}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="py-6 text-center text-sm text-gray-400">
              داده‌ای برای این رژیم موجود نیست.
            </p>
          )}

          {/* ── Legend ── */}
          <div className="mt-4 flex items-center justify-center gap-4 text-[11px] text-gray-400">
            <span className="flex items-center gap-1">
              <span className="inline-block h-2 w-2 rounded-full bg-blue-500" /> همبستگی منفی
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block h-2 w-2 rounded-full bg-red-500" /> همبستگی مثبت
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
