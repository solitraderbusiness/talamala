"use client";

import { cn } from "@/lib/utils";
import type { CorrelationsResponse } from "@/lib/api";
import DataPending from "./DataPending";
import SkeletonCard from "./SkeletonCard";

function getCorrelationColor(corr: number): string {
  if (corr >= 0.7) return "bg-emerald-500";
  if (corr >= 0.3) return "bg-emerald-400/70";
  if (corr > 0) return "bg-emerald-300/40";
  if (corr === 0) return "bg-gray-500";
  if (corr > -0.3) return "bg-red-300/40";
  if (corr > -0.7) return "bg-red-400/70";
  return "bg-red-500";
}

function getCorrelationLabel(corr: number): string {
  const abs = Math.abs(corr);
  if (abs >= 0.7) return "قوی";
  if (abs >= 0.3) return "متوسط";
  return "ضعیف";
}

interface Props {
  data: CorrelationsResponse | null;
  loading: boolean;
}

export default function CorrelationMatrix({ data, loading }: Props) {
  const hasData = data && data.pairs.length > 0;

  return (
    <div>
      <div className="mb-4 flex items-center gap-2">
        <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100">
          &#x1F517; همبستگی دارایی‌ها با طلا
        </h2>
        {data?.computed_date && (
          <span className="text-xs text-gray-400" dir="ltr">
            ({data.computed_date})
          </span>
        )}
      </div>

      {loading ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <SkeletonCard key={i} className="h-20" />
          ))}
        </div>
      ) : !hasData ? (
        <DataPending message="همبستگی‌ها پس از جمع‌آوری حداقل ۳۰ روز داده قیمتی محاسبه خواهند شد." />
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {data!.pairs.map((pair) => (
              <div key={pair.pair_b} className="card flex items-center gap-3 py-3">
                {/* Correlation bar */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                      {pair.label_fa}
                    </span>
                    <span
                      className={cn(
                        "text-sm font-bold",
                        pair.correlation >= 0 ? "text-emerald-500" : "text-red-500"
                      )}
                      dir="ltr"
                    >
                      {pair.correlation > 0 ? "+" : ""}{pair.correlation.toFixed(2)}
                    </span>
                  </div>

                  {/* Visual bar */}
                  <div className="relative h-3 rounded-full bg-gray-200 dark:bg-gray-700">
                    {/* Center line */}
                    <div className="absolute right-1/2 top-0 h-full w-0.5 bg-gray-400 dark:bg-gray-500" />
                    {/* Correlation bar */}
                    <div
                      className={cn(
                        "absolute top-0 h-full rounded-full transition-all",
                        getCorrelationColor(pair.correlation),
                      )}
                      style={{
                        width: `${Math.abs(pair.correlation) * 50}%`,
                        ...(pair.correlation >= 0
                          ? { right: "50%", borderTopRightRadius: 0, borderBottomRightRadius: 0 }
                          : { left: "50%", borderTopLeftRadius: 0, borderBottomLeftRadius: 0 }),
                      }}
                    />
                  </div>

                  <div className="mt-1 flex items-center justify-between text-[11px] text-gray-400">
                    <span>{getCorrelationLabel(pair.correlation)}</span>
                    <span
                      className={cn(
                        pair.impact === "bullish"
                          ? "text-emerald-500"
                          : pair.impact === "bearish"
                            ? "text-red-500"
                            : "text-gray-400"
                      )}
                    >
                      {pair.impact === "bullish" ? "صعودی" : pair.impact === "bearish" ? "نزولی" : "خنثی"}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>

          <div className="mt-3 rounded-lg border border-blue-500/20 bg-blue-500/5 p-3">
            <p className="text-xs text-blue-600 dark:text-blue-400">
              <span className="ml-1 font-bold">&#x26A1; چرا مهم است؟</span>
              همبستگی منفی طلا با شاخص دلار (DXY) یکی از قوی‌ترین روابط بازار است.
              تغییر ناگهانی در همبستگی‌ها می‌تواند نشانه تغییر رژیم بازار باشد.
              همبستگی مثبت با VIX نشان‌دهنده نقش طلا به عنوان پناهگاه امن است.
            </p>
          </div>
        </>
      )}
    </div>
  );
}
