"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { getVideos, type CuratedVideo, type VideosResponse } from "@/lib/api";
import VideoCard from "@/components/videos/VideoCard";
import LiveStreamSection from "@/components/videos/LiveStreamSection";
import VideoFilters from "@/components/videos/VideoFilters";

export default function VideosPage() {
  const [data, setData] = useState<VideosResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [page, setPage] = useState(1);
  const [category, setCategory] = useState("");
  const [topic, setTopic] = useState("");
  const perPage = 12;

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string | number | boolean> = {
        page,
        per_page: perPage,
      };
      if (category) params.category = category;
      if (topic) params.topic = topic;

      const result = await getVideos(params as Parameters<typeof getVideos>[0]);
      setData(result);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "خطا در بارگذاری");
    } finally {
      setLoading(false);
    }
  }, [page, category, topic]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const videos = data?.videos || [];
  const total = data?.total || 0;
  const totalPages = Math.ceil(total / perPage);

  if (loading && !data) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="text-center">
          <div className="mx-auto h-10 w-10 animate-spin rounded-full border-4 border-gold-500 border-t-transparent" />
          <p className="mt-3 text-gray-500">در حال بارگذاری ویدیوها...</p>
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
            ویدیوهای طلا و اقتصاد
          </h1>
        </div>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          ویدیوهای تحلیلی بازار طلا و اقتصاد جهانی با خلاصه فارسی
        </p>
      </div>

      {error && (
        <div className="rounded-lg bg-red-50 p-4 text-sm text-red-700 dark:bg-red-900/20 dark:text-red-400">
          {error}
        </div>
      )}

      {/* Live streams */}
      <LiveStreamSection />

      {/* Filters */}
      <VideoFilters
        category={category}
        setCategory={setCategory}
        topic={topic}
        setTopic={setTopic}
        onReset={() => setPage(1)}
      />

      {/* Video grid */}
      {videos.length > 0 ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
          {videos.map((video) => (
            <VideoCard key={video.id} video={video} />
          ))}
        </div>
      ) : (
        <div className="card py-12 text-center">
          <p className="text-gray-400">ویدیویی یافت نشد</p>
          <p className="mt-2 text-xs text-gray-400">
            ویدیوها هر ساعت به‌روزرسانی می‌شوند
          </p>
        </div>
      )}

      {/* Load more / pagination */}
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
