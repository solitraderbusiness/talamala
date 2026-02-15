"use client";

import { useState, useEffect } from "react";
import { cn } from "@/lib/utils";
import DataPending from "./DataPending";
import SkeletonCard from "./SkeletonCard";
import InfoTip from "@/components/InfoTip";

/* ── Types ── */

interface EventRanking {
  category: string;
  event_name: string;
  avg_abs_move_4h: number;
  avg_move_4h: number;
  count: number;
}

interface EventImpactResponse {
  rankings: EventRanking[];
}

/* ── Component ── */

export default function EventImpactTracker() {
  const [data, setData] = useState<EventImpactResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function fetchData() {
      try {
        const res = await fetch("/api/analysis/event-impact/rankings");
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json: EventImpactResponse = await res.json();
        if (!cancelled) setData(json);
      } catch {
        if (!cancelled) setData(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    fetchData();
    return () => {
      cancelled = true;
    };
  }, []);

  const hasData = data && data.rankings.length > 0;

  // Sort by avg_abs_move_4h descending
  const sorted = hasData
    ? [...data!.rankings].sort((a, b) => b.avg_abs_move_4h - a.avg_abs_move_4h)
    : [];

  return (
    <div className="flex flex-col">
      <div className="mb-4 flex items-center gap-2">
        <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100">
          &#x1F4CA; تاثیر رویدادها بر طلا
        </h2>
        <InfoTip term="event_impact" />
      </div>

      {loading ? (
        <div className="space-y-3 flex-1">
          {[1, 2, 3, 4].map((i) => (
            <SkeletonCard key={i} className="h-12" />
          ))}
        </div>
      ) : !hasData ? (
        <DataPending message="در انتظار داده" />
      ) : (
        <div className="flex flex-col flex-1 gap-3">
          <div className="card overflow-hidden flex-1">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 dark:border-gray-800">
                  <th className="px-4 py-3 text-right text-xs font-bold text-gray-500 dark:text-gray-400">
                    #
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-bold text-gray-500 dark:text-gray-400">
                    رویداد
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-bold text-gray-500 dark:text-gray-400">
                    دسته‌بندی
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-bold text-gray-500 dark:text-gray-400">
                    میانگین حرکت مطلق (۴ ساعته)
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-bold text-gray-500 dark:text-gray-400">
                    میانگین جهت حرکت
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-bold text-gray-500 dark:text-gray-400">
                    تعداد
                  </th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((item, idx) => {
                  const moveColor =
                    item.avg_move_4h > 0
                      ? "text-emerald-500"
                      : item.avg_move_4h < 0
                        ? "text-red-500"
                        : "text-gray-400";
                  const moveSign = item.avg_move_4h > 0 ? "+" : "";

                  return (
                    <tr
                      key={`${item.category}-${item.event_name}`}
                      className="border-b border-gray-50 transition-colors hover:bg-gray-50/50 dark:border-gray-800/50 dark:hover:bg-gray-800/30"
                    >
                      <td className="px-4 py-2.5 text-xs text-gray-400">
                        {idx + 1}
                      </td>
                      <td className="px-4 py-2.5 font-medium text-gray-900 dark:text-gray-100">
                        {item.event_name}
                      </td>
                      <td className="px-4 py-2.5 text-xs text-gray-500 dark:text-gray-400">
                        {item.category}
                      </td>
                      <td className="px-4 py-2.5 text-left" dir="ltr">
                        <div className="flex items-center gap-2">
                          <div className="h-2 flex-1 max-w-[80px] rounded-full bg-gray-200 dark:bg-gray-700">
                            <div
                              className="h-full rounded-full bg-amber-500 transition-all duration-500"
                              style={{
                                width: `${Math.min(
                                  100,
                                  (item.avg_abs_move_4h /
                                    Math.max(...sorted.map((s) => s.avg_abs_move_4h))) *
                                    100
                                )}%`,
                              }}
                            />
                          </div>
                          <span className="text-xs font-bold text-gray-700 dark:text-gray-300">
                            {item.avg_abs_move_4h.toFixed(2)}%
                          </span>
                        </div>
                      </td>
                      <td
                        className={cn(
                          "px-4 py-2.5 text-left text-xs font-bold",
                          moveColor
                        )}
                        dir="ltr"
                      >
                        {moveSign}{item.avg_move_4h.toFixed(2)}%
                      </td>
                      <td className="px-4 py-2.5 text-left text-xs text-gray-500 dark:text-gray-400">
                        {item.count}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="rounded-lg border border-blue-500/20 bg-blue-500/5 p-3">
            <p className="text-xs text-blue-600 dark:text-blue-400">
              <span className="ml-1 font-bold">&#x26A1; چرا مهم است؟</span>
              این جدول نشان می‌دهد هر رویداد اقتصادی به‌طور میانگین چقدر بر قیمت طلا تاثیر گذاشته
              است. رویدادهای بالای جدول بیشترین نوسان را ایجاد کرده‌اند. رنگ سبز نشان‌دهنده تاثیر
              صعودی و رنگ قرمز نشان‌دهنده تاثیر نزولی بر طلاست.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
