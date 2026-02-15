"use client";

import { useState } from "react";
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import type { MoneyFlowResponse } from "@/lib/api";
import DataPending from "./DataPending";
import SkeletonCard from "./SkeletonCard";
import InfoTip from "@/components/InfoTip";

const CHART_TOOLTIP_STYLE = {
  backgroundColor: "#1F2937",
  border: "1px solid #374151",
  borderRadius: "8px",
  color: "#F3F4F6",
  fontSize: "12px",
};

// Signal color/style mapping
const SIGNAL_STYLES: Record<string, { bg: string; text: string; border: string }> = {
  CONFIRMING:        { bg: "bg-emerald-500/10", text: "text-emerald-500", border: "border-emerald-500/30" },
  CONFIRMING_BEARISH:{ bg: "bg-red-500/10",     text: "text-red-500",     border: "border-red-500/30" },
  DIVERGING:         { bg: "bg-amber-500/10",    text: "text-amber-500",   border: "border-amber-500/30" },
  EXTREME_RISK:      { bg: "bg-purple-500/10",   text: "text-purple-500",  border: "border-purple-500/30" },
  NEUTRAL:           { bg: "bg-gray-500/10",     text: "text-gray-400",    border: "border-gray-500/30" },
};

function ZScoreBadge({ value }: { value: number | null }) {
  if (value == null) return <span className="text-xs text-gray-500">-</span>;
  const color = value > 0.5 ? "text-emerald-500" : value < -0.5 ? "text-red-500" : "text-gray-400";
  const bg = value > 0.5 ? "bg-emerald-500/10" : value < -0.5 ? "bg-red-500/10" : "bg-gray-500/10";
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-bold ${bg} ${color}`} dir="ltr">
      {value > 0 ? "+" : ""}{value.toFixed(2)}σ
    </span>
  );
}

function PercentileBar({ value, label }: { value: number | null; label: string }) {
  if (value == null) return <span className="text-xs text-gray-500">-</span>;
  const color = value > 60 ? "bg-emerald-500" : value < 40 ? "bg-red-500" : "bg-gray-400";
  return (
    <div className="flex flex-col gap-0.5">
      <div className="flex items-center justify-between">
        <span className="text-[10px] text-gray-500">{label}</span>
        <span className="text-[10px] font-bold text-gray-300" dir="ltr">{value.toFixed(0)}%</span>
      </div>
      <div className="h-1.5 w-full rounded-full bg-gray-700">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${Math.min(100, Math.max(0, value))}%` }} />
      </div>
    </div>
  );
}

interface Props {
  data: MoneyFlowResponse | null;
  loading: boolean;
}

