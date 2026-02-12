"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { cn, timeAgo } from "@/lib/utils";
import {
  getGoldArticles,
  type GoldArticle,
  type GoldArticlesResponse,
} from "@/lib/api";

/* ════════════════════════════════════════════════════════════════════════
   Topic / Outlook config
   ════════════════════════════════════════════════════════════════════════ */

const TOPIC_FILTERS: { key: string; label: string }[] = [
  { key: "fed_policy", label: "سیاست فدرال رزرو" },
  { key: "central_banks", label: "بانک‌های مرکزی" },
  { key: "china_demand", label: "تقاضای چین" },
  { key: "etf_flows", label: "ETF" },
  { key: "technical_analysis", label: "تحلیل تکنیکال" },
  { key: "price_forecast", label: "پیش‌بینی قیمت" },
  { key: "geopolitics", label: "ژئوپلیتیک" },
  { key: "inflation", label: "تورم" },
  { key: "dollar", label: "دلار" },
  { key: "investment_strategy", label: "استراتژی سرمایه‌گذاری" },
];

const OUTLOOK_OPTIONS: { key: string; label: string; color: string }[] = [
  { key: "bullish", label: "صعودی", color: "text-green-500" },
  { key: "bearish", label: "نزولی", color: "text-red-500" },
  { key: "neutral", label: "خنثی", color: "text-gray-400" },
  { key: "mixed", label: "ترکیبی", color: "text-yellow-500" },
];

const TIME_RANGE_OPTIONS: { key: string; label: string }[] = [
  { key: "today", label: "امروز" },
  { key: "week", label: "هفته" },
  { key: "month", label: "ماه" },
];

