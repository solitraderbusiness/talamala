"use client";

import { useState, useEffect, useMemo } from "react";
import { getRulesLibrary, type Rule, type RulesLibrary } from "@/lib/api";
import { sectionLabel } from "@/lib/utils";

export default function LibraryPage() {
  const [library, setLibrary] = useState<RulesLibrary>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [sectionFilter, setSectionFilter] = useState("");
  const [expandedRule, setExpandedRule] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const data = await getRulesLibrary();
        setLibrary(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "خطا در بارگذاری");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const sections = useMemo(() => Object.keys(library), [library]);

  const filteredRules = useMemo(() => {
    const result: { section: string; rules: Rule[] }[] = [];
    for (const [section, rules] of Object.entries(library)) {
      if (sectionFilter && section !== sectionFilter) continue;
      const filtered = rules.filter((rule) => {
        if (!search) return true;
        const q = search.toLowerCase();
        return (
          rule.title.toLowerCase().includes(q) ||
          rule.what_it_is?.toLowerCase().includes(q) ||
          rule.why_important?.toLowerCase().includes(q) ||
          rule.keywords?.some((k) => k.toLowerCase().includes(q))
        );
      });
      if (filtered.length > 0) {
        result.push({ section, rules: filtered });
      }
    }
    return result;
  }, [library, search, sectionFilter]);

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="h-10 w-10 animate-spin rounded-full border-4 border-gold-500 border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
          کتابخانه قوانین
        </h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          مجموعه قوانین و سیگنال‌های رصد بازار طلا
        </p>
      </div>

      {error && (
        <div className="rounded-lg bg-red-50 p-4 text-sm text-red-700 dark:bg-red-900/20 dark:text-red-400">
          {error}
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <input
          type="text"
          placeholder="جستجوی قوانین..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="input-field max-w-sm"
        />
        <select
          value={sectionFilter}
          onChange={(e) => setSectionFilter(e.target.value)}
          className="select-field w-auto"
        >
          <option value="">همه بخش‌ها</option>
          {sections.map((s) => (
            <option key={s} value={s}>
              {sectionLabel(s)}
            </option>
          ))}
        </select>
      </div>

      {/* Rules grouped by section */}
      {filteredRules.length === 0 ? (
        <div className="card py-12 text-center text-gray-400">
          قانونی یافت نشد
        </div>
      ) : (
        filteredRules.map(({ section, rules }) => (
          <div key={section}>
            <h2 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
              {sectionLabel(section)}
              <span className="mr-2 text-sm font-normal text-gray-400">
                ({rules.length} قانون)
              </span>
            </h2>
            <div className="space-y-3">
              {rules.map((rule) => {
                const isExpanded = expandedRule === rule.id;
                return (
                  <div key={rule.id} className="card">
                    <button
                      onClick={() =>
                        setExpandedRule(isExpanded ? null : rule.id)
                      }
                      className="flex w-full items-center justify-between text-right"
                    >
                      <h3 className="font-semibold text-gray-900 dark:text-gray-100">
                        {rule.title}
                      </h3>
                      <svg
                        className={`h-5 w-5 shrink-0 text-gray-400 transition-transform ${
                          isExpanded ? "rotate-180" : ""
                        }`}
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                        strokeWidth={2}
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          d="M19 9l-7 7-7-7"
                        />
                      </svg>
                    </button>

                    {isExpanded && (
                      <div className="mt-4 space-y-4 border-t border-gray-100 pt-4 dark:border-gray-800">
                        {rule.what_it_is && (
                          <div>
                            <h4 className="text-xs font-semibold uppercase text-gray-500 dark:text-gray-400">
                              چیست؟
                            </h4>
                            <p className="mt-1 text-sm leading-6 text-gray-700 dark:text-gray-300">
                              {rule.what_it_is}
                            </p>
                          </div>
                        )}

                        {rule.why_important && (
                          <div>
                            <h4 className="text-xs font-semibold uppercase text-gray-500 dark:text-gray-400">
                              چرا مهم است؟
                            </h4>
                            <p className="mt-1 text-sm leading-6 text-gray-700 dark:text-gray-300">
                              {rule.why_important}
                            </p>
                          </div>
                        )}

                        {rule.keywords && rule.keywords.length > 0 && (
                          <div>
                            <h4 className="text-xs font-semibold uppercase text-gray-500 dark:text-gray-400">
                              کلمات کلیدی
                            </h4>
                            <div className="mt-1 flex flex-wrap gap-1">
                              {rule.keywords.map((kw, i) => (
                                <span
                                  key={i}
                                  className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-700 dark:bg-gray-800 dark:text-gray-300"
                                >
                                  {kw}
                                </span>
                              ))}
                            </div>
                          </div>
                        )}

                        {rule.signals && rule.signals.length > 0 && (
                          <div>
                            <h4 className="text-xs font-semibold uppercase text-gray-500 dark:text-gray-400">
                              سیگنال‌ها
                            </h4>
                            <ul className="mt-1 list-inside list-disc space-y-1 text-sm text-gray-700 dark:text-gray-300">
                              {rule.signals.map((signal, i) => (
                                <li key={i}>{signal}</li>
                              ))}
                            </ul>
                          </div>
                        )}

                        {rule.importance && (
                          <div>
                            <h4 className="text-xs font-semibold uppercase text-gray-500 dark:text-gray-400">
                              معیار اهمیت
                            </h4>
                            <p className="mt-1 text-sm leading-6 text-gray-700 dark:text-gray-300">
                              {rule.importance}
                            </p>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))
      )}
    </div>
  );
}
