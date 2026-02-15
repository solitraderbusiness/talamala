"use client";

import Link from "next/link";
import { timeAgo } from "@/lib/utils";
import type { CuratedVideo } from "@/lib/api";

export default function VideoCard({ video }: { video: CuratedVideo }) {
  return (
    <Link
      href={`/analysis/videos/${video.id}`}
      className="group block overflow-hidden rounded-xl border border-gray-200 bg-white transition-shadow hover:shadow-lg dark:border-gray-800 dark:bg-gray-900"
    >
      {/* Thumbnail */}
      <div className="relative aspect-video overflow-hidden bg-gray-100 dark:bg-gray-800">
        <img
          src={video.thumbnail_url}
          alt={video.title_fa || video.title_original || ""}
          className="h-full w-full object-cover transition-transform group-hover:scale-105"
          loading="lazy"
        />
        {/* Duration badge */}
        {video.duration_formatted && (
          <span className="absolute bottom-2 left-2 rounded bg-black/80 px-1.5 py-0.5 text-xs font-medium text-white">
            {video.duration_formatted}
          </span>
        )}
      </div>

      {/* Content */}
      <div className="p-3">
        {/* Title */}
        <h3 className="mb-1 line-clamp-2 text-sm font-bold text-gray-900 dark:text-gray-100">
          {video.title_fa || video.title_original || video.youtube_id}
        </h3>

        {/* Channel + meta */}
        <div className="flex flex-wrap items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
          {video.channel_name && <span>{video.channel_name}</span>}
          {video.view_count_formatted && (
            <span>{video.view_count_formatted} بازدید</span>
          )}
          {video.published_at && (
            <span>{timeAgo(video.published_at)}</span>
          )}
        </div>
      </div>
    </Link>
  );
}
