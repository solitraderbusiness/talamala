"use client";

import { useState, useEffect } from "react";
import {
  getAdminSettings,
  updateAdminSettings,
  type AdminSettings,
} from "@/lib/api";
import { getToken } from "@/lib/auth";

const defaultSettings: AdminSettings = {
  openrouter_model: "anthropic/claude-3.5-sonnet",
  temperature: 0.3,
  max_tokens: 4096,
  enable_llm: true,
};

export default function AdminSettingsPage() {
  const [settings, setSettings] = useState<AdminSettings>(defaultSettings);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const token = getToken() || "";

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const data = await getAdminSettings(token);
        setSettings(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "خطا در بارگذاری");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [token]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setSuccess(false);
    try {
      const data = await updateAdminSettings(token, settings);
      setSettings(data);
      setSuccess(true);
      setTimeout(() => setSuccess(false), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "خطا در ذخیره تنظیمات");
    } finally {
      setSaving(false);
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
    <div className="mx-auto max-w-2xl">
      {error && (
        <div className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-700 dark:bg-red-900/20 dark:text-red-400">
          {error}
        </div>
      )}

      {success && (
        <div className="mb-4 rounded-lg bg-green-50 p-3 text-sm text-green-700 dark:bg-green-900/20 dark:text-green-400">
          تنظیمات با موفقیت ذخیره شد
        </div>
      )}

      <form onSubmit={handleSubmit} className="card space-y-6">
        <h3 className="text-lg font-bold text-gray-900 dark:text-gray-100">
          تنظیمات LLM
        </h3>

        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
            مدل OpenRouter
          </label>
          <input
            type="text"
            value={settings.openrouter_model}
            onChange={(e) =>
              setSettings({ ...settings, openrouter_model: e.target.value })
            }
            className="input-field"
            dir="ltr"
          />
          <p className="mt-1 text-xs text-gray-400">
            مثال: anthropic/claude-3.5-sonnet, openai/gpt-4o
          </p>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
              دما (Temperature)
            </label>
            <input
              type="number"
              step="0.1"
              min="0"
              max="2"
              value={settings.temperature}
              onChange={(e) =>
                setSettings({
                  ...settings,
                  temperature: parseFloat(e.target.value) || 0,
                })
              }
              className="input-field"
              dir="ltr"
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
              حداکثر توکن (Max Tokens)
            </label>
            <input
              type="number"
              min="256"
              max="128000"
              value={settings.max_tokens}
              onChange={(e) =>
                setSettings({
                  ...settings,
                  max_tokens: parseInt(e.target.value) || 4096,
                })
              }
              className="input-field"
              dir="ltr"
            />
          </div>
        </div>

        <div>
          <label className="flex cursor-pointer items-center gap-2">
            <input
              type="checkbox"
              checked={settings.enable_llm}
              onChange={(e) =>
                setSettings({ ...settings, enable_llm: e.target.checked })
              }
              className="h-4 w-4 rounded border-gray-300 text-gold-500 focus:ring-gold-500"
            />
            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
              فعال‌سازی پردازش LLM
            </span>
          </label>
          <p className="mr-6 mt-1 text-xs text-gray-400">
            در صورت غیرفعال بودن، هشدارها بدون تحلیل LLM ایجاد می‌شوند
          </p>
        </div>

        <div className="border-t border-gray-200 pt-4 dark:border-gray-700">
          <button type="submit" disabled={saving} className="btn-primary">
            {saving ? "ذخیره..." : "ذخیره تنظیمات"}
          </button>
        </div>
      </form>
    </div>
  );
}
