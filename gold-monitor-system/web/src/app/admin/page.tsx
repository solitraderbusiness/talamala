"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { getToken } from "@/lib/auth";
import InfoTip from "@/components/InfoTip";
import {
  getMonitoringOverview,
  getDataHealthOverview,
  type MonitoringOverview,
  type DataHealthOverview,
} from "@/lib/api";
import { cn } from "@/lib/utils";

/* ── Types for data we fetch directly ──────────────────────────────── */

interface ChatOverview {
  total_users: number;
  total_messages: number;
  total_sessions: number;
  avg_messages_per_session: number;
}

interface SourceCount {
  total: number;
  enabled: number;
}

interface VideoStats {
  total: number;
  published: number;
}

/* ── Helpers ───────────────────────────────────────────────────────── */

function timeAgo(ts: string): string {
  const diff = (Date.now() - new Date(ts).getTime()) / 60000;
  if (diff < 1) return "همین الان";
  if (diff < 60) return `${Math.floor(diff)} دقیقه پیش`;
  if (diff < 1440) return `${Math.floor(diff / 60)} ساعت پیش`;
  return `${Math.floor(diff / 1440)} روز پیش`;
}

/* ── Quick-link definitions ────────────────────────────────────────── */

const quickLinks = [
  {
    href: "/admin/sources",
    label: "منابع خبری",
    desc: "مدیریت فیدهای خبری",
    color: "bg-blue-500/10 text-blue-600 dark:text-blue-400",
  },
  {
    href: "/admin/signal-sources",
    label: "منابع سیگنال",
    desc: "سیگنال‌های تلگرام و تریدینگ‌ویو",
    color: "bg-purple-500/10 text-purple-600 dark:text-purple-400",
  },
  {
    href: "/admin/videos",
    label: "ویدیوها",
    desc: "مدیریت ویدیوهای طلا",
    color: "bg-pink-500/10 text-pink-600 dark:text-pink-400",
  },
  {
    href: "/admin/monitoring",
    label: "پایش عملیات",
    desc: "وضعیت جاب‌ها و ورکرها",
    color: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
  },
  {
    href: "/admin/data-health",
    label: "سلامت داده",
    desc: "پایپلاین داده و اسنپ‌شات",
    color: "bg-cyan-500/10 text-cyan-600 dark:text-cyan-400",
  },
  {
    href: "/admin/data-reliability",
    label: "اعتبار داده‌ها",
    desc: "کیفیت محاسبات و QA",
    color: "bg-amber-500/10 text-amber-600 dark:text-amber-400",
  },
  {
    href: "/admin/chat",
    label: "بینش‌های چت",
    desc: "آنالیز مکالمات هوش مصنوعی",
    color: "bg-indigo-500/10 text-indigo-600 dark:text-indigo-400",
  },
  {
    href: "/admin/regime",
    label: "رژیم کلان",
    desc: "تحلیل رژیم نقدینگی",
    color: "bg-rose-500/10 text-rose-600 dark:text-rose-400",
  },
  {
    href: "/admin/backtest",
    label: "بک‌تست جامع",
    desc: "داده‌های ۱۰+ ساله و اعتبارسنجی",
    color: "bg-teal-500/10 text-teal-600 dark:text-teal-400",
  },
  {
    href: "/admin/audit-logs",
    label: "لاگ حسابرسی",
    desc: "ردیابی عملیات و ممیزی سیستم",
    color: "bg-slate-500/10 text-slate-600 dark:text-slate-400",
  },
  {
    href: "/admin/database",
    label: "هوش پایگاه داده",
    desc: "اسکیمای جداول و سلامت داده‌ها",
    color: "bg-violet-500/10 text-violet-600 dark:text-violet-400",
  },
];

/* ── Component ─────────────────────────────────────────────────────── */