export default function MoneyFlowAnalysis({ data, loading }: Props) {
  const [showReasons, setShowReasons] = useState(false);

  const hasEtf = data && Object.keys(data.etf_holdings).length > 0;
  const hasCot = data && data.cot_positions.length > 0;
  const hasData = hasEtf || hasCot;
  const derived = data?.derived;
  const meta = data?.meta;

  // Compute ETF data with change info
  const etfData = hasEtf
    ? data!.etf_holdings["GLD"] || data!.etf_holdings[Object.keys(data!.etf_holdings)[0]]
    : [];
  const etfLatest = etfData.length > 0 ? etfData[etfData.length - 1] : null;
  const etfFirst = etfData.length > 0 ? etfData[0] : null;
  const etfChange = etfLatest && etfFirst
    ? etfLatest.total_tonnes - etfFirst.total_tonnes
    : null;

  // Compute COT summary
  const cotData = hasCot ? data!.cot_positions : [];
  const cotLatest = cotData.length > 0 ? cotData[cotData.length - 1] : null;
  const cotPrev = cotData.length > 1 ? cotData[cotData.length - 2] : null;
  const cotChange = cotLatest?.non_commercial_net != null && cotPrev?.non_commercial_net != null
    ? cotLatest.non_commercial_net - cotPrev.non_commercial_net
    : null;

  return (
    <div className="flex flex-col">
      <div className="mb-4 flex items-center gap-2">
        <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100">
          &#x1F4B0; جریان پول نهادی
        </h2>
        <InfoTip term="etf_flow" />
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
          {/* Combined Signal Badge */}
          {derived?.combined_signal && (
            <div
              className={`mb-4 rounded-lg border p-3 ${
                SIGNAL_STYLES[derived.combined_signal.signal]?.bg ?? "bg-gray-500/10"
              } ${
                SIGNAL_STYLES[derived.combined_signal.signal]?.border ?? "border-gray-500/30"
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span
                    className={`text-sm font-bold ${
                      SIGNAL_STYLES[derived.combined_signal.signal]?.text ?? "text-gray-400"
                    }`}
                  >
                    {derived.combined_signal.label_fa}
                  </span>
                  <span className="rounded bg-gray-800 px-1.5 py-0.5 text-[10px] text-gray-400" dir="ltr">
                    {derived.combined_signal.signal}
                  </span>
                  <span className="text-[10px] text-gray-500">
                    اطمینان: {derived.combined_signal.confidence}%
                  </span>
                </div>
                {derived.combined_signal.reasons.length > 0 && (
                  <button
                    onClick={() => setShowReasons(!showReasons)}
                    className="text-[10px] text-gray-400 hover:text-gray-200 transition-colors"
                  >
                    {showReasons ? "بستن" : "جزئیات"}
                  </button>
                )}
              </div>
              {showReasons && derived.combined_signal.reasons.length > 0 && (
                <ul className="mt-2 space-y-1 border-t border-gray-700 pt-2">
                  {derived.combined_signal.reasons.map((reason, i) => (
                    <li key={i} className="text-[11px] text-gray-400">
                      {reason}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {/* Derived Stats Row */}
          {derived && (
            <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
              {/* GLD Z-Score */}
              <div className="card !p-3">
                <div className="mb-1 text-[10px] text-gray-500">z-score تغییرات GLD (۹۰ روزه)</div>
                <ZScoreBadge value={derived.etf.zscore_90d} />
              </div>

              {/* GLD Percentile */}
              <div className="card !p-3">
                <PercentileBar value={derived.etf.percentile_2yr} label="صدک GLD (۲ ساله)" />
              </div>

              {/* COT WoW % of OI */}
              <div className="card !p-3">
                <div className="mb-1 text-[10px] text-gray-500">تغییر هفتگی COT (% بهره باز)</div>
                {derived.cot.wow_change_pct_of_oi != null ? (
                  <span
                    className={`text-xs font-bold ${
                      derived.cot.wow_change_pct_of_oi > 0 ? "text-emerald-500" : derived.cot.wow_change_pct_of_oi < 0 ? "text-red-500" : "text-gray-400"
                    }`}
                    dir="ltr"
                  >
                    {derived.cot.wow_change_pct_of_oi > 0 ? "+" : ""}
                    {derived.cot.wow_change_pct_of_oi.toFixed(2)}%
                  </span>
                ) : (
                  <span className="text-xs text-gray-500">-</span>
                )}
              </div>

              {/* COT Percentile */}
              <div className="card !p-3">
                <PercentileBar value={derived.cot.percentile_3yr} label="صدک COT (۳ ساله)" />
              </div>
            </div>
          )}

          <div className="grid gap-4 md:grid-cols-2">
            {/* ETF Holdings Chart */}
            {hasEtf && (
              <div className="card">
                <div className="mb-3 flex items-center justify-between">
                  <h3 className="text-sm font-bold text-gray-900 dark:text-gray-100">
                    موجودی صندوق‌های طلا (تن)
                    <InfoTip term="etf_holdings_tonnes" />
                  </h3>
                  {etfLatest && (
                    <div className="flex items-center gap-2">
                      <span className="text-lg font-bold text-gray-900 dark:text-gray-100" dir="ltr">
                        {etfLatest.total_tonnes.toFixed(1)}
                      </span>
                      {etfChange != null && (
                        <span
                          className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${
                            etfChange >= 0
                              ? "bg-emerald-500/10 text-emerald-500"
                              : "bg-red-500/10 text-red-500"
                          }`}
                          dir="ltr"
                        >
                          {etfChange >= 0 ? "+" : ""}
                          {etfChange.toFixed(1)}
                        </span>
                      )}
                    </div>
                  )}
                </div>
                <div className="h-56" dir="ltr">
                  <ResponsiveContainer width="100%" height="100%" minWidth={0}>
                    <AreaChart data={etfData}>
                      <defs>
                        <linearGradient id="etfGradient" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#F59E0B" stopOpacity={0.3} />
                          <stop offset="95%" stopColor="#F59E0B" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
                      <XAxis
                        dataKey="date"
                        tick={{ fontSize: 10, fill: "#9CA3AF" }}
                        tickFormatter={(val: string) => {
                          const d = new Date(val);
                          return `${d.getMonth() + 1}/${d.getDate()}`;
                        }}
                      />
                      <YAxis
                        tick={{ fontSize: 10, fill: "#9CA3AF" }}
                        domain={["dataMin - 5", "dataMax + 5"]}
                        tickFormatter={(val: number) => val.toFixed(0)}
                      />
                      <Tooltip contentStyle={CHART_TOOLTIP_STYLE}
                        formatter={(value) => [`${Number(value).toFixed(1)} تن`, "موجودی"]}
                      />
                      <Area
                        type="monotone"
                        dataKey="total_tonnes"
                        stroke="#F59E0B"
                        strokeWidth={2}
                        fill="url(#etfGradient)"
                        dot={false}
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}

            {/* COT Net Position Chart */}
            {hasCot && (
              <div className="card">
                <div className="mb-3 flex items-center justify-between">
                  <h3 className="text-sm font-bold text-gray-900 dark:text-gray-100">
                    موقعیت خالص سفته‌بازان (COT)
                    <InfoTip term="cot_net_position" />
                  </h3>
                  {cotLatest && cotLatest.non_commercial_net != null && (
                    <div className="flex items-center gap-2">
                      <span className="text-lg font-bold text-gray-900 dark:text-gray-100" dir="ltr">
                        {Number(cotLatest.non_commercial_net).toLocaleString()}
                      </span>
                      {cotChange != null && (
                        <span
                          className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${
                            cotChange >= 0
                              ? "bg-emerald-500/10 text-emerald-500"
                              : "bg-red-500/10 text-red-500"
                          }`}
                          dir="ltr"
                        >
                          {cotChange >= 0 ? "+" : ""}
                          {Number(cotChange).toLocaleString()}
                        </span>
                      )}
                    </div>
                  )}
                </div>
                <div className="h-56" dir="ltr">
                  <ResponsiveContainer width="100%" height="100%" minWidth={0}>
                    <BarChart data={cotData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
                      <XAxis
                        dataKey="date"
                        tick={{ fontSize: 10, fill: "#9CA3AF" }}
                        tickFormatter={(val: string) => {
                          const d = new Date(val);
                          const months = ["ژانویه", "فوریه", "مارس", "آوریل", "مه", "ژوئن", "ژوئیه", "اوت", "سپتامبر", "اکتبر", "نوامبر", "دسامبر"];
                          return `${d.getDate()} ${months[d.getMonth()]}`;
                        }}
                      />
                      <YAxis
                        tick={{ fontSize: 10, fill: "#9CA3AF" }}
                        tickFormatter={(val: number) => `${(val / 1000).toFixed(0)}K`}
                      />
                      <Tooltip
                        contentStyle={CHART_TOOLTIP_STYLE}
                        labelFormatter={(label) => {
                          const d = new Date(String(label));
                          return d.toLocaleDateString("fa-IR");
                        }}
                        formatter={(value) => [`${Number(value).toLocaleString()} قرارداد`, "خالص"]}
                      />
                      <ReferenceLine y={0} stroke="#6B7280" strokeDasharray="3 3" />
                      <Bar dataKey="non_commercial_net" radius={[4, 4, 0, 0]}>
                        {cotData.map((entry, index) => (
                          <Cell
                            key={`cell-${index}`}
                            fill={(entry.non_commercial_net ?? 0) >= 0 ? "#10B981" : "#EF4444"}
                            fillOpacity={index === cotData.length - 1 ? 1 : 0.6}
                          />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                {cotLatest && cotLatest.non_commercial_net != null && (
                  <div className="mt-2 text-center text-[11px] text-gray-500 dark:text-gray-400">
                    {cotLatest.non_commercial_net > 0
                      ? "مثبت = سفته‌بازان بیشتر خریدار (صعودی)"
                      : cotLatest.non_commercial_net < 0
                      ? "منفی = سفته‌بازان بیشتر فروشنده (نزولی)"
                      : "خنثی"}
                    {" · "}
                    گزارش هفتگی CFTC
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Source Attribution */}
          {meta && (
            <div className="mt-3 flex flex-wrap items-center gap-3 text-[10px] text-gray-500">
              {meta.etf_source?.url && (
                <a
                  href={meta.etf_source.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:text-amber-400 transition-colors"
                  dir="ltr"
                >
                  ETF: {meta.etf_source.name}
                  {meta.etf_source.last_date && ` (${meta.etf_source.last_date})`}
                </a>
              )}
              {meta.cot_source?.url && (
                <a
                  href={meta.cot_source.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:text-amber-400 transition-colors"
                  dir="ltr"
                >
                  COT: {meta.cot_source.name}
                  {meta.cot_source.last_date && ` (${meta.cot_source.last_date})`}
                </a>
              )}
            </div>
          )}

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
