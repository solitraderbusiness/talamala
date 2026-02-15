"use client";

import { useState, useEffect } from "react";
import { cn } from "@/lib/utils";
import InfoTip from "@/components/InfoTip";
import DataPending from "./DataPending";
import SkeletonCard from "./SkeletonCard";

/* ---------- Interfaces ---------- */

interface CorrelationLag {
  lag: string;
  lag_rows: number;
  correlation: number;
}

interface SentimentCorrelationData {
  lags: CorrelationLag[];
  data_points: number;
}

interface ExtremeData {
  count: number;
  avg_change_1h: number | null;
  avg_change_4h: number | null;
  avg_change_24h: number | null;
}

interface SentimentExtremesData {
  bullish_extreme: ExtremeData;
  bearish_extreme: ExtremeData;
}

/* ---------- Helpers ---------- */

function getCorrelationColor(corr: number): string {
  if (corr >= 0.6) return "bg-emerald-500";
  if (corr >= 0.3) return "bg-emerald-400";
  if (corr > 0) return "bg-emerald-300/60";
  if (corr === 0) return "bg-gray-400";
  if (corr > -0.3) return "bg-red-300/60";
  if (corr > -0.6) return "bg-red-400";
  return "bg-red-500";
}

function getCorrelationTextColor(corr: number): string {
  if (corr >= 0.3) return "text-emerald-500";
  if (corr > 0) return "text-emerald-400";
  if (corr === 0) return "text-gray-400";
  if (corr > -0.3) return "text-red-400";
  return "text-red-500";
}

function getMoveColor(value: number | null): string {
  if (value == null) return "text-gray-400";
  if (value > 0) return "text-emerald-500";
  if (value < 0) return "text-red-500";
  return "text-gray-400";
}

