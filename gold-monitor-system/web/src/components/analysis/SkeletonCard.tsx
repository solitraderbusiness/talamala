"use client";

import { cn } from "@/lib/utils";

export default function SkeletonCard({ className = "" }: { className?: string }) {
  return (
    <div className={cn("card animate-pulse", className)}>
      <div className="h-4 w-1/3 rounded bg-gray-200 dark:bg-gray-700" />
      <div className="mt-3 h-8 w-1/2 rounded bg-gray-200 dark:bg-gray-700" />
      <div className="mt-2 h-3 w-2/3 rounded bg-gray-200 dark:bg-gray-700" />
      <div className="mt-2 h-3 w-1/2 rounded bg-gray-200 dark:bg-gray-700" />
    </div>
  );
}
