"use client";

import Link from "next/link";
import type { Alert } from "@/lib/api";
import { timeAgo, timeHorizonLabel, sectionLabel } from "@/lib/utils";
import SeverityBadge from "./SeverityBadge";

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

const SEVERITY_BORDER: Record<string, string> = {
  critical: "border-r-4 border-r-purple-600",
  high: "border-r-4 border-r-red-500",
  medium: "border-r-4 border-r-amber-500/40",
  low: "",
};

function scoreColor(score: number, isPriceReport: boolean): string {
  if (isPriceReport) return "text-gray-400 dark:text-gray-500";
  if (score >= 70) return "text-emerald-500";
  if (score >= 58) return "text-emerald-400";
  if (score <= 30) return "text-red-500";
  if (score <= 42) return "text-red-400";
  return "text-gray-400 dark:text-gray-500";
}

function scoreBg(score: number, isPriceReport: boolean): string {
  if (isPriceReport) return "bg-gray-500/8";
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
  const hasEnglishTitle = isLikelyEnglish(alert.title) && displayTitle !== alert.title;

  // Use server-provided direction and score (computed by direction.py)
  const direction: Direction =
    (alert.direction as Direction) || "neutral";
  const dir = DIR_CONFIG[direction];
  const score = alert.alert_score ?? 50;
  const isPriceReport = alert.news_type === "price_report";

  if (compact) {
    return (
      <Link href={`/alert/${alert.id}`}>
        <div className={`group flex cursor-pointer items-center gap-3 px-4 py-2.5 transition-colors hover:bg-gray-50 dark:hover:bg-gray-800/50 ${isPriceReport ? "opacity-60" : ""} ${SEVERITY_BORDER[alert.severity] || ""}`}>
          {/* Score circle */}
          <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${scoreBg(score, isPriceReport)}`}>
            <span className={`text-xs font-bold ${scoreColor(score, isPriceReport)}`}>{score}</span>
          </div>
          {/* Title + meta */}
          <div className="min-w-0 flex-1">
            <h3 className="truncate text-sm font-medium text-gray-900 group-hover:text-gold-600 dark:text-gray-100 dark:group-hover:text-gold-400">
              {displayTitle}
            </h3>
            <div className="mt-0.5 flex items-center gap-2 text-[10px] text-gray-400 dark:text-gray-500">
              {isPriceReport && (
                <span className="inline-flex items-center rounded-full bg-slate-100 px-1.5 py-0 text-[9px] font-medium text-slate-500 dark:bg-slate-800 dark:text-slate-400">
                  گزارش قیمت
                </span>
              )}
              <span>{alert.source_name}</span>
              <span>·</span>
              <span>{timeAgo(alert.timestamp_utc)}</span>
            </div>
          </div>
          {/* Direction + severity */}
          <div className="flex shrink-0 flex-col items-end gap-0.5">
            {isPriceReport ? (
              <span className="inline-flex items-center rounded-full bg-slate-100 px-1.5 py-0 text-[10px] font-medium text-slate-500 dark:bg-slate-800 dark:text-slate-400">
                قیمت
              </span>
            ) : (
              <SeverityBadge severity={alert.severity} className="!text-[10px] !px-1.5 !py-0" />
            )}
            {!isPriceReport && (
              <span className={`text-[10px] font-medium ${dir.color}`}>
                {dir.icon} {dir.label}
              </span>
            )}
          </div>
        </div>
      </Link>
    );
  }

  return (
    <Link href={`/alert/${alert.id}`}>
      <div
        className={`card group cursor-pointer transition-all hover:shadow-md ${isPriceReport ? "opacity-60" : ""} ${SEVERITY_BORDER[alert.severity] || ""}`}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <h3 className="text-base font-semibold text-gray-900 group-hover:text-gold-600 dark:text-gray-100 dark:group-hover:text-gold-400">
                {displayTitle}
              </h3>
              {isPriceReport && (
                <span className="inline-flex shrink-0 items-center rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-500 dark:bg-slate-800 dark:text-slate-400">
                  گزارش قیمت
                </span>
              )}
            </div>
            {hasEnglishTitle && (
              <p className="mt-0.5 text-xs text-gray-400 dark:text-gray-500" dir="ltr">
                {alert.title}
              </p>
            )}
            {!hasEnglishTitle && (
              <p className="mt-1 line-clamp-2 text-sm text-gray-600 dark:text-gray-400">
                {alert.summary_fa}
              </p>
            )}
          </div>
          {/* Score circle */}
          <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${scoreBg(score, isPriceReport)}`}>
            <span className={`text-sm font-bold ${scoreColor(score, isPriceReport)}`}>{score}</span>
          </div>
        </div>
        <div className="mt-2 flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-500">
            {isPriceReport ? (
              <span className="inline-flex items-center rounded-full bg-slate-100 px-1.5 py-0 text-[10px] font-medium text-slate-500 dark:bg-slate-800 dark:text-slate-400">
                قیمت
              </span>
            ) : (
              <SeverityBadge severity={alert.severity} className="!text-[10px] !px-1.5 !py-0" />
            )}
            {alert.section && (
              <>
                <span className="text-gray-300 dark:text-gray-700">|</span>
                <span className="text-[10px]">
                  {sectionLabel(alert.section)}
                </span>
              </>
            )}
            <span className="text-gray-300 dark:text-gray-700">|</span>
            <span>{alert.source_name}</span>
            <span className="text-gray-300 dark:text-gray-700">|</span>
            <span>{timeAgo(alert.timestamp_utc)}</span>
          </div>
          {/* Direction label */}
          {!isPriceReport && (
            <span className={`text-xs font-medium ${dir.color}`}>
              {dir.icon} {dir.label}
            </span>
          )}
        </div>
      </div>
    </Link>
  );
}
