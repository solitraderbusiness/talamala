'use client';

import { useState, useMemo } from 'react';
import Link from 'next/link';
import { RuleSection, Rule } from '@/types';
import { rules } from '@/data/rules';
import { SECTION_CONFIG } from '@/lib/constants';
import { cn } from '@/lib/utils';
import Card from '@/components/ui/Card';
import SearchInput from '@/components/ui/SearchInput';

export default function LibraryPage() {
  const [activeSection, setActiveSection] = useState<RuleSection | 'all'>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedRules, setExpandedRules] = useState<Set<string>>(new Set());

  const toggleRule = (id: string) => {
    setExpandedRules((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const filteredRules = useMemo(() => {
    let result = rules;

    if (activeSection !== 'all') {
      result = result.filter((r) => r.section === activeSection);
    }

    if (searchQuery.trim()) {
      const q = searchQuery.trim().toLowerCase();
      result = result.filter(
        (r) =>
          r.title.includes(q) ||
          r.what_it_is.includes(q) ||
          r.why_important.includes(q) ||
          r.watch_for.keywords.some((kw) => kw.toLowerCase().includes(q)) ||
          r.id.toLowerCase().includes(q)
      );
    }

    return result;
  }, [activeSection, searchQuery]);

  const groupedRules = useMemo(() => {
    const groups: Record<string, Rule[]> = {};
    for (const rule of filteredRules) {
      const sectionTitle = SECTION_CONFIG[rule.section]?.title || 'سایر';
      if (!groups[sectionTitle]) groups[sectionTitle] = [];
      groups[sectionTitle].push(rule);
    }
    return groups;
  }, [filteredRules]);

  const sections: { id: RuleSection | 'all'; label: string }[] = [
    { id: 'all', label: 'همه' },
    { id: 'global_gold', label: 'جهانی' },
    { id: 'iran_gold', label: 'ایران' },
    { id: 'coin', label: 'سکه' },
    { id: 'gold_funds', label: 'صندوق‌ها' },
  ];

  return (
    <div className="space-y-6">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-xs text-gray-400 dark:text-gray-500">
        <Link href="/" className="hover:text-gray-600 dark:hover:text-gray-300">داشبورد</Link>
        <span>/</span>
        <span className="text-gray-700 dark:text-gray-200">کتابخانه قوانین</span>
      </div>

      {/* Header */}
      <div>
        <h1 className="text-lg font-bold text-gray-900 dark:text-gray-100 sm:text-xl">
          کتابخانه قوانین و عوامل بازار
        </h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          دایره‌المعارف عوامل تاثیرگذار بر بازار طلا. هر قانون توضیح می‌دهد چه اتفاقی مهم است و چرا.
        </p>
      </div>

      {/* Search + section filter */}
      <div className="space-y-3">
        <SearchInput
          value={searchQuery}
          onChange={setSearchQuery}
          placeholder="جستجو در قوانین (مثلاً: نرخ بهره، دلار، حباب)..."
        />

        <div className="flex items-center gap-1 overflow-x-auto rounded-lg border border-gray-200 p-1 dark:border-gray-700">
          {sections.map((s) => (
            <button
              key={s.id}
              onClick={() => setActiveSection(s.id)}
              className={cn(
                'shrink-0 rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                activeSection === s.id
                  ? 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300'
                  : 'text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800'
              )}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>

      {/* Results count */}
      <p className="text-xs text-gray-400 dark:text-gray-500">
        {filteredRules.length} قانون یافت شد
      </p>

      {/* Rules grouped by section */}
      {Object.entries(groupedRules).map(([sectionTitle, sectionRules]) => (
        <div key={sectionTitle}>
          <h2 className="mb-3 text-base font-bold text-gray-800 dark:text-gray-200">
            {sectionTitle}
          </h2>
          <div className="space-y-2">
            {sectionRules.map((rule) => {
              const isExpanded = expandedRules.has(rule.id);
              return (
                <Card key={rule.id} padding="sm">
                  <button
                    onClick={() => toggleRule(rule.id)}
                    className="flex w-full items-start gap-3 text-right"
                  >
                    <svg
                      className={cn(
                        'mt-1 h-4 w-4 shrink-0 text-gray-400 transition-transform',
                        isExpanded && 'rotate-90'
                      )}
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                      strokeWidth={2}
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                    </svg>
                    <div className="min-w-0 flex-1">
                      <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                        {rule.title}
                      </h3>
                      <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
                        {rule.what_it_is}
                      </p>
                    </div>
                  </button>

                  {isExpanded && (
                    <div className="mt-3 space-y-3 border-t border-gray-100 pr-7 pt-3 dark:border-gray-800">
                      {/* Why important */}
                      <div>
                        <p className="mb-1 text-xs font-medium text-amber-700 dark:text-amber-400">
                          چرا مهم است؟
                        </p>
                        <p className="text-xs leading-5 text-gray-600 dark:text-gray-400">
                          {rule.why_important}
                        </p>
                      </div>

                      {/* What to watch */}
                      <div>
                        <p className="mb-1 text-xs font-medium text-gray-700 dark:text-gray-300">
                          چه خبرهایی مهم است؟
                        </p>
                        <ul className="space-y-1">
                          {rule.watch_for.signals.map((signal, i) => (
                            <li key={i} className="flex gap-1.5 text-xs text-gray-500 dark:text-gray-400">
                              <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-gray-400" />
                              {signal}
                            </li>
                          ))}
                        </ul>
                      </div>

                      {/* Keywords */}
                      <div>
                        <p className="mb-1 text-xs font-medium text-gray-700 dark:text-gray-300">
                          کلمات کلیدی
                        </p>
                        <div className="flex flex-wrap gap-1">
                          {rule.watch_for.keywords.map((kw) => (
                            <span
                              key={kw}
                              className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] text-gray-500 dark:bg-gray-800 dark:text-gray-400"
                            >
                              {kw}
                            </span>
                          ))}
                        </div>
                      </div>

                      {/* Importance criteria */}
                      <div>
                        <p className="mb-1 text-xs font-medium text-gray-700 dark:text-gray-300">
                          معیار اهمیت
                        </p>
                        <div className="space-y-1">
                          {rule.importance_criteria.high_if && (
                            <div className="flex gap-1.5 text-xs">
                              <span className="shrink-0 rounded bg-red-50 px-1 text-red-600 dark:bg-red-950/30 dark:text-red-400">بحرانی:</span>
                              <span className="text-gray-500 dark:text-gray-400">{rule.importance_criteria.high_if.join(' | ')}</span>
                            </div>
                          )}
                          {rule.importance_criteria.medium_if && (
                            <div className="flex gap-1.5 text-xs">
                              <span className="shrink-0 rounded bg-amber-50 px-1 text-amber-600 dark:bg-amber-950/30 dark:text-amber-400">مهم:</span>
                              <span className="text-gray-500 dark:text-gray-400">{rule.importance_criteria.medium_if.join(' | ')}</span>
                            </div>
                          )}
                          {rule.importance_criteria.low_if && (
                            <div className="flex gap-1.5 text-xs">
                              <span className="shrink-0 rounded bg-gray-100 px-1 text-gray-500 dark:bg-gray-800 dark:text-gray-400">عادی:</span>
                              <span className="text-gray-500 dark:text-gray-400">{rule.importance_criteria.low_if.join(' | ')}</span>
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Rule ID */}
                      <div className="text-[10px] text-gray-300 dark:text-gray-600">
                        ID: {rule.id} | افق: {rule.horizon}
                      </div>
                    </div>
                  )}
                </Card>
              );
            })}
          </div>
        </div>
      ))}

      {filteredRules.length === 0 && (
        <div className="py-12 text-center text-sm text-gray-400 dark:text-gray-500">
          قانونی با این عبارت یافت نشد.
        </div>
      )}
    </div>
  );
}
