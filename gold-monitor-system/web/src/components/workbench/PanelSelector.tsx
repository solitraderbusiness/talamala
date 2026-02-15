"use client";

import { cn } from "@/lib/utils";

interface PanelOption {
  id: string;
  label: string;
  icon: string;
}

const PANELS: PanelOption[] = [
  { id: "macro_overview", label: "نمای کلان", icon: "📊" },
  { id: "sentiment_gauge", label: "سنجش احساسات", icon: "🎯" },
  { id: "regime_monitor", label: "رژیم بازار", icon: "📈" },
  { id: "correlation_matrix", label: "همبستگی", icon: "🔗" },
  { id: "money_flow", label: "جریان پول", icon: "💰" },
  { id: "real_rates", label: "نرخ بهره", icon: "🏦" },
  { id: "market_activity", label: "رویدادها", icon: "⚡" },
];

interface PanelSelectorProps {
  activePanels: Set<string>;
  onToggle: (panelId: string) => void;
}

export default function PanelSelector({ activePanels, onToggle }: PanelSelectorProps) {
  return (
    <div className="flex flex-wrap gap-2">
      {PANELS.map((panel) => {
        const isActive = activePanels.has(panel.id);
        return (
          <button
            key={panel.id}
            onClick={() => onToggle(panel.id)}
            className={cn(
              "flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-all",
              isActive
                ? "border-gold-500 bg-gold-100 text-gold-800 dark:border-gold-600 dark:bg-gold-900/30 dark:text-gold-300"
                : "border-gray-300 bg-white text-gray-600 hover:border-gray-400 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-400 dark:hover:border-gray-600"
            )}
          >
            <span>{panel.icon}</span>
            <span>{panel.label}</span>
          </button>
        );
      })}
    </div>
  );
}

export { PANELS };
export type { PanelOption };
