"use client";

import { cn } from "@/lib/utils";
import type { MacroOverviewResponse, MacroCard } from "@/lib/api";
import DataPending from "./DataPending";
import SkeletonCard from "./SkeletonCard";
import InfoTip from "@/components/InfoTip";

const CARD_ICONS: Record<string, string> = {
  money_flow: "\uD83D\uDCB0",
  real_rates: "\uD83C\uDFE6",
  dollar: "\uD83D\uDCB5",
  risk: "\u26A0\uFE0F",
};

const CARD_TERM_KEY: Record<string, string> = {
  money_flow: "money_flow",
  real_rates: "real_rates",
  dollar: "dollar_strength",
  risk: "market_risk",
};

const IMPACT_STYLES: Record<string, { color: string; bg: string; border: string; label: string }> = {
  bullish: {
    color: "text-emerald-500",
    bg: "bg-emerald-500/10",
    border: "border-emerald-500/30",
    label: "صعودی برای طلا",
  },
  bearish: {
    color: "text-red-500",
    bg: "bg-red-500/10",
    border: "border-red-500/30",
    label: "نزولی برای طلا",
  },
  neutral: {
    color: "text-gray-400",
    bg: "bg-gray-500/10",
    border: "border-gray-500/30",
    label: "خنثی",
  },
};

function formatCardValue(card: MacroCard): string {
  if (!card.data) return "---";
  switch (card.id) {
    case "money_flow":
      if (card.data.gld_tonnes) return `${Number(card.data.gld_tonnes).toFixed(1)}t`;
      return "---";
    case "real_rates":
      if (card.data.real_rate != null) return `${Number(card.data.real_rate).toFixed(2)}%`;
      return "---";
    case "dollar":
      if (card.data.dxy != null) return Number(card.data.dxy).toFixed(2);
      return "---";
    case "risk":
      if (card.data.vix != null) return Number(card.data.vix).toFixed(1);
      return "---";
    default:
      return "---";
  }
}

function formatCardSubtext(card: MacroCard): string | null {
  if (!card.data) return null;
  switch (card.id) {
    case "money_flow":
      if (card.data.gld_change != null) {
        const ch = Number(card.data.gld_change);
        return `${ch > 0 ? "+" : ""}${ch.toFixed(2)}t تغییر روزانه`;
      }
      return null;
    case "dollar":
      if (card.data.change != null) {
        const ch = Number(card.data.change);
        return `${ch > 0 ? "+" : ""}${ch.toFixed(2)} تغییر`;
      }
      return null;
    default:
      return null;
  }
}

interface Props {
  data: MacroOverviewResponse | null;
  loading: boolean;
}

export default function MacroOverview({ data, loading }: Props) {
  return (
    <div>
      <div className="mb-4 flex items-center gap-2">
        <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100">
          نمای کلی بنیادی
        </h2>
        <InfoTip term="money_flow" />
      </div>

      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      ) : !data || !data.cards || data.cards.every((c) => c.status === "pending") ? (
        <DataPending message="داده‌های کلان اقتصادی پس از اجرای اولیه ورکرها نمایش داده خواهند شد." />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {data.cards.map((card) => {
              if (card.status === "pending") {
                return (
                  <div key={card.id} className="card border border-gray-200 dark:border-gray-700 opacity-60">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-xl">{CARD_ICONS[card.id] || ""}</span>
                      <h3 className="text-sm font-bold text-gray-900 dark:text-gray-100">
                        {card.title_fa}
                        <InfoTip term={CARD_TERM_KEY[card.id] || card.id} />
                      </h3>
                    </div>
                    <p className="text-xs text-gray-400">در انتظار داده...</p>
                  </div>
                );
              }

              const impact = IMPACT_STYLES[card.impact || "neutral"];
              return (
                <div
                  key={card.id}
                  className={cn("card border transition-all", impact.border)}
                >
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <span className="text-xl">{CARD_ICONS[card.id] || ""}</span>
                      <h3 className="text-sm font-bold text-gray-900 dark:text-gray-100">
                        {card.title_fa}
                        <InfoTip term={CARD_TERM_KEY[card.id] || card.id} />
                      </h3>
                    </div>
                    <span
                      className={cn(
                        "rounded-full border px-2 py-0.5 text-[11px] font-medium",
                        impact.bg,
                        impact.border,
                        impact.color,
                      )}
                    >
                      {impact.label}
                    </span>
                  </div>
                  <p className="text-2xl font-bold text-gray-900 dark:text-gray-100" dir="ltr">
                    {formatCardValue(card)}
                  </p>
                  {formatCardSubtext(card) && (
                    <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                      {formatCardSubtext(card)}
                    </p>
                  )}
                  {card.data?.direction_note_fa && (
                    <p className="mt-1 text-[11px] text-amber-600 dark:text-amber-400">
                      {String(card.data.direction_note_fa)}
                    </p>
                  )}
                  {card.data?.source && (
                    <p className="mt-1.5 text-[10px] text-gray-400" dir="ltr">
                      {String(card.data.source)}
                      {card.data.source_date && ` · ${String(card.data.source_date)}`}
                    </p>
                  )}
                </div>
              );
            })}
          </div>

          <div className="mt-3 rounded-lg border border-blue-500/20 bg-blue-500/5 p-3">
            <p className="text-xs text-blue-600 dark:text-blue-400">
              <span className="ml-1 font-bold">&#x26A1; چرا مهم است؟</span>
              جریان پول نهادی، نرخ بهره واقعی، قدرت دلار و ریسک بازار چهار عامل اصلی قیمت جهانی طلا هستند.
              این کارت‌ها وضعیت لحظه‌ای هر عامل را نشان می‌دهند.
            </p>
          </div>
        </>
      )}
    </div>
  );
}
