"use client";

import { useState, useEffect } from "react";
import { cn } from "@/lib/utils";
import DataPending from "./DataPending";
import SkeletonCard from "./SkeletonCard";
import InfoTip from "@/components/InfoTip";

/* ── Types ── */

interface EtfMomentumResponse {
  fund: string;
  streak_days: number;
  streak_direction: string;
  streak_total_tonnes: number;
  last_date: string;
}

interface CotPercentileResponse {
  current_net: number | null;
  percentile_1yr: number | null;
  percentile_3yr: number | null;
  window_used_1yr?: number;
  window_used_3yr?: number;
  min_required?: number;
  crowding_warning?: boolean;
  total_records: number;
  latest_date: string | null;
  frequency?: string;
}

/* ── Helpers ── */

function getPercentileColor(pct: number): string {
  if (pct >= 90) return "bg-red-500";
  if (pct >= 70) return "bg-amber-500";
  if (pct >= 30) return "bg-emerald-500";
  if (pct >= 10) return "bg-amber-500";
  return "bg-red-500";
}

function getPercentileTextColor(pct: number): string {
  if (pct >= 90) return "text-red-500";
  if (pct >= 70) return "text-amber-500";
  if (pct >= 30) return "text-emerald-500";
  if (pct >= 10) return "text-amber-500";
  return "text-red-500";
}

/* ── Component ── */

