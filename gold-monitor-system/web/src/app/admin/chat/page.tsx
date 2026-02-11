"use client";

import { useEffect, useState } from "react";
import { getToken } from "@/lib/auth";
import { timeAgo } from "@/lib/utils";
import {
  getChatDashboard,
  getChatSessions,
  getChatConversation,
  getChatSettings,
  updateChatSettings,
  getPopularQuestions,
  ChatDashboard,
  ChatSessionSummary,
  ChatConversation,
  ChatSettingsData,
} from "@/lib/api";

export default function ChatAnalyticsPage() {
  const [dashboard, setDashboard] = useState<ChatDashboard | null>(null);
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
  const [selectedConversation, setSelectedConversation] = useState<ChatConversation | null>(null);
  const [chatSettings, setChatSettings] = useState<ChatSettingsData | null>(null);
  const [popularQuestions, setPopularQuestions] = useState<Array<{ question: string; count: number }>>([]);
  const [activeTab, setActiveTab] = useState<"dashboard" | "sessions" | "settings">("dashboard");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const token = getToken() || "";

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    setLoading(true);
    setError("");
    try {
      const [dash, sess, popular] = await Promise.all([
        getChatDashboard(token),
        getChatSessions(token),
        getPopularQuestions(token),
      ]);
      setDashboard(dash);
      setSessions(sess);
      setPopularQuestions(popular);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load data";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  async function loadSettings() {
    try {
      const settings = await getChatSettings(token);
      setChatSettings(settings);
    } catch {
      setError("Failed to load chat settings");
    }
  }

  async function handleSaveSettings() {
    if (!chatSettings) return;
    setSaving(true);
    try {
      await updateChatSettings(token, chatSettings);
      setSaving(false);
    } catch {
      setError("Failed to save settings");
      setSaving(false);
    }
  }

  async function loadConversation(sessionId: string) {
    try {
      const convo = await getChatConversation(token, sessionId);
      setSelectedConversation(convo);
    } catch {
      setError("Failed to load conversation");
    }
  }

  useEffect(() => {
    if (activeTab === "settings" && !chatSettings) {
      loadSettings();
    }
  }, [activeTab]);

  if (loading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <div className="h-10 w-10 animate-spin rounded-full border-4 border-gold-500 border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">
          چت هوشمند
        </h2>
        <div className="flex gap-2">
          {(["dashboard", "sessions", "settings"] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
                activeTab === tab
                  ? "bg-gold-500 text-white"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
              }`}
            >
              {tab === "dashboard" ? "داشبورد" : tab === "sessions" ? "مکالمات" : "تنظیمات"}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-800 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
          {error}
        </div>
      )}

      {/* Dashboard Tab */}
      {activeTab === "dashboard" && dashboard && (
        <div className="space-y-6">
          {/* Stats cards */}
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <StatCard label="پیام‌های امروز" value={dashboard.messages_today} />
            <StatCard label="پیام‌های این هفته" value={dashboard.messages_this_week} />
            <StatCard label="پیام‌های این ماه" value={dashboard.messages_this_month} />
            <StatCard label="جلسات امروز" value={dashboard.sessions_today} />
          </div>

          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
            <StatCard label="میانگین پیام/جلسه" value={dashboard.avg_messages_per_session} />
            <StatCard label="توکن مصرفی امروز" value={dashboard.total_tokens_today.toLocaleString("fa-IR")} />
            <StatCard label="کل جلسات" value={dashboard.total_sessions} />
          </div>

          {/* Popular questions */}
          {popularQuestions.length > 0 && (
            <div className="card">
              <h3 className="mb-3 font-semibold text-gray-900 dark:text-gray-100">
                سوالات پرتکرار
              </h3>
              <div className="space-y-2">
                {popularQuestions.map((q, i) => (
                  <div
                    key={i}
                    className="flex items-center justify-between rounded-lg bg-gray-50 px-3 py-2 dark:bg-gray-800"
                  >
                    <span className="text-sm text-gray-700 dark:text-gray-300 truncate max-w-[80%]">
                      {q.question}
                    </span>
                    <span className="rounded-full bg-gold-100 px-2 py-0.5 text-xs font-medium text-gold-700 dark:bg-gold-900/30 dark:text-gold-400">
                      {q.count}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Sessions Tab */}
      {activeTab === "sessions" && (
        <div className="space-y-4">
          {selectedConversation ? (
            <div className="card">
              <div className="mb-4 flex items-center justify-between">
                <button
                  onClick={() => setSelectedConversation(null)}
                  className="btn-secondary text-sm"
                >
                  بازگشت به لیست
                </button>
                <span className="text-xs text-gray-500">
                  {selectedConversation.session.messages_count} پیام
                </span>
              </div>

              <div className="space-y-3">
                {selectedConversation.messages.map((msg) => (
                  <div
                    key={msg.id}
                    className={`rounded-lg p-3 ${
                      msg.role === "user"
                        ? "mr-8 bg-gold-50 dark:bg-gold-900/20"
                        : "ml-8 bg-gray-50 dark:bg-gray-800"
                    }`}
                  >
                    <div className="mb-1 flex items-center justify-between">
                      <span className="text-xs font-medium text-gray-500">
                        {msg.role === "user" ? "کاربر" : "دستیار هوشمند"}
                      </span>
                      <span className="text-xs text-gray-400">
                        {timeAgo(msg.created_at)}
                      </span>
                    </div>
                    <p className="whitespace-pre-wrap text-sm text-gray-800 dark:text-gray-200">
                      {msg.content}
                    </p>
                    {msg.tool_calls ? (
                      <div className="mt-2 rounded bg-gray-100 p-2 text-xs text-gray-500 dark:bg-gray-700">
                        Tools used: {JSON.stringify(msg.tool_calls, null, 2)}
                      </div>
                    ) : null}
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="card">
              <h3 className="mb-3 font-semibold text-gray-900 dark:text-gray-100">
                مکالمات اخیر
              </h3>
              {sessions.length === 0 ? (
                <p className="text-sm text-gray-500">هنوز مکالمه‌ای ثبت نشده.</p>
              ) : (
                <div className="divide-y divide-gray-100 dark:divide-gray-800">
                  {sessions.map((s) => (
                    <button
                      key={s.id}
                      onClick={() => loadConversation(s.id)}
                      className="flex w-full items-center justify-between px-2 py-3 text-right transition-colors hover:bg-gray-50 dark:hover:bg-gray-800"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium text-gray-800 dark:text-gray-200">
                          {s.first_message || "(بدون پیام)"}
                        </p>
                        <p className="text-xs text-gray-500">
                          {s.messages_count} پیام &middot; {timeAgo(s.last_active_at)}
                        </p>
                      </div>
                      <span className="mr-2 text-xs text-gray-400">
                        {s.id.slice(0, 8)}...
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Settings Tab */}
      {activeTab === "settings" && chatSettings && (
        <div className="card space-y-4">
          <h3 className="font-semibold text-gray-900 dark:text-gray-100">
            تنظیمات چت هوشمند
          </h3>

          <div className="space-y-4">
            {/* Enabled toggle */}
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                فعال بودن چت
              </label>
              <button
                onClick={() =>
                  setChatSettings({
                    ...chatSettings,
                    enabled: chatSettings.enabled === "true" ? "false" : "true",
                  })
                }
                className={`relative h-6 w-11 rounded-full transition-colors ${
                  chatSettings.enabled === "true" ? "bg-gold-500" : "bg-gray-300 dark:bg-gray-600"
                }`}
              >
                <span
                  className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform ${
                    chatSettings.enabled === "true" ? "right-0.5" : "right-[22px]"
                  }`}
                />
              </button>
            </div>

            {/* Model */}
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
                مدل
              </label>
              <input
                type="text"
                value={chatSettings.model}
                onChange={(e) => setChatSettings({ ...chatSettings, model: e.target.value })}
                className="input-field"
                dir="ltr"
              />
            </div>

            {/* Rate limits */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
                  محدودیت هر IP (در ساعت)
                </label>
                <input
                  type="number"
                  value={chatSettings.rate_limit_ip}
                  onChange={(e) =>
                    setChatSettings({ ...chatSettings, rate_limit_ip: e.target.value })
                  }
                  className="input-field"
                  dir="ltr"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
                  محدودیت کل (در ساعت)
                </label>
                <input
                  type="number"
                  value={chatSettings.rate_limit_global}
                  onChange={(e) =>
                    setChatSettings({ ...chatSettings, rate_limit_global: e.target.value })
                  }
                  className="input-field"
                  dir="ltr"
                />
              </div>
            </div>

            {/* Welcome message */}
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
                پیام خوش‌آمدگویی
              </label>
              <textarea
                value={chatSettings.welcome_message}
                onChange={(e) =>
                  setChatSettings({ ...chatSettings, welcome_message: e.target.value })
                }
                className="input-field min-h-[80px]"
                rows={3}
              />
            </div>

            {/* System prompt */}
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
                پرامپت سیستم (اختیاری)
              </label>
              <textarea
                value={chatSettings.system_prompt}
                onChange={(e) =>
                  setChatSettings({ ...chatSettings, system_prompt: e.target.value })
                }
                className="input-field min-h-[120px] font-mono text-xs"
                rows={6}
                dir="ltr"
                placeholder="Leave empty to use default prompt from file..."
              />
            </div>

            <button
              onClick={handleSaveSettings}
              disabled={saving}
              className="btn-primary"
            >
              {saving ? "در حال ذخیره..." : "ذخیره تنظیمات"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="card text-center">
      <p className="text-2xl font-bold text-gold-600 dark:text-gold-400">
        {typeof value === "number" ? value.toLocaleString("fa-IR") : value}
      </p>
      <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{label}</p>
    </div>
  );
}
