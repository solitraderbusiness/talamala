"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { cn, timeAgo, formatDate } from "@/lib/utils";
import { getVideo, type CuratedVideo } from "@/lib/api";
import VideoPlayer from "@/components/videos/VideoPlayer";
import VideoCard from "@/components/videos/VideoCard";
import TranscriptViewer from "@/components/videos/TranscriptViewer";
import { useChatContext } from "@/components/ChatWidget/ChatContext";

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

export default function VideoDetailPage() {
  const params = useParams();
  const id = Number(params.id);

  const [video, setVideo] = useState<CuratedVideo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { setPageContext, openWithContext } = useChatContext();

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    getVideo(id)
      .then((data) => {
        setVideo(data);
        setError(null);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "خطا در بارگذاری");
      })
      .finally(() => setLoading(false));
  }, [id]);

  // Set page context for global chat when video loads
  useEffect(() => {
    if (video) {
      setPageContext({
        type: "video",
        videoId: video.id,
        title: video.title_fa || video.title_original || undefined,
        summary: video.summary_fa || undefined,
        channel: video.channel_name || undefined,
        url: `/analysis/videos/${video.id}`,
      });
    }
    return () => setPageContext(null);
  }, [video, setPageContext]);

  const handleAskAI = useCallback(() => {
    if (!video) return;
    openWithContext(
      {
        type: "video",
        videoId: video.id,
        title: video.title_fa || video.title_original || undefined,
        summary: video.summary_fa || undefined,
        channel: video.channel_name || undefined,
        url: `/analysis/videos/${video.id}`,
      },
      `درباره این ویدیو بیشتر توضیح بده: ${video.title_fa || video.title_original || ""}`
    );
  }, [video, openWithContext]);

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="text-center">
          <div className="mx-auto h-10 w-10 animate-spin rounded-full border-4 border-gold-500 border-t-transparent" />
          <p className="mt-3 text-gray-500">در حال بارگذاری...</p>
        </div>
      </div>
    );
  }

  if (error || !video) {
    return (
      <div className="space-y-4">
        <Link
          href="/analysis/videos"
          className="text-sm text-gold-600 hover:text-gold-700 dark:text-gold-400"
        >
          ← بازگشت به لیست
        </Link>
        <div className="card py-12 text-center">
          <p className="text-gray-400">{error || "ویدیو یافت نشد"}</p>
        </div>
      </div>
    );
  }

  const badge = getOutlookBadge(video.gold_outlook);

  return (
    <div className="space-y-5">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm">
        <Link
          href="/"
          className="text-gray-400 transition-colors hover:text-gray-600 dark:hover:text-gray-300"
        >
          داشبورد
        </Link>
        <span className="text-gray-300 dark:text-gray-600">/</span>
        <Link
          href="/analysis/videos"
          className="text-gray-400 transition-colors hover:text-gray-600 dark:hover:text-gray-300"
        >
          ویدیوها
        </Link>
        <span className="text-gray-300 dark:text-gray-600">/</span>
        <span className="text-gray-600 dark:text-gray-300">
          {(video.title_fa || video.title_original || "").slice(0, 40)}...
        </span>
      </div>

      {/* Player */}
      <VideoPlayer youtubeId={video.youtube_id} title={video.title_fa || video.title_original || ""} />

      {/* Title section */}
      <div>
        <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100">
          {video.title_fa || video.title_original || video.youtube_id}
        </h1>
        {video.title_fa && video.title_original && (
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400" dir="ltr">
            {video.title_original}
          </p>
        )}
      </div>

      {/* Meta row */}
      <div className="flex flex-wrap items-center gap-3 text-sm text-gray-500 dark:text-gray-400">
        {video.channel_name && <span>📺 {video.channel_name}</span>}
        {video.published_at && <span>⏰ {formatDate(video.published_at)}</span>}
        {video.duration_formatted && <span>⏱️ {video.duration_formatted}</span>}
        {video.view_count_formatted && (
          <span>👁️ {video.view_count_formatted} بازدید</span>
        )}
        <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", badge.cls)}>
          {badge.icon} {badge.label}
        </span>
        {video.category_fa && <span>📁 {video.category_fa}</span>}
      </div>

      {/* Summary */}
      {video.summary_fa && (
        <div className="rounded-xl border border-gray-200 bg-white p-5 dark:border-gray-800 dark:bg-gray-900">
          <h3 className="mb-3 text-sm font-bold text-gray-700 dark:text-gray-300">
            خلاصه فارسی
          </h3>
          <p className="whitespace-pre-line text-sm leading-relaxed text-gray-700 dark:text-gray-300">
            {video.summary_fa}
          </p>
        </div>
      )}

      {/* Key points */}
      {video.key_points_fa && video.key_points_fa.length > 0 && (
        <div className="rounded-xl border border-gray-200 bg-white p-5 dark:border-gray-800 dark:bg-gray-900">
          <h3 className="mb-3 text-sm font-bold text-gray-700 dark:text-gray-300">
            نکات کلیدی
          </h3>
          <ul className="space-y-2">
            {video.key_points_fa.map((point, i) => (
              <li
                key={i}
                className="flex gap-2 text-sm text-gray-600 dark:text-gray-400"
              >
                <span className="mt-0.5 text-gold-500">●</span>
                <span>{point}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Topic tags */}
      {video.topics_fa && video.topics_fa.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {video.topics_fa.map((t, i) => (
            <span
              key={i}
              className="rounded-full bg-gray-100 px-3 py-1 text-xs text-gray-500 dark:bg-gray-800 dark:text-gray-400"
            >
              {t}
            </span>
          ))}
        </div>
      )}

      {/* Transcript viewer */}
      {video.transcript && (
        <TranscriptViewer transcript={video.transcript} onAskAI={handleAskAI} />
      )}

      {/* Related videos */}
      {video.related_videos && video.related_videos.length > 0 && (
        <div>
          <h3 className="mb-3 text-sm font-bold text-gray-700 dark:text-gray-300">
            ویدیوهای مشابه
          </h3>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-4">
            {video.related_videos.map((rv) => (
              <VideoCard key={rv.id} video={rv} />
            ))}
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="flex flex-wrap items-center gap-3">
        <button
          onClick={handleAskAI}
          className="inline-flex items-center gap-1.5 rounded-lg bg-gold-500 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-gold-600"
        >
          از هوش مصنوعی بپرس
        </button>
        <a
          href={video.watch_url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-red-700"
        >
          تماشا در YouTube ↗
        </a>
        <Link
          href="/analysis/videos"
          className="inline-flex items-center gap-1.5 rounded-lg bg-gray-100 px-4 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700"
        >
          بازگشت به لیست
        </Link>
      </div>
    </div>
  );
}
