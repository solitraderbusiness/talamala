"use client";

import Link from "next/link";
import type { Alert } from "@/lib/api";
import { timeAgo, timeHorizonLabel, sectionLabel } from "@/lib/utils";
import SeverityBadge from "./SeverityBadge";

/** Check if a string is mostly Latin/English characters. */
function isLikelyEnglish(text: string): boolean {
  if (!text) return false;
  // Strip spaces, digits, and common punctuation
  const letters = text.replace(/[\s\d.,;:!?'"()\-\[\]{}/\\@#$%^&*+=<>|~`_]/g, "");
  if (!letters) return false;
  const latinCount = (letters.match(/[a-zA-Z]/g) || []).length;
  return latinCount / letters.length > 0.5;
}

/** Get the best display title — prefer Persian summary over English title. */
function getDisplayTitle(alert: Alert): string {
  if (isLikelyEnglish(alert.title) && alert.summary_fa && !isLikelyEnglish(alert.summary_fa)) {
    // Use first sentence of summary_fa as title (up to 120 chars)
    const firstSentence = alert.summary_fa.split(/[.۔。،؛]/)[0]?.trim();
    if (firstSentence && firstSentence.length > 10) {
      return firstSentence.length > 120 ? firstSentence.slice(0, 117) + "..." : firstSentence;
    }
    return alert.summary_fa.length > 120 ? alert.summary_fa.slice(0, 117) + "..." : alert.summary_fa;
  }
  return alert.title;
}

interface AlertCardProps {
  alert: Alert;
  compact?: boolean;
}

export default function AlertCard({ alert, compact = false }: AlertCardProps) {
  const displayTitle = getDisplayTitle(alert);
  const hasEnglishTitle = isLikelyEnglish(alert.title) && displayTitle !== alert.title;

  return (
    <Link href={`/alert/${alert.id}`}>
      <div className="card group cursor-pointer transition-shadow hover:shadow-md">
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
        <div className="mt-2 flex items-center gap-3 text-xs text-gray-500 dark:text-gray-500">
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
          {!compact && (
            <>
              <span className="text-gray-300 dark:text-gray-700">|</span>
              <span>اطمینان: {Math.round(alert.confidence * 100)}%</span>
            </>
          )}
        </div>
      </div>
    </Link>
  );
}
