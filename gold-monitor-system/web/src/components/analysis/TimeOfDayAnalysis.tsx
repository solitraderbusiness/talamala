"use client";

import { useState, useEffect } from "react";
import { cn } from "@/lib/utils";
import InfoTip from "@/components/InfoTip";
import SkeletonCard from "./SkeletonCard";
import DataPending from "./DataPending";

/* ── Types ── */

interface WeekdayData {
  day: number;
  day_fa: string;
  day_en: string;
  avg_range_usd: number;
  avg_return_pct: number;
  count: number;
}

interface SessionData {
  name: string;
  name_fa: string;
  avg_range_usd: number;
  avg_return_pct: number;
  share_pct?: number;
  note?: string;
}

interface TimeOfDayData {
  weekdays: WeekdayData[];
  sessions: SessionData[];
  daily_avg_range_usd?: number;
  daily_avg_return_pct?: number;
  data_days?: number;
  note?: string;
}

/* ── Helpers ── */

function heatmapColor(range: number, minRange: number, maxRange: number): string {
  if (maxRange === minRange) return "bg-red-200 dark:bg-red-900/30";
  const t = (range - minRange) / (maxRange - minRange);
  if (t >= 0.8) return "bg-red-600 dark:bg-red-500";
  if (t >= 0.6) return "bg-red-500 dark:bg-red-500/80";
  if (t >= 0.4) return "bg-red-400 dark:bg-red-400/70";
  if (t >= 0.2) return "bg-red-300 dark:bg-red-400/40";
  return "bg-red-200 dark:bg-red-400/20";
}

function heatmapTextColor(range: number, minRange: number, maxRange: number): string {
  if (maxRange === minRange) return "text-gray-700 dark:text-gray-300";
  const t = (range - minRange) / (maxRange - minRange);
  if (t >= 0.6) return "text-white dark:text-white";
  return "text-gray-700 dark:text-gray-200";
}

const SESSION_ICONS: Record<string, string> = {
  asia: "\u{1F30F}",
  london: "\u{1F30D}",
  new_york: "\u{1F30E}",
};

const SESSION_COLORS: Record<string, { border: string; bg: string; accent: string }> = {
  asia: {
    border: "border-blue-500/30",
    bg: "bg-blue-500/5 dark:bg-blue-500/10",
    accent: "text-blue-600 dark:text-blue-400",
  },
  london: {
    border: "border-amber-500/30",
    bg: "bg-amber-500/5 dark:bg-amber-500/10",
    accent: "text-amber-600 dark:text-amber-400",
  },
  new_york: {
    border: "border-emerald-500/30",
    bg: "bg-emerald-500/5 dark:bg-emerald-500/10",
    accent: "text-emerald-600 dark:text-emerald-400",
  },
};

/* ── Component ── */

