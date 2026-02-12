"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { cn, timeAgo, formatDate } from "@/lib/utils";
import { getGoldArticle, type GoldArticle } from "@/lib/api";

function getOutlookBadge(outlook: string | null) {
  switch (outlook) {
    case "bullish":
      return { icon: "\ud83d\udfe2", label: "\u0635\u0639\u0648\u062f\u06cc", cls: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400" };
    case "bearish":
      return { icon: "\ud83d\udd34", label: "\u0646\u0632\u0648\u0644\u06cc", cls: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400" };
    case "mixed":
      return { icon: "\ud83d\udfe1", label: "\u062a\u0631\u06a9\u06cc\u0628\u06cc", cls: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400" };
    default:
      return { icon: "\u26aa", label: "\u062e\u0646\u062b\u06cc", cls: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400" };
  }
}

export default function ArticleDetailPage() {
  const params = useParams();
  const id = Number(params.id);

  const [article, setArticle] = useState<GoldArticle | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    getGoldArticle(id)
      .then((data) => {
        setArticle(data);
        setError(null);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "\u062e\u0637\u0627 \u062f\u0631 \u0628\u0627\u0631\u06af\u0630\u0627\u0631\u06cc");
      })
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="text-center">
          <div className="mx-auto h-10 w-10 animate-spin rounded-full border-4 border-gold-500 border-t-transparent" />
          <p className="mt-3 text-gray-500">\u062f\u0631 \u062d\u0627\u0644 \u0628\u0627\u0631\u06af\u0630\u0627\u0631\u06cc...</p>
        </div>
      </div>
    );
  }

  if (error || !article) {
    return (
      <div className="space-y-4">
        <Link
          href="/analysis/articles"
          className="text-sm text-gold-600 hover:text-gold-700 dark:text-gold-400"
        >
          \u2190 \u0628\u0627\u0632\u06af\u0634\u062a \u0628\u0647 \u0644\u06cc\u0633\u062a
        </Link>
        <div className="card py-12 text-center">
          <p className="text-gray-400">{error || "\u0645\u0642\u0627\u0644\u0647 \u06cc\u0627\u0641\u062a \u0646\u0634\u062f"}</p>
        </div>
      </div>
    );
  }

  const badge = getOutlookBadge(article.gold_outlook);

  return (
    <div className="space-y-5">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm">
        <Link
          href="/"
          className="text-gray-400 transition-colors hover:text-gray-600 dark:hover:text-gray-300"
        >
          \u062f\u0627\u0634\u0628\u0648\u0631\u062f
        </Link>
        <span className="text-gray-300 dark:text-gray-600">/</span>
        <Link
          href="/analysis/articles"
          className="text-gray-400 transition-colors hover:text-gray-600 dark:hover:text-gray-300"
        >
          \u0645\u0642\u0627\u0644\u0647\u200c\u0647\u0627
        </Link>
        <span className="text-gray-300 dark:text-gray-600">/</span>
        <span className="text-gray-600 dark:text-gray-300">
          {(article.title_fa || article.title_original || "").slice(0, 40)}...
        </span>
      </div>

      {/* Title section */}
      <div>
        <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100">
          {article.title_fa || article.title_original}
        </h1>
        {article.title_fa && (
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400" dir="ltr">
            {article.title_original}
          </p>
        )}
      </div>

      {/* Meta row */}
      <div className="flex flex-wrap items-center gap-3 text-sm text-gray-500 dark:text-gray-400">
        <span>\ud83d\udcf0 {article.source_name_fa}</span>
        {article.author && <span>\u270d\ufe0f {article.author}</span>}
        {article.published_at && (
          <span>\u23f0 {formatDate(article.published_at)}</span>
        )}
        <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", badge.cls)}>
          {badge.icon} {badge.label}
        </span>
        {article.time_horizon_fa && (
          <span>\ud83d\udcc5 {article.time_horizon_fa}</span>
        )}
        {article.importance_score != null && (
          <span>\u2b50 \u0627\u0645\u062a\u06cc\u0627\u0632 \u0627\u0647\u0645\u06cc\u062a: {Math.round(article.importance_score)}</span>
        )}
      </div>

      {/* Related alert cross-link */}
      {article.related_alert && (
        <div className="rounded-lg bg-amber-50 p-3 text-sm dark:bg-amber-900/20">
          <span className="text-amber-700 dark:text-amber-400">
            \ud83d\udd14 \u0647\u0634\u062f\u0627\u0631 \u0645\u0631\u062a\u0628\u0637 \u0645\u0648\u062c\u0648\u062f \u0627\u0633\u062a:{" "}
            <Link
              href={`/?alert=${article.related_alert.id}`}
              className="font-medium underline"
            >
              {article.related_alert.title}
            </Link>
          </span>
        </div>
      )}

      {/* Summary box */}
      {article.summary_fa && (
        <div className="rounded-xl border border-gray-200 bg-white p-5 dark:border-gray-800 dark:bg-gray-900">
          <h3 className="mb-3 text-sm font-bold text-gray-700 dark:text-gray-300">
            \u062e\u0644\u0627\u0635\u0647
          </h3>
          <p className="whitespace-pre-line text-sm leading-relaxed text-gray-700 dark:text-gray-300">
            {article.summary_fa}
          </p>
        </div>
      )}

      {/* Key takeaways */}
      {article.key_takeaways_fa && article.key_takeaways_fa.length > 0 && (
        <div className="rounded-xl border border-gray-200 bg-white p-5 dark:border-gray-800 dark:bg-gray-900">
          <h3 className="mb-3 text-sm font-bold text-gray-700 dark:text-gray-300">
            \u0646\u06a9\u0627\u062a \u06a9\u0644\u06cc\u062f\u06cc
          </h3>
          <ul className="space-y-2">
            {article.key_takeaways_fa.map((point, i) => (
              <li
                key={i}
                className="flex gap-2 text-sm text-gray-600 dark:text-gray-400"
              >
                <span className="mt-0.5 text-gold-500">\u25cf</span>
                <span>{point}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Affected assets */}
      {article.affected_assets_fa && article.affected_assets_fa.length > 0 && (
        <div className="rounded-xl border border-gray-200 bg-white p-5 dark:border-gray-800 dark:bg-gray-900">
          <h3 className="mb-3 text-sm font-bold text-gray-700 dark:text-gray-300">
            \u062f\u0627\u0631\u0627\u06cc\u06cc\u200c\u0647\u0627\u06cc \u0645\u0631\u062a\u0628\u0637
          </h3>
          <div className="flex flex-wrap gap-2">
            {article.affected_assets_fa.map((asset, i) => (
              <span
                key={i}
                className="rounded-lg bg-gray-100 px-3 py-1.5 text-xs font-medium text-gray-600 dark:bg-gray-800 dark:text-gray-400"
              >
                {asset}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Topic tags */}
      {article.topics_fa && article.topics_fa.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {article.topics_fa.map((topic, i) => (
            <span
              key={i}
              className="rounded-full bg-gray-100 px-3 py-1 text-xs text-gray-500 dark:bg-gray-800 dark:text-gray-400"
            >
              {topic}
            </span>
          ))}
        </div>
      )}

      {/* Related articles */}
      {article.related_articles && article.related_articles.length > 0 && (
        <div className="rounded-xl border border-gray-200 bg-white p-5 dark:border-gray-800 dark:bg-gray-900">
          <h3 className="mb-3 text-sm font-bold text-gray-700 dark:text-gray-300">
            \u0645\u0642\u0627\u0644\u0627\u062a \u0645\u0634\u0627\u0628\u0647
          </h3>
          <div className="space-y-2">
            {article.related_articles.map((related) => {
              const rBadge = getOutlookBadge(related.gold_outlook);
              return (
                <Link
                  key={related.id}
                  href={`/analysis/articles/${related.id}`}
                  className="flex items-center gap-2 rounded-lg p-2 text-sm transition-colors hover:bg-gray-50 dark:hover:bg-gray-800"
                >
                  <span className={cn("rounded px-1.5 py-0.5 text-xs", rBadge.cls)}>
                    {rBadge.icon}
                  </span>
                  <span className="flex-1 text-gray-700 dark:text-gray-300">
                    {related.title_fa || related.title_original}
                  </span>
                  {related.published_at && (
                    <span className="text-xs text-gray-400">
                      {timeAgo(related.published_at)}
                    </span>
                  )}
                </Link>
              );
            })}
          </div>
        </div>
      )}

      {/* Action buttons */}
      <div className="flex flex-wrap items-center gap-3">
        <a
          href={article.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 rounded-lg bg-gold-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-gold-700"
        >
          \u0645\u0637\u0627\u0644\u0639\u0647 \u0645\u0642\u0627\u0644\u0647 \u0627\u0635\u0644\u06cc \u2197
        </a>
        <Link
          href="/analysis/articles"
          className="inline-flex items-center gap-1.5 rounded-lg bg-gray-100 px-4 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700"
        >
          \u0628\u0627\u0632\u06af\u0634\u062a \u0628\u0647 \u0644\u06cc\u0633\u062a
        </Link>
      </div>
    </div>
  );
}
