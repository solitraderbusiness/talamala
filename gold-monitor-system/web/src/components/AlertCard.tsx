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

/**
 * Determine per-alert gold market direction.
 * CONSERVATIVE: only marks bullish/bearish when there's strong gold-specific
 * evidence. Defaults to neutral — most news is neutral.
 */
function getAlertDirection(alert: Alert): Direction {
  // 1. Check expected_impact for explicit direction
  const impacts = alert.expected_impact || [];
  if (impacts.length > 0) {
    const hasUp = impacts.some((i) => i.direction === "up");
    const hasDown = impacts.some((i) => i.direction === "down");
    if (hasUp && !hasDown) return "bullish";
    if (hasDown && !hasUp) return "bearish";
  }

  // 2. Gold-specific keyword analysis — ONLY strong signals
  const text = ((alert.title || "") + " " + (alert.summary_fa || "")).toLowerCase();

  // Must be gold-specific, not generic economic terms
  const bullishPatterns = [
    // English: gold going up
    "gold rises", "gold surges", "gold rallies", "gold jumps", "gold soars",
    "gold climbs", "gold gains", "gold hits record", "gold all-time high",
    "gold safe haven", "gold demand",
    // English: rate cuts (bullish for gold)
    "rate cut", "dovish",
    // Persian: gold going up
    "طلا صعود", "طلا افزایش یافت", "قیمت طلا بالا", "رشد قیمت طلا",
    "رکورد قیمت طلا", "رکورد طلا", "جهش طلا", "جهش قیمت طلا",
    "طلا رشد کرد", "بازگشت طلا به بالا", "رشد طلا",
    // Persian: rate cut
    "کاهش نرخ بهره",
  ];

  const bearishPatterns = [
    // English: gold going down
    "gold falls", "gold drops", "gold slips", "gold declines", "gold plunges",
    "gold sinks", "gold crashes", "gold slides", "gold retreats",
    // English: rate hikes (bearish for gold)
    "rate hike", "hawkish", "stronger dollar",
    // Persian: gold going down
    "طلا نزول", "طلا کاهش یافت", "قیمت طلا پایین", "کاهش قیمت طلا",
    "افت طلا", "سقوط طلا", "ریزش طلا", "افت قیمت طلا",
    // Persian: rate hike / strong dollar
    "افزایش نرخ بهره", "تقویت دلار",
  ];

  const hasBull = bullishPatterns.some((p) => text.includes(p));
  const hasBear = bearishPatterns.some((p) => text.includes(p));

  if (hasBull && !hasBear) return "bullish";
  if (hasBear && !hasBull) return "bearish";
  return "neutral";
}

/**
 * Compute a 0-100 per-alert sentiment score.
 * Uses direction + severity + actual confidence for variance.
 * 50 = neutral, >50 = bullish for gold, <50 = bearish for gold.
 */
function getAlertScore(direction: Direction, severity: string, confidence: number): number {
  if (direction === "neutral") {
    // Neutral still varies slightly by severity
    const nudge: Record<string, number> = { high: 3, medium: 0, low: -2 };
    return 50 + (nudge[severity] || 0);
  }

  const sign = direction === "bullish" ? 1 : -1;
  // confidence ranges 0.30-0.95, map to 10-30 range for the shift
  const confShift = 10 + (confidence - 0.3) * (20 / 0.65);
  const sevBonus: Record<string, number> = { high: 10, medium: 5, low: 0 };
  const score = 50 + sign * (confShift + (sevBonus[severity] || 0));
  return Math.round(Math.max(0, Math.min(100, score)));
}

const DIR_CONFIG: Record<Direction, { icon: string; label: string; color: string }> = {
  bullish: { icon: "▲", label: "صعودی", color: "text-emerald-500" },
  bearish: { icon: "▼", label: "نزولی", color: "text-red-500" },
  neutral: { icon: "◆", label: "خنثی", color: "text-gray-400 dark:text-gray-500" },
};

const SEVERITY_BORDER: Record<string, string> = {
  high: "border-r-4 border-r-red-500",
  medium: "border-r-4 border-r-amber-500/40",
  low: "",
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
  const hasEnglishTitle = isLikelyEnglish(alert.title) && displayTitle !== alert.title;
  const direction = getAlertDirection(alert);
  const dir = DIR_CONFIG[direction];
  const score = getAlertScore(direction, alert.severity, alert.confidence);

  if (compact) {
    return (
      <Link href={`/alert/${alert.id}`}>
        <div className={`group flex cursor-pointer items-center gap-3 px-4 py-2.5 transition-colors hover:bg-gray-50 dark:hover:bg-gray-800/50 ${SEVERITY_BORDER[alert.severity] || ""}`}>
          {/* Score circle */}
          <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${scoreBg(score)}`}>
            <span className={`text-xs font-bold ${scoreColor(score)}`}>{score}</span>
          </div>
          {/* Title + meta */}
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
          {/* Direction + severity */}
          <div className="flex shrink-0 flex-col items-end gap-0.5">
            <SeverityBadge severity={alert.severity} className="!text-[10px] !px-1.5 !py-0" />
            <span className={`text-[10px] font-medium ${dir.color}`}>
              {dir.icon} {dir.label}
            </span>
          </div>
        </div>
      </Link>
    );
  }

  return (
    <Link href={`/alert/${alert.id}`}>
      <div
        className={`card group cursor-pointer transition-all hover:shadow-md ${SEVERITY_BORDER[alert.severity] || ""}`}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <h3 className="text-base font-semibold text-gray-900 group-hover:text-gold-600 dark:text-gray-100 dark:group-hover:text-gold-400">
              {displayTitle}
            </h3>
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
          <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${scoreBg(score)}`}>
            <span className={`text-sm font-bold ${scoreColor(score)}`}>{score}</span>
          </div>
        </div>
        <div className="mt-2 flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-500">
            <SeverityBadge severity={alert.severity} className="!text-[10px] !px-1.5 !py-0" />
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
          <span className={`text-xs font-medium ${dir.color}`}>
            {dir.icon} {dir.label}
          </span>
        </div>
      </div>
    </Link>
  );
}
