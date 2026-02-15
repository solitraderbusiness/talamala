"use client";

import { cn } from "@/lib/utils";
import type { MarketActivityResponse } from "@/lib/api";
import DataPending from "./DataPending";
import SkeletonCard from "./SkeletonCard";
import InfoTip from "@/components/InfoTip";

const EVENT_TYPE_ICONS: Record<string, string> = {
  etf_flow: "\uD83D\uDCB0",
  cot_change: "\uD83D\uDCC8",
  price_move: "\uD83D\uDCC9",
  macro_release: "\uD83C\uDFE6",
  correlation_shift: "\uD83D\uDD17",
};

const IMPACT_BADGE: Record<string, { label: string; className: string }> = {
  bullish: {
    label: "صعودی",
    className: "bg-emerald-500/10 text-emerald-500 border-emerald-500/30",
  },
  bearish: {
    label: "نزولی",
    className: "bg-red-500/10 text-red-500 border-red-500/30",
  },
  neutral: {
    label: "خنثی",
    className: "bg-gray-500/10 text-gray-400 border-gray-500/30",
  },
};

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return "";
  try {
    const diff = Date.now() - new Date(dateStr).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return "همین الان";
    if (mins < 60) return `${mins} دقیقه پیش`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours} ساعت پیش`;
    const days = Math.floor(hours / 24);
    return `${days} روز پیش`;
  } catch {
    return "";
  }
}

interface Props {
  data: MarketActivityResponse | null;
  loading: boolean;
}

export default function MarketActivityFeed({ data, loading }: Props) {
  const hasData = data && data.events.length > 0;

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100">
          &#x1F4F0; رویدادهای بازار
        </h2>
        <InfoTip term="market_event" />
        {data && (
          <span className="text-xs text-gray-400">
            {data.total} رویداد در {data.period_hours} ساعت اخیر
          </span>
        )}
      </div>

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3, 4].map((i) => (
            <SkeletonCard key={i} className="h-16" />
          ))}
        </div>
      ) : !hasData ? (
        <DataPending message="رویدادهای بازار به صورت خودکار از تغییرات داده‌ها تولید خواهند شد." />
      ) : (
        <>
          <div className="space-y-2">
            {data!.events.map((event) => {
              const badge = IMPACT_BADGE[event.impact] || IMPACT_BADGE.neutral;
              const icon = EVENT_TYPE_ICONS[event.event_type] || "\u26A1";
              return (
                <div
                  key={event.id}
                  className="card flex items-start gap-3 px-4 py-3"
                >
                  <span className="mt-0.5 text-lg shrink-0">{icon}</span>
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                        {event.title_fa || event.title}
                      </p>
                      <span
                        className={cn(
                          "shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-medium",
                          badge.className,
                        )}
                      >
                        {badge.label}
                      </span>
                    </div>
                    {(event.description_fa || event.description) && (
                      <p className="mt-1 text-xs text-gray-500 dark:text-gray-400 line-clamp-2">
                        {event.description_fa || event.description}
                      </p>
                    )}
                    <span className="mt-1 block text-[11px] text-gray-400">
                      {timeAgo(event.created_at)}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>

          <div className="mt-3 rounded-lg border border-blue-500/20 bg-blue-500/5 p-3">
            <p className="text-xs text-blue-600 dark:text-blue-400">
              <span className="ml-1 font-bold">&#x26A1; چرا مهم است؟</span>
              این فید تغییرات مهم داده‌های بنیادی را به صورت خودکار شناسایی و نمایش می‌دهد.
              تغییرات ناگهانی در جریان ETF، موقعیت COT یا انتشار داده‌های کلان اقتصادی می‌تواند سیگنال‌های مهمی برای بازار طلا باشد.
            </p>
          </div>
        </>
      )}
    </div>
  );
}
