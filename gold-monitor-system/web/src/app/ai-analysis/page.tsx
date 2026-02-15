"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { useChatContext } from "@/components/ChatWidget/ChatContext";

const TradingViewChart = dynamic(() => import("@/components/TradingViewChart"), {
  ssr: false,
  loading: () => (
    <div className="card flex h-[350px] items-center justify-center sm:h-[500px]">
      <span className="text-sm text-gray-400">در حال بارگذاری نمودار...</span>
    </div>
  ),
});

import ActionBox from "@/components/analysis/ActionBox";
import DeltasPanel from "@/components/analysis/DeltasPanel";
import MacroOverview from "@/components/analysis/MacroOverview";
import MoneyFlowAnalysis from "@/components/analysis/MoneyFlowAnalysis";
import RealRatesSection from "@/components/analysis/RealRatesSection";
import CorrelationMatrix from "@/components/analysis/CorrelationMatrix";
import SentimentGauge from "@/components/analysis/SentimentGauge";
import RegimeMonitor from "@/components/analysis/RegimeMonitor";
import MarketActivityFeed from "@/components/analysis/MarketActivityFeed";
import RiskRadar from "@/components/analysis/RiskRadar";
import MomentumDashboard from "@/components/analysis/MomentumDashboard";
import SentimentPriceAnalysis from "@/components/analysis/SentimentPriceAnalysis";
import TimeOfDayAnalysis from "@/components/analysis/TimeOfDayAnalysis";
import EventImpactTracker from "@/components/analysis/EventImpactTracker";
import EtfMomentumCot from "@/components/analysis/EtfMomentumCot";
import ExpertConsensus from "@/components/analysis/ExpertConsensus";
import CorrelationByRegime from "@/components/analysis/CorrelationByRegime";
import RegimeGoldPerformance from "@/components/analysis/RegimeGoldPerformance";

import type {
  MacroOverviewResponse,
  MoneyFlowResponse,
  RealRatesResponse,
  CorrelationsResponse,
  SentimentGaugeResponse,
  MarketActivityResponse,
  ActionSummaryResponse,
  DeltasResponse,
} from "@/lib/api";

/* ════════════════════════════════════════════════════════════════════════
   Constants
   ════════════════════════════════════════════════════════════════════════ */

const REFRESH_INTERVAL_MS = 60_000;

/* ════════════════════════════════════════════════════════════════════════
   AskCard — small "ask the copilot" button for each section
   ════════════════════════════════════════════════════════════════════════ */

function AskCard({ cardId, question }: { cardId: string; question: string }) {
  const { openWithContext } = useChatContext();
  return (
    <button
      onClick={() => openWithContext({ type: "page", title: cardId }, question)}
      className="text-[10px] text-gold-500/60 hover:text-gold-500 transition-colors"
      title="بپرس از دستیار"
    >
      💬 بپرس
    </button>
  );
}

/* ════════════════════════════════════════════════════════════════════════
   Main Page Component
   ════════════════════════════════════════════════════════════════════════ */

