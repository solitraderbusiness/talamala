'use client';

import { useParams } from 'next/navigation';
import Link from 'next/link';
import { mockAlerts } from '@/data/mock-alerts';
import { getRuleById } from '@/data/rules';
import { useApp } from '@/context/AppContext';
import { formatPersianDate, cn } from '@/lib/utils';
import { GLOSSARY, HORIZON_CONFIG, SEVERITY_CONFIG } from '@/lib/constants';
import Card from '@/components/ui/Card';
import SeverityBadge from '@/components/ui/SeverityBadge';
import HorizonBadge from '@/components/ui/HorizonBadge';
import ImpactMatrix from '@/components/ui/ImpactMatrix';
import Tooltip from '@/components/ui/Tooltip';

function GlossaryText({ text }: { text: string }) {
  const terms = Object.keys(GLOSSARY).sort((a, b) => b.length - a.length);
  const parts: (string | { term: string; tooltip: string })[] = [];
  let remaining = text;

  while (remaining.length > 0) {
    let found = false;
    for (const term of terms) {
      const idx = remaining.indexOf(term);
      if (idx !== -1) {
        if (idx > 0) parts.push(remaining.slice(0, idx));
        parts.push({ term, tooltip: GLOSSARY[term] });
        remaining = remaining.slice(idx + term.length);
        found = true;
        break;
      }
    }
    if (!found) {
      parts.push(remaining);
      remaining = '';
    }
  }

  return (
    <span>
      {parts.map((part, i) =>
        typeof part === 'string' ? (
          <span key={i}>{part}</span>
        ) : (
          <Tooltip key={i} content={part.tooltip}>
            {part.term}
          </Tooltip>
        )
      )}
    </span>
  );
}

