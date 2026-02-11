"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import Link from "next/link";
import {
  getCalendarEvents,
  type CalendarEvent,
  type CalendarResponse,
} from "@/lib/api";
import { cn } from "@/lib/utils";

// ── Constants ────────────────────────────────────────────────────────

const ASSET_FILTERS = [
  { value: "all", label: "همه", icon: "📋" },
  { value: "xauusd", label: "طلای جهانی", icon: "🌍" },
  { value: "usd_irr", label: "دلار/ریال", icon: "💵" },
  { value: "coin", label: "سکه", icon: "🪙" },
  { value: "gold_fund", label: "صندوق طلا", icon: "📈" },
] as const;

const IMPACT_FILTERS = [
  { value: "all", label: "همه" },
  { value: "high", label: "بالا", color: "text-red-500" },
  { value: "medium", label: "متوسط", color: "text-orange-500" },
  { value: "low", label: "پایین", color: "text-green-500" },
] as const;

const VIEW_MODES = [
  { value: "list", label: "لیستی" },
  { value: "week", label: "هفتگی" },
] as const;

const IMPACT_COLORS: Record<string, string> = {
  high: "bg-red-500",
  medium: "bg-orange-500",
  low: "bg-green-500",
};

const IMPACT_BG: Record<string, string> = {
  high: "bg-red-500/10 border-red-500/30",
  medium: "bg-orange-500/10 border-orange-500/30",
  low: "bg-green-500/10 border-green-500/30",
};

const IMPACT_TEXT: Record<string, string> = {
  high: "text-red-500",
  medium: "text-orange-500",
  low: "text-green-500",
};

const IMPACT_LABEL: Record<string, string> = {
  high: "بالا",
  medium: "متوسط",
  low: "پایین",
};

const COUNTRY_FLAGS: Record<string, string> = {
  US: "\u{1F1FA}\u{1F1F8}",
  EU: "\u{1F1EA}\u{1F1FA}",
  GB: "\u{1F1EC}\u{1F1E7}",
  JP: "\u{1F1EF}\u{1F1F5}",
  CN: "\u{1F1E8}\u{1F1F3}",
  AU: "\u{1F1E6}\u{1F1FA}",
  CA: "\u{1F1E8}\u{1F1E6}",
  CH: "\u{1F1E8}\u{1F1ED}",
  NZ: "\u{1F1F3}\u{1F1FF}",
  IR: "\u{1F1EE}\u{1F1F7}",
  KR: "\u{1F1F0}\u{1F1F7}",
  DE: "\u{1F1E9}\u{1F1EA}",
  FR: "\u{1F1EB}\u{1F1F7}",
};

const ASSET_LABELS: Record<string, string> = {
  xauusd: "طلای جهانی",
  global_gold: "طلای جهانی",
  iran_gold: "طلای ایران",
  usd_irr: "دلار/ریال",
  coin: "سکه",
  gold_fund: "صندوق طلا",
};

// ── Helpers ──────────────────────────────────────────────────────────

function formatTehranTime(tehranStr: string): string {
  try {
    const dt = new Date(tehranStr);
    return new Intl.DateTimeFormat("fa-IR", {
      hour: "2-digit",
      minute: "2-digit",
    }).format(dt);
  } catch {
    return tehranStr;
  }
}

function formatTehranDate(tehranStr: string): string {
  try {
    const dt = new Date(tehranStr);
    return new Intl.DateTimeFormat("fa-IR", {
      weekday: "long",
      day: "numeric",
      month: "long",
    }).format(dt);
  } catch {
    return tehranStr;
  }
}

function getDateKey(tehranStr: string): string {
  try {
    const dt = new Date(tehranStr);
    return dt.toISOString().split("T")[0];
  } catch {
    return tehranStr;
  }
}

function groupEventsByDate(
  events: CalendarEvent[]
): Map<string, CalendarEvent[]> {
  const groups = new Map<string, CalendarEvent[]>();
  for (const event of events) {
    const key = getDateKey(event.datetime_tehran || event.datetime_utc);
    if (!groups.has(key)) {
      groups.set(key, []);
    }
    groups.get(key)!.push(event);
  }
  return groups;
}

