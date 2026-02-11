"use client";

import { useState, useEffect, useCallback } from "react";
import {
  getSources,
  createSource,
  updateSource,
  deleteSource,
  fetchSourceNow,
  getSourceLogs,
  type Source,
  type FetchLog,
} from "@/lib/api";
import { getToken } from "@/lib/auth";
import { formatDate } from "@/lib/utils";

interface SourceFormData {
  name: string;
  type: string;
  base_url: string;
  enabled: boolean;
  poll_interval_seconds: number;
}

const emptyForm: SourceFormData = {
  name: "",
  type: "rss",
  base_url: "",
  enabled: true,
  poll_interval_seconds: 300,
};

export default function AdminSourcesPage() {
  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<SourceFormData>(emptyForm);
  const [saving, setSaving] = useState(false);
  const [logsSourceId, setLogsSourceId] = useState<string | null>(null);
  const [logs, setLogs] = useState<FetchLog[]>([]);
  const [logsLoading, setLogsLoading] = useState(false);

  const token = getToken() || "";

  const loadSources = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getSources(token);
      setSources(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "خطا در بارگذاری منابع");
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

  function openEditForm(source: Source) {
    setForm({
      name: source.name,
      type: source.type,
      base_url: source.base_url,
      enabled: source.enabled,
      poll_interval_seconds: source.poll_interval_seconds,
    });
    setEditingId(source.id);
    setShowForm(true);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      if (editingId) {
        await updateSource(token, editingId, form);
      } else {
        await createSource(token, form);
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

  async function handleDelete(id: string) {
    if (!confirm("آیا از حذف این منبع اطمینان دارید؟")) return;
    try {
      await deleteSource(token, id);
      await loadSources();
    } catch (err) {
      setError(err instanceof Error ? err.message : "خطا در حذف");
    }
  }

  async function handleFetchNow(id: string) {
    try {
      await fetchSourceNow(token, id);
      alert("درخواست دریافت ارسال شد");
    } catch (err) {
      setError(err instanceof Error ? err.message : "خطا در ارسال درخواست");
    }
  }

  async function handleShowLogs(sourceId: string) {
    if (logsSourceId === sourceId) {
      setLogsSourceId(null);
      return;
    }
    setLogsSourceId(sourceId);
    setLogsLoading(true);
    try {
      const data = await getSourceLogs(token, sourceId);
      setLogs(Array.isArray(data) ? data : []);
    } catch {
      setLogs([]);
    } finally {
      setLogsLoading(false);
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

      {/* Add source button */}
      <div className="flex justify-end">
        <button onClick={openCreateForm} className="btn-primary">
          + افزودن منبع
        </button>
      </div>

      {/* Form modal */}
      {showForm && (
        <div className="card border-gold-300 dark:border-gold-700">
          <h3 className="mb-4 text-lg font-bold text-gray-900 dark:text-gray-100">
            {editingId ? "ویرایش منبع" : "افزودن منبع جدید"}
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
                  <option value="rss">RSS</option>
                  <option value="html">HTML</option>
                  <option value="json_api">JSON API</option>
                </select>
              </div>
              <div className="sm:col-span-2">
                <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
                  آدرس (URL)
                </label>
                <input
                  type="url"
                  value={form.base_url}
                  onChange={(e) =>
                    setForm({ ...form, base_url: e.target.value })
                  }
                  required
                  className="input-field"
                  dir="ltr"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
                  فاصله بررسی (ثانیه)
                </label>
                <input
                  type="number"
                  value={form.poll_interval_seconds}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      poll_interval_seconds: parseInt(e.target.value) || 300,
                    })
                  }
                  min={60}
                  className="input-field"
                  dir="ltr"
                />
              </div>
              <div className="flex items-end">
                <label className="flex cursor-pointer items-center gap-2">
                  <input
                    type="checkbox"
                    checked={form.enabled}
                    onChange={(e) =>
                      setForm({ ...form, enabled: e.target.checked })
                    }
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
          منبعی ثبت نشده است
        </div>
      ) : (
        <div className="space-y-3">
          {sources.map((source) => (
            <div key={source.id}>
              <div className="card">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <h3 className="font-semibold text-gray-900 dark:text-gray-100">
                        {source.name}
                      </h3>
                      <span
                        className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                          source.enabled
                            ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                            : "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-500"
                        }`}
                      >
                        {source.enabled ? "فعال" : "غیرفعال"}
                      </span>
                    </div>
                    <p className="mt-1 truncate text-sm text-gray-500" dir="ltr">
                      {source.base_url}
                    </p>
                    <p className="mt-1 text-xs text-gray-400">
                      نوع: {source.type} | فاصله: {source.poll_interval_seconds} ثانیه
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      onClick={() => handleFetchNow(source.id)}
                      className="btn-secondary text-xs"
                    >
                      دریافت الان
                    </button>
                    <button
                      onClick={() => handleShowLogs(source.id)}
                      className="btn-secondary text-xs"
                    >
                      لاگ‌ها
                    </button>
                    <button
                      onClick={() => openEditForm(source)}
                      className="btn-secondary text-xs"
                    >
                      ویرایش
                    </button>
                    <button
                      onClick={() => handleDelete(source.id)}
                      className="btn-danger text-xs"
                    >
                      حذف
                    </button>
                  </div>
                </div>
              </div>

              {/* Logs panel */}
              {logsSourceId === source.id && (
                <div className="mr-4 mt-2 rounded-lg border border-gray-200 bg-gray-50 p-4 dark:border-gray-700 dark:bg-gray-900">
                  <h4 className="mb-2 text-sm font-semibold text-gray-700 dark:text-gray-300">
                    لاگ‌های دریافت
                  </h4>
                  {logsLoading ? (
                    <p className="text-sm text-gray-400">بارگذاری...</p>
                  ) : logs.length === 0 ? (
                    <p className="text-sm text-gray-400">لاگی موجود نیست</p>
                  ) : (
                    <div className="max-h-60 overflow-auto">
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="text-gray-500">
                            <th className="py-1 text-right">زمان</th>
                            <th className="py-1 text-right">وضعیت</th>
                            <th className="py-1 text-right">تعداد</th>
                            <th className="py-1 text-right">خطا</th>
                          </tr>
                        </thead>
                        <tbody>
                          {logs.map((log) => (
                            <tr
                              key={log.id}
                              className="border-t border-gray-200 dark:border-gray-700"
                            >
                              <td className="py-1">
                                {formatDate(log.started_at)}
                              </td>
                              <td className="py-1">
                                <span
                                  className={
                                    log.status === "success"
                                      ? "text-green-600"
                                      : "text-red-600"
                                  }
                                >
                                  {log.status}
                                </span>
                              </td>
                              <td className="py-1">{log.items_fetched_count}</td>
                              <td className="py-1 text-red-500">
                                {log.error_message || "-"}
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
          ))}
        </div>
      )}
    </div>
  );
}
