"use client";

import Link from "next/link";
import type { Alert } from "@/lib/api";
import { timeAgo, timeHorizonLabel } from "@/lib/utils";
import SeverityBadge from "./SeverityBadge";

interface AlertCardProps {
  alert: Alert;
  compact?: boolean;
}

export default function AlertCard({ alert, compact = false }: AlertCardProps) {
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
              {alert.title}
            </h3>
            {!compact && (
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
