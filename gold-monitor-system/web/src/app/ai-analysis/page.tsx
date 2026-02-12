"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";

const TradingViewChart = dynamic(() => import("@/components/TradingViewChart"), {
  ssr: false,
  loading: () => (
    <div className="card flex h-[350px] items-center justify-center sm:h-[500px]">
      <span className="text-sm text-gray-400">در حال بارگذاری نمودار...</span>
    </div>
  ),
});

import MacroOverview from "@/components/analysis/MacroOverview";
import MoneyFlowAnalysis from "@/components/analysis/MoneyFlowAnalysis";
import RealRatesSection from "@/components/analysis/RealRatesSection";
import CorrelationMatrix from "@/components/analysis/CorrelationMatrix";
import SentimentGauge from "@/components/analysis/SentimentGauge";
import ShanghaiPremium from "@/components/analysis/ShanghaiPremium";
import MarketActivityFeed from "@/components/analysis/MarketActivityFeed";

import type {
  MacroOverviewResponse,
  MoneyFlowResponse,
  RealRatesResponse,
  CorrelationsResponse,
  SentimentGaugeResponse,
  ShanghaiPremiumResponse,
  MarketActivityResponse,
} from "@/lib/api";

/* ════════════════════════════════════════════════════════════════════════
   Constants
   ════════════════════════════════════════════════════════════════════════ */

const REFRESH_INTERVAL_MS = 60_000;

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
  const [shanghaiPremium, setShanghaiPremium] = useState<ShanghaiPremiumResponse | null>(null);
  const [marketActivity, setMarketActivity] = useState<MarketActivityResponse | null>(null);

  // ── Loading states ──
  const [macroLoading, setMacroLoading] = useState(true);
  const [moneyFlowLoading, setMoneyFlowLoading] = useState(true);
  const [realRatesLoading, setRealRatesLoading] = useState(true);
  const [correlationsLoading, setCorrelationsLoading] = useState(true);
  const [sentimentLoading, setSentimentLoading] = useState(true);
  const [shanghaiLoading, setShanghaiLoading] = useState(true);
  const [activityLoading, setActivityLoading] = useState(true);

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
      fetchSection<ShanghaiPremiumResponse>("/api/analysis/shanghai-premium", setShanghaiPremium, setShanghaiLoading),
      fetchSection<MarketActivityResponse>("/api/analysis/market-activity", setMarketActivity, setActivityLoading),
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
         ║  SECTION 2: Sentiment Gauge                                      ║
         ╚══════════════════════════════════════════════════════════════════╝ */}
      <section id="sentiment">
        <SentimentGauge data={sentimentGauge} loading={sentimentLoading} />
      </section>

      {/* ╔══════════════════════════════════════════════════════════════════╗
         ║  SECTION 3: Macro Overview Cards                                 ║
         ╚══════════════════════════════════════════════════════════════════╝ */}
      <section id="macro-overview">
        <MacroOverview data={macroOverview} loading={macroLoading} />
      </section>

      {/* ╔══════════════════════════════════════════════════════════════════╗
         ║  SECTION 4: Money Flow Analysis                                  ║
         ╚══════════════════════════════════════════════════════════════════╝ */}
      <section id="money-flow">
        <MoneyFlowAnalysis data={moneyFlow} loading={moneyFlowLoading} />
      </section>

      {/* ╔══════════════════════════════════════════════════════════════════╗
         ║  SECTION 5: Real Rates Section                                   ║
         ╚══════════════════════════════════════════════════════════════════╝ */}
      <section id="real-rates">
        <RealRatesSection data={realRates} loading={realRatesLoading} />
      </section>

      {/* ╔══════════════════════════════════════════════════════════════════╗
         ║  SECTION 6: Correlation Matrix                                   ║
         ╚══════════════════════════════════════════════════════════════════╝ */}
      <section id="correlations">
        <CorrelationMatrix data={correlations} loading={correlationsLoading} />
      </section>

      {/* ╔══════════════════════════════════════════════════════════════════╗
         ║  SECTION 7: Shanghai Premium                                     ║
         ╚══════════════════════════════════════════════════════════════════╝ */}
      <section id="shanghai-premium">
        <ShanghaiPremium data={shanghaiPremium} loading={shanghaiLoading} />
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