function getWeekRange(offset: number): { from: string; to: string; label: string } {
  const now = new Date();
  const dayOfWeek = now.getDay();
  // Saturday-based week for Iran
  const satOffset = (dayOfWeek + 1) % 7;
  const weekStart = new Date(now);
  weekStart.setDate(now.getDate() - satOffset + offset * 7);
  const weekEnd = new Date(weekStart);
  weekEnd.setDate(weekStart.getDate() + 6);

  const from = weekStart.toISOString().split("T")[0];
  const to = weekEnd.toISOString().split("T")[0];

  const startLabel = new Intl.DateTimeFormat("fa-IR", {
    day: "numeric",
    month: "long",
  }).format(weekStart);
  const endLabel = new Intl.DateTimeFormat("fa-IR", {
    day: "numeric",
    month: "long",
  }).format(weekEnd);

  return { from, to, label: `${startLabel} - ${endLabel}` };
}

function isWithin2Hours(utcStr: string): boolean {
  try {
    const dt = new Date(utcStr);
    const now = new Date();
    const diff = dt.getTime() - now.getTime();
    return diff > 0 && diff < 2 * 60 * 60 * 1000;
  } catch {
    return false;
  }
}

// ── Components ──────────────────────────────────────────────────────

function CountdownTimer({ event }: { event: CalendarEvent }) {
  const [timeLeft, setTimeLeft] = useState(event.time_until || "");

  useEffect(() => {
    const interval = setInterval(() => {
      try {
        const dt = new Date(event.datetime_utc);
        const now = new Date();
        const diff = dt.getTime() - now.getTime();
        if (diff <= 0) {
          setTimeLeft("اکنون");
          clearInterval(interval);
          return;
        }
        const days = Math.floor(diff / 86400000);
        const hours = Math.floor((diff % 86400000) / 3600000);
        const minutes = Math.floor((diff % 3600000) / 60000);
        const parts = [];
        if (days > 0) parts.push(`${days} روز`);
        if (hours > 0) parts.push(`${hours} ساعت`);
        if (minutes > 0) parts.push(`${minutes} دقیقه`);
        setTimeLeft(parts.join(" و ") || "کمتر از یک دقیقه");
      } catch {
        setTimeLeft(event.time_until || "");
      }
    }, 60000);

    return () => clearInterval(interval);
  }, [event.datetime_utc, event.time_until]);

  return <span>{timeLeft}</span>;
}

