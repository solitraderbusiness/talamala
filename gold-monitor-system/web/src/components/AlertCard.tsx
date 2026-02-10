"use client";

import Link from "next/link";
import type { Alert } from "@/lib/api";
import { timeAgo } from "@/lib/utils";

/** Check if a string is mostly Latin/English characters. */
function isLikelyEnglish(text: string): boolean {
  if (!text) return false;
  const letters = text.replace(/[\s\d.,;:!?'"()\-\[\]{}/\\@#$%^&*+=<>|~`_]/g, "");
  if (!letters) return false;
  const latinCount = (letters.match(/[a-zA-Z]/g) || []).length;
  return latinCount / letters.length > 0.5;
}

/** Get the best display title — prefer Persian summary over English title. */
function getDisplayTitle(alert: Alert): string {
  if (isLikelyEnglish(alert.title) && alert.summary_fa && !isLikelyEnglish(alert.summary_fa)) {
    const firstSentence = alert.summary_fa.split(/[.۔。،؛]/)[0]?.trim();
    if (firstSentence && firstSentence.length > 10) {
      return firstSentence.length > 120 ? firstSentence.slice(0, 117) + "..." : firstSentence;
    }
    return alert.summary_fa.length > 120 ? alert.summary_fa.slice(0, 117) + "..." : alert.summary_fa;
  }
  return alert.title;
}

type Direction = "bullish" | "bearish" | "neutral";

const DIR_CONFIG: Record<Direction, { icon: string; label: string; color: string }> = {
  bullish: { icon: "▲", label: "صعودی", color: "text-emerald-500" },
  bearish: { icon: "▼", label: "نزولی", color: "text-red-500" },
  neutral: { icon: "◆", label: "خنثی", color: "text-gray-400 dark:text-gray-500" },
};

function scoreColor(score: number): string {
  if (score >= 70) return "text-emerald-500";
  if (score >= 58) return "text-emerald-400";
  if (score <= 30) return "text-red-500";
  if (score <= 42) return "text-red-400";
  return "text-gray-400 dark:text-gray-500";
}

function scoreBg(score: number): string {
  if (score >= 70) return "bg-emerald-500/15";
  if (score >= 58) return "bg-emerald-500/10";
  if (score <= 30) return "bg-red-500/15";
  if (score <= 42) return "bg-red-500/10";
  return "bg-gray-500/8";
}

interface AlertCardProps {
  alert: Alert;
  compact?: boolean;
}

export default function AlertCard({ alert, compact = false }: AlertCardProps) {
  const displayTitle = getDisplayTitle(alert);

  const direction: Direction =
    (alert.direction as Direction) || "neutral";
  const dir = DIR_CONFIG[direction];
  const score = alert.alert_score ?? 50;

  if (compact) {
    return (
      <Link href={`/alert/${alert.id}`}>
        <div className="group flex cursor-pointer items-center gap-3 px-4 py-2.5 transition-colors hover:bg-gray-50 dark:hover:bg-gray-800/50">
          {/* Score circle */}
          <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${scoreBg(score)}`}>
            <span className={`text-xs font-bold ${scoreColor(score)}`}>{score}</span>
          </div>
          {/* Title + source/time */}
          <div className="min-w-0 flex-1">
            <h3 className="truncate text-sm font-medium text-gray-900 group-hover:text-gold-600 dark:text-gray-100 dark:group-hover:text-gold-400">
              {displayTitle}
            </h3>
            <div className="mt-0.5 flex items-center gap-2 text-[10px] text-gray-400 dark:text-gray-500">
              <span>{alert.source_name}</span>
              <span>·</span>
              <span>{timeAgo(alert.timestamp_utc)}</span>
            </div>
          </div>
          {/* Direction */}
          <span className={`shrink-0 text-[11px] font-medium ${dir.color}`}>
            {dir.icon} {dir.label}
          </span>
        </div>
      </Link>
    );
  }

  return (
    <Link href={`/alert/${alert.id}`}>
      <div className="card group cursor-pointer transition-all hover:shadow-md">
        <div className="flex items-center gap-3">
          {/* Score circle */}
          <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${scoreBg(score)}`}>
            <span className={`text-sm font-bold ${scoreColor(score)}`}>{score}</span>
          </div>
          {/* Title + source/time */}
          <div className="min-w-0 flex-1">
            <h3 className="text-base font-semibold text-gray-900 group-hover:text-gold-600 dark:text-gray-100 dark:group-hover:text-gold-400">
              {displayTitle}
            </h3>
            <div className="mt-1 flex items-center gap-2 text-xs text-gray-500 dark:text-gray-500">
              <span>{alert.source_name}</span>
              <span className="text-gray-300 dark:text-gray-700">·</span>
              <span>{timeAgo(alert.timestamp_utc)}</span>
            </div>
          </div>
          {/* Direction label */}
          <span className={`shrink-0 text-xs font-medium ${dir.color}`}>
            {dir.icon} {dir.label}
          </span>
        </div>
      </div>
    </Link>
  );
}
