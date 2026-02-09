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

/** Determine per-alert market direction from impact data and title keywords. */
function getAlertDirection(alert: Alert): Direction {
  // 1. Check expected_impact for explicit direction
  const impacts = alert.expected_impact || [];
  if (impacts.length > 0) {
    const hasUp = impacts.some((i) => i.direction === "up");
    const hasDown = impacts.some((i) => i.direction === "down");
    if (hasUp && !hasDown) return "bullish";
    if (hasDown && !hasUp) return "bearish";
  }

  // 2. Keyword analysis on title + summary
  const text = ((alert.title || "") + " " + (alert.summary_fa || "")).toLowerCase();

  const bullishPatterns = [
    "rises", "rally", "surges", "gains", "climbs", "jumps", "soars",
    "record high", "rate cut", "dovish", "safe haven", "all-time high",
    "صعود", "افزایش قیمت", "رشد", "جهش", "بالا رفت", "رکورد",
    "کاهش نرخ بهره", "تحریم", "بازگشت به بالا",
  ];
  const bearishPatterns = [
    "falls", "drops", "slips", "declines", "plunges", "sinks", "crashes",
    "rate hike", "hawkish", "stronger dollar",
    "نزول", "کاهش قیمت", "افت", "سقوط", "ریزش", "افزایش نرخ بهره",
  ];

  const hasBull = bullishPatterns.some((p) => text.includes(p));
  const hasBear = bearishPatterns.some((p) => text.includes(p));

  if (hasBull && !hasBear) return "bullish";
  if (hasBear && !hasBull) return "bearish";
  return "neutral";
}

/** Compute a 0-100 per-alert sentiment score.
 *  50 = neutral, >50 = bullish for gold, <50 = bearish for gold. */
function getAlertScore(direction: Direction, severity: string): number {
  const directionBase: Record<Direction, number> = {
    bullish: 25,
    bearish: -25,
    neutral: 0,
  };
  const severityMult: Record<string, number> = {
    high: 1.5,
    medium: 1.0,
    low: 0.5,
  };
  const score = 50 + directionBase[direction] * (severityMult[severity] || 1.0);
  return Math.round(Math.max(0, Math.min(100, score)));
}

const DIR_CONFIG: Record<Direction, { icon: string; label: string; color: string }> = {
  bullish: { icon: "▲", label: "صعودی", color: "text-emerald-500" },
  bearish: { icon: "▼", label: "نزولی", color: "text-red-500" },
  neutral: { icon: "◆", label: "خنثی", color: "text-gray-400" },
};

const SEVERITY_BORDER: Record<string, string> = {
  high: "border-r-4 border-r-red-500",
  medium: "border-r-4 border-r-amber-500",
  low: "",
};

function scoreColor(score: number): string {
  if (score >= 65) return "text-emerald-500";
  if (score >= 55) return "text-emerald-400";
  if (score <= 35) return "text-red-500";
  if (score <= 45) return "text-red-400";
  return "text-gray-400";
}

function scoreBg(score: number): string {
  if (score >= 65) return "bg-emerald-500/10";
  if (score >= 55) return "bg-emerald-500/5";
  if (score <= 35) return "bg-red-500/10";
  if (score <= 45) return "bg-red-500/5";
  return "bg-gray-500/5";
}

interface AlertCardProps {
  alert: Alert;
  compact?: boolean;
}

export default function AlertCard({ alert, compact = false }: AlertCardProps) {
  const displayTitle = getDisplayTitle(alert);
  const hasEnglishTitle = isLikelyEnglish(alert.title) && displayTitle !== alert.title;
  const direction = getAlertDirection(alert);
  const dir = DIR_CONFIG[direction];
  const score = getAlertScore(direction, alert.severity);

  return (
    <Link href={`/alert/${alert.id}`}>
      <div
        className={`card group cursor-pointer transition-shadow hover:shadow-md ${SEVERITY_BORDER[alert.severity] || ""}`}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <h3
              className={`font-semibold text-gray-900 group-hover:text-gold-600 dark:text-gray-100 dark:group-hover:text-gold-400 ${
                compact ? "text-sm" : "text-base"
              }`}
            >
              {displayTitle}
            </h3>
            {hasEnglishTitle && !compact && (
              <p className="mt-0.5 text-xs text-gray-400 dark:text-gray-500" dir="ltr">
                {alert.title}
              </p>
            )}
            {!compact && !hasEnglishTitle && (
              <p className="mt-1 line-clamp-2 text-sm text-gray-600 dark:text-gray-400">
                {alert.summary_fa}
              </p>
            )}
          </div>
          <div className="flex shrink-0 flex-col items-end gap-1">
            <SeverityBadge severity={alert.severity} />
            <span className="text-xs text-gray-500 dark:text-gray-500">
              {timeHorizonLabel(alert.time_horizon)}
            </span>
          </div>
        </div>
        <div className="mt-2 flex items-center justify-between">
          <div className="flex items-center gap-3 text-xs text-gray-500 dark:text-gray-500">
            {alert.section && !compact && (
              <>
                <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] font-medium dark:bg-gray-800">
                  {sectionLabel(alert.section)}
                </span>
                <span className="text-gray-300 dark:text-gray-700">|</span>
              </>
            )}
            <span>{alert.source_name}</span>
            <span className="text-gray-300 dark:text-gray-700">|</span>
            <span>{timeAgo(alert.timestamp_utc)}</span>
          </div>
          {/* Per-alert sentiment score + direction */}
          <div className={`flex items-center gap-1.5 rounded-full px-2 py-0.5 ${scoreBg(score)}`}>
            <span className={`text-xs font-medium ${dir.color}`}>
              {dir.icon} {dir.label}
            </span>
            <span className={`text-xs font-bold ${scoreColor(score)}`}>
              {score}
            </span>
          </div>
        </div>
      </div>
    </Link>
  );
}
