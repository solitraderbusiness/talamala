"use client";

import { useState, useEffect, useCallback } from "react";
import { cn } from "@/lib/utils";
import { getToken } from "@/lib/auth";
import {
  getVideos,
  adminAddVideo,
  adminUpdateVideo,
  adminRegenerateVideo,
  adminGetVideoChannels,
  adminAddVideoChannel,
  adminUpdateVideoChannel,
  type CuratedVideo,
  type MonitoredChannel,
} from "@/lib/api";

export default function AdminVideosPage() {
  const token = getToken() || "";

  // Videos tab state
  const [videos, setVideos] = useState<CuratedVideo[]>([]);
  const [totalVideos, setTotalVideos] = useState(0);
  const [page, setPage] = useState(1);
  const [videosLoading, setVideosLoading] = useState(true);

  // Channels tab state
  const [channels, setChannels] = useState<MonitoredChannel[]>([]);
  const [channelsLoading, setChannelsLoading] = useState(true);

  // Add video form
  const [newVideoUrl, setNewVideoUrl] = useState("");
  const [addingVideo, setAddingVideo] = useState(false);
  const [addVideoMsg, setAddVideoMsg] = useState("");

  // Add channel form
  const [newChannelName, setNewChannelName] = useState("");
  const [newChannelId, setNewChannelId] = useState("");
  const [addingChannel, setAddingChannel] = useState(false);
  const [addChannelMsg, setAddChannelMsg] = useState("");

  // Active tab
  const [tab, setTab] = useState<"videos" | "channels">("videos");

  const fetchVideos = useCallback(async () => {
    setVideosLoading(true);
    try {
      // Fetch all videos (including unpublished) via the standard endpoint
      // Admin sees all — we fetch with a large per_page
      const result = await getVideos({ page, per_page: 20 });
      setVideos(result.videos);
      setTotalVideos(result.total);
    } catch {
      // Fallback: empty
    } finally {
      setVideosLoading(false);
    }
  }, [page]);

  const fetchChannels = useCallback(async () => {
    if (!token) return;
    setChannelsLoading(true);
    try {
      const result = await adminGetVideoChannels(token);
      setChannels(result.channels);
    } catch {
      // ignore
    } finally {
      setChannelsLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchVideos();
    fetchChannels();
  }, [fetchVideos, fetchChannels]);

  async function handleAddVideo() {
    if (!newVideoUrl.trim() || !token) return;
    setAddingVideo(true);
    setAddVideoMsg("");
    try {
      const result = await adminAddVideo(token, newVideoUrl.trim());
      setAddVideoMsg(`ویدیو اضافه شد (ID: ${result.youtube_id})`);
      setNewVideoUrl("");
      fetchVideos();
    } catch (err) {
      setAddVideoMsg(err instanceof Error ? err.message : "خطا");
    } finally {
      setAddingVideo(false);
    }
  }

  async function handleTogglePublished(video: CuratedVideo) {
    if (!token) return;
    try {
      await adminUpdateVideo(token, video.id, {
        is_published: !video.is_published,
      });
      fetchVideos();
    } catch {
      // ignore
    }
  }

  async function handleToggleFeatured(video: CuratedVideo) {
    if (!token) return;
    try {
      await adminUpdateVideo(token, video.id, {
        is_featured: !video.is_featured,
      });
      fetchVideos();
    } catch {
      // ignore
    }
  }

  async function handleDelete(video: CuratedVideo) {
    if (!token || !confirm("حذف این ویدیو؟")) return;
    try {
      await adminUpdateVideo(token, video.id, { deleted: true });
      fetchVideos();
    } catch {
      // ignore
    }
  }

  async function handleRegenerate(video: CuratedVideo) {
    if (!token) return;
    try {
      await adminRegenerateVideo(token, video.id);
      fetchVideos();
    } catch {
      // ignore
    }
  }

  async function handleAddChannel() {
    if (!newChannelName.trim() || !newChannelId.trim() || !token) return;
    setAddingChannel(true);
    setAddChannelMsg("");
    try {
      await adminAddVideoChannel(token, {
        name: newChannelName.trim(),
        youtube_channel_id: newChannelId.trim(),
      });
      setAddChannelMsg("کانال اضافه شد");
      setNewChannelName("");
      setNewChannelId("");
      fetchChannels();
    } catch (err) {
      setAddChannelMsg(err instanceof Error ? err.message : "خطا");
    } finally {
      setAddingChannel(false);
    }
  }

  async function handleToggleChannel(ch: MonitoredChannel, field: "is_active" | "auto_publish" | "always_relevant") {
    if (!token) return;
    const value = field === "is_active" ? !ch.is_active : field === "auto_publish" ? !ch.auto_publish : !ch.always_relevant;
    try {
      await adminUpdateVideoChannel(token, ch.id, { [field]: value });
      fetchChannels();
    } catch {
      // ignore
    }
  }

  const totalPages = Math.ceil(totalVideos / 20);

  return (
    <div className="space-y-5">
      <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100">
        مدیریت ویدیوها
      </h2>

      {/* Sub-tabs */}
      <div className="flex gap-2">
        <button
          onClick={() => setTab("videos")}
          className={cn(
            "rounded-lg px-4 py-2 text-sm font-medium transition-colors",
            tab === "videos"
              ? "bg-gold-600 text-white"
              : "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400"
          )}
        >
          ویدیوها ({totalVideos})
        </button>
        <button
          onClick={() => setTab("channels")}
          className={cn(
            "rounded-lg px-4 py-2 text-sm font-medium transition-colors",
            tab === "channels"
              ? "bg-gold-600 text-white"
              : "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400"
          )}
        >
          کانال‌ها ({channels.length})
        </button>
      </div>

      {/* Videos tab */}
      {tab === "videos" && (
        <div className="space-y-4">
          {/* Add video form */}
          <div className="rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900">
            <h3 className="mb-3 text-sm font-bold text-gray-700 dark:text-gray-300">
              افزودن ویدیو
            </h3>
            <div className="flex gap-2">
              <input
                type="text"
                value={newVideoUrl}
                onChange={(e) => setNewVideoUrl(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleAddVideo()}
                placeholder="لینک YouTube..."
                className="flex-1 rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-gold-500 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300"
                dir="ltr"
              />
              <button
                onClick={handleAddVideo}
                disabled={addingVideo}
                className="rounded-lg bg-gold-600 px-4 py-2 text-sm font-medium text-white hover:bg-gold-700 disabled:opacity-50"
              >
                {addingVideo ? "..." : "افزودن"}
              </button>
            </div>
            {addVideoMsg && (
              <p className="mt-2 text-xs text-gray-500">{addVideoMsg}</p>
            )}
          </div>

          {/* Videos table */}
          {videosLoading ? (
            <div className="py-8 text-center text-gray-400">بارگذاری...</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 dark:border-gray-800">
                    <th className="px-3 py-2 text-right font-medium text-gray-500">عنوان</th>
                    <th className="px-3 py-2 text-right font-medium text-gray-500">کانال</th>
                    <th className="px-3 py-2 text-center font-medium text-gray-500">LLM</th>
                    <th className="px-3 py-2 text-center font-medium text-gray-500">منتشر</th>
                    <th className="px-3 py-2 text-center font-medium text-gray-500">برتر</th>
                    <th className="px-3 py-2 text-center font-medium text-gray-500">امتیاز</th>
                    <th className="px-3 py-2 text-center font-medium text-gray-500">عملیات</th>
                  </tr>
                </thead>
                <tbody>
                  {videos.map((v) => (
                    <tr
                      key={v.id}
                      className="border-b border-gray-100 dark:border-gray-800"
                    >
                      <td className="max-w-[200px] truncate px-3 py-2 text-gray-700 dark:text-gray-300">
                        {v.title_fa || v.title_original || v.youtube_id}
                      </td>
                      <td className="px-3 py-2 text-gray-500">
                        {v.channel_name || "-"}
                      </td>
                      <td className="px-3 py-2 text-center">
                        {v.has_transcript ? "✅" : "⏳"}
                      </td>
                      <td className="px-3 py-2 text-center">
                        <button
                          onClick={() => handleTogglePublished(v)}
                          className={cn(
                            "rounded px-2 py-0.5 text-xs",
                            v.is_published
                              ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                              : "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400"
                          )}
                        >
                          {v.is_published ? "بله" : "خیر"}
                        </button>
                      </td>
                      <td className="px-3 py-2 text-center">
                        <button
                          onClick={() => handleToggleFeatured(v)}
                          className={cn(
                            "rounded px-2 py-0.5 text-xs",
                            v.is_featured
                              ? "bg-gold-100 text-gold-700 dark:bg-gold-900/30 dark:text-gold-400"
                              : "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400"
                          )}
                        >
                          {v.is_featured ? "⭐" : "-"}
                        </button>
                      </td>
                      <td className="px-3 py-2 text-center text-gray-500">
                        {v.relevance_score != null
                          ? Math.round(v.relevance_score)
                          : "-"}
                      </td>
                      <td className="px-3 py-2 text-center">
                        <div className="flex justify-center gap-1">
                          <button
                            onClick={() => handleRegenerate(v)}
                            title="بازسازی"
                            className="rounded px-1.5 py-0.5 text-xs text-blue-600 hover:bg-blue-50 dark:text-blue-400 dark:hover:bg-blue-900/20"
                          >
                            🔄
                          </button>
                          <button
                            onClick={() => handleDelete(v)}
                            title="حذف"
                            className="rounded px-1.5 py-0.5 text-xs text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-900/20"
                          >
                            🗑️
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

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
      )}

      {/* Channels tab */}
      {tab === "channels" && (
        <div className="space-y-4">
          {/* Add channel form */}
          <div className="rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900">
            <h3 className="mb-3 text-sm font-bold text-gray-700 dark:text-gray-300">
              افزودن کانال
            </h3>
            <div className="flex flex-wrap gap-2">
              <input
                type="text"
                value={newChannelName}
                onChange={(e) => setNewChannelName(e.target.value)}
                placeholder="نام کانال..."
                className="rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-gold-500 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300"
              />
              <input
                type="text"
                value={newChannelId}
                onChange={(e) => setNewChannelId(e.target.value)}
                placeholder="Channel ID..."
                className="rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-gold-500 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300"
                dir="ltr"
              />
              <button
                onClick={handleAddChannel}
                disabled={addingChannel}
                className="rounded-lg bg-gold-600 px-4 py-2 text-sm font-medium text-white hover:bg-gold-700 disabled:opacity-50"
              >
                {addingChannel ? "..." : "افزودن"}
              </button>
            </div>
            {addChannelMsg && (
              <p className="mt-2 text-xs text-gray-500">{addChannelMsg}</p>
            )}
          </div>

          {/* Channels table */}
          {channelsLoading ? (
            <div className="py-8 text-center text-gray-400">بارگذاری...</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 dark:border-gray-800">
                    <th className="px-3 py-2 text-right font-medium text-gray-500">نام</th>
                    <th className="px-3 py-2 text-right font-medium text-gray-500">Channel ID</th>
                    <th className="px-3 py-2 text-center font-medium text-gray-500">فعال</th>
                    <th className="px-3 py-2 text-center font-medium text-gray-500">انتشار خودکار</th>
                    <th className="px-3 py-2 text-center font-medium text-gray-500">همیشه مرتبط</th>
                    <th className="px-3 py-2 text-right font-medium text-gray-500">آخرین بررسی</th>
                  </tr>
                </thead>
                <tbody>
                  {channels.map((ch) => (
                    <tr
                      key={ch.id}
                      className="border-b border-gray-100 dark:border-gray-800"
                    >
                      <td className="px-3 py-2 text-gray-700 dark:text-gray-300">
                        {ch.name}
                      </td>
                      <td className="px-3 py-2 font-mono text-xs text-gray-500" dir="ltr">
                        {ch.youtube_channel_id}
                      </td>
                      <td className="px-3 py-2 text-center">
                        <button
                          onClick={() => handleToggleChannel(ch, "is_active")}
                          className={cn(
                            "rounded px-2 py-0.5 text-xs",
                            ch.is_active
                              ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                              : "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400"
                          )}
                        >
                          {ch.is_active ? "بله" : "خیر"}
                        </button>
                      </td>
                      <td className="px-3 py-2 text-center">
                        <button
                          onClick={() => handleToggleChannel(ch, "auto_publish")}
                          className={cn(
                            "rounded px-2 py-0.5 text-xs",
                            ch.auto_publish
                              ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                              : "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400"
                          )}
                        >
                          {ch.auto_publish ? "بله" : "خیر"}
                        </button>
                      </td>
                      <td className="px-3 py-2 text-center">
                        <button
                          onClick={() => handleToggleChannel(ch, "always_relevant")}
                          className={cn(
                            "rounded px-2 py-0.5 text-xs",
                            ch.always_relevant
                              ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                              : "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400"
                          )}
                        >
                          {ch.always_relevant ? "بله" : "خیر"}
                        </button>
                      </td>
                      <td className="px-3 py-2 text-xs text-gray-400">
                        {ch.last_checked_at || "-"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
