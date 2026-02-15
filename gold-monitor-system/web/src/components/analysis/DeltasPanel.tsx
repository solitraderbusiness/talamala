"use client";

import { cn } from "@/lib/utils";
import type { DeltasResponse, DeltaItem } from "@/lib/api";
import SkeletonCard from "./SkeletonCard";
import InfoTip from "@/components/InfoTip";

/* ── Helpers ── */

function arrowChar(direction: string): string {
  if (direction === "up") return "\u25B2";
  if (direction === "down") return "\u25BC";
  return "\u25AC";
}

function changeColor(impact: string | undefined, direction: string): string {
  // Color based on gold impact, not raw direction
  if (impact === "bullish") return "text-emerald-500";
  if (impact === "bearish") return "text-red-500";
  return "text-gray-400";
}

function isSignificant(item: DeltaItem): boolean {
  // Highlight if 1d change is large relative to context
  if (item.change_1d == null) return false;
  if (item.unit === "score") return Math.abs(item.change_1d) >= 5;
  if (item.unit === "%") return Math.abs(item.change_1d) >= 0.05;
  if (item.unit === "$") return Math.abs(item.change_1d) >= 20;
  if (item.unit === "tonnes") return Math.abs(item.change_1d) >= 2;
  if (item.unit === "contracts") return Math.abs(item.change_1d) >= 10000;
  if (item.unit === "index") return Math.abs(item.change_1d) >= 0.5;
  return false;
}

function formatChange(val: number | null, unit: string): string {
  if (val == null) return "—";
  const sign = val > 0 ? "+" : "";
  switch (unit) {
    case "$":
      return `${sign}${val.toFixed(1)}`;
    case "%":
      return `${sign}${val.toFixed(2)}`;
    case "score":
      return `${sign}${val.toFixed(1)}`;
    case "tonnes":
      return `${sign}${val.toFixed(1)}t`;
    case "contracts":
      return `${sign}${(val / 1000).toFixed(1)}k`;
    case "index":
      return `${sign}${val.toFixed(2)}`;
    default:
      return `${sign}${val.toFixed(2)}`;
  }
}

function formatCurrent(val: number, unit: string): string {
  switch (unit) {
    case "$":
      return `$${val.toFixed(1)}`;
    case "%":
      return `${val.toFixed(2)}%`;
    case "score":
      return val.toFixed(0);
    case "tonnes":
      return `${val.toFixed(1)}t`;
    case "contracts":
      return val.toLocaleString();
    case "index":
      return val.toFixed(2);
    default:
      return val.toFixed(2);
  }
}

/* ── Component ── */

interface Props {
  data: DeltasResponse | null;
  loading: boolean;
}

export default function DeltasPanel({ data, loading }: Props) {
  if (loading) {
    return (
      <div>
        <div className="mb-3 flex items-center gap-2">
          <h2 className="text-base font-bold text-gray-900 dark:text-gray-100">
            چه تغییر کرده؟
          </h2>
        </div>
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <SkeletonCard key={i} className="h-20" />
          ))}
        </div>
      </div>
    );
  }

  if (!data || data.deltas.length === 0) {
    return null;
  }

  return (
    <div>
      <div className="mb-3 flex items-center gap-2">
        <h2 className="text-base font-bold text-gray-900 dark:text-gray-100">
          چه تغییر کرده؟
        </h2>
        <InfoTip term="deltas_today" />
      </div>

      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {data.deltas.map((item) => {
          const significant = isSignificant(item);
          const color1d = changeColor(item.gold_impact, item.direction);

          return (
            <div
              key={item.id}
              className={cn(
                "card rounded-lg px-3 py-2.5 transition-all",
                significant && "ring-1 ring-inset",
                significant && item.gold_impact === "bullish" && "ring-emerald-500/30",
                significant && item.gold_impact === "bearish" && "ring-red-500/30",
              )}
            >
              {/* Metric name */}
              <p className="text-[11px] font-medium text-gray-500 dark:text-gray-400 truncate">
                {item.label_fa}
              </p>

              {/* Current value */}
              <p
                className={cn(
                  "mt-0.5 text-lg font-bold text-gray-900 dark:text-gray-100",
                  significant && "font-black",
                )}
                dir="ltr"
              >
                {formatCurrent(item.current, item.unit)}
              </p>

              {/* Deltas row */}
              <div className="mt-1 flex items-center gap-3 text-xs" dir="ltr">
                {/* 1d change */}
                <span className={cn("flex items-center gap-0.5 font-medium", color1d)}>
                  <span className="text-[10px]">{arrowChar(item.direction)}</span>
                  {formatChange(item.change_1d, item.unit)}
                  <span className="text-[9px] opacity-60">1d</span>
                </span>

                {/* 5d change */}
                {item.change_5d != null && (
                  <span className="flex items-center gap-0.5 text-gray-400">
                    {formatChange(item.change_5d, item.unit)}
                    <span className="text-[9px] opacity-60">5d</span>
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