export default function AdminDashboardPage() {
  const [monitoring, setMonitoring] = useState<MonitoringOverview | null>(null);
  const [dataHealth, setDataHealth] = useState<DataHealthOverview | null>(null);
  const [chatOverview, setChatOverview] = useState<ChatOverview | null>(null);
  const [sourceCount, setSourceCount] = useState<SourceCount | null>(null);
  const [videoStats, setVideoStats] = useState<VideoStats | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchAll = useCallback(async () => {
    const token = getToken();
    if (!token) return;

    const results = await Promise.allSettled([
      getMonitoringOverview(token),
      getDataHealthOverview(token),
      // Chat overview
      fetch("/api/admin/chat/overview?period=today", {
        headers: { Authorization: `Bearer ${token}` },
      }).then((r) => (r.ok ? r.json() : null)),
      // Source count
      fetch("/api/sources", {
        headers: { Authorization: `Bearer ${token}` },
      }).then((r) => (r.ok ? r.json() : null)),
      // Video stats
      fetch("/api/analysis/videos?per_page=1", {}).then((r) =>
        r.ok ? r.json() : null
      ),
    ]);

    if (results[0].status === "fulfilled") setMonitoring(results[0].value);
    if (results[1].status === "fulfilled") setDataHealth(results[1].value);
    if (results[2].status === "fulfilled" && results[2].value) {
      setChatOverview(results[2].value);
    }
    if (results[3].status === "fulfilled" && results[3].value) {
      const sources = results[3].value;
      const list = Array.isArray(sources) ? sources : sources.items || [];
      setSourceCount({
        total: list.length,
        enabled: list.filter((s: { enabled?: boolean }) => s.enabled).length,
      });
    }
    if (results[4].status === "fulfilled" && results[4].value) {
      setVideoStats({
        total: results[4].value.total || 0,
        published: results[4].value.total || 0,
      });
    }

    setLoading(false);
  }, []);

  useEffect(() => {
    fetchAll();
    const interval = setInterval(fetchAll, 60_000);
    return () => clearInterval(interval);
  }, [fetchAll]);

  if (loading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <div className="text-center">
          <div className="mx-auto h-10 w-10 animate-spin rounded-full border-4 border-gold-500 border-t-transparent" />
          <p className="mt-3 text-sm text-gray-500">در حال بارگذاری...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100">
          داشبورد مدیریت
        </h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          نمای کلی وضعیت سیستم و فعالیت‌ها
        </p>
      </div>

      {/* ── Summary Cards ────────────────────────────────────────── */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {/* System Health */}
        <Link
          href="/admin/monitoring"
          className="card group transition-shadow hover:shadow-md"
        >
          <div className="mb-2 flex items-center justify-between">
            <h3 className="flex items-center text-xs font-bold text-gray-500 dark:text-gray-400">
              سلامت سیستم
              <InfoTip term="admin_system_health" />
            </h3>
            <span className="text-xs text-gray-400 group-hover:text-gold-500">
              &#8592;
            </span>
          </div>
          {monitoring ? (
            <>
              <div className="flex items-baseline gap-2">
                <span className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                  {Math.round(monitoring.success_rate_24h)}%
                </span>
                <span className="text-xs text-gray-400">نرخ موفقیت ۲۴ ساعته</span>
              </div>
              <div className="mt-2 flex gap-3 text-xs">
                <span className="flex items-center gap-1">
                  <span className="inline-block h-2 w-2 rounded-full bg-emerald-500" />
                  {monitoring.jobs_healthy} سالم
                </span>
                {monitoring.jobs_warning > 0 && (
                  <span className="flex items-center gap-1">
                    <span className="inline-block h-2 w-2 rounded-full bg-amber-500" />
                    {monitoring.jobs_warning} هشدار
                  </span>
                )}
                {monitoring.jobs_error > 0 && (
                  <span className="flex items-center gap-1">
                    <span className="inline-block h-2 w-2 rounded-full bg-red-500" />
                    {monitoring.jobs_error} خطا
                  </span>
                )}
              </div>
            </>
          ) : (
            <p className="text-sm text-gray-400">داده‌ای موجود نیست</p>
          )}
        </Link>

        {/* Data Pipeline */}
        <Link
          href="/admin/data-health"
          className="card group transition-shadow hover:shadow-md"
        >
          <div className="mb-2 flex items-center justify-between">
            <h3 className="flex items-center text-xs font-bold text-gray-500 dark:text-gray-400">
              پایپلاین داده
              <InfoTip term="admin_data_pipeline" />
            </h3>
            <span className="text-xs text-gray-400 group-hover:text-gold-500">
              &#8592;
            </span>
          </div>
          {dataHealth ? (
            <>
              <div className="flex items-baseline gap-2">
                <span className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                  {dataHealth.snapshot_coverage_pct != null
                    ? `${Math.round(dataHealth.snapshot_coverage_pct)}%`
                    : "---"}
                </span>
                <span className="text-xs text-gray-400">پوشش اسنپ‌شات</span>
              </div>
              <div className="mt-2 flex gap-3 text-xs text-gray-500">
                <span>{dataHealth.alerts_24h} هشدار ۲۴ ساعته</span>
                {dataHealth.outcome_errors > 0 && (
                  <span className="text-red-500">
                    {dataHealth.outcome_errors} خطا
                  </span>
                )}
              </div>
            </>
          ) : (
            <p className="text-sm text-gray-400">داده‌ای موجود نیست</p>
          )}
        </Link>

        {/* Content */}
        <Link
          href="/admin/sources"
          className="card group transition-shadow hover:shadow-md"
        >
          <div className="mb-2 flex items-center justify-between">
            <h3 className="flex items-center text-xs font-bold text-gray-500 dark:text-gray-400">
              محتوا
              <InfoTip term="admin_content" />
            </h3>
            <span className="text-xs text-gray-400 group-hover:text-gold-500">
              &#8592;
            </span>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-bold text-gray-900 dark:text-gray-100">
              {sourceCount?.total ?? "---"}
            </span>
            <span className="text-xs text-gray-400">منبع خبری</span>
          </div>
          <div className="mt-2 flex gap-3 text-xs text-gray-500">
            {sourceCount && (
              <span>{sourceCount.enabled} فعال</span>
            )}
            {videoStats && (
              <span>{videoStats.total} ویدیو</span>
            )}
          </div>
        </Link>

        {/* Chat */}
        <Link
          href="/admin/chat"
          className="card group transition-shadow hover:shadow-md"
        >
          <div className="mb-2 flex items-center justify-between">
            <h3 className="flex items-center text-xs font-bold text-gray-500 dark:text-gray-400">
              چت هوش مصنوعی
              <InfoTip term="admin_chat" />
            </h3>
            <span className="text-xs text-gray-400 group-hover:text-gold-500">
              &#8592;
            </span>
          </div>
          {chatOverview ? (
            <>
              <div className="flex items-baseline gap-2">
                <span className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                  {chatOverview.total_messages}
                </span>
                <span className="text-xs text-gray-400">پیام امروز</span>
              </div>
              <div className="mt-2 flex gap-3 text-xs text-gray-500">
                <span>{chatOverview.total_sessions} مکالمه</span>
                <span>{chatOverview.total_users} کاربر</span>
              </div>
            </>
          ) : (
            <p className="text-sm text-gray-400">داده‌ای موجود نیست</p>
          )}
        </Link>
      </div>

      {/* ── Freshness Indicators ─────────────────────────────────── */}
      {dataHealth && (
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2 rounded-lg bg-gray-50 px-4 py-3 text-xs dark:bg-gray-800/50">
          <span className="font-medium text-gray-500 dark:text-gray-400">
            تازگی داده‌ها:
          </span>
          {dataHealth.sentiment_last_recorded && (
            <FreshnessIndicator
              label="احساسات"
              timestamp={dataHealth.sentiment_last_recorded}
            />
          )}
          {dataHealth.price_data_last_update && (
            <FreshnessIndicator
              label="قیمت"
              timestamp={dataHealth.price_data_last_update}
            />
          )}
          {monitoring?.last_check_at && (
            <FreshnessIndicator
              label="پایش"
              timestamp={monitoring.last_check_at}
            />
          )}
        </div>
      )}

      {/* ── Quick Links ──────────────────────────────────────────── */}
      <div>
        <h2 className="mb-3 text-sm font-bold text-gray-900 dark:text-gray-100">
          دسترسی سریع
        </h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {quickLinks.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="group flex items-center gap-3 rounded-xl border border-gray-200 bg-white px-4 py-3 transition-all hover:border-gold-300 hover:shadow-sm dark:border-gray-800 dark:bg-gray-900 dark:hover:border-gold-700"
            >
              <div
                className={cn(
                  "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-sm font-bold",
                  link.color
                )}
              >
                {link.label.charAt(0)}
              </div>
              <div className="min-w-0">
                <div className="text-sm font-medium text-gray-900 dark:text-gray-100">
                  {link.label}
                </div>
                <div className="truncate text-xs text-gray-500 dark:text-gray-400">
                  {link.desc}
                </div>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ── Sub-components ────────────────────────────────────────────────── */

function FreshnessIndicator({
  label,
  timestamp,
}: {
  label: string;
  timestamp: string;
}) {
  const diffMin = (Date.now() - new Date(timestamp).getTime()) / 60000;
  const dotColor =
    diffMin <= 15
      ? "bg-emerald-500"
      : diffMin <= 60
        ? "bg-amber-500"
        : "bg-red-500";

  return (
    <span className="flex items-center gap-1">
      <span className={cn("inline-block h-2 w-2 rounded-full", dotColor)} />
      <span className="text-gray-600 dark:text-gray-400">{label}:</span>
      <span className="text-gray-500 dark:text-gray-400">
        {timeAgo(timestamp)}
      </span>
    </span>
  );
}
