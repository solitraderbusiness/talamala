"use client";

import { severityLabel, cn } from "@/lib/utils";

interface SeverityBadgeProps {
  severity: "critical" | "high" | "medium" | "low";
  className?: string;
}

export default function SeverityBadge({
  severity,
  className,
}: SeverityBadgeProps) {
  const colorMap: Record<string, string> = {
    critical:
      "bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400",
    high: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
    medium:
      "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400",
    low: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-400",
  };

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
        colorMap[severity] || colorMap.medium,
        className
      )}
    >
      {severityLabel(severity)}
    </span>
  );
}