export default function EtfMomentumCot() {
  const [etfData, setEtfData] = useState<EtfMomentumResponse | null>(null);
  const [cotData, setCotData] = useState<CotPercentileResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function fetchAll() {
      const [etfRes, cotRes] = await Promise.allSettled([
        fetch("/api/analysis/etf-momentum").then((r) => {
          if (!r.ok) throw new Error(`HTTP ${r.status}`);
          return r.json() as Promise<EtfMomentumResponse>;
        }),
        fetch("/api/analysis/cot-percentile").then((r) => {
          if (!r.ok) throw new Error(`HTTP ${r.status}`);
          return r.json() as Promise<CotPercentileResponse>;
        }),
      ]);

      if (!cancelled) {
        setEtfData(etfRes.status === "fulfilled" ? etfRes.value : null);
        setCotData(cotRes.status === "fulfilled" ? cotRes.value : null);
        setLoading(false);
      }
    }

    fetchAll();
    return () => {
      cancelled = true;
    };
  }, []);

  const hasAnyData = etfData !== null || cotData !== null;

  return (
    <div className="flex flex-col">
      <div className="mb-4 flex items-center gap-2">
        <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100">
          &#x1F3E6; جریان نقدینگی نهادی
        </h2>
      </div>

      {loading ? (
        <div className="grid gap-4 md:grid-cols-2">
          <SkeletonCard className="h-48" />
          <SkeletonCard className="h-48" />
        </div>
      ) : !hasAnyData ? (
        <DataPending message="در انتظار داده" />
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-2">
            {/* ── ETF Momentum Card ── */}
            <div className="card p-5">
              <div className="mb-4 flex items-center gap-2">
                <h3 className="text-sm font-bold text-gray-900 dark:text-gray-100">
                  شتاب جریان ETF
                </h3>
                <InfoTip term="etf_streak" />
              </div>

              {!etfData ? (
                <p className="py-6 text-center text-xs text-gray-400">
                  در انتظار داده
                </p>
              ) : (
                <div className="space-y-4">
                  {/* Streak badge */}
                  <div className="flex items-center justify-center">
                    <span
                      className={cn(
                        "inline-flex items-center gap-1.5 rounded-full px-4 py-2 text-base font-black",
                        etfData.streak_direction === "inflow"
                          ? "bg-emerald-500/10 text-emerald-500 border border-emerald-500/30"
                          : "bg-red-500/10 text-red-500 border border-red-500/30"
                      )}
                    >
                      {etfData.streak_direction === "inflow" ? "+" : "-"}
                      {Math.abs(etfData.streak_days)} روز{" "}
                      {etfData.streak_direction === "inflow" ? "ورود" : "خروج"}
                    </span>
                  </div>

                  {/* Details */}
                  <div className="flex justify-center">
                    <div className="rounded-lg border border-gray-100 p-3 dark:border-gray-800 min-w-[140px] text-center">
                      <span className="block text-[11px] text-gray-400">
                        تغییر کل (تن)
                      </span>
                      <span
                        className={cn(
                          "text-lg font-bold",
                          etfData.streak_total_tonnes >= 0
                            ? "text-emerald-500"
                            : "text-red-500"
                        )}
                        dir="ltr"
                      >
                        {etfData.streak_total_tonnes >= 0 ? "+" : ""}
                        {etfData.streak_total_tonnes.toFixed(1)}
                      </span>
                    </div>
                  </div>

                  {/* Date */}
                  <p className="text-center text-[11px] text-gray-400" dir="ltr">
                    {etfData.last_date}
                    <span className="mr-1.5 rounded bg-gray-100 px-1 py-0.5 dark:bg-gray-800">روزانه</span>
                  </p>
                </div>
              )}
            </div>

            {/* ── COT Percentile Card ── */}
            <div className="card p-5">
              <div className="mb-4 flex items-center gap-2">
                <h3 className="text-sm font-bold text-gray-900 dark:text-gray-100">
                  صدک موقعیت COT
                </h3>
                <InfoTip term="cot_percentile" />
              </div>

              {!cotData || cotData.current_net == null ? (
                <p className="py-6 text-center text-xs text-gray-400">
                  در انتظار داده — گزارش COT هنوز دریافت نشده
                </p>
              ) : (
                <div className="space-y-4">
                  {/* Current net position */}
                  <div className="text-center">
                    <span className="block text-[11px] text-gray-400">
                      موقعیت خالص فعلی
                    </span>
                    <span className="text-2xl font-black text-gray-900 dark:text-gray-100" dir="ltr">
                      {cotData.current_net.toLocaleString()}
                    </span>
                  </div>

                  {/* 1yr Percentile bar */}
                  <div>
                    <div className="mb-1.5 flex items-center justify-between">
                      <span className="text-xs text-gray-500 dark:text-gray-400">
                        صدک ۱ ساله
                        {cotData.window_used_1yr != null && (
                          <span className="mr-1 text-[10px] text-gray-400">
                            ({cotData.window_used_1yr} هفته)
                          </span>
                        )}
                      </span>
                      {cotData.percentile_1yr != null ? (
                        <span
                          className={cn(
                            "text-xs font-bold",
                            getPercentileTextColor(cotData.percentile_1yr)
                          )}
                        >
                          p{Math.round(cotData.percentile_1yr)}
                        </span>
                      ) : (
                        <span className="text-xs text-gray-400">داده ناکافی</span>
                      )}
                    </div>
                    {cotData.percentile_1yr != null && (
                      <div className="h-3 rounded-full bg-gray-200 dark:bg-gray-700">
                        <div
                          className={cn(
                            "h-full rounded-full transition-all duration-700",
                            getPercentileColor(cotData.percentile_1yr)
                          )}
                          style={{ width: `${cotData.percentile_1yr}%` }}
                        />
                      </div>
                    )}
                  </div>

                  {/* 3yr Percentile bar */}
                  <div>
                    <div className="mb-1.5 flex items-center justify-between">
                      <span className="text-xs text-gray-500 dark:text-gray-400">
                        صدک ۳ ساله
                        {cotData.window_used_3yr != null && (
                          <span className="mr-1 text-[10px] text-gray-400">
                            ({cotData.window_used_3yr} هفته)
                          </span>
                        )}
                      </span>
                      {cotData.percentile_3yr != null ? (
                        <span
                          className={cn(
                            "text-xs font-bold",
                            getPercentileTextColor(cotData.percentile_3yr)
                          )}
                        >
                          p{Math.round(cotData.percentile_3yr)}
                        </span>
                      ) : (
                        <span className="text-xs text-gray-400">داده ناکافی</span>
                      )}
                    </div>
                    {cotData.percentile_3yr != null && (
                      <div className="h-3 rounded-full bg-gray-200 dark:bg-gray-700">
                        <div
                          className={cn(
                            "h-full rounded-full transition-all duration-700",
                            getPercentileColor(cotData.percentile_3yr)
                          )}
                          style={{ width: `${cotData.percentile_3yr}%` }}
                        />
                      </div>
                    )}
                  </div>

                  {/* Extreme warning */}
                  {((cotData.percentile_1yr != null && (cotData.percentile_1yr >= 90 || cotData.percentile_1yr <= 10)) ||
                    (cotData.percentile_3yr != null && (cotData.percentile_3yr >= 90 || cotData.percentile_3yr <= 10))) && (
                    <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-2.5">
                      <p className="text-xs font-medium text-amber-600 dark:text-amber-400">
                        &#x26A0;&#xFE0F; موقعیت در ناحیه افراطی — احتمال برگشت
                        بازار وجود دارد.
                      </p>
                    </div>
                  )}

                  {/* Date and count */}
                  <div className="flex items-center justify-between text-[11px] text-gray-400">
                    <span className="flex items-center gap-1">
                      {cotData.total_records} گزارش
                      <span className="rounded bg-gray-100 px-1 py-0.5 dark:bg-gray-800">هفتگی</span>
                    </span>
                    {cotData.latest_date && <span dir="ltr">{cotData.latest_date}</span>}
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="mt-3 rounded-lg border border-blue-500/20 bg-blue-500/5 p-3">
            <p className="text-xs text-blue-600 dark:text-blue-400">
              <span className="ml-1 font-bold">&#x26A1; چرا مهم است؟</span>
              ورود یا خروج متوالی سرمایه از صندوق‌های ETF طلا نشان‌دهنده جهت حرکت
              نهادی‌هاست. صدک‌های بالای ۹۰ یا زیر ۱۰ در موقعیت COT اغلب نشانه
              اشباع بازار و احتمال برگشت قیمت هستند.
            </p>
          </div>
        </>
      )}
    </div>
  );
}