export default function AIAnalysisPage() {
  // ── Section data ──
  const [macroOverview, setMacroOverview] = useState<MacroOverviewResponse | null>(null);
  const [moneyFlow, setMoneyFlow] = useState<MoneyFlowResponse | null>(null);
  const [realRates, setRealRates] = useState<RealRatesResponse | null>(null);
  const [correlations, setCorrelations] = useState<CorrelationsResponse | null>(null);
  const [sentimentGauge, setSentimentGauge] = useState<SentimentGaugeResponse | null>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [regimeData, setRegimeData] = useState<any>(null);
  const [marketActivity, setMarketActivity] = useState<MarketActivityResponse | null>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [riskRadar, setRiskRadar] = useState<any>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [momentum, setMomentum] = useState<any>(null);
  const [actionSummary, setActionSummary] = useState<ActionSummaryResponse | null>(null);
  const [deltasData, setDeltasData] = useState<DeltasResponse | null>(null);

  // ── Loading states ──
  const [macroLoading, setMacroLoading] = useState(true);
  const [moneyFlowLoading, setMoneyFlowLoading] = useState(true);
  const [realRatesLoading, setRealRatesLoading] = useState(true);
  const [correlationsLoading, setCorrelationsLoading] = useState(true);
  const [sentimentLoading, setSentimentLoading] = useState(true);
  const [regimeLoading, setRegimeLoading] = useState(true);
  const [activityLoading, setActivityLoading] = useState(true);
  const [riskRadarLoading, setRiskRadarLoading] = useState(true);
  const [momentumLoading, setMomentumLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(true);
  const [deltasLoading, setDeltasLoading] = useState(true);

  // ── Global ──
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const refreshTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  /* ────────────────────────────────────────────────────────────────────
     Data Fetching
     ──────────────────────────────────────────────────────────────────── */

  const fetchSection = useCallback(
    async <T,>(
      url: string,
      setter: (d: T) => void,
      loadingSetter: (b: boolean) => void,
    ) => {
      try {
        const res = await fetch(url);
        if (res.ok) {
          const data = await res.json();
          setter(data as T);
        }
      } catch {
        // Silent — section shows pending state
      } finally {
        loadingSetter(false);
      }
    },
    [],
  );

  const refreshAll = useCallback(async () => {
    await Promise.allSettled([
      fetchSection<MacroOverviewResponse>("/api/analysis/macro-overview", setMacroOverview, setMacroLoading),
      fetchSection<MoneyFlowResponse>("/api/analysis/money-flow", setMoneyFlow, setMoneyFlowLoading),
      fetchSection<RealRatesResponse>("/api/analysis/real-rates", setRealRates, setRealRatesLoading),
      fetchSection<CorrelationsResponse>("/api/analysis/correlations", setCorrelations, setCorrelationsLoading),
      fetchSection<SentimentGaugeResponse>("/api/analysis/sentiment-gauge", setSentimentGauge, setSentimentLoading),
      fetchSection("/api/regime/latest", setRegimeData, setRegimeLoading),
      fetchSection<MarketActivityResponse>("/api/analysis/market-activity", setMarketActivity, setActivityLoading),
      fetchSection("/api/analysis/risk-radar", setRiskRadar, setRiskRadarLoading),
      fetchSection("/api/analysis/momentum", setMomentum, setMomentumLoading),
      fetchSection<ActionSummaryResponse>("/api/analysis/action-summary", setActionSummary, setActionLoading),
      fetchSection<DeltasResponse>("/api/analysis/deltas", setDeltasData, setDeltasLoading),
    ]);
    setLastUpdated(new Date());
  }, [fetchSection]);

  /* ────────────────────────────────────────────────────────────────────
     Effects
     ──────────────────────────────────────────────────────────────────── */

  const refreshAllRef = useRef(refreshAll);
  refreshAllRef.current = refreshAll;

  useEffect(() => {
    refreshAllRef.current();
  }, []);

  useEffect(() => {
    if (refreshTimer.current) {
      clearInterval(refreshTimer.current);
      refreshTimer.current = null;
    }
    if (autoRefresh) {
      refreshTimer.current = setInterval(refreshAll, REFRESH_INTERVAL_MS);
    }
    return () => {
      if (refreshTimer.current) clearInterval(refreshTimer.current);
    };
  }, [autoRefresh, refreshAll]);

  /* ════════════════════════════════════════════════════════════════════════
     Render
     ════════════════════════════════════════════════════════════════════════ */

  return (
    <div className="space-y-8">
      {/* ── Page Header ── */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Link
              href="/"
              className="text-gray-400 transition-colors hover:text-gray-600 dark:hover:text-gray-300"
            >
              داشبورد
            </Link>
            <span className="text-gray-300 dark:text-gray-600">/</span>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
              تحلیل بنیادی
            </h1>
          </div>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            تحلیل بنیادی لحظه‌ای بازار طلا — جریان پول، نرخ بهره، همبستگی‌ها و احساسات بازار
          </p>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/10 px-3 py-1 text-xs font-medium text-emerald-500 border border-emerald-500/30">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
            </span>
            زنده
          </span>
          {lastUpdated && (
            <span className="text-gray-400">
              {lastUpdated.toLocaleTimeString("fa-IR", { hour: "2-digit", minute: "2-digit" })}
            </span>
          )}
          <button
            onClick={() => refreshAll()}
            className="btn-secondary inline-flex items-center gap-1 px-3 py-1.5 text-xs"
            title="به‌روزرسانی"
          >
            &#x21bb; به‌روزرسانی
          </button>
          <label className="inline-flex cursor-pointer items-center gap-1.5">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="h-4 w-4 accent-gold-600"
            />
            <span className="text-gray-500 dark:text-gray-400">خودکار</span>
          </label>
        </div>
      </div>

      {/* ╔══════════════════════════════════════════════════════════════════╗
         ║  SECTION 1: TradingView Chart                                    ║
         ╚══════════════════════════════════════════════════════════════════╝ */}
      <section id="chart">
        <TradingViewChart />
      </section>

      {/* ╔══════════════════════════════════════════════════════════════════╗
         ║  SECTION 1.1: Action Summary                                     ║
         ╚══════════════════════════════════════════════════════════════════╝ */}
      <section id="action-summary">
        <div className="flex items-center justify-between mb-1">
          <span />
          <AskCard cardId="action" question="توصیه عملیاتی امروز چیه؟" />
        </div>
        <ActionBox data={actionSummary} loading={actionLoading} />
      </section>

      {/* ╔══════════════════════════════════════════════════════════════════╗
         ║  SECTION 1.2: What Changed (Deltas)                              ║
         ╚══════════════════════════════════════════════════════════════════╝ */}
      <section id="deltas">
        <div className="flex items-center justify-between mb-1">
          <span />
          <AskCard cardId="deltas" question="امروز چه تغییراتی شده؟" />
        </div>
        <DeltasPanel data={deltasData} loading={deltasLoading} />
      </section>

      {/* ╔══════════════════════════════════════════════════════════════════╗
         ║  SECTION 1.5: Risk Radar + Momentum (side by side)               ║
         ╚══════════════════════════════════════════════════════════════════╝ */}
      <section id="risk-momentum">
        <div className="flex items-center justify-end gap-4 mb-1">
          <AskCard cardId="risk" question="شاخص ریسک بازار الان چقدره؟" />
          <AskCard cardId="momentum" question="شتاب و عوامل بنیادی طلا چطوره؟" />
        </div>
        <div className="grid gap-6 lg:grid-cols-2">
          <RiskRadar data={riskRadar} loading={riskRadarLoading} />
          <MomentumDashboard data={momentum} loading={momentumLoading} />
        </div>
      </section>

      {/* ╔══════════════════════════════════════════════════════════════════╗
         ║  SECTION 2: Sentiment Gauge                                      ║
         ╚══════════════════════════════════════════════════════════════════╝ */}
      <section id="sentiment">
        <div className="flex items-center justify-between mb-1">
          <span />
          <AskCard cardId="sentiment" question="امتیاز احساسات بازار چقدر است و چرا؟" />
        </div>
        <SentimentGauge data={sentimentGauge} loading={sentimentLoading} />
      </section>

      {/* ╔══════════════════════════════════════════════════════════════════╗
         ║  SECTION 2.5: Regime Monitor                                     ║
         ╚══════════════════════════════════════════════════════════════════╝ */}
      <section id="regime">
        <RegimeMonitor data={regimeData} loading={regimeLoading} />
      </section>

      {/* ╔══════════════════════════════════════════════════════════════════╗
         ║  SECTION 3: Macro Overview Cards                                 ║
         ╚══════════════════════════════════════════════════════════════════╝ */}
      <section id="macro-overview">
        <div className="flex items-center justify-between mb-1">
          <span />
          <AskCard cardId="macro" question="خلاصه وضعیت کلان بازار چطوره؟" />
        </div>
        <MacroOverview data={macroOverview} loading={macroLoading} />
      </section>

      {/* ╔══════════════════════════════════════════════════════════════════╗
         ║  SECTION 4: Money Flow Analysis                                  ║
         ╚══════════════════════════════════════════════════════════════════╝ */}
      <section id="money-flow">
        <div className="flex items-center justify-between mb-1">
          <span />
          <AskCard cardId="money_flow" question="جریان ETF و موقعیت COT چطوره؟" />
        </div>
        <MoneyFlowAnalysis data={moneyFlow} loading={moneyFlowLoading} />
      </section>

      {/* ╔══════════════════════════════════════════════════════════════════╗
         ║  SECTION 5: Real Rates Section                                   ║
         ╚══════════════════════════════════════════════════════════════════╝ */}
      <section id="real-rates">
        <div className="flex items-center justify-between mb-1">
          <span />
          <AskCard cardId="real_rates" question="نرخ بهره واقعی الان چنده؟" />
        </div>
        <RealRatesSection data={realRates} loading={realRatesLoading} />
      </section>

      {/* ╔══════════════════════════════════════════════════════════════════╗
         ║  SECTION 6: Correlation Matrix                                   ║
         ╚══════════════════════════════════════════════════════════════════╝ */}
      <section id="correlations">
        <div className="flex items-center justify-between mb-1">
          <span />
          <AskCard cardId="correlations" question="همبستگی طلا با دلار و بازارها چطوره؟" />
        </div>
        <CorrelationMatrix data={correlations} loading={correlationsLoading} />
      </section>

      {/* ╔══════════════════════════════════════════════════════════════════╗
         ║  SECTION 6.5: Sentiment vs Price Analysis                        ║
         ╚══════════════════════════════════════════════════════════════════╝ */}
      <section id="sentiment-price">
        <SentimentPriceAnalysis />
      </section>

      {/* ╔══════════════════════════════════════════════════════════════════╗
         ║  SECTION 6.6: Regime Gold Performance + Correlation by Regime    ║
         ╚══════════════════════════════════════════════════════════════════╝ */}
      <section id="regime-insights" className="grid gap-6 lg:grid-cols-2">
        <RegimeGoldPerformance />
        <CorrelationByRegime />
      </section>

      {/* ╔══════════════════════════════════════════════════════════════════╗
         ║  SECTION 6.7: ETF Momentum + Expert Consensus                   ║
         ╚══════════════════════════════════════════════════════════════════╝ */}
      <section id="institutional-flow">
        <EtfMomentumCot />
      </section>

      {/* ╔══════════════════════════════════════════════════════════════════╗
         ║  SECTION 6.8: Expert Consensus + Event Impact                   ║
         ╚══════════════════════════════════════════════════════════════════╝ */}
      <section id="expert-events" className="grid gap-6 lg:grid-cols-2">
        <ExpertConsensus />
        <EventImpactTracker />
      </section>

      {/* ╔══════════════════════════════════════════════════════════════════╗
         ║  SECTION 6.9: Time of Day Analysis                               ║
         ╚══════════════════════════════════════════════════════════════════╝ */}
      <section id="time-of-day">
        <TimeOfDayAnalysis />
      </section>

      {/* ╔══════════════════════════════════════════════════════════════════╗
         ║  SECTION 8: Market Activity Feed                                 ║
         ╚══════════════════════════════════════════════════════════════════╝ */}
      <section id="market-activity">
        <MarketActivityFeed data={marketActivity} loading={activityLoading} />
      </section>

      {/* ── Footer Attribution ── */}
      <div className="pb-4 text-center text-xs text-gray-400">
        تحلیل‌ها توسط سیستم طلاملا تولید شده‌اند و جایگزین مشاوره مالی نیستند.
      </div>
    </div>
  );
}