export default function TimeOfDayAnalysis() {
  const [data, setData] = useState<TimeOfDayData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function fetchData() {
      try {
        const res = await fetch("/api/analysis/time-of-day");
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json: TimeOfDayData = await res.json();
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

  /* ── Header ── */
  const header = (
    <div className="mb-4 flex items-center gap-2">
      <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100">
        &#x1F551; تحلیل الگوی روزانه بازار طلا
      </h2>
      <InfoTip term="time_of_day" />
    </div>
  );

  /* ── Loading ── */
  if (loading) {
    return (
      <div className="flex flex-col">
        {header}
        <div className="space-y-4">
          <SkeletonCard className="h-32" />
          <div className="grid gap-3 sm:grid-cols-3">
            <SkeletonCard className="h-24" />
            <SkeletonCard className="h-24" />
            <SkeletonCard className="h-24" />
          </div>
        </div>
      </div>
    );
  }

  /* ── No data ── */
  if (!data || !data.weekdays || data.weekdays.length === 0) {
    return (
      <div className="flex flex-col">
        {header}
        <DataPending
          title="در انتظار داده"
          message="داده‌های تحلیل الگوی روزانه پس از جمع‌آوری کافی داده‌های قیمتی نمایش داده خواهند شد."
        />
      </div>
    );
  }

  /* ── Prepare weekday data ── */
  const ranges = data.weekdays.map((w) => w.avg_range_usd);
  const minRange = Math.min(...ranges);
  const maxRange = Math.max(...ranges);

  const mostActiveSession =
    data.sessions.length > 0
      ? data.sessions.reduce((max, s) => (s.avg_range_usd > max.avg_range_usd ? s : max))
      : null;

  return (
    <div className="flex flex-col">
      {header}

      <div className="card space-y-6 flex-1">
        {/* ── Section 1: Weekday Heatmap ── */}
        <div>
          <h3 className="mb-3 text-sm font-bold text-gray-700 dark:text-gray-300">
            نقشه حرارتی نوسان روزهای هفته
          </h3>

          <div className="grid grid-cols-5 gap-2">
            {data.weekdays.map((wd) => (
              <div
                key={wd.day}
                className={cn(
                  "flex flex-col items-center rounded-lg px-2 py-4 transition-colors",
                  heatmapColor(wd.avg_range_usd, minRange, maxRange),
                )}
                title={`${wd.day_en} | نوسان: $${wd.avg_range_usd.toFixed(1)} | بازده: ${wd.avg_return_pct >= 0 ? "+" : ""}${wd.avg_return_pct.toFixed(3)}% | ${wd.count} روز`}
              >
                <span
                  className={cn(
                    "text-sm font-bold",
                    heatmapTextColor(wd.avg_range_usd, minRange, maxRange),
                  )}
                >
                  {wd.day_fa}
                </span>
                <span
                  className={cn(
                    "mt-1 text-lg font-bold",
                    heatmapTextColor(wd.avg_range_usd, minRange, maxRange),
                  )}
                  dir="ltr"
                >
                  ${wd.avg_range_usd > 0 ? wd.avg_range_usd.toFixed(1) : "—"}
                </span>
                <span
                  className={cn(
                    "mt-0.5 text-[10px]",
                    heatmapTextColor(wd.avg_range_usd, minRange, maxRange),
                  )}
                  dir="ltr"
                >
                  {wd.avg_return_pct >= 0 ? "+" : ""}
                  {wd.avg_return_pct.toFixed(3)}%
                </span>
              </div>
            ))}
          </div>

          {/* Legend */}
          <div className="mt-2 flex items-center justify-between text-[10px] text-gray-400">
            <span>
              {data.data_days != null && `${data.data_days} روز داده`}
            </span>
            <div className="flex items-center gap-1">
              <span>کم</span>
              <div className="flex gap-0.5">
                <div className="h-2 w-4 rounded bg-red-200 dark:bg-red-400/20" />
                <div className="h-2 w-4 rounded bg-red-300 dark:bg-red-400/40" />
                <div className="h-2 w-4 rounded bg-red-400 dark:bg-red-400/70" />
                <div className="h-2 w-4 rounded bg-red-500 dark:bg-red-500/80" />
                <div className="h-2 w-4 rounded bg-red-600 dark:bg-red-500" />
              </div>
              <span>زیاد</span>
              <span className="mr-1">نوسان</span>
            </div>
          </div>
        </div>

        {/* ── Section 1.5: Daily stats ── */}
        {data.daily_avg_range_usd != null && (
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-lg border border-gray-100 p-3 text-center dark:border-gray-800">
              <span className="block text-[10px] text-gray-500 dark:text-gray-400">میانگین نوسان روزانه</span>
              <span className="text-xl font-bold text-gray-900 dark:text-gray-100" dir="ltr">
                ${data.daily_avg_range_usd.toFixed(1)}
              </span>
            </div>
            <div className="rounded-lg border border-gray-100 p-3 text-center dark:border-gray-800">
              <span className="block text-[10px] text-gray-500 dark:text-gray-400">میانگین بازده روزانه</span>
              <span
                className={cn(
                  "text-xl font-bold",
                  (data.daily_avg_return_pct ?? 0) > 0 ? "text-emerald-500" : (data.daily_avg_return_pct ?? 0) < 0 ? "text-red-500" : "text-gray-400",
                )}
                dir="ltr"
              >
                {(data.daily_avg_return_pct ?? 0) >= 0 ? "+" : ""}
                {(data.daily_avg_return_pct ?? 0).toFixed(3)}%
              </span>
            </div>
          </div>
        )}

        {/* ── Section 2: Session Comparison Cards ── */}
        {data.sessions.length > 0 && (
          <div>
            <h3 className="mb-3 text-sm font-bold text-gray-700 dark:text-gray-300">
              مقایسه جلسات معاملاتی (تخمینی)
              <InfoTip term="trading_session" />
            </h3>

            <div className="grid gap-3 sm:grid-cols-3">
              {data.sessions.map((session) => {
                const isActive = mostActiveSession?.name === session.name;
                const colors = SESSION_COLORS[session.name] || SESSION_COLORS.asia;
                const icon = SESSION_ICONS[session.name] || "\u{1F30F}";

                return (
                  <div
                    key={session.name}
                    className={cn(
                      "relative rounded-xl border p-4 transition-all",
                      isActive
                        ? `${colors.border} ${colors.bg} ring-1 ring-inset ring-current/5`
                        : "border-gray-100 dark:border-gray-800",
                    )}
                  >
                    {isActive && (
                      <span className={cn(
                        "absolute top-2 left-2 rounded-full px-2 py-0.5 text-[10px] font-bold",
                        colors.accent,
                        colors.bg,
                      )}>
                        فعال‌ترین
                      </span>
                    )}

                    <div className="flex items-center gap-2 mb-3">
                      <span className="text-xl">{icon}</span>
                      <span className={cn(
                        "text-sm font-bold",
                        isActive ? colors.accent : "text-gray-900 dark:text-gray-100",
                      )}>
                        {session.name_fa}
                      </span>
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <p className="text-[10px] text-gray-500 dark:text-gray-400">
                          تخمین نوسان
                        </p>
                        <p
                          className={cn(
                            "mt-0.5 text-lg font-bold",
                            isActive ? colors.accent : "text-gray-900 dark:text-gray-100",
                          )}
                          dir="ltr"
                        >
                          {session.avg_range_usd > 0 ? `$${session.avg_range_usd.toFixed(1)}` : "—"}
                        </p>
                      </div>
                      <div>
                        <p className="text-[10px] text-gray-500 dark:text-gray-400">
                          سهم از نوسان
                        </p>
                        <p
                          className={cn(
                            "mt-0.5 text-lg font-bold",
                            isActive ? colors.accent : "text-gray-900 dark:text-gray-100",
                          )}
                          dir="ltr"
                        >
                          {session.share_pct ?? "—"}%
                        </p>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* ── Note about estimates ── */}
        {data.note && (
          <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-2.5">
            <p className="text-[11px] text-amber-600 dark:text-amber-400">
              {data.note}
            </p>
          </div>
        )}

        {/* ── Info Box ── */}
        <div className="rounded-lg border border-blue-500/20 bg-blue-500/5 p-3">
          <p className="text-xs text-blue-600 dark:text-blue-400">
            <span className="ml-1 font-bold">&#x26A1; چرا مهم است؟</span>
            شناخت الگوی نوسان روزهای هفته به مدیریت ریسک کمک می‌کند.
            ساعات همپوشانی لندن و نیویورک (حدود ۱۶:۳۰ تا ۱۹:۳۰ تهران) معمولا بیشترین نقدینگی و نوسان را دارند.
            ساعات آسیایی معمولا آرام‌تر و مناسب معاملات محدوده‌ای هستند.
          </p>
        </div>
      </div>
    </div>
  );
}
