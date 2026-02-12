"use client";

import { cn } from "@/lib/utils";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { RealRatesResponse } from "@/lib/api";
import DataPending from "./DataPending";
import SkeletonCard from "./SkeletonCard";

const CHART_TOOLTIP_STYLE = {
  backgroundColor: "#1F2937",
  border: "1px solid #374151",
  borderRadius: "8px",
  color: "#F3F4F6",
  fontSize: "12px",
};

const LINE_COLORS = ["#F59E0B", "#10B981", "#3B82F6", "#EF4444", "#8B5CF6"];

interface Props {
  data: RealRatesResponse | null;
  loading: boolean;
}

export default function RealRatesSection({ data, loading }: Props) {
  const hasData = data && data.indicators.some((i) => i.latest_value != null);

  return (
    <div>
      <div className="mb-4 flex items-center gap-2">
        <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100">
          &#x1F3E6; نرخ‌های بهره و تورم
        </h2>
      </div>

      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3, 4, 5].map((i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      ) : !hasData ? (
        <DataPending message="داده‌های FRED (نرخ بهره، تورم) پس از اجرای ورکر تحلیل بنیادی نمایش داده خواهند شد." />
      ) : (
        <>
          {/* Indicator cards */}
          <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
            {data!.indicators.map((ind) => {
              const hasValue = ind.latest_value != null;
              return (
                <div key={ind.series_id} className="card py-3">
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    {ind.label_fa}
                  </p>
                  <p
                    className={cn(
                      "mt-1 text-xl font-bold",
                      hasValue ? "text-gray-900 dark:text-gray-100" : "text-gray-400"
                    )}
                    dir="ltr"
                  >
                    {hasValue ? `${ind.latest_value!.toFixed(2)}%` : "---"}
                  </p>
                  {ind.latest_date && (
                    <p className="mt-0.5 text-[11px] text-gray-400" dir="ltr">
                      {ind.latest_date}
                    </p>
                  )}
                </div>
              );
            })}
          </div>

          {/* History chart — show indicators that have history */}
          {(() => {
            const withHistory = data!.indicators.filter((i) => i.history.length > 3);
            if (withHistory.length === 0) return null;

            // Merge histories into a single chart dataset
            const dateMap = new Map<string, Record<string, number>>();
            for (const ind of withHistory) {
              for (const pt of ind.history) {
                const existing = dateMap.get(pt.date) || {};
                existing[ind.series_id] = pt.value;
                dateMap.set(pt.date, existing);
              }
            }
            const chartData = Array.from(dateMap.entries())
              .sort(([a], [b]) => a.localeCompare(b))
              .map(([dt, vals]) => ({ date: dt, ...vals }));

            return (
              <div className="card">
                <h3 className="mb-3 text-sm font-bold text-gray-900 dark:text-gray-100">
                  روند تاریخی ({data!.period_days} روز)
                </h3>
                <div className="h-64" dir="ltr">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={chartData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
                      <XAxis
                        dataKey="date"
                        tick={{ fontSize: 10, fill: "#9CA3AF" }}
                        tickFormatter={(val: string) => {
                          const d = new Date(val);
                          return `${d.getMonth() + 1}/${d.getDate()}`;
                        }}
                      />
                      <YAxis tick={{ fontSize: 10, fill: "#9CA3AF" }} />
                      <Tooltip contentStyle={CHART_TOOLTIP_STYLE} />
                      {withHistory.map((ind, idx) => (
                        <Line
                          key={ind.series_id}
                          type="monotone"
                          dataKey={ind.series_id}
                          name={ind.label_fa}
                          stroke={LINE_COLORS[idx % LINE_COLORS.length]}
                          strokeWidth={2}
                          dot={false}
                        />
                      ))}
                    </LineChart>
                  </ResponsiveContainer>
                </div>
                {/* Legend */}
                <div className="mt-3 flex flex-wrap gap-3">
                  {withHistory.map((ind, idx) => (
                    <div key={ind.series_id} className="flex items-center gap-1.5 text-[11px] text-gray-500 dark:text-gray-400">
                      <span
                        className="inline-block h-2 w-4 rounded-full"
                        style={{ backgroundColor: LINE_COLORS[idx % LINE_COLORS.length] }}
                      />
                      {ind.label_fa}
                    </div>
                  ))}
                </div>
              </div>
            );
          })()}

          <div className="mt-3 rounded-lg border border-blue-500/20 bg-blue-500/5 p-3">
            <p className="text-xs text-blue-600 dark:text-blue-400">
              <span className="ml-1 font-bold">&#x26A1; چرا مهم است؟</span>
              نرخ بهره واقعی (DFII10) مهم‌ترین عامل تعیین‌کننده قیمت طلاست.
              وقتی نرخ بهره واقعی منفی یا کاهشی باشد، هزینه فرصت نگهداری طلا کاهش یافته و قیمت طلا افزایش می‌یابد.
              انتظارات تورمی (T10YIE) بالا نیز به نفع طلاست.
            </p>
          </div>
        </>
      )}
    </div>
  );
}