function getOutlookBadge(outlook: string | null) {
  switch (outlook) {
    case "bullish":
      return { icon: "🟢", label: "صعودی", cls: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400" };
    case "bearish":
      return { icon: "🔴", label: "نزولی", cls: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400" };
    case "mixed":
      return { icon: "🟡", label: "ترکیبی", cls: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400" };
    default:
      return { icon: "⚪", label: "خنثی", cls: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400" };
  }
}

/* ════════════════════════════════════════════════════════════════════════
   Main Page
   ════════════════════════════════════════════════════════════════════════ */

export default function GoldArticlesPage() {
  const [data, setData] = useState<GoldArticlesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [page, setPage] = useState(1);
  const [topic, setTopic] = useState<string>("");
  const [outlook, setOutlook] = useState<string>("");
  const [timeRange, setTimeRange] = useState<string>("");

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string | number | boolean> = { page, per_page: 10 };
      if (topic) params.topic = topic;
      if (outlook) params.outlook = outlook;

      // Time range filter
      if (timeRange === "today") {
        params.from = new Date().toISOString().split("T")[0];
      } else if (timeRange === "week") {
        const d = new Date();
        d.setDate(d.getDate() - 7);
        params.from = d.toISOString().split("T")[0];
      } else if (timeRange === "month") {
        const d = new Date();
        d.setMonth(d.getMonth() - 1);
        params.from = d.toISOString().split("T")[0];
      }

      const result = await getGoldArticles(params as Parameters<typeof getGoldArticles>[0]);
      setData(result);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "خطا در بارگذاری");
    } finally {
      setLoading(false);
    }
  }, [page, topic, outlook, timeRange]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Find featured article
  const featured = data?.articles.find((a) => a.is_featured) || null;
  const articles = data?.articles || [];
  const total = data?.total || 0;
  const todaySummary = data?.today_outlook_summary;
  const todayCount = data?.today_count || 0;
  const totalPages = Math.ceil(total / 10);

  if (loading && !data) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="text-center">
          <div className="mx-auto h-10 w-10 animate-spin rounded-full border-4 border-gold-500 border-t-transparent" />
          <p className="mt-3 text-gray-500">در حال بارگذاری مقاله‌ها...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2">
          <Link
            href="/"
            className="text-gray-400 transition-colors hover:text-gray-600 dark:hover:text-gray-300"
          >
            داشبورد
          </Link>
          <span className="text-gray-300 dark:text-gray-600">/</span>
          <Link
            href="/ai-analysis"
            className="text-gray-400 transition-colors hover:text-gray-600 dark:hover:text-gray-300"
          >
            تحلیل هوشمند
          </Link>
          <span className="text-gray-300 dark:text-gray-600">/</span>
          <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100">
            مقاله‌های مهم طلا
          </h1>
        </div>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          تحلیل‌های تخصصی بازار طلا از منابع معتبر جهانی
        </p>
      </div>

      {error && (
        <div className="rounded-lg bg-red-50 p-4 text-sm text-red-700 dark:bg-red-900/20 dark:text-red-400">
          {error}
        </div>
      )}

      {/* ── Featured Article (Hero) ── */}
      {featured && page === 1 && !topic && !outlook && (
        <FeaturedArticleCard article={featured} />
      )}

      {/* ── Today's Outlook Summary ── */}
      {todayCount > 0 && (
        <div className="flex flex-wrap items-center gap-3 rounded-lg bg-gray-50 px-4 py-2.5 text-sm dark:bg-gray-800/50">
          <span className="font-medium text-gray-600 dark:text-gray-400">
            چشم‌انداز امروز:
          </span>
          <span className="text-gray-500 dark:text-gray-400">
            {todayCount} مقاله
          </span>
          {(todaySummary?.bullish ?? 0) > 0 && (
            <span className="text-green-600 dark:text-green-400">
              🟢 {todaySummary!.bullish} صعودی
            </span>
          )}
          {(todaySummary?.bearish ?? 0) > 0 && (
            <span className="text-red-600 dark:text-red-400">
              🔴 {todaySummary!.bearish} نزولی
            </span>
          )}
          {(todaySummary?.neutral ?? 0) > 0 && (
            <span className="text-gray-500 dark:text-gray-400">
              ⚪ {todaySummary!.neutral} خنثی
            </span>
          )}
          {(todaySummary?.mixed ?? 0) > 0 && (
            <span className="text-yellow-600 dark:text-yellow-400">
              🟡 {todaySummary!.mixed} ترکیبی
            </span>
          )}
        </div>
      )}

      {/* ── Filters ── */}
      <div className="space-y-3">
        {/* Topic filters */}
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => { setTopic(""); setPage(1); }}
            className={cn(
              "rounded-full px-3 py-1.5 text-xs font-medium transition-colors",
              !topic
                ? "bg-gold-600 text-white shadow-sm"
                : "bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400"
            )}
          >
            همه موضوعات
          </button>
          {TOPIC_FILTERS.map((t) => (
            <button
              key={t.key}
              onClick={() => { setTopic(topic === t.key ? "" : t.key); setPage(1); }}
              className={cn(
                "rounded-full px-3 py-1.5 text-xs font-medium transition-colors",
                topic === t.key
                  ? "bg-gold-600 text-white shadow-sm"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400"
              )}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Outlook + Time range row */}
        <div className="flex flex-wrap gap-3">
          <div className="flex gap-1.5">
            <button
              onClick={() => { setOutlook(""); setPage(1); }}
              className={cn(
                "rounded-full px-3 py-1.5 text-xs font-medium transition-colors",
                !outlook
                  ? "bg-gold-600 text-white shadow-sm"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400"
              )}
            >
              همه
            </button>
            {OUTLOOK_OPTIONS.map((o) => (
              <button
                key={o.key}
                onClick={() => { setOutlook(outlook === o.key ? "" : o.key); setPage(1); }}
                className={cn(
                  "rounded-full px-3 py-1.5 text-xs font-medium transition-colors",
                  outlook === o.key
                    ? "bg-gold-600 text-white shadow-sm"
                    : "bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400"
                )}
              >
                {o.label}
              </button>
            ))}
          </div>

          <div className="flex gap-1.5">
            <button
              onClick={() => { setTimeRange(""); setPage(1); }}
              className={cn(
                "rounded-full px-3 py-1.5 text-xs font-medium transition-colors",
                !timeRange
                  ? "bg-gold-600 text-white shadow-sm"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400"
              )}
            >
              همه زمان‌ها
            </button>
            {TIME_RANGE_OPTIONS.map((tr) => (
              <button
                key={tr.key}
                onClick={() => { setTimeRange(timeRange === tr.key ? "" : tr.key); setPage(1); }}
                className={cn(
                  "rounded-full px-3 py-1.5 text-xs font-medium transition-colors",
                  timeRange === tr.key
                    ? "bg-gold-600 text-white shadow-sm"
                    : "bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400"
                )}
              >
                {tr.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ── Article List ── */}
      <div className="space-y-3">
        {articles.length > 0 ? (
          articles.map((article) => (
            <ArticleCard key={article.id} article={article} />
          ))
        ) : (
          <div className="card py-12 text-center">
            <p className="text-gray-400">مقاله‌ای یافت نشد</p>
            <p className="mt-2 text-xs text-gray-400">
              مقاله‌ها هر ۴ ساعت به‌روزرسانی می‌شوند
            </p>
          </div>
        )}
      </div>

      {/* ── Pagination ── */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-4">
          <button
            onClick={() => setPage(Math.max(1, page - 1))}
            disabled={page <= 1}
            className="btn-secondary"
          >
            قبلی
          </button>
          <span className="text-sm text-gray-500">
            صفحه {page} از {totalPages}
          </span>
          <button
            onClick={() => setPage(page + 1)}
            disabled={page >= totalPages}
            className="btn-secondary"
          >
            بعدی
          </button>
        </div>
      )}
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────────── */
/*  Featured Article Card                                                */
/* ────────────────────────────────────────────────────────────────────── */

function FeaturedArticleCard({ article }: { article: GoldArticle }) {
  const badge = getOutlookBadge(article.gold_outlook);

  return (
    <div className="rounded-xl border-2 border-gold-300 bg-gradient-to-br from-gold-50 to-white p-5 shadow-sm dark:border-gold-700/50 dark:from-gold-950/30 dark:to-gray-900">
      <div className="mb-3 flex items-center gap-2">
        <span className="text-lg">⭐</span>
        <span className="text-sm font-bold text-gold-700 dark:text-gold-400">
          مقاله برتر امروز
        </span>
      </div>

      <h2 className="mb-1 text-lg font-bold text-gray-900 dark:text-gray-100">
        {article.title_fa || article.title_original}
      </h2>
      {article.title_fa && (
        <p className="mb-3 text-sm text-gray-500 dark:text-gray-400" dir="ltr">
          {article.title_original}
        </p>
      )}

      <div className="mb-4 flex flex-wrap items-center gap-3 text-xs text-gray-500 dark:text-gray-400">
        <span>📰 {article.source_name_fa}</span>
        {article.published_at && (
          <span>⏰ {timeAgo(article.published_at)}</span>
        )}
        <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", badge.cls)}>
          {badge.icon} {badge.label}
        </span>
        {article.time_horizon_fa && (
          <span>📅 {article.time_horizon_fa}</span>
        )}
      </div>

      {article.summary_fa && (
        <p className="mb-4 text-sm leading-relaxed text-gray-700 dark:text-gray-300">
          {article.summary_fa.length > 400
            ? article.summary_fa.slice(0, 400) + "..."
            : article.summary_fa}
        </p>
      )}

      {article.key_takeaways_fa && article.key_takeaways_fa.length > 0 && (
        <div className="mb-4">
          <h4 className="mb-2 text-sm font-bold text-gray-700 dark:text-gray-300">
            نکات کلیدی:
          </h4>
          <ul className="space-y-1">
            {article.key_takeaways_fa.map((point, i) => (
              <li key={i} className="flex gap-2 text-sm text-gray-600 dark:text-gray-400">
                <span className="text-gold-500">●</span>
                <span>{point}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <Link
          href={`/analysis/articles/${article.id}`}
          className="text-sm font-medium text-gold-600 hover:text-gold-700 dark:text-gold-400"
        >
          ادامه مطلب
        </Link>
        <a
          href={article.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-sm font-medium text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300"
        >
          مطالعه مقاله اصلی ↗
        </a>
      </div>
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────────── */
/*  Article Card                                                          */
/* ────────────────────────────────────────────────────────────────────── */

function ArticleCard({ article }: { article: GoldArticle }) {
  const badge = getOutlookBadge(article.gold_outlook);

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 transition-shadow hover:shadow-md dark:border-gray-800 dark:bg-gray-900">
      {/* Top meta row */}
      <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
        <span className={cn("rounded-full px-2 py-0.5 font-medium", badge.cls)}>
          {badge.icon} {badge.label}
        </span>
        <span>📰 {article.source_name_fa}</span>
        {article.published_at && (
          <span>⏰ {timeAgo(article.published_at)}</span>
        )}
        {article.is_featured && (
          <span className="rounded-full bg-gold-100 px-2 py-0.5 text-xs font-medium text-gold-700 dark:bg-gold-900/30 dark:text-gold-400">
            ⭐ برتر
          </span>
        )}
      </div>

      {/* Title */}
      <h3 className="mb-1 text-sm font-bold text-gray-900 dark:text-gray-100">
        {article.title_fa || article.title_original}
      </h3>
      {article.title_fa && (
        <p className="mb-2 text-xs text-gray-400" dir="ltr">
          {article.title_original}
        </p>
      )}

      {/* Summary preview */}
      {article.summary_fa && (
        <p className="mb-3 text-xs leading-relaxed text-gray-600 dark:text-gray-400">
          {article.summary_fa.length > 200
            ? article.summary_fa.slice(0, 200) + "..."
            : article.summary_fa}
        </p>
      )}

      {/* Topic tags */}
      {article.topics_fa && article.topics_fa.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-1.5">
          {article.topics_fa.map((t, i) => (
            <span
              key={i}
              className="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] text-gray-500 dark:bg-gray-800 dark:text-gray-400"
            >
              {t}
            </span>
          ))}
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-3">
        <Link
          href={`/analysis/articles/${article.id}`}
          className="text-xs font-medium text-gold-600 hover:text-gold-700 dark:text-gold-400"
        >
          ادامه مطلب
        </Link>
        <a
          href={article.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs font-medium text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
        >
          مقاله اصلی ↗
        </a>
      </div>
    </div>
  );
}