function formatMove(value: number | null): string {
  if (value == null) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

function getStrengthLabel(corr: number): string {
  const abs = Math.abs(corr);
  if (abs >= 0.7) return "قوی";
  if (abs >= 0.3) return "متوسط";
  return "ضعیف";
}

/* ---------- Component ---------- */

export default function SentimentPriceAnalysis() {
  const [correlationData, setCorrelationData] =
    useState<SentimentCorrelationData | null>(null);
  const [extremesData, setExtremesData] =
    useState<SentimentExtremesData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function fetchData() {
      setLoading(true);
      try {
        const [corrRes, extRes] = await Promise.all([
          fetch("/api/analysis/sentiment-price-correlation").then((r) =>
            r.ok ? r.json() : null
          ),
          fetch("/api/analysis/sentiment-extremes").then((r) =>
            r.ok ? r.json() : null
          ),
        ]);
        if (!cancelled) {
          setCorrelationData(corrRes);
          setExtremesData(extRes);
        }
      } catch {
        // Silently handle fetch errors — component will show "no data" state
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetchData();
    return () => {
      cancelled = true;
    };
  }, []);

  const hasCorrelation =
    correlationData && correlationData.lags && correlationData.lags.length > 0;
  const hasExtremes =
    extremesData &&
    extremesData.bullish_extreme &&
    extremesData.bearish_extreme &&
    (extremesData.bullish_extreme.count > 0 || extremesData.bearish_extreme.count > 0);
  const hasData = hasCorrelation || hasExtremes;

  // Find the strongest correlation lag
  const strongestLag = hasCorrelation
    ? correlationData!.lags.reduce((best, lag) =>
        Math.abs(lag.correlation) > Math.abs(best.correlation) ? lag : best
      )
    : null;

  // Max absolute correlation for scaling bars
  const maxAbsCorr = hasCorrelation
    ? Math.max(
        ...correlationData!.lags.map((l) => Math.abs(l.correlation)),
        0.1
      )
    : 1;

  return (
    <div className="flex flex-col">
      {/* Header */}
      <div className="mb-4 flex items-center gap-2">
        <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100">
          همبستگی احساسات و قیمت
        </h2>
        <InfoTip term="sentiment_price_lag" />
      </div>

      {loading ? (
        <div className="space-y-4">
          <SkeletonCard className="h-48" />
          <div className="grid gap-4 sm:grid-cols-2">
            <SkeletonCard className="h-40" />
            <SkeletonCard className="h-40" />
          </div>
        </div>
      ) : !hasData ? (
        <DataPending message="در انتظار داده — داده‌های همبستگی احساسات و قیمت پس از جمع‌آوری کافی نمایش داده خواهند شد." />
      ) : (
        <div className="space-y-6">
          {/* Section 1: Cross-Correlation */}
          {hasCorrelation && (
            <div className="card">
              <div className="mb-4 flex items-center justify-between">
                <h3 className="text-sm font-bold text-gray-900 dark:text-gray-100">
                  همبستگی متقابل (Cross-Correlation)
                </h3>
                <span className="text-[11px] text-gray-400" dir="ltr">
                  {correlationData!.data_points} نقطه داده
                </span>
              </div>

              <div className="space-y-3">
                {correlationData!.lags.map((lag) => {
                  const isStrongest =
                    strongestLag &&
                    lag.lag === strongestLag.lag;
                  const barWidth =
                    (Math.abs(lag.correlation) / maxAbsCorr) * 50;

                  return (
                    <div
                      key={lag.lag}
                      className={cn(
                        "rounded-lg p-2.5 transition-colors",
                        isStrongest
                          ? "bg-amber-500/10 ring-1 ring-amber-500/30"
                          : "bg-gray-50 dark:bg-gray-800/50"
                      )}
                    >
                      <div className="mb-1.5 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-medium text-gray-600 dark:text-gray-400">
                            تاخیر:{" "}
                            <span className="font-bold text-gray-900 dark:text-gray-100" dir="ltr">
                              {lag.lag}
                            </span>
                          </span>
                          {isStrongest && (
                            <span className="rounded-full bg-amber-500/20 px-2 py-0.5 text-[10px] font-bold text-amber-600 dark:text-amber-400">
                              قوی‌ترین
                            </span>
                          )}
                        </div>
                        <span
                          className={cn(
                            "text-sm font-bold",
                            getCorrelationTextColor(lag.correlation)
                          )}
                          dir="ltr"
                        >
                          {lag.correlation > 0 ? "+" : ""}
                          {lag.correlation.toFixed(2)}
                        </span>
                      </div>

                      {/* Horizontal bar chart */}
                      <div className="relative h-5 rounded-full bg-gray-200 dark:bg-gray-700">
                        {/* Center line */}
                        <div className="absolute left-1/2 top-0 h-full w-0.5 -translate-x-0.5 bg-gray-400 dark:bg-gray-500 z-10" />

                        {/* Correlation bar */}
                        <div
                          className={cn(
                            "absolute top-0 h-full rounded-full transition-all duration-500",
                            getCorrelationColor(lag.correlation)
                          )}
                          style={{
                            width: `${barWidth}%`,
                            ...(lag.correlation >= 0
                              ? {
                                  left: "50%",
                                  borderTopLeftRadius: 0,
                                  borderBottomLeftRadius: 0,
                                }
                              : {
                                  right: "50%",
                                  borderTopRightRadius: 0,
                                  borderBottomRightRadius: 0,
                                }),
                          }}
                        />
                      </div>

                      <div className="mt-1 text-[10px] text-gray-400">
                        <span>{getStrengthLabel(lag.correlation)}</span>
                      </div>
                    </div>
                  );
                })}
              </div>

              {strongestLag && (
                <div className="mt-4 rounded-lg border border-blue-500/20 bg-blue-500/5 p-3">
                  <p className="text-xs text-blue-600 dark:text-blue-400">
                    <span className="ml-1 font-bold">نتیجه:</span>
                    بیشترین همبستگی در تاخیر{" "}
                    <span className="font-bold" dir="ltr">
                      {strongestLag.lag}
                    </span>{" "}
                    با مقدار{" "}
                    <span className="font-bold" dir="ltr">
                      {strongestLag.correlation > 0 ? "+" : ""}
                      {strongestLag.correlation.toFixed(2)}
                    </span>{" "}
                    مشاهده شد.
                    {Math.abs(strongestLag.correlation) >= 0.5
                      ? " این نشان‌دهنده رابطه قابل توجه بین احساسات و تغییرات قیمت است."
                      : " این رابطه نسبتا ضعیف بوده و باید با احتیاط تفسیر شود."}
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Section 2: Extreme Signal Cards — only show when we have actual data */}
          <div>
            <h3 className="mb-3 flex items-center gap-2 text-sm font-bold text-gray-900 dark:text-gray-100">
              سیگنال‌های افراطی
              <InfoTip term="sentiment_extreme_signal" />
            </h3>
            {!hasExtremes ? (
              <div className="rounded-xl border border-dashed border-gray-300 p-6 text-center dark:border-gray-700">
                <p className="text-sm text-gray-400">
                  هنوز داده کافی جمع‌آوری نشده است.
                </p>
                <p className="mt-1 text-xs text-gray-400">
                  وقتی شاخص احساسات به بالای ۸۰ یا زیر ۲۰ برسد، تاثیر آن بر قیمت طلا اینجا نمایش داده خواهد شد.
                </p>
              </div>
            ) : (
              <div className="grid gap-4 sm:grid-cols-2">
                {/* Bullish Extreme Card */}
                <div className="card border-t-2 border-emerald-500">
                  <div className="mb-3 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <div className="flex h-8 w-8 items-center justify-center rounded-full bg-emerald-500/10">
                        <svg
                          className="h-4 w-4 text-emerald-500"
                          viewBox="0 0 20 20"
                          fill="currentColor"
                        >
                          <path
                            fillRule="evenodd"
                            d="M12.577 4.878a.75.75 0 01.919-.53l4.78 1.281a.75.75 0 01.531.919l-1.281 4.78a.75.75 0 01-1.449-.387l.81-3.022a19.407 19.407 0 00-5.594 5.203.75.75 0 01-1.139.093L7 10.06l-4.72 4.72a.75.75 0 01-1.06-1.06l5.25-5.25a.75.75 0 011.06 0l3.074 3.073a20.923 20.923 0 015.545-4.931l-3.042.815a.75.75 0 01-.53-.919z"
                            clipRule="evenodd"
                          />
                        </svg>
                      </div>
                      <span className="text-sm font-bold text-emerald-600 dark:text-emerald-400">
                        صعودی شدید
                      </span>
                    </div>
                    <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[11px] font-medium text-emerald-600 dark:text-emerald-400">
                      احساسات &gt; ۸۰
                    </span>
                  </div>

                  <div className="mb-3 text-xs text-gray-500 dark:text-gray-400">
                    {extremesData!.bullish_extreme.count} مورد ثبت شده
                  </div>

                  <div className="space-y-2.5">
                    {[
                      {
                        label: "میانگین تغییر ۱ ساعته",
                        value: extremesData!.bullish_extreme.avg_change_1h,
                      },
                      {
                        label: "میانگین تغییر ۴ ساعته",
                        value: extremesData!.bullish_extreme.avg_change_4h,
                      },
                      {
                        label: "میانگین تغییر ۲۴ ساعته",
                        value: extremesData!.bullish_extreme.avg_change_24h,
                      },
                    ].map((item) => (
                      <div
                        key={item.label}
                        className="flex items-center justify-between rounded-lg bg-gray-50 px-3 py-2 dark:bg-gray-800/50"
                      >
                        <span className="text-xs text-gray-600 dark:text-gray-400">
                          {item.label}
                        </span>
                        <span
                          className={cn(
                            "text-sm font-bold",
                            getMoveColor(item.value)
                          )}
                          dir="ltr"
                        >
                          {formatMove(item.value)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Bearish Extreme Card */}
                <div className="card border-t-2 border-red-500">
                  <div className="mb-3 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <div className="flex h-8 w-8 items-center justify-center rounded-full bg-red-500/10">
                        <svg
                          className="h-4 w-4 text-red-500"
                          viewBox="0 0 20 20"
                          fill="currentColor"
                        >
                          <path
                            fillRule="evenodd"
                            d="M1.22 5.222a.75.75 0 011.06 0L7 9.942l3.768-3.769a.75.75 0 011.113.058 20.908 20.908 0 013.813 7.254l1.574-2.727a.75.75 0 011.3.75l-2.475 4.286a.75.75 0 01-1.025.275l-4.287-2.475a.75.75 0 01.75-1.3l2.71 1.565a19.422 19.422 0 00-3.013-5.88L7.53 11.533a.75.75 0 01-1.06 0l-5.25-5.25a.75.75 0 010-1.06z"
                            clipRule="evenodd"
                          />
                        </svg>
                      </div>
                      <span className="text-sm font-bold text-red-600 dark:text-red-400">
                        نزولی شدید
                      </span>
                    </div>
                    <span className="rounded-full bg-red-500/10 px-2 py-0.5 text-[11px] font-medium text-red-600 dark:text-red-400">
                      احساسات &lt; ۲۰
                    </span>
                  </div>

                  <div className="mb-3 text-xs text-gray-500 dark:text-gray-400">
                    {extremesData!.bearish_extreme.count} مورد ثبت شده
                  </div>

                  <div className="space-y-2.5">
                    {[
                      {
                        label: "میانگین تغییر ۱ ساعته",
                        value: extremesData!.bearish_extreme.avg_change_1h,
                      },
                      {
                        label: "میانگین تغییر ۴ ساعته",
                        value: extremesData!.bearish_extreme.avg_change_4h,
                      },
                      {
                        label: "میانگین تغییر ۲۴ ساعته",
                        value: extremesData!.bearish_extreme.avg_change_24h,
                      },
                    ].map((item) => (
                      <div
                        key={item.label}
                        className="flex items-center justify-between rounded-lg bg-gray-50 px-3 py-2 dark:bg-gray-800/50"
                      >
                        <span className="text-xs text-gray-600 dark:text-gray-400">
                          {item.label}
                        </span>
                        <span
                          className={cn(
                            "text-sm font-bold",
                            getMoveColor(item.value)
                          )}
                          dir="ltr"
                        >
                          {formatMove(item.value)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
