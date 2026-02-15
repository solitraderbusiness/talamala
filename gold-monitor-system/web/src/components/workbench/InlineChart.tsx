"use client";

import {
  ResponsiveContainer,
  LineChart,
  Line,
  BarChart,
  Bar,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from "recharts";
import type { ChartSpec } from "@/hooks/useSSEChat";

const COLORS = ["#F59E0B", "#10B981", "#3B82F6", "#EF4444", "#8B5CF6", "#EC4899"];

const TOOLTIP_STYLE = {
  backgroundColor: "#1F2937",
  border: "1px solid #374151",
  borderRadius: "8px",
  color: "#F3F4F6",
  fontSize: "11px",
};

function formatNumber(val: unknown): string {
  if (typeof val !== "number") return String(val ?? "");
  if (Math.abs(val) >= 1000) return val.toLocaleString("en-US", { maximumFractionDigits: 2 });
  return val.toLocaleString("en-US", { maximumFractionDigits: 4 });
}

interface Props {
  spec: ChartSpec;
}

export default function InlineChart({ spec }: Props) {
  const { chart_type, title_fa, x_key, y_keys, y_labels, data, unit } = spec;

  if (!data || data.length === 0) return null;

  // Determine if we need dual Y-axis (when y_keys have very different scales)
  const needsDualAxis = y_keys.length === 2 && (() => {
    const vals0 = data.map((d) => Number(d[y_keys[0]] ?? 0)).filter((v) => v !== 0);
    const vals1 = data.map((d) => Number(d[y_keys[1]] ?? 0)).filter((v) => v !== 0);
    if (!vals0.length || !vals1.length) return false;
    const avg0 = vals0.reduce((a, b) => a + b, 0) / vals0.length;
    const avg1 = vals1.reduce((a, b) => a + b, 0) / vals1.length;
    return Math.max(avg0, avg1) / Math.min(avg0, avg1) > 10;
  })();

  // Shorten x-axis labels if dates
  const shortLabel = (val: string) => {
    if (!val) return "";
    // "2025-01-15" -> "01/15"
    const m = val.match(/^\d{4}-(\d{2})-(\d{2})$/);
    if (m) return `${m[1]}/${m[2]}`;
    return val;
  };

  const commonProps = {
    data,
    margin: { top: 5, right: 5, left: 5, bottom: 5 },
  };

  const xAxisProps = {
    dataKey: x_key,
    tick: { fontSize: 10, fill: "#9CA3AF" },
    tickFormatter: shortLabel,
    interval: Math.max(0, Math.floor(data.length / 8) - 1),
  };

  const yAxisProps = (idx: number) => ({
    tick: { fontSize: 10, fill: "#9CA3AF" },
    width: 55,
    tickFormatter: (v: number) => formatNumber(v),
    yAxisId: needsDualAxis ? `y${idx}` : undefined,
    orientation: (needsDualAxis && idx === 1 ? "right" : "left") as "left" | "right",
  });

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const tooltipFormatter = (value: any, name: any) => {
    const label = y_labels[name as string] || String(name ?? "");
    return [formatNumber(value ?? 0) + (unit ? ` ${unit}` : ""), label];
  };

  const legendFormatter = (value: string) => y_labels[value] || value;

  const renderChart = () => {
    if (chart_type === "bar") {
      return (
        <BarChart {...commonProps}>
          <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
          <XAxis {...xAxisProps} />
          <YAxis {...yAxisProps(0)} />
          <Tooltip contentStyle={TOOLTIP_STYLE} formatter={tooltipFormatter} />
          {y_keys.length > 1 && <Legend formatter={legendFormatter} />}
          {y_keys.map((key, i) => (
            <Bar key={key} dataKey={key} fill={COLORS[i % COLORS.length]} radius={[2, 2, 0, 0]} />
          ))}
        </BarChart>
      );
    }

    if (chart_type === "area") {
      return (
        <AreaChart {...commonProps}>
          <defs>
            {y_keys.map((key, i) => (
              <linearGradient key={key} id={`grad-${key}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={COLORS[i % COLORS.length]} stopOpacity={0.3} />
                <stop offset="95%" stopColor={COLORS[i % COLORS.length]} stopOpacity={0} />
              </linearGradient>
            ))}
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
          <XAxis {...xAxisProps} />
          {y_keys.map((_, i) => (
            <YAxis key={i} {...yAxisProps(i)} />
          ))}
          <Tooltip contentStyle={TOOLTIP_STYLE} formatter={tooltipFormatter} />
          {y_keys.length > 1 && <Legend formatter={legendFormatter} />}
          {y_keys.map((key, i) => (
            <Area
              key={key}
              type="monotone"
              dataKey={key}
              stroke={COLORS[i % COLORS.length]}
              fill={`url(#grad-${key})`}
              strokeWidth={2}
              yAxisId={needsDualAxis ? `y${i}` : undefined}
              connectNulls
            />
          ))}
        </AreaChart>
      );
    }

    // Default: line
    return (
      <LineChart {...commonProps}>
        <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
        <XAxis {...xAxisProps} />
        {y_keys.map((_, i) => (
          <YAxis key={i} {...yAxisProps(i)} />
        ))}
        <Tooltip contentStyle={TOOLTIP_STYLE} formatter={tooltipFormatter} />
        {y_keys.length > 1 && <Legend formatter={legendFormatter} />}
        {y_keys.map((key, i) => (
          <Line
            key={key}
            type="monotone"
            dataKey={key}
            stroke={COLORS[i % COLORS.length]}
            strokeWidth={2}
            dot={data.length <= 30}
            yAxisId={needsDualAxis ? `y${i}` : undefined}
            connectNulls
          />
        ))}
      </LineChart>
    );
  };

  return (
    <div className="my-3 rounded-xl border border-gray-200 bg-white p-3 dark:border-gray-700 dark:bg-gray-900">
      <h4
        className="mb-2 text-xs font-bold text-gray-700 dark:text-gray-300"
        style={{ direction: "rtl" }}
      >
        {title_fa}
      </h4>
      <div style={{ direction: "ltr" }}>
        <ResponsiveContainer width="100%" height={220}>
          {renderChart()}
        </ResponsiveContainer>
      </div>
    </div>
  );
}
