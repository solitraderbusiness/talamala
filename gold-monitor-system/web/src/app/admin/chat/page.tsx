"use client";

import { useCallback, useEffect, useState } from "react";
import { getToken } from "@/lib/auth";
import { timeAgo } from "@/lib/utils";
import {
  getChatOverview,
  getChatIntents,
  getChatTopics,
  getChatAssets,
  getChatFeatureGaps,
  getChatUsageHours,
  getChatSessionDepth,
  getChatConversations,
  getChatConversation,
  getChatSettings,
  updateChatSettings,
  ChatOverview,
  IntentCount,
  TopicCount,
  AssetCount,
  FeatureGap,
  UsageHour,
  SessionDepthBucket,
  ConversationsPage,
  ChatConversation,
  ChatSettingsData,
} from "@/lib/api";

// Recharts
import {
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

type Period = "today" | "week" | "month" | "all";
type Tab = "insights" | "conversations" | "settings";

const PERIOD_LABELS: Record<Period, string> = {
  today: "امروز",
  week: "این هفته",
  month: "این ماه",
  all: "همه",
};

const INTENT_LABELS: Record<string, string> = {
  news_search: "جستجوی خبر",
  calendar_query: "تقویم اقتصادی",
  price_check: "استعلام قیمت",
  sentiment_query: "سنتیمنت",
  comparison: "مقایسه",
  prediction: "پیش‌بینی",
  how_to_use: "راهنمای سایت",
  off_topic: "خارج از موضوع",
  feature_not_available: "قابلیت ناموجود",
};

const PIE_COLORS = [
  "#d4a017", "#e6b422", "#f0c929", "#c4951a",
  "#a67c14", "#6b7280", "#9ca3af", "#4b5563", "#374151",
];

const DOW_LABELS = ["یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه"];

export default function ChatInsightsPage() {
  const [tab, setTab] = useState<Tab>("insights");
  const [period, setPeriod] = useState<Period>("week");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Insights data
  const [overview, setOverview] = useState<ChatOverview | null>(null);
  const [intents, setIntents] = useState<IntentCount[]>([]);
  const [topics, setTopics] = useState<TopicCount[]>([]);
  const [assets, setAssets] = useState<AssetCount[]>([]);
  const [featureGaps, setFeatureGaps] = useState<FeatureGap[]>([]);
  const [usageHours, setUsageHours] = useState<UsageHour[]>([]);
  const [sessionDepth, setSessionDepth] = useState<SessionDepthBucket[]>([]);

  // Conversations
  const [conversations, setConversations] = useState<ConversationsPage | null>(null);
  const [selectedConvo, setSelectedConvo] = useState<ChatConversation | null>(null);
  const [convoPage, setConvoPage] = useState(1);
  const [convoFilter, setConvoFilter] = useState<{ intent?: string; had_answer?: boolean }>({});

  // Settings
  const [settings, setSettings] = useState<ChatSettingsData | null>(null);
  const [saving, setSaving] = useState(false);

  const token = getToken() || "";

  const loadInsights = useCallback(
    async (p: Period) => {
      setLoading(true);
      setError("");
      try {
        const [ov, int, top, ast, gaps, hours, depth] = await Promise.all([
          getChatOverview(token, p),
          getChatIntents(token, p),
          getChatTopics(token, p),
          getChatAssets(token, p),
          getChatFeatureGaps(token, p),
          getChatUsageHours(token, p),
          getChatSessionDepth(token, p),
        ]);
        setOverview(ov);
        setIntents(int);
        setTopics(top);
        setAssets(ast);
        setFeatureGaps(gaps);
        setUsageHours(hours);
        setSessionDepth(depth);
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : "خطا در بارگذاری");
      } finally {
        setLoading(false);
      }
    },
    [token],
  );

  const loadConversations = useCallback(
    async (page: number = 1) => {
      try {
        const data = await getChatConversations(token, {
          page,
          limit: 20,
          period,
          ...convoFilter,
        });
        setConversations(data);
        setConvoPage(page);
      } catch {
        setError("خطا در بارگذاری مکالمات");
      }
    },
    [token, period, convoFilter],
  );

  useEffect(() => {
    loadInsights(period);
  }, [period, loadInsights]);

  useEffect(() => {
    if (tab === "conversations") {
      loadConversations(1);
    }
    if (tab === "settings" && !settings) {
      getChatSettings(token).then(setSettings).catch(() => setError("خطا در بارگذاری تنظیمات"));
    }
  }, [tab]);

  const handlePeriodChange = (p: Period) => {
    setPeriod(p);
    if (tab === "conversations") {
      setConvoPage(1);
    }
  };

  const handleViewConversation = async (sessionId: string) => {
    try {
      const convo = await getChatConversation(token, sessionId);
      setSelectedConvo(convo);
    } catch {
      setError("خطا در بارگذاری مکالمه");
    }
  };

  const handleSaveSettings = async () => {
    if (!settings) return;
    setSaving(true);
    try {
      await updateChatSettings(token, settings);
    } catch {
      setError("خطا در ذخیره تنظیمات");
    } finally {
      setSaving(false);
    }
  };

  const trend = (current: number, prev: number) => {
    if (prev === 0) return current > 0 ? "+100%" : "";
    const pct = Math.round(((current - prev) / prev) * 100);
    return pct >= 0 ? `+${pct}%` : `${pct}%`;
  };

  const exportCsv = (type: string) => {
    const url = `/api/admin/chat/export?type=${type}`;
    fetch(url, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => r.blob())
      .then((blob) => {
        const blobUrl = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = blobUrl;
        a.download = `chat_${type}.csv`;
        a.click();
        URL.revokeObjectURL(blobUrl);
      });
  };

  if (loading && tab === "insights") {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <div className="h-10 w-10 animate-spin rounded-full border-4 border-gold-500 border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">
          بینش‌های کاربران
        </h2>
        <div className="flex gap-2">
          {(["insights", "conversations", "settings"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
                tab === t
                  ? "bg-gold-500 text-white"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300"
              }`}
            >
              {t === "insights" ? "بینش‌ها" : t === "conversations" ? "مکالمات" : "تنظیمات"}
            </button>
          ))}
        </div>
      </div>

      {/* Period filter */}
      {tab !== "settings" && (
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-500 dark:text-gray-400">دوره:</span>
          {(Object.keys(PERIOD_LABELS) as Period[]).map((p) => (
            <button
              key={p}
              onClick={() => handlePeriodChange(p)}
              className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                period === p
                  ? "bg-gold-100 text-gold-700 dark:bg-gold-900/30 dark:text-gold-400"
                  : "text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800"
              }`}
            >
              {PERIOD_LABELS[p]}
            </button>
          ))}
          {tab === "insights" && (
            <div className="mr-auto flex gap-1">
              <button
                onClick={() => exportCsv("analytics")}
                className="rounded-md bg-gray-100 px-2.5 py-1 text-xs text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300"
              >
                CSV خروجی
              </button>
            </div>
          )}
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-800 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
          {error}
          <button onClick={() => setError("")} className="mr-2 underline">
            بستن
          </button>
        </div>
      )}

      {/* INSIGHTS TAB */}
      {tab === "insights" && overview && (
        <div className="space-y-6">
          {/* 3.1 Overview Cards */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            <OverviewCard
              label="کل پیام‌ها"
              value={overview.total_messages}
              trend={trend(overview.total_messages, overview.prev_total_messages)}
            />
            <OverviewCard
              label="جلسات یکتا"
              value={overview.unique_sessions}
              trend={trend(overview.unique_sessions, overview.prev_unique_sessions)}
            />
            <OverviewCard label="میانگین پیام/جلسه" value={overview.avg_messages_per_session} />
            <OverviewCard label="هزینه API ($)" value={`$${overview.api_cost_estimate}`} />
            <OverviewCard
              label="بدون پاسخ"
              value={overview.unanswered_count}
              highlight={overview.unanswered_count > 0}
            />
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            {/* 3.2 Intent Distribution */}
            {intents.length > 0 && (
              <div className="card">
                <h3 className="mb-3 font-semibold text-gray-900 dark:text-gray-100">
                  توزیع نوع سوالات
                </h3>
                <div className="flex items-center justify-center">
                  <ResponsiveContainer width="100%" height={220}>
                    <PieChart>
                      <Pie
                        data={intents.map((d) => ({ ...d, name: INTENT_LABELS[d.intent] || d.intent }))}
                        dataKey="count"
                        nameKey="name"
                        cx="50%"
                        cy="50%"
                        outerRadius={80}
                        label={({ name, percent }: { name?: string; percent?: number }) =>
                          `${name ?? ""} ${((percent ?? 0) * 100).toFixed(0)}%`
                        }
                        labelLine={false}
                        fontSize={11}
                      >
                        {intents.map((_, i) => (
                          <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip formatter={(v: number) => v.toLocaleString("fa-IR")} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}

            {/* 3.4 Asset Interest */}
            {assets.length > 0 && (
              <div className="card">
                <h3 className="mb-3 font-semibold text-gray-900 dark:text-gray-100">
                  علاقه به دارایی‌ها
                </h3>
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={assets} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" opacity={0.2} />
                    <XAxis type="number" fontSize={11} />
                    <YAxis type="category" dataKey="label" width={120} fontSize={11} />
                    <Tooltip formatter={(v: number) => v.toLocaleString("fa-IR")} />
                    <Bar dataKey="count" fill="#d4a017" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>

          {/* 3.3 Trending Topics */}
          {topics.length > 0 && (
            <div className="card">
              <h3 className="mb-3 font-semibold text-gray-900 dark:text-gray-100">
                موضوعات داغ
              </h3>
              <ResponsiveContainer width="100%" height={Math.min(topics.length * 28 + 40, 300)}>
                <BarChart data={topics.slice(0, 15)} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" opacity={0.2} />
                  <XAxis type="number" fontSize={11} />
                  <YAxis type="category" dataKey="topic" width={130} fontSize={12} />
                  <Tooltip formatter={(v: number) => v.toLocaleString("fa-IR")} />
                  <Bar dataKey="count" fill="#e6b422" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* 3.5 Feature Gap Report */}
          {featureGaps.length > 0 && (
            <div className="card">
              <h3 className="mb-3 font-semibold text-gray-900 dark:text-gray-100">
                <span className="ml-2 inline-block h-2.5 w-2.5 rounded-full bg-red-500" />
                گزارش شکاف قابلیت‌ها (نقشه راه محصول)
              </h3>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-200 dark:border-gray-700">
                      <th className="px-3 py-2 text-right font-medium text-gray-500">#</th>
                      <th className="px-3 py-2 text-right font-medium text-gray-500">درخواست کاربر</th>
                      <th className="px-3 py-2 text-center font-medium text-gray-500">تعداد</th>
                      <th className="px-3 py-2 text-right font-medium text-gray-500">نمونه سوال</th>
                    </tr>
                  </thead>
                  <tbody>
                    {featureGaps.map((gap, i) => (
                      <tr
                        key={i}
                        className="border-b border-gray-100 last:border-0 dark:border-gray-800"
                      >
                        <td className="px-3 py-2 text-gray-400">
                          {(i + 1).toLocaleString("fa-IR")}
                        </td>
                        <td className="px-3 py-2 font-medium text-gray-800 dark:text-gray-200">
                          {gap.feature}
                        </td>
                        <td className="px-3 py-2 text-center">
                          <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-bold text-red-700 dark:bg-red-900/30 dark:text-red-400">
                            {gap.count.toLocaleString("fa-IR")}
                          </span>
                        </td>
                        <td className="max-w-[200px] truncate px-3 py-2 text-xs text-gray-500">
                          {gap.example}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          <div className="grid gap-6 lg:grid-cols-2">
            {/* 3.6 Peak Usage Hours */}
            {usageHours.length > 0 && (
              <div className="card">
                <h3 className="mb-3 font-semibold text-gray-900 dark:text-gray-100">
                  ساعات اوج استفاده
                </h3>
                <UsageHeatmap data={usageHours} />
              </div>
            )}

            {/* 3.7 Session Depth */}
            {sessionDepth.length > 0 && (
              <div className="card">
                <h3 className="mb-3 font-semibold text-gray-900 dark:text-gray-100">
                  عمق مکالمات
                </h3>
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={sessionDepth}>
                    <CartesianGrid strokeDasharray="3 3" opacity={0.2} />
                    <XAxis dataKey="bucket" fontSize={12} />
                    <YAxis fontSize={11} />
                    <Tooltip
                      formatter={(v: number) => v.toLocaleString("fa-IR")}
                      labelFormatter={(l) => `${l} پیام`}
                    />
                    <Bar dataKey="count" fill="#c4951a" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>

          {/* Empty state */}
          {intents.length === 0 && topics.length === 0 && (
            <div className="card py-12 text-center">
              <p className="text-gray-400">
                هنوز داده‌ای برای نمایش وجود ندارد. با شروع مکالمات چت، داده‌ها جمع‌آوری می‌شوند.
              </p>
            </div>
          )}
        </div>
      )}

      {/* CONVERSATIONS TAB */}
      {tab === "conversations" && (
        <div className="space-y-4">
          {selectedConvo ? (
            <ConversationDetail
              convo={selectedConvo}
              onBack={() => setSelectedConvo(null)}
            />
          ) : (
            <>
              {/* Filters */}
              <div className="flex flex-wrap gap-2">
                <select
                  value={convoFilter.intent || ""}
                  onChange={(e) => {
                    setConvoFilter({ ...convoFilter, intent: e.target.value || undefined });
                    setTimeout(() => loadConversations(1), 0);
                  }}
                  className="rounded-md border border-gray-300 bg-white px-2 py-1 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
                >
                  <option value="">همه نوع‌ها</option>
                  {Object.entries(INTENT_LABELS).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </select>
                <select
                  value={convoFilter.had_answer === undefined ? "" : String(convoFilter.had_answer)}
                  onChange={(e) => {
                    const v = e.target.value;
                    setConvoFilter({
                      ...convoFilter,
                      had_answer: v === "" ? undefined : v === "true",
                    });
                    setTimeout(() => loadConversations(1), 0);
                  }}
                  className="rounded-md border border-gray-300 bg-white px-2 py-1 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
                >
                  <option value="">همه وضعیت‌ها</option>
                  <option value="true">پاسخ داده شده</option>
                  <option value="false">بدون پاسخ</option>
                </select>
              </div>

              {/* Session list */}
              <div className="card">
                <h3 className="mb-3 font-semibold text-gray-900 dark:text-gray-100">
                  مکالمات اخیر
                </h3>
                {conversations && conversations.items.length > 0 ? (
                  <>
                    <div className="divide-y divide-gray-100 dark:divide-gray-800">
                      {conversations.items.map((s) => (
                        <button
                          key={s.id}
                          onClick={() => handleViewConversation(s.id)}
                          className="flex w-full items-center gap-3 px-2 py-3 text-right transition-colors hover:bg-gray-50 dark:hover:bg-gray-800"
                        >
                          <div className="min-w-0 flex-1">
                            <p className="truncate text-sm font-medium text-gray-800 dark:text-gray-200">
                              {s.first_message || "(بدون پیام)"}
                            </p>
                            <div className="mt-1 flex flex-wrap gap-2 text-xs text-gray-500">
                              <span>{s.messages_count} پیام</span>
                              {s.primary_intent && (
                                <span className="rounded bg-gray-100 px-1.5 py-0.5 dark:bg-gray-700">
                                  {INTENT_LABELS[s.primary_intent] || s.primary_intent}
                                </span>
                              )}
                              {s.had_answer_rate !== null && s.had_answer_rate < 1 && (
                                <span className="rounded bg-red-100 px-1.5 py-0.5 text-red-700 dark:bg-red-900/30 dark:text-red-400">
                                  {Math.round(s.had_answer_rate * 100)}% پاسخ
                                </span>
                              )}
                              <span>{timeAgo(s.last_active_at)}</span>
                            </div>
                          </div>
                        </button>
                      ))}
                    </div>

                    {/* Pagination */}
                    {conversations.pages > 1 && (
                      <div className="mt-3 flex items-center justify-center gap-2">
                        <button
                          onClick={() => loadConversations(convoPage - 1)}
                          disabled={convoPage <= 1}
                          className="rounded-md bg-gray-100 px-3 py-1 text-sm disabled:opacity-40 dark:bg-gray-700"
                        >
                          قبلی
                        </button>
                        <span className="text-sm text-gray-500">
                          {convoPage.toLocaleString("fa-IR")} / {conversations.pages.toLocaleString("fa-IR")}
                        </span>
                        <button
                          onClick={() => loadConversations(convoPage + 1)}
                          disabled={convoPage >= conversations.pages}
                          className="rounded-md bg-gray-100 px-3 py-1 text-sm disabled:opacity-40 dark:bg-gray-700"
                        >
                          بعدی
                        </button>
                      </div>
                    )}
                  </>
                ) : (
                  <p className="text-sm text-gray-500">مکالمه‌ای یافت نشد.</p>
                )}
              </div>
            </>
          )}
        </div>
      )}

      {/* SETTINGS TAB */}
      {tab === "settings" && settings && (
        <div className="card space-y-4">
          <h3 className="font-semibold text-gray-900 dark:text-gray-100">
            تنظیمات چت هوشمند
          </h3>
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                فعال بودن چت
              </label>
              <button
                onClick={() =>
                  setSettings({
                    ...settings,
                    enabled: settings.enabled === "true" ? "false" : "true",
                  })
                }
                className={`relative h-6 w-11 rounded-full transition-colors ${
                  settings.enabled === "true" ? "bg-gold-500" : "bg-gray-300 dark:bg-gray-600"
                }`}
              >
                <span
                  className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform ${
                    settings.enabled === "true" ? "right-0.5" : "right-[22px]"
                  }`}
                />
              </button>
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
                مدل
              </label>
              <input
                type="text"
                value={settings.model}
                onChange={(e) => setSettings({ ...settings, model: e.target.value })}
                className="input-field"
                dir="ltr"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
                  محدودیت هر IP (در ساعت)
                </label>
                <input
                  type="number"
                  value={settings.rate_limit_ip}
                  onChange={(e) => setSettings({ ...settings, rate_limit_ip: e.target.value })}
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
                  value={settings.rate_limit_global}
                  onChange={(e) => setSettings({ ...settings, rate_limit_global: e.target.value })}
                  className="input-field"
                  dir="ltr"
                />
              </div>
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
                پیام خوش‌آمدگویی
              </label>
              <textarea
                value={settings.welcome_message}
                onChange={(e) => setSettings({ ...settings, welcome_message: e.target.value })}
                className="input-field min-h-[80px]"
                rows={3}
              />
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
                پرامپت سیستم (اختیاری)
              </label>
              <textarea
                value={settings.system_prompt}
                onChange={(e) => setSettings({ ...settings, system_prompt: e.target.value })}
                className="input-field min-h-[120px] font-mono text-xs"
                rows={6}
                dir="ltr"
                placeholder="Leave empty to use default prompt from file..."
              />
            </div>

            <button onClick={handleSaveSettings} disabled={saving} className="btn-primary">
              {saving ? "در حال ذخیره..." : "ذخیره تنظیمات"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Sub-components ────────────────────────────────────────────────────

function OverviewCard({
  label,
  value,
  trend,
  highlight,
}: {
  label: string;
  value: number | string;
  trend?: string;
  highlight?: boolean;
}) {
  const isPositive = trend?.startsWith("+");
  return (
    <div className={`card text-center ${highlight ? "ring-2 ring-red-400/50" : ""}`}>
      <p
        className={`text-2xl font-bold ${
          highlight
            ? "text-red-500"
            : "text-gold-600 dark:text-gold-400"
        }`}
      >
        {typeof value === "number" ? value.toLocaleString("fa-IR") : value}
      </p>
      <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{label}</p>
      {trend && (
        <p
          className={`mt-0.5 text-xs font-medium ${
            isPositive ? "text-green-500" : "text-red-500"
          }`}
        >
          {trend} نسبت به قبل
        </p>
      )}
    </div>
  );
}

function UsageHeatmap({ data }: { data: UsageHour[] }) {
  const grid: Record<string, number> = {};
  let max = 0;
  for (const d of data) {
    const key = `${d.dow}-${d.hour}`;
    grid[key] = (grid[key] || 0) + d.count;
    if (grid[key] > max) max = grid[key];
  }

  const hours = Array.from({ length: 24 }, (_, i) => i);
  const days = Array.from({ length: 7 }, (_, i) => i);

  return (
    <div className="overflow-x-auto">
      <div className="inline-grid gap-0.5" style={{ gridTemplateColumns: `70px repeat(24, 18px)` }}>
        <div />
        {hours.map((h) => (
          <div key={h} className="text-center text-[9px] text-gray-400">
            {h}
          </div>
        ))}

        {days.map((d) => (
          <div key={`row-${d}`} className="contents">
            <div className="text-[10px] leading-[18px] text-gray-500">
              {DOW_LABELS[d]}
            </div>
            {hours.map((h) => {
              const count = grid[`${d}-${h}`] || 0;
              const intensity = max > 0 ? count / max : 0;
              return (
                <div
                  key={`${d}-${h}`}
                  className="h-[18px] w-[18px] rounded-sm"
                  style={{
                    backgroundColor: intensity > 0
                      ? `rgba(212, 160, 23, ${0.15 + intensity * 0.85})`
                      : "rgba(107, 114, 128, 0.1)",
                  }}
                  title={`${DOW_LABELS[d]} ${h}:00 - ${count} پیام`}
                />
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

function ConversationDetail({
  convo,
  onBack,
}: {
  convo: ChatConversation;
  onBack: () => void;
}) {
  return (
    <div className="card">
      <div className="mb-4 flex items-center justify-between">
        <button onClick={onBack} className="btn-secondary text-sm">
          بازگشت به لیست
        </button>
        <div className="flex items-center gap-2 text-xs text-gray-500">
          {convo.session.primary_intent && (
            <span className="rounded bg-gray-100 px-1.5 py-0.5 dark:bg-gray-700">
              {INTENT_LABELS[convo.session.primary_intent] || convo.session.primary_intent}
            </span>
          )}
          <span>{convo.session.messages_count} پیام</span>
        </div>
      </div>

      <div className="space-y-3">
        {convo.messages.map((msg) => (
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
              <span className="text-xs text-gray-400">{timeAgo(msg.created_at)}</span>
            </div>
            <p className="whitespace-pre-wrap text-sm text-gray-800 dark:text-gray-200">
              {msg.content}
            </p>
            {msg.tool_calls ? (
              <div className="mt-2 rounded bg-gray-100 p-2 text-xs text-gray-500 dark:bg-gray-700">
                ابزارها: {JSON.stringify(msg.tool_calls, null, 2)}
              </div>
            ) : null}
            {msg.analytics && (
              <div className="mt-2 flex flex-wrap gap-1">
                <span className="rounded bg-blue-100 px-1.5 py-0.5 text-[10px] text-blue-700 dark:bg-blue-900/30 dark:text-blue-400">
                  {INTENT_LABELS[msg.analytics.intent] || msg.analytics.intent}
                </span>
                {!msg.analytics.had_answer && (
                  <span className="rounded bg-red-100 px-1.5 py-0.5 text-[10px] text-red-700 dark:bg-red-900/30 dark:text-red-400">
                    بدون پاسخ
                  </span>
                )}
                {msg.analytics.missing_feature && (
                  <span className="rounded bg-orange-100 px-1.5 py-0.5 text-[10px] text-orange-700 dark:bg-orange-900/30 dark:text-orange-400">
                    {msg.analytics.missing_feature}
                  </span>
                )}
                {msg.analytics.topics?.map((t, i) => (
                  <span
                    key={i}
                    className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] text-gray-600 dark:bg-gray-700 dark:text-gray-300"
                  >
                    {t}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
