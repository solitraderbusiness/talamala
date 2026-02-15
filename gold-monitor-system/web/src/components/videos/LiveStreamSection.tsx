"use client";

import { useState, useEffect } from "react";
import { getLiveStreams, type LiveStreamChannel } from "@/lib/api";

export default function LiveStreamSection() {
  const [channels, setChannels] = useState<LiveStreamChannel[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeChannel, setActiveChannel] = useState<LiveStreamChannel | null>(null);

  useEffect(() => {
    getLiveStreams()
      .then((data) => {
        setChannels(data.channels);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="h-20 animate-pulse rounded-xl bg-gray-100 dark:bg-gray-800" />
    );
  }

  if (channels.length === 0) return null;

  return (
    <div className="space-y-3">
      <h2 className="text-sm font-bold text-gray-700 dark:text-gray-300">
        پخش زنده
      </h2>

      {/* Live stream cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
        {channels.map((ch) => (
          <button
            key={ch.id}
            onClick={() =>
              setActiveChannel(activeChannel?.id === ch.id ? null : ch)
            }
            className={`group block overflow-hidden rounded-xl border-2 bg-white text-right transition-shadow hover:shadow-lg dark:bg-gray-900 ${
              activeChannel?.id === ch.id
                ? "border-red-500 shadow-red-500/20 shadow-lg"
                : "border-red-500/40 hover:border-red-500"
            }`}
          >
            {/* Thumbnail */}
            <div className="relative aspect-video overflow-hidden bg-gray-100 dark:bg-gray-800">
              {ch.thumbnail_url ? (
                <img
                  src={ch.thumbnail_url}
                  alt={ch.name_fa || ch.name}
                  className="h-full w-full object-cover transition-transform group-hover:scale-105"
                  loading="lazy"
                />
              ) : (
                <div className="flex h-full w-full items-center justify-center text-4xl text-gray-300 dark:text-gray-600">
                  📺
                </div>
              )}
              {/* LIVE badge */}
              <span className="absolute top-2 left-2 inline-flex items-center gap-1.5 rounded bg-red-600 px-2 py-0.5 text-[11px] font-bold text-white">
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-white opacity-75" />
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-white" />
                </span>
                LIVE
              </span>
            </div>

            {/* Content */}
            <div className="p-3">
              <h3 className="line-clamp-1 text-sm font-bold text-gray-900 dark:text-gray-100">
                {ch.name_fa || ch.name}
              </h3>
              <p className="mt-0.5 text-xs text-red-500 dark:text-red-400">
                در حال پخش زنده
              </p>
            </div>
          </button>
        ))}
      </div>

      {/* Inline player */}
      {activeChannel && (
        <div className="overflow-hidden rounded-xl border-2 border-red-500">
          <div className="aspect-video">
            <iframe
              src={activeChannel.embed_url}
              className="h-full w-full"
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
              allowFullScreen
              title={activeChannel.name}
            />
          </div>
          <div className="flex items-center gap-2 bg-gray-50 px-4 py-2 text-sm text-gray-600 dark:bg-gray-800 dark:text-gray-400">
            <span className="relative flex h-2.5 w-2.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-500 opacity-75" />
              <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-red-500" />
            </span>
            {activeChannel.name_fa || activeChannel.name} — پخش زنده
          </div>
        </div>
      )}
    </div>
  );
}