export default function AlertDetailPage() {
  const params = useParams();
  const alertId = params.alertId as string;
  const { viewMode } = useApp();

  const alert = mockAlerts.find((a) => a.id === alertId);

  if (!alert) {
    return (
      <div className="py-20 text-center">
        <p className="text-gray-500 dark:text-gray-400">هشدار مورد نظر یافت نشد.</p>
        <Link href="/" className="mt-4 inline-block text-sm text-amber-600 hover:text-amber-700">
          بازگشت به داشبورد
        </Link>
      </div>
    );
  }

  const matchedRules = alert.matched_rule_ids.map((id) => getRuleById(id)).filter(Boolean);

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-xs text-gray-400 dark:text-gray-500">
        <Link href="/" className="hover:text-gray-600 dark:hover:text-gray-300">داشبورد</Link>
        <span>/</span>
        <span className="text-gray-700 dark:text-gray-200">جزئیات هشدار</span>
      </div>

      {/* Header */}
      <Card padding="lg">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <SeverityBadge severity={alert.severity} />
          <HorizonBadge horizon={alert.time_horizon} showDescription />
          <span className="text-xs text-gray-400 dark:text-gray-500">
            {formatPersianDate(alert.timestamp_utc)}
          </span>
        </div>

        <h1 className="mb-2 text-lg font-bold leading-8 text-gray-900 dark:text-gray-100 sm:text-xl">
          <GlossaryText text={alert.title} />
        </h1>

        <div className="flex items-center gap-3 text-xs text-gray-400 dark:text-gray-500">
          <span>منبع: {alert.source_name}</span>
          {alert.source_url !== '#' && (
            <a href={alert.source_url} target="_blank" rel="noopener noreferrer" className="text-amber-600 hover:underline">
              لینک اصلی
            </a>
          )}
        </div>
      </Card>

      {/* Summary */}
      <Card>
        <h2 className="mb-2 text-sm font-semibold text-gray-900 dark:text-gray-100">خلاصه</h2>
        <p className="text-sm leading-7 text-gray-700 dark:text-gray-300">
          <GlossaryText text={alert.summary_fa} />
        </p>
      </Card>

      {/* Why important */}
      <Card className="border-amber-200 bg-amber-50/30 dark:border-amber-800/40 dark:bg-amber-950/10">
        <h2 className="mb-2 text-sm font-semibold text-amber-800 dark:text-amber-300">
          چرا مهم است؟
        </h2>
        <p className="text-sm leading-7 text-amber-700 dark:text-amber-400">
          <GlossaryText text={alert.why_important_fa} />
        </p>
      </Card>

      {/* Impact on 4 assets */}
      <Card>
        <h2 className="mb-3 text-sm font-semibold text-gray-900 dark:text-gray-100">
          اثر بر دارایی‌ها
        </h2>
        <ImpactMatrix impacts={alert.expected_impact} />
      </Card>

      {/* Confidence */}
      <Card>
        <h2 className="mb-3 text-sm font-semibold text-gray-900 dark:text-gray-100">
          سطح اطمینان
        </h2>
        <div className="flex items-center gap-3">
          <div className="h-2 flex-1 overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
            <div
              className={cn(
                'h-full rounded-full transition-all',
                alert.confidence >= 80 ? 'bg-emerald-400' : alert.confidence >= 60 ? 'bg-amber-400' : 'bg-red-400'
              )}
              style={{ width: `${alert.confidence}%` }}
            />
          </div>
          <span className="text-sm font-bold text-gray-700 dark:text-gray-300">{alert.confidence}%</span>
        </div>
        <p className="mt-2 text-[11px] text-gray-400 dark:text-gray-500">
          {alert.confidence >= 80
            ? 'اطمینان بالا — منابع معتبر و داده‌های واضح'
            : alert.confidence >= 60
              ? 'اطمینان متوسط — نیاز به تایید بیشتر'
              : 'اطمینان پایین — خبر تایید نشده یا مبهم'
          }
        </p>
      </Card>

      {/* Follow-up questions */}
      {alert.follow_up_questions.length > 0 && (
        <Card>
          <h2 className="mb-3 text-sm font-semibold text-gray-900 dark:text-gray-100">
            سوالات پیگیری
          </h2>
          <ul className="space-y-2">
            {alert.follow_up_questions.map((q, i) => (
              <li key={i} className="flex gap-2 text-sm text-gray-600 dark:text-gray-400">
                <span className="mt-0.5 text-amber-500">?</span>
                {q}
              </li>
            ))}
          </ul>
        </Card>
      )}

      {/* Professional mode: matched rules */}
      {viewMode === 'professional' && matchedRules.length > 0 && (
        <Card>
          <h2 className="mb-3 text-sm font-semibold text-gray-900 dark:text-gray-100">
            قوانین تطبیق‌یافته
          </h2>
          <div className="space-y-3">
            {matchedRules.map((rule) =>
              rule ? (
                <div key={rule.id} className="rounded-lg border border-gray-100 p-3 dark:border-gray-800">
                  <div className="flex items-center gap-2">
                    <span className="rounded bg-gray-100 px-1.5 py-0.5 font-mono text-[10px] text-gray-500 dark:bg-gray-800 dark:text-gray-400">
                      {rule.id}
                    </span>
                    <span className="text-sm font-medium text-gray-800 dark:text-gray-200">{rule.title}</span>
                  </div>
                  <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{rule.what_it_is}</p>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {rule.watch_for.keywords.slice(0, 5).map((kw) => (
                      <span key={kw} className="rounded bg-gray-50 px-1.5 py-0.5 text-[10px] text-gray-400 dark:bg-gray-800">
                        {kw}
                      </span>
                    ))}
                  </div>
                </div>
              ) : null
            )}
          </div>
        </Card>
      )}

      {/* Back link */}
      <div className="pb-8 text-center">
        <Link
          href="/"
          className="text-sm text-gray-500 hover:text-amber-600 dark:text-gray-400 dark:hover:text-amber-400"
        >
          ← بازگشت به داشبورد
        </Link>
      </div>
    </div>
  );
}
