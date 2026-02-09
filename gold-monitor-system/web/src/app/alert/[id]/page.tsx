"use client";

import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { getAlertById, type Alert, type ImpactItem } from "@/lib/api";
import SeverityBadge from "@/components/SeverityBadge";
import {
  formatDate,
  timeHorizonLabel,
  directionLabel,
  confidencePercent,
} from "@/lib/utils";

/** Check if text is mostly Latin/English. */
function isLikelyEnglish(text: string): boolean {
  if (!text) return false;
  const letters = text.replace(/[\s\d.,;:!?'"()\-\[\]{}/\\@#$%^&*+=<>|~`_]/g, "");
  if (!letters) return false;
  const latinCount = (letters.match(/[a-zA-Z]/g) || []).length;
  return latinCount / letters.length > 0.5;
}

/** Extract a clean domain name from a URL. */
function extractDomain(url: string): string {
  try {
    const u = new URL(url);
    return u.hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

/** Normalize expected_impact to an array of ImpactItem. */
function normalizeImpact(impact: unknown): ImpactItem[] {
  if (!impact) return [];
  // Array format (new)
  if (Array.isArray(impact)) {
    return impact.filter(
      (item) => item && typeof item === "object" && item.asset
    );
  }
  // Object/dict format (legacy)
  if (typeof impact === "object" && impact !== null) {
    return Object.entries(impact as Record<string, { direction?: string; mechanism?: string }>).map(
      ([asset, details]) => ({
        asset,
        direction: details?.direction || "",
        mechanism: details?.mechanism || "",
      })
    );
  }
  return [];
}

export default function AlertDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;

  const [alert, setAlert] = useState<Alert | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const data = await getAlertById(id);
        setAlert(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "خطا در بارگذاری هشدار");
      } finally {
        setLoading(false);
      }
    }
    if (id) load();
  }, [id]);

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="h-10 w-10 animate-spin rounded-full border-4 border-gold-500 border-t-transparent" />
      </div>
    );
  }

  if (error || !alert) {
    return (
      <div className="mx-auto max-w-2xl py-12 text-center">
        <h2 className="text-xl font-bold text-red-600">خطا</h2>
        <p className="mt-2 text-gray-500">{error || "هشدار یافت نشد"}</p>
        <button onClick={() => router.back()} className="btn-primary mt-4">
          بازگشت
        </button>
      </div>
    );
  }

  const horizonColorMap: Record<string, string> = {
    immediate: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
    short:
      "bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400",
    medium:
      "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400",
    long: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-400",
  };

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      {/* Breadcrumb */}
      <nav className="flex items-center gap-2 text-sm text-gray-500">
        <Link href="/" className="hover:text-gold-600">
          داشبورد
        </Link>
        <span>/</span>
        <span className="text-gray-700 dark:text-gray-300">جزئیات هشدار</span>
      </nav>

      {/* Header */}
      <div className="card">
        <div className="flex flex-wrap items-start gap-3">
          <div className="flex-1">
            <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100">
              {isLikelyEnglish(alert.title) && alert.summary_fa && !isLikelyEnglish(alert.summary_fa)
                ? alert.summary_fa.split(/[.۔。]/)[0]?.trim() || alert.summary_fa
                : alert.title}
            </h1>
            {isLikelyEnglish(alert.title) && (
              <p className="mt-1 text-sm text-gray-400 dark:text-gray-500" dir="ltr">
                {alert.title}
              </p>
            )}
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <SeverityBadge severity={alert.severity} />
              <span
                className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
                  horizonColorMap[alert.time_horizon] || horizonColorMap.long
                }`}
              >
                {timeHorizonLabel(alert.time_horizon)}
              </span>
            </div>
          </div>
          <div className="text-left text-sm text-gray-500 dark:text-gray-400">
            <p>{formatDate(alert.timestamp_utc)}</p>
            <p className="mt-1">{alert.source_name}</p>
          </div>
        </div>
      </div>

      {/* Summary */}
      <div className="card">
        <h2 className="mb-2 text-sm font-semibold text-gray-500 dark:text-gray-400">
          خلاصه
        </h2>
        <p className="leading-7 text-gray-800 dark:text-gray-200">
          {alert.summary_fa}
        </p>
      </div>

      {/* Why Important */}
      <div className="rounded-xl border border-amber-300 bg-amber-50 p-4 dark:border-amber-800 dark:bg-amber-950/30">
        <h2 className="mb-2 text-sm font-semibold text-amber-800 dark:text-amber-400">
          چرا مهم است؟
        </h2>
        <ul className="space-y-1.5 text-amber-900 dark:text-amber-200">
          {alert.why_important_fa
            .split(/\n/)
            .map((line) => line.replace(/^[-–•]\s*/, "").trim())
            .filter((line) => line.length > 0)
            .map((line, i) => (
              <li key={i} className="flex items-start gap-2 leading-7">
                <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-amber-500 dark:bg-amber-400" />
                <span>{line}</span>
              </li>
            ))}
        </ul>
      </div>

      {/* Expected Impact */}
      {(() => {
        const impacts = normalizeImpact(alert.expected_impact);
        return impacts.length > 0 ? (
          <div className="card">
            <h2 className="mb-3 text-sm font-semibold text-gray-500 dark:text-gray-400">
              تاثیر مورد انتظار
            </h2>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 dark:border-gray-700">
                    <th className="py-2 text-right font-medium text-gray-600 dark:text-gray-400">
                      دارایی
                    </th>
                    <th className="py-2 text-right font-medium text-gray-600 dark:text-gray-400">
                      جهت
                    </th>
                    <th className="py-2 text-right font-medium text-gray-600 dark:text-gray-400">
                      مکانیزم
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {impacts.map((impact, idx) => (
                    <tr
                      key={idx}
                      className="border-b border-gray-100 dark:border-gray-800"
                    >
                      <td className="py-2 font-medium text-gray-800 dark:text-gray-200">
                        {impact.asset}
                      </td>
                      <td className="py-2">
                        <span
                          className={`inline-flex items-center gap-1 font-medium ${
                            impact.direction === "up"
                              ? "text-green-600"
                              : impact.direction === "down"
                                ? "text-red-600"
                                : "text-amber-600"
                          }`}
                        >
                          {impact.direction === "up" && "▲"}
                          {impact.direction === "down" && "▼"}
                          {impact.direction === "mixed" && "◆"}
                          {directionLabel(impact.direction)}
                        </span>
                      </td>
                      <td className="py-2 text-gray-600 dark:text-gray-400">
                        {impact.mechanism}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null;
      })()}

      {/* Confidence */}
      <div className="card">
        <h2 className="mb-2 text-sm font-semibold text-gray-500 dark:text-gray-400">
          سطح اطمینان
        </h2>
        <div className="flex items-center gap-3">
          <div className="h-3 flex-1 overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
            <div
              className="h-full rounded-full bg-gold-500 transition-all"
              style={{ width: `${alert.confidence * 100}%` }}
            />
          </div>
          <span className="text-sm font-bold text-gray-700 dark:text-gray-300">
            {confidencePercent(alert.confidence)}
          </span>
        </div>
      </div>

      {/* Follow-up Questions */}
      {alert.follow_up_questions && alert.follow_up_questions.length > 0 && (
        <div className="card">
          <h2 className="mb-3 text-sm font-semibold text-gray-500 dark:text-gray-400">
            سوالات پیگیری
          </h2>
          <ul className="space-y-2">
            {alert.follow_up_questions.map((q, i) => (
              <li
                key={i}
                className="flex items-start gap-2 text-gray-700 dark:text-gray-300"
              >
                <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-gold-100 text-xs font-medium text-gold-800 dark:bg-gold-900/30 dark:text-gold-400">
                  {i + 1}
                </span>
                <span>{q}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Source link */}
      {alert.source_url && (
        <div className="card">
          <h2 className="mb-2 text-sm font-semibold text-gray-500 dark:text-gray-400">
            منبع
          </h2>
          <div className="flex items-center gap-3">
            <span className="text-sm text-gray-600 dark:text-gray-400">
              {alert.source_name || extractDomain(alert.source_url)}
            </span>
            <a
              href={alert.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 rounded-lg bg-gold-50 px-3 py-1.5 text-sm font-medium text-gold-700 transition-colors hover:bg-gold-100 dark:bg-gold-900/20 dark:text-gold-400 dark:hover:bg-gold-900/40"
            >
              مشاهده منبع
              <svg className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M4.25 5.5a.75.75 0 00-.75.75v8.5c0 .414.336.75.75.75h8.5a.75.75 0 00.75-.75v-4a.75.75 0 011.5 0v4A2.25 2.25 0 0112.75 17h-8.5A2.25 2.25 0 012 14.75v-8.5A2.25 2.25 0 014.25 4h5a.75.75 0 010 1.5h-5zm7.25-.75a.75.75 0 01.75-.75h3.5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0V6.31l-5.97 5.97a.75.75 0 11-1.06-1.06l5.97-5.97H12.25a.75.75 0 01-.75-.75z" clipRule="evenodd" />
              </svg>
            </a>
          </div>
        </div>
      )}

      {/* Back button */}
      <div>
        <button onClick={() => router.back()} className="btn-secondary">
          بازگشت
        </button>
      </div>
    </div>
  );
}
