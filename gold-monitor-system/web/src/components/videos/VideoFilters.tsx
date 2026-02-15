"use client";

import { cn } from "@/lib/utils";

const CATEGORY_FILTERS: { key: string; label: string }[] = [
  { key: "analysis", label: "تحلیل بازار" },
  { key: "news", label: "اخبار" },
  { key: "education", label: "آموزشی" },
  { key: "interview", label: "مصاحبه" },
  { key: "documentary", label: "مستند" },
  { key: "podcast", label: "پادکست" },
];

const TOPIC_FILTERS: { key: string; label: string }[] = [
  { key: "gold_price", label: "قیمت طلا" },
  { key: "fed_policy", label: "فدرال رزرو" },
  { key: "central_banks", label: "بانک‌های مرکزی" },
  { key: "geopolitics", label: "ژئوپلیتیک" },
  { key: "inflation", label: "تورم" },
  { key: "dollar", label: "دلار" },
  { key: "technical_analysis", label: "تحلیل تکنیکال" },
  { key: "market_outlook", label: "چشم‌انداز" },
  { key: "investment_strategy", label: "استراتژی" },
];

interface VideoFiltersProps {
  category: string;
  setCategory: (v: string) => void;
  topic: string;
  setTopic: (v: string) => void;
  onReset: () => void;
}

export default function VideoFilters({
  category,
  setCategory,
  topic,
  setTopic,
  onReset,
}: VideoFiltersProps) {
  return (
    <div className="space-y-3">
      {/* Category filters */}
      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => { setCategory(""); onReset(); }}
          className={cn(
            "rounded-full px-3 py-1.5 text-xs font-medium transition-colors",
            !category
              ? "bg-gold-600 text-white shadow-sm"
              : "bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400"
          )}
        >
          همه دسته‌ها
        </button>
        {CATEGORY_FILTERS.map((c) => (
          <button
            key={c.key}
            onClick={() => { setCategory(category === c.key ? "" : c.key); onReset(); }}
            className={cn(
              "rounded-full px-3 py-1.5 text-xs font-medium transition-colors",
              category === c.key
                ? "bg-gold-600 text-white shadow-sm"
                : "bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400"
            )}
          >
            {c.label}
          </button>
        ))}
      </div>

      {/* Topic filters */}
      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => { setTopic(""); onReset(); }}
          className={cn(
            "rounded-full px-3 py-1.5 text-xs font-medium transition-colors",
            !topic
              ? "bg-gold-600 text-white shadow-sm"
              : "bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400"
          )}
        >
          همه موضوعات
        </button>
        {TOPIC_FILTERS.map((t) => (
          <button
            key={t.key}
            onClick={() => { setTopic(topic === t.key ? "" : t.key); onReset(); }}
            className={cn(
              "rounded-full px-3 py-1.5 text-xs font-medium transition-colors",
              topic === t.key
                ? "bg-gold-600 text-white shadow-sm"
                : "bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400"
            )}
          >
            {t.label}
          </button>
        ))}
      </div>
    </div>
  );
}
