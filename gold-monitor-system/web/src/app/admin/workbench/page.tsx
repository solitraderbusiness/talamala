"use client";

import { useCallback, useEffect, useState } from "react";
import PanelSelector from "@/components/workbench/PanelSelector";
import WorkbenchChat from "@/components/workbench/WorkbenchChat";
import MacroOverview from "@/components/analysis/MacroOverview";
import SentimentGauge from "@/components/analysis/SentimentGauge";
import CorrelationMatrix from "@/components/analysis/CorrelationMatrix";
import MoneyFlowAnalysis from "@/components/analysis/MoneyFlowAnalysis";
import RealRatesSection from "@/components/analysis/RealRatesSection";
import MarketActivityFeed from "@/components/analysis/MarketActivityFeed";
import RegimeMonitor from "@/components/analysis/RegimeMonitor";
import type {
  MacroOverviewResponse,
  SentimentGaugeResponse,
  CorrelationsResponse,
  MoneyFlowResponse,
  RealRatesResponse,
  MarketActivityResponse,
} from "@/lib/api";

/* Regime data is defined locally in the component, not exported from api.ts */
interface RegimeData {
  ts: string;
  liquidity_stress_index: number | null;
  usd_pressure_index: number | null;
  real_yield_pressure_index: number | null;
  p_expansion: number | null;
  p_tightening: number | null;
  p_stress: number | null;
  p_recovery: number | null;
  smoothed_p_expansion: number | null;
  smoothed_p_tightening: number | null;
  smoothed_p_stress: number | null;
  smoothed_p_recovery: number | null;
  chosen_regime: string | null;
  real_yield_source: string | null;
  credit_proxy_source: string | null;
  status?: string;
}

export default function WorkbenchPage() {
  const [activePanels, setActivePanels] = useState<Set<string>>(new Set());

  const handleToggle = useCallback((panelId: string) => {
    setActivePanels((prev) => {
      const next = new Set(prev);
      if (next.has(panelId)) {
        next.delete(panelId);
      } else {
        next.add(panelId);
      }
      return next;
    });
  }, []);

  const activePanelIds = Array.from(activePanels);

  return (
    <div className="space-y-4">
      {/* Header */}
      <div>
        <h1 className="text-lg font-bold text-gray-900 dark:text-gray-100">
          میز تحلیل
        </h1>
        <p className="text-xs text-gray-500 dark:text-gray-400">
          پنل‌های تحلیلی را فعال کنید و با هوش مصنوعی داده‌ها را کاوش کنید
        </p>
      </div>

      {/* Panel selector */}
      <PanelSelector activePanels={activePanels} onToggle={handleToggle} />

      {/* Main layout: panels + chat */}
      <div className="flex flex-col gap-4 lg:flex-row" style={{ minHeight: "70vh" }}>
        {/* Active panels (collapsible on mobile) */}
        {activePanelIds.length > 0 && (
          <div className="w-full space-y-4 overflow-y-auto lg:w-[40%]" style={{ maxHeight: "80vh" }}>
            {activePanelIds.map((panelId) => (
              <SelfFetchPanel key={panelId} panelId={panelId} />
            ))}
          </div>
        )}

        {/* Chat */}
        <div
          className={`flex-1 ${activePanelIds.length > 0 ? "lg:w-[60%]" : "w-full"}`}
          style={{ minHeight: "60vh", maxHeight: "80vh" }}
        >
          <WorkbenchChat activePanels={activePanels} />
        </div>
      </div>
    </div>
  );
}

/* Self-fetching wrapper that loads data and renders the correct analysis component */
function SelfFetchPanel({ panelId }: { panelId: string }) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const endpoints: Record<string, string> = {
      macro_overview: "/api/analysis/macro-overview",
      sentiment_gauge: "/api/analysis/sentiment-gauge",
      regime_monitor: "/api/regime/latest",
      correlation_matrix: "/api/analysis/correlations",
      money_flow: "/api/analysis/money-flow",
      real_rates: "/api/analysis/real-rates",
      market_activity: "/api/analysis/market-activity",
    };

    const url = endpoints[panelId];
    if (!url) return;

    setLoading(true);
    fetch(url)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setData(d))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [panelId]);

  switch (panelId) {
    case "macro_overview":
      return <MacroOverview data={data as MacroOverviewResponse | null} loading={loading} />;
    case "sentiment_gauge":
      return <SentimentGauge data={data as SentimentGaugeResponse | null} loading={loading} />;
    case "regime_monitor":
      return <RegimeMonitor data={data as RegimeData | null} loading={loading} />;
    case "correlation_matrix":
      return <CorrelationMatrix data={data as CorrelationsResponse | null} loading={loading} />;
    case "money_flow":
      return <MoneyFlowAnalysis data={data as MoneyFlowResponse | null} loading={loading} />;
    case "real_rates":
      return <RealRatesSection data={data as RealRatesResponse | null} loading={loading} />;
    case "market_activity":
      return <MarketActivityFeed data={data as MarketActivityResponse | null} loading={loading} />;
    default:
      return null;
  }
}
