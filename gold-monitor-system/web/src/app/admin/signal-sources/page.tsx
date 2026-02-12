"use client";

import { useState, useEffect, useCallback } from "react";
import {
  getSignalSources,
  createSignalSource,
  updateSignalSource,
  deleteSignalSource,
  type SignalSourceAdmin,
} from "@/lib/api";
import { getToken } from "@/lib/auth";
import { formatDate } from "@/lib/utils";

interface SourceFormData {
  name: string;
  type: string;
  telegram_channel_id: string;
  telegram_channel_name: string;
  url: string;
  active: boolean;
  current_weight: number;
}

const emptyForm: SourceFormData = {
  name: "",
  type: "telegram",
  telegram_channel_id: "",
  telegram_channel_name: "",
  url: "",
  active: true,
  current_weight: 0.5,
};

const sourceTypeLabels: Record<string, string> = {
  telegram: "تلگرام",
  tradingview: "TradingView",
  website: "وب‌سایت",
  forum: "فروم",
};

function weightBadge(weight: number) {
  if (weight >= 0.7) return { label: "بالا", className: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400" };
  if (weight >= 0.3) return { label: "متوسط", className: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400" };
  return { label: "پایین", className: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400" };
}

export default function AdminSignalSourcesPage() {
  const [sources, setSources] = useState<SignalSourceAdmin[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<SourceFormData>(emptyForm);
  const [saving, setSaving] = useState(false);

  const token = getToken() || "";

  const loadSources = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getSignalSources(token);
      setSources(data.items || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "خطا در بارگذاری منابع سیگنال");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    loadSources();
  }, [loadSources]);

  function openCreateForm() {
    setForm(emptyForm);
    setEditingId(null);
    setShowForm(true);
  }

  function openEditForm(source: SignalSourceAdmin) {
    setForm({
      name: source.name,
      type: source.type,
      telegram_channel_id: source.telegram_channel_id || "",
      telegram_channel_name: source.telegram_channel_name || "",
      url: source.url || "",
      active: source.active,
      current_weight: source.current_weight,
    });
    setEditingId(source.id);
    setShowForm(true);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const payload: Record<string, unknown> = {
        name: form.name,
        type: form.type,
        active: form.active,
      };

      // Include type-specific fields
      if (form.type === "telegram") {
        payload.telegram_channel_id = form.telegram_channel_id || null;
        payload.telegram_channel_name = form.telegram_channel_name || null;
      } else {
        payload.url = form.url || null;
      }

      // Include weight only on edit
      if (editingId) {
        payload.current_weight = form.current_weight;
        await updateSignalSource(token, editingId, payload);
      } else {
        await createSignalSource(token, payload);
      }
      setShowForm(false);
      setEditingId(null);
      await loadSources();
    } catch (err) {
      setError(err instanceof Error ? err.message : "خطا در ذخیره");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: string, name: string) {
    if (!confirm(`آیا از حذف منبع "${name}" اطمینان دارید؟ تمام سیگنال‌های مرتبط نیز حذف خواهند شد.`)) return;
    try {
      await deleteSignalSource(token, id);
      await loadSources();
    } catch (err) {
      setError(err instanceof Error ? err.message : "خطا در حذف");
    }
  }

  async function handleToggleActive(source: SignalSourceAdmin) {
    try {
      await updateSignalSource(token, source.id, { active: !source.active });
      await loadSources();
    } catch (err) {
      setError(err instanceof Error ? err.message : "خطا در تغییر وضعیت");
    }
  }

  if (loading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <div className="h-10 w-10 animate-spin rounded-full border-4 border-gold-500 border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {error && (
        <div className="rounded-lg bg-red-50 p-3 text-sm text-red-700 dark:bg-red-900/20 dark:text-red-400">
          {error}
        </div>
      )}

      {/* Header with stats */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex gap-4 text-sm text-gray-500 dark:text-gray-400">
          <span>کل منابع: <strong className="text-gray-900 dark:text-gray-100">{sources.length}</strong></span>
          <span>فعال: <strong className="text-green-600">{sources.filter(s => s.active).length}</strong></span>
          <span>کل سیگنال‌ها: <strong className="text-gold-600">{sources.reduce((a, s) => a + s.total_signals, 0)}</strong></span>
        </div>
        <button onClick={openCreateForm} className="btn-primary">
          + افزودن منبع سیگنال
        </button>
      </div>

      {/* Form modal */}
      {showForm && (
        <div className="card border-gold-300 dark:border-gold-700">
          <h3 className="mb-4 text-lg font-bold text-gray-900 dark:text-gray-100">
            {editingId ? "ویرایش منبع سیگنال" : "افزودن منبع سیگنال جدید"}
          </h3>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
                  نام
                </label>
                <input
                  type="text"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  required
                  className="input-field"
                  placeholder="مثال: SureShotFX Gold"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
                  نوع
                </label>
                <select
                  value={form.type}
                  onChange={(e) => setForm({ ...form, type: e.target.value })}
                  className="select-field"
                >
                  <option value="telegram">تلگرام</option>
                  <option value="tradingview">TradingView</option>
                  <option value="website">وب‌سایت</option>
                  <option value="forum">فروم</option>
                </select>
              </div>

              {/* Telegram-specific fields */}
              {form.type === "telegram" && (
                <>
                  <div>
                    <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
                      شناسه کانال تلگرام
                    </label>
                    <input
                      type="text"
                      value={form.telegram_channel_id}
                      onChange={(e) => setForm({ ...form, telegram_channel_id: e.target.value })}
                      className="input-field"
                      dir="ltr"
                      placeholder="-1001234567890"
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
                      نام کاربری کانال
                    </label>
                    <input
                      type="text"
                      value={form.telegram_channel_name}
                      onChange={(e) => setForm({ ...form, telegram_channel_name: e.target.value })}
                      className="input-field"
                      dir="ltr"
                      placeholder="@SureShotFXGold"
                    />
                  </div>
                </>
              )}

              {/* URL field for non-telegram types */}
              {form.type !== "telegram" && (
                <div className="sm:col-span-2">
                  <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
                    آدرس (URL)
                  </label>
                  <input
                    type="url"
                    value={form.url}
                    onChange={(e) => setForm({ ...form, url: e.target.value })}
                    className="input-field"
                    dir="ltr"
                    placeholder="https://www.tradingview.com/..."
                  />
                </div>
              )}

              {/* Weight (only on edit) */}
              {editingId && (
                <div>
                  <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
                    وزن (0 تا 1)
                  </label>
                  <input
                    type="number"
                    value={form.current_weight}
                    onChange={(e) =>
                      setForm({ ...form, current_weight: parseFloat(e.target.value) || 0.5 })
                    }
                    min={0}
                    max={1}
                    step={0.05}
                    className="input-field"
                    dir="ltr"
                  />
                </div>
              )}

              <div className="flex items-end">
                <label className="flex cursor-pointer items-center gap-2">
                  <input
                    type="checkbox"
                    checked={form.active}
                    onChange={(e) => setForm({ ...form, active: e.target.checked })}
                    className="h-4 w-4 rounded border-gray-300 text-gold-500 focus:ring-gold-500"
                  />
                  <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                    فعال
                  </span>
                </label>
              </div>
            </div>
            <div className="flex gap-2">
              <button type="submit" disabled={saving} className="btn-primary">
                {saving ? "ذخیره..." : "ذخیره"}
              </button>
              <button
                type="button"
                onClick={() => {
                  setShowForm(false);
                  setEditingId(null);
                }}
                className="btn-secondary"
              >
                انصراف
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Sources list */}
      {sources.length === 0 ? (
        <div className="card py-12 text-center text-gray-400">
          منبع سیگنالی ثبت نشده است
        </div>
      ) : (
        <div className="space-y-3">
          {sources.map((source) => {
            const wb = weightBadge(source.current_weight);
            const winRate = source.accuracy_rate != null
              ? `${(source.accuracy_rate * 100).toFixed(1)}%`
              : "-";

            return (
              <div key={source.id} className="card">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    {/* Header row */}
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="font-semibold text-gray-900 dark:text-gray-100">
                        {source.name}
                      </h3>
                      <span
                        className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                          source.active
                            ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                            : "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-500"
                        }`}
                      >
                        {source.active ? "فعال" : "غیرفعال"}
                      </span>
                      <span className="inline-flex items-center rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-700 dark:bg-blue-900/30 dark:text-blue-400">
                        {sourceTypeLabels[source.type] || source.type}
                      </span>
                      <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${wb.className}`}>
                        وزن: {wb.label} ({source.current_weight.toFixed(2)})
                      </span>
                    </div>

                    {/* Connection info */}
                    <p className="mt-1 truncate text-sm text-gray-500" dir="ltr">
                      {source.type === "telegram"
                        ? source.telegram_channel_name || source.telegram_channel_id || "-"
                        : source.url || "-"}
                    </p>

                    {/* Stats row */}
                    <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500 dark:text-gray-400">
                      <span>سیگنال‌ها: <strong>{source.total_signals}</strong></span>
                      <span>درست: <strong className="text-green-600">{source.correct_signals}</strong></span>
                      <span>غلط: <strong className="text-red-600">{source.wrong_signals}</strong></span>
                      <span>منقضی: <strong>{source.expired_signals}</strong></span>
                      <span>نرخ موفقیت: <strong className="text-gold-600">{winRate}</strong></span>
                      {source.profit_factor != null && (
                        <span>فاکتور سود: <strong>{source.profit_factor.toFixed(2)}</strong></span>
                      )}
                      {source.avg_profit_pips != null && (
                        <span>میانگین سود: <strong className="text-green-600">{source.avg_profit_pips.toFixed(1)} پیپ</strong></span>
                      )}
                      {source.avg_loss_pips != null && (
                        <span>میانگین ضرر: <strong className="text-red-600">{source.avg_loss_pips.toFixed(1)} پیپ</strong></span>
                      )}
                    </div>

                    {/* Timestamps */}
                    <div className="mt-1 flex flex-wrap gap-x-4 text-xs text-gray-400">
                      <span>افزوده شده: {formatDate(source.added_at)}</span>
                      {source.last_signal_at && (
                        <span>آخرین سیگنال: {formatDate(source.last_signal_at)}</span>
                      )}
                    </div>
                  </div>

                  {/* Action buttons */}
                  <div className="flex flex-wrap gap-2">
                    <button
                      onClick={() => handleToggleActive(source)}
                      className="btn-secondary text-xs"
                    >
                      {source.active ? "غیرفعال‌سازی" : "فعال‌سازی"}
                    </button>
                    <button
                      onClick={() => openEditForm(source)}
                      className="btn-secondary text-xs"
                    >
                      ویرایش
                    </button>
                    <button
                      onClick={() => handleDelete(source.id, source.name)}
                      className="btn-danger text-xs"
                    >
                      حذف
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
