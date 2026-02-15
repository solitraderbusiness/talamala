"use client";

import { cn } from "@/lib/utils";
import type { ActionSummaryResponse } from "@/lib/api";
import SkeletonCard from "./SkeletonCard";
import InfoTip from "@/components/InfoTip";

/* ── Helpers ── */

function biasColor(score: number | null): string {
  if (score == null) return "text-gray-400";
  if (score >= 65) return "text-emerald-500";
  if (score >= 55) return "text-emerald-400";
  if (score >= 45) return "text-gray-400";
  if (score >= 35) return "text-red-400";
  return "text-red-500";
}

function biasBorderColor(score: number | null): string {
  if (score == null) return "border-gray-300 dark:border-gray-600";
  if (score >= 55) return "border-emerald-500/40";
  if (score >= 45) return "border-gray-400/40";
  return "border-red-500/40";
}

function confidenceBadge(conf: string): { label: string; color: string } {
  switch (conf) {
    case "high":
      return { label: "اعتماد بالا", color: "bg-emerald-500/10 text-emerald-500 border-emerald-500/30" };
    case "medium":
      return { label: "اعتماد متوسط", color: "bg-amber-500/10 text-amber-500 border-amber-500/30" };
    default:
      return { label: "اعتماد پایین", color: "bg-red-500/10 text-red-500 border-red-500/30" };
  }
}

const TRIGGER_ICONS: Record<string, string> = {
  event: "\uD83D\uDCC5",
  level: "\uD83D\uDCC8",
  regime: "\u26A1",
};

/* ── Component ── */

interface Props {
  data: ActionSummaryResponse | null;
  loading: boolean;
}

export default function ActionBox({ data, loading }: Props) {
  if (loading) {
    return <SkeletonCard className="h-40" />;
  }

  if (!data || data.bias_score == null) {
    return null;
  }

  const conf = confidenceBadge(data.confidence);

  return (
    <div className={cn("card border-2 p-5", biasBorderColor(data.bias_score))}>
      <div className="mb-3 flex items-center gap-2">
        <h2 className="text-base font-bold text-gray-900 dark:text-gray-100">
          خلاصه اقدام
        </h2>
        <InfoTip term="action_summary" />
        <span className={cn("mr-auto rounded-full border px-2 py-0.5 text-[11px] font-medium", conf.color)}>
          {conf.label}
        </span>
      </div>

      <div className="grid gap-4 sm:grid-cols-[auto_1fr_auto]">
        {/* ── Left: Bias circle ── */}
        <div className="flex flex-col items-center gap-1">
          <div className={cn(
            "flex h-16 w-16 items-center justify-center rounded-full border-4",
            biasBorderColor(data.bias_score),
          )}>
            <span className={cn("text-2xl font-black", biasColor(data.bias_score))}>
              {data.bias_score}
            </span>
          </div>
          <span className={cn("text-xs font-bold", biasColor(data.bias_score))}>
            {data.bias_label_fa}
          </span>
        </div>

        {/* ── Center: Story + Stance ── */}
        <div className="flex flex-col justify-center gap-2">
          {data.story_fa && (
            <p className="text-sm text-gray-700 dark:text-gray-300">
              {data.story_fa}
            </p>
          )}
          {data.stance_fa && (
            <p className="rounded bg-gray-50 px-2 py-1 text-sm font-bold text-gray-900 dark:bg-gray-800 dark:text-gray-100">
              {data.stance_fa}
            </p>
          )}
        </div>

        {/* ── Right: Triggers ── */}
        {data.triggers.length > 0 && (
          <div className="flex flex-col gap-1.5">
            <span className="text-[10px] font-bold text-gray-500 dark:text-gray-400">محرک‌ها</span>
            {data.triggers.map((t, i) => (
              <div key={i} className="flex items-center gap-1.5 text-xs text-gray-600 dark:text-gray-400">
                <span>{TRIGGER_ICONS[t.type] || ""}</span>
                <span>{t.label_fa}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── Bottom bar: Range + Key levels ── */}
      <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-gray-100 pt-3 text-xs dark:border-gray-800">
        {data.expected_range_1d_usd != null && (
          <span className="text-gray-500 dark:text-gray-400">
            محدوده مورد انتظار:
            <span className="mr-1 font-bold text-gray-900 dark:text-gray-100" dir="ltr">
              ${data.expected_range_1d_usd}
            </span>
            {data.expected_range_1d_pct != null && (
              <span className="text-gray-400" dir="ltr">
                ({data.expected_range_1d_pct}%)
              </span>
            )}
          </span>
        )}
        {data.key_levels && (
          <>
            <span className="text-gray-400">|</span>
            <span className="text-gray-500 dark:text-gray-400">
              حمایت:
              <span className="mr-1 font-bold text-emerald-500" dir="ltr">
                {data.key_levels.supports.map((s) => `$${s}`).join(" · ")}
              </span>
            </span>
            <span className="text-gray-400">|</span>
            <span className="text-gray-500 dark:text-gray-400">
              مقاومت:
              <span className="mr-1 font-bold text-red-500" dir="ltr">
                {data.key_levels.resistances.map((r) => `$${r}`).join(" · ")}
              </span>
            </span>
            <span className="text-gray-400">|</span>
            <span className="text-gray-500 dark:text-gray-400">
              ابطال:
              <span className="mr-1 font-bold text-red-700 dark:text-red-400" dir="ltr">
                ${data.key_levels.invalidation}
              </span>
            </span>
          </>
        )}
        {data.confidence_reasons.length > 0 && (
          <>
            <span className="text-gray-400">|</span>
            <span className="text-[11px] text-gray-400">
              {data.confidence_reasons.join(" · ")}
            </span>
          </>
        )}
      </div>
    </div>
  );
}
