"use client";

import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { MoneyFlowResponse } from "@/lib/api";
import DataPending from "./DataPending";
import SkeletonCard from "./SkeletonCard";

const CHART_TOOLTIP_STYLE = {
  backgroundColor: "#1F2937",
  border: "1px solid #374151",
  borderRadius: "8px",
  color: "#F3F4F6",
  fontSize: "12px",
};

interface Props {
  data: MoneyFlowResponse | null;
  loading: boolean;
}

export default function MoneyFlowAnalysis({ data, loading }: Props) {
  const hasEtf = data && Object.keys(data.etf_holdings).length > 0;
  const hasCot = data && data.cot_positions.length > 0;
  const hasData = hasEtf || hasCot;

  return (
    <div>
      <div className="mb-4 flex items-center gap-2">
        <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100">
          &#x1F4B0; جریان پول نهادی
        </h2>
      </div>

      {loading ? (
        <div className="grid gap-4 md:grid-cols-2">
          <SkeletonCard className="h-72" />
          <SkeletonCard className="h-72" />
        </div>
      ) : !hasData ? (
        <DataPending message="داده‌های جریان پول (ETF و COT) پس از اجرای ورکر تحلیل بنیادی نمایش داده خواهند شد." />
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-2">
            {/* ETF Holdings Chart */}
            {hasEtf && (
              <div className="card">
                <h3 className="mb-3 text-sm font-bold text-gray-900 dark:text-gray-100">
                  موجودی صندوق‌های طلا (تن)
                </h3>
                <div className="h-56" dir="ltr">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={data!.etf_holdings["GLD"] || data!.etf_holdings[Object.keys(data!.etf_holdings)[0]]}>
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
                      <Tooltip contentStyle={CHART_TOOLTIP_STYLE}
                        formatter={(value) => [`${Number(value).toFixed(1)} تن`, "موجودی"]}
                      />
                      <Line
                        type="monotone"
                        dataKey="total_tonnes"
                        stroke="#F59E0B"
                        strokeWidth={2}
                        dot={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}

            {/* COT Net Position Chart */}
            {hasCot && (
              <div className="card">
                <h3 className="mb-3 text-sm font-bold text-gray-900 dark:text-gray-100">
                  موقعیت خالص سفته‌بازان (COT)
                </h3>
                <div className="h-56" dir="ltr">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={data!.cot_positions}>
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
                      <Tooltip contentStyle={CHART_TOOLTIP_STYLE}
                        formatter={(value) => [`${Number(value).toLocaleString()}`, "خالص"]}
                      />
                      <Bar
                        dataKey="non_commercial_net"
                        fill="#F59E0B"
                        radius={[2, 2, 0, 0]}
                      />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}
          </div>

          <div className="mt-3 rounded-lg border border-blue-500/20 bg-blue-500/5 p-3">
            <p className="text-xs text-blue-600 dark:text-blue-400">
              <span className="ml-1 font-bold">&#x26A1; چرا مهم است؟</span>
              افزایش موجودی ETFهای طلا (مانند GLD و IAU) نشان‌دهنده تقاضای نهادی است.
              موقعیت خالص مثبت سفته‌بازان در COT نشانه احساسات صعودی بازار آتی طلاست.
            </p>
          </div>
        </>
      )}
    </div>
  );
}