function EventCard({
  event,
  expanded,
  onToggle,
}: {
  event: CalendarEvent;
  expanded: boolean;
  onToggle: () => void;
}) {
  const isPast = !event.is_upcoming;
  const isNear = isWithin2Hours(event.datetime_utc);

  return (
    <div
      onClick={onToggle}
      className={cn(
        "card cursor-pointer transition-all",
        isPast && "opacity-60",
        isNear && "ring-2 ring-gold-400/50 animate-subtle-pulse",
        expanded && "ring-2 ring-gold-500/40"
      )}
    >
      {/* Event header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          {/* Impact dot */}
          <div
            className={cn(
              "h-3 w-3 shrink-0 rounded-full",
              IMPACT_COLORS[event.impact] || "bg-gray-400"
            )}
            title={IMPACT_LABEL[event.impact]}
          />

          {/* Time */}
          <span className="text-sm font-mono text-gray-500 dark:text-gray-400 shrink-0">
            {formatTehranTime(event.datetime_tehran || event.datetime_utc)}
          </span>

          {/* Name */}
          <div className="min-w-0">
            <p className="font-medium text-gray-900 dark:text-gray-100 truncate">
              {event.event_name_fa !== event.event_name
                ? event.event_name_fa
                : event.event_name}
            </p>
            {event.event_name_fa !== event.event_name && (
              <p className="text-xs text-gray-500 dark:text-gray-400 truncate">
                {event.event_name}
              </p>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {/* Country flag */}
          <span className="text-lg" title={event.country}>
            {COUNTRY_FLAGS[event.country] || event.country}
          </span>

          {/* Currency */}
          <span className="text-xs px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400">
            {event.currency}
          </span>
        </div>
      </div>

      {/* Forecast / Previous / Actual row */}
      <div className="mt-2 flex items-center gap-4 text-sm">
        {event.forecast && (
          <span className="text-gray-500 dark:text-gray-400">
            پیش‌بینی: <span className="font-medium text-gray-700 dark:text-gray-300">{event.forecast}</span>
          </span>
        )}
        {event.previous && (
          <span className="text-gray-500 dark:text-gray-400">
            قبلی: <span className="font-medium text-gray-700 dark:text-gray-300">{event.previous}</span>
          </span>
        )}
        {event.actual && (
          <span className={cn(
            "font-bold",
            event.forecast && parseFloat(event.actual) > parseFloat(event.forecast)
              ? "text-green-500"
              : event.forecast && parseFloat(event.actual) < parseFloat(event.forecast)
                ? "text-red-500"
                : "text-gray-700 dark:text-gray-300"
          )}>
            واقعی: {event.actual}
          </span>
        )}

        {/* Time until */}
        {event.is_upcoming && event.time_until && (
          <span className="mr-auto text-xs text-gold-600 dark:text-gold-400">
            <CountdownTimer event={event} />
          </span>
        )}
      </div>

      {/* Asset tags */}
      {event.affected_assets && event.affected_assets.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {event.affected_assets.map((asset) => (
            <span
              key={asset}
              className="text-xs px-2 py-0.5 rounded-full bg-gold-100 text-gold-700 dark:bg-gold-900/30 dark:text-gold-400"
            >
              {ASSET_LABELS[asset] || asset}
            </span>
          ))}
        </div>
      )}

      {/* Expanded details */}
      {expanded && (
        <div className="mt-4 border-t border-gray-200 dark:border-gray-700 pt-4 space-y-3">
          {/* Data table */}
          <div className="grid grid-cols-3 gap-4 text-center">
            <div>
              <p className="text-xs text-gray-500 dark:text-gray-400">پیش‌بینی</p>
              <p className="text-lg font-bold text-gray-800 dark:text-gray-200">
                {event.forecast || "—"}
              </p>
            </div>
            <div>
              <p className="text-xs text-gray-500 dark:text-gray-400">قبلی</p>
              <p className="text-lg font-bold text-gray-800 dark:text-gray-200">
                {event.previous || "—"}
              </p>
            </div>
            <div>
              <p className="text-xs text-gray-500 dark:text-gray-400">واقعی</p>
              <p className={cn(
                "text-lg font-bold",
                event.actual
                  ? event.forecast && parseFloat(event.actual) > parseFloat(event.forecast)
                    ? "text-green-500"
                    : event.forecast && parseFloat(event.actual) < parseFloat(event.forecast)
                      ? "text-red-500"
                      : "text-gray-800 dark:text-gray-200"
                  : "text-gray-400"
              )}>
                {event.actual || "—"}
              </p>
            </div>
          </div>

          {/* Gold Impact Notes */}
          {event.gold_impact_note && (
            <div className="rounded-lg border border-gold-200 bg-gold-50 p-3 dark:border-gold-800 dark:bg-gold-900/20">
              <p className="text-sm font-medium text-gold-800 dark:text-gold-300 mb-2">
                تاثیر بر دارایی‌ها:
              </p>
              {event.gold_impact_note.above_forecast && (
                <p className="text-sm text-gray-700 dark:text-gray-300 mb-1">
                  <span className="text-red-500">&#9650; بالاتر از پیش‌بینی:</span>{" "}
                  {event.gold_impact_note.above_forecast}
                </p>
              )}
              {event.gold_impact_note.below_forecast && (
                <p className="text-sm text-gray-700 dark:text-gray-300 mb-1">
                  <span className="text-green-500">&#9660; پایین‌تر از پیش‌بینی:</span>{" "}
                  {event.gold_impact_note.below_forecast}
                </p>
              )}
              {event.gold_impact_note.hawkish && (
                <p className="text-sm text-gray-700 dark:text-gray-300 mb-1">
                  <span className="text-red-500">سختگیرانه:</span>{" "}
                  {event.gold_impact_note.hawkish}
                </p>
              )}
              {event.gold_impact_note.dovish && (
                <p className="text-sm text-gray-700 dark:text-gray-300">
                  <span className="text-green-500">انبساطی:</span>{" "}
                  {event.gold_impact_note.dovish}
                </p>
              )}
            </div>
          )}

          {/* Event metadata */}
          <div className="flex flex-wrap gap-3 text-xs text-gray-500 dark:text-gray-400">
            <span>منبع: {event.source}</span>
            <span>دسته: {event.category || "—"}</span>
            <span>
              زمان: {new Intl.DateTimeFormat("fa-IR", {
                weekday: "long",
                year: "numeric",
                month: "long",
                day: "numeric",
                hour: "2-digit",
                minute: "2-digit",
              }).format(new Date(event.datetime_tehran || event.datetime_utc))}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main Page ───────────────────────────────────────────────────────

export default function CalendarPage() {
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [counts, setCounts] = useState({ total: 0, high: 0, medium: 0, low: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [assetFilter, setAssetFilter] = useState("all");
  const [impactFilter, setImpactFilter] = useState("all");
  const [viewMode, setViewMode] = useState<"list" | "week">("list");
  const [weekOffset, setWeekOffset] = useState(0);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const weekRange = getWeekRange(weekOffset);

  const fetchEvents = useCallback(async () => {
    try {
      setError(null);
      const data = await getCalendarEvents({
        from: weekRange.from,
        to: weekRange.to,
        asset: assetFilter !== "all" ? assetFilter : undefined,
        impact: impactFilter !== "all" ? impactFilter : undefined,
      });
      setEvents(data.events || []);
      setCounts(data.counts || { total: 0, high: 0, medium: 0, low: 0 });
    } catch (err) {
      setError(err instanceof Error ? err.message : "خطا در بارگذاری تقویم");
    } finally {
      setLoading(false);
    }
  }, [weekRange.from, weekRange.to, assetFilter, impactFilter]);

  useEffect(() => {
    setLoading(true);
    fetchEvents();
  }, [fetchEvents]);

  // Auto-refresh every 5 minutes
  useEffect(() => {
    const interval = setInterval(fetchEvents, 300_000);
    return () => clearInterval(interval);
  }, [fetchEvents]);

  // Find next high-impact event for countdown
  const nextHighImpact = events.find(
    (e) => e.is_upcoming && e.impact === "high"
  );

  // Group by date for list/week views
  const grouped = groupEventsByDate(events);

  return (
    <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6 lg:px-8">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
          تقویم رویدادهای اقتصادی
        </h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          رویدادهای مهم اقتصادی که بر بازار طلا و ارز تاثیر می‌گذارند
        </p>
      </div>

      {/* Countdown Banner */}
      {nextHighImpact && (
        <div className="mb-6 rounded-xl border border-gold-300 bg-gradient-to-l from-gold-50 to-gold-100 px-4 py-3 dark:border-gold-700 dark:from-gold-900/20 dark:to-gold-900/40">
          <div className="flex items-center gap-3">
            <span className="text-xl">&#9201;</span>
            <div>
              <span className="text-sm font-bold text-gold-800 dark:text-gold-300">
                <CountdownTimer event={nextHighImpact} />
              </span>
              <span className="text-sm text-gold-700 dark:text-gold-400">
                {" "}تا{" "}
                {nextHighImpact.event_name_fa !== nextHighImpact.event_name
                  ? nextHighImpact.event_name_fa
                  : nextHighImpact.event_name}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="card mb-6 space-y-4">
        {/* Asset filters */}
        <div className="flex flex-wrap gap-2">
          <span className="text-sm text-gray-500 dark:text-gray-400 ml-2 self-center">
            دارایی:
          </span>
          {ASSET_FILTERS.map((f) => (
            <button
              key={f.value}
              onClick={() => setAssetFilter(f.value)}
              className={cn(
                "rounded-full px-3 py-1.5 text-sm font-medium transition-colors",
                assetFilter === f.value
                  ? "bg-gold-500 text-white"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700"
              )}
            >
              {f.icon} {f.label}
            </button>
          ))}
        </div>

        {/* Impact filters */}
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm text-gray-500 dark:text-gray-400 ml-2">
            اهمیت:
          </span>
          {IMPACT_FILTERS.map((f) => (
            <button
              key={f.value}
              onClick={() => setImpactFilter(f.value)}
              className={cn(
                "rounded-full px-3 py-1.5 text-sm font-medium transition-colors",
                impactFilter === f.value
                  ? "bg-gold-500 text-white"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700"
              )}
            >
              {f.value !== "all" && (
                <span className={cn("inline-block h-2 w-2 rounded-full ml-1", IMPACT_COLORS[f.value])} />
              )}
              {f.label}
            </button>
          ))}

          {/* View mode toggle */}
          <div className="mr-auto flex gap-1">
            {VIEW_MODES.map((v) => (
              <button
                key={v.value}
                onClick={() => setViewMode(v.value as "list" | "week")}
                className={cn(
                  "rounded-lg px-3 py-1.5 text-sm font-medium transition-colors",
                  viewMode === v.value
                    ? "bg-gray-200 text-gray-900 dark:bg-gray-700 dark:text-gray-100"
                    : "text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800"
                )}
              >
                {v.label}
              </button>
            ))}
          </div>
        </div>

        {/* Week navigator */}
        <div className="flex items-center justify-center gap-4">
          <button
            onClick={() => setWeekOffset(weekOffset - 1)}
            className="btn-secondary text-sm"
          >
            &#9664; هفته قبل
          </button>
          <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
            {weekRange.label}
          </span>
          <button
            onClick={() => setWeekOffset(weekOffset + 1)}
            className="btn-secondary text-sm"
          >
            هفته بعد &#9654;
          </button>
          {weekOffset !== 0 && (
            <button
              onClick={() => setWeekOffset(0)}
              className="text-xs text-gold-600 dark:text-gold-400 hover:underline"
            >
              این هفته
            </button>
          )}
        </div>
      </div>

      {/* Stats bar */}
      <div className="mb-4 flex items-center gap-4 text-sm text-gray-500 dark:text-gray-400">
        <span>{counts.total} رویداد</span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-full bg-red-500" />
          {counts.high} بالا
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-full bg-orange-500" />
          {counts.medium} متوسط
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-full bg-green-500" />
          {counts.low} پایین
        </span>
      </div>

      {/* Loading */}
      {loading && (
        <div className="card py-12 text-center">
          <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-gold-400 border-t-transparent" />
          <p className="mt-3 text-gray-400">در حال بارگذاری تقویم...</p>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="card border-red-300 bg-red-50 py-6 text-center dark:border-red-800 dark:bg-red-900/20">
          <p className="text-red-600 dark:text-red-400">{error}</p>
          <button
            onClick={() => {
              setLoading(true);
              fetchEvents();
            }}
            className="btn-secondary mt-3"
          >
            تلاش مجدد
          </button>
        </div>
      )}

      {/* Events */}
      {!loading && !error && (
        <>
          {events.length === 0 ? (
            <div className="card py-12 text-center">
              <p className="text-gray-400">رویدادی برای نمایش وجود ندارد</p>
              <p className="mt-2 text-sm text-gray-400">
                تقویم اقتصادی هنوز همگام‌سازی نشده یا رویدادی برای این بازه زمانی ثبت نشده است.
              </p>
            </div>
          ) : viewMode === "list" ? (
            /* List view — grouped by date */
            <div className="space-y-6">
              {Array.from(grouped.entries()).map(([dateKey, dateEvents]) => (
                <div key={dateKey}>
                  {/* Date header */}
                  <div className="sticky top-16 z-10 mb-3 border-b border-gray-200 bg-gray-50/90 px-1 py-2 backdrop-blur-sm dark:border-gray-800 dark:bg-gray-950/90">
                    <h3 className="text-sm font-bold text-gray-700 dark:text-gray-300">
                      {dateEvents[0]
                        ? formatTehranDate(
                            dateEvents[0].datetime_tehran || dateEvents[0].datetime_utc
                          )
                        : dateKey}
                    </h3>
                  </div>

                  {/* Events for this date */}
                  <div className="space-y-2">
                    {dateEvents.map((event) => (
                      <EventCard
                        key={event.id}
                        event={event}
                        expanded={expandedId === event.id}
                        onToggle={() =>
                          setExpandedId(expandedId === event.id ? null : event.id)
                        }
                      />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            /* Week view — 7-day grid */
            <div className="space-y-4">
              {Array.from(grouped.entries()).map(([dateKey, dateEvents]) => (
                <div key={dateKey} className="card">
                  <h3 className="mb-3 text-sm font-bold text-gray-700 dark:text-gray-300 border-b border-gray-200 dark:border-gray-700 pb-2">
                    {dateEvents[0]
                      ? formatTehranDate(
                          dateEvents[0].datetime_tehran || dateEvents[0].datetime_utc
                        )
                      : dateKey}
                    <span className="mr-2 text-xs font-normal text-gray-400">
                      ({dateEvents.length} رویداد)
                    </span>
                  </h3>

                  <div className="space-y-2">
                    {dateEvents.map((event) => (
                      <div
                        key={event.id}
                        onClick={() =>
                          setExpandedId(expandedId === event.id ? null : event.id)
                        }
                        className={cn(
                          "flex items-center gap-3 rounded-lg px-3 py-2 cursor-pointer transition-colors",
                          "hover:bg-gray-50 dark:hover:bg-gray-800/50",
                          !event.is_upcoming && "opacity-60",
                          isWithin2Hours(event.datetime_utc) && "animate-subtle-pulse bg-gold-50/50 dark:bg-gold-900/10"
                        )}
                      >
                        <div
                          className={cn(
                            "h-2.5 w-2.5 shrink-0 rounded-full",
                            IMPACT_COLORS[event.impact] || "bg-gray-400"
                          )}
                        />
                        <span className="text-xs font-mono text-gray-500 dark:text-gray-400 w-12 shrink-0">
                          {formatTehranTime(event.datetime_tehran || event.datetime_utc)}
                        </span>
                        <span className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                          {event.event_name_fa !== event.event_name
                            ? event.event_name_fa
                            : event.event_name}
                        </span>
                        <span className="text-base shrink-0">
                          {COUNTRY_FLAGS[event.country] || ""}
                        </span>
                        {event.forecast && (
                          <span className="text-xs text-gray-400 shrink-0">
                            پیش‌بینی: {event.forecast}
                          </span>
                        )}
                        {event.previous && (
                          <span className="text-xs text-gray-400 shrink-0">
                            قبلی: {event.previous}
                          </span>
                        )}
                        {event.is_upcoming && event.time_until && (
                          <span className="mr-auto text-xs text-gold-600 dark:text-gold-400 shrink-0">
                            <CountdownTimer event={event} />
                          </span>
                        )}
                      </div>
                    ))}
                  </div>

                  {/* Expanded detail card */}
                  {dateEvents.some((e) => e.id === expandedId) && (
                    <div className="mt-3 border-t border-gray-200 dark:border-gray-700 pt-3">
                      {dateEvents
                        .filter((e) => e.id === expandedId)
                        .map((event) => (
                          <EventCard
                            key={event.id}
                            event={event}
                            expanded={true}
                            onToggle={() => setExpandedId(null)}
                          />
                        ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
