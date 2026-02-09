"use client";

import { useState, useEffect } from "react";
import { getSentimentHistory, type SentimentHistoryPoint } from "@/lib/api";

interface SentimentChartProps {
  timeframe: "1h" | "4h" | "24h";
  hours?: number;
  height?: number;
}

function scoreToColor(score: number): string {
  if (score > 60) return "#22c55e"; // green (bullish)
  if (score > 40) return "#f59e0b"; // amber (neutral)
  return "#ef4444"; // red (bearish)
}

export default function SentimentChart({
  timeframe,
  hours = 48,
  height = 140,
}: SentimentChartProps) {
  const [data, setData] = useState<SentimentHistoryPoint[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getSentimentHistory(timeframe, hours)
      .then((res) => {
        if (!cancelled) setData(res.data || []);
      })
      .catch(() => {
        if (!cancelled) setData([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [timeframe, hours]);

  if (loading) {
    return (
      <div
        className="flex items-center justify-center"
        style={{ height }}
      >
        <div className="h-4 w-4 animate-spin rounded-full border-2 border-gold-500 border-t-transparent" />
      </div>
    );
  }

  if (data.length < 2) {
    return (
      <div
        className="flex items-center justify-center text-sm text-gray-400"
        style={{ height }}
      >
        داده کافی برای نمودار نیست
      </div>
    );
  }

  // Chart dimensions
  const width = 300;
  const padTop = 10;
  const padBottom = 22;
  const padLeft = 28;
  const padRight = 8;
  const chartW = width - padLeft - padRight;
  const chartH = height - padTop - padBottom;

  // Data bounds (score is 0-100)
  const minY = 0;
  const maxY = 100;

  // Map data to chart coordinates
  const points = data.map((d, i) => {
    const x = padLeft + (i / (data.length - 1)) * chartW;
    const y = padTop + chartH - ((d.score - minY) / (maxY - minY)) * chartH;
    return { x, y, ...d };
  });

  // Build SVG path
  const linePath = points
    .map((p, i) => `${i === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`)
    .join(" ");

  // Area path (fill under the line)
  const areaPath =
    linePath +
    ` L ${points[points.length - 1].x.toFixed(1)} ${(padTop + chartH).toFixed(1)}` +
    ` L ${points[0].x.toFixed(1)} ${(padTop + chartH).toFixed(1)} Z`;

  // Latest score color for gradient
  const latestScore = data[data.length - 1]?.score ?? 50;
  const lineColor = scoreToColor(latestScore);

  // Y-axis labels
  const yLabels = [0, 25, 50, 75, 100];

  // X-axis time labels (show ~4 labels)
  const xLabelCount = Math.min(4, data.length);
  const xLabels: { x: number; label: string }[] = [];
  for (let i = 0; i < xLabelCount; i++) {
    const idx = Math.round((i / (xLabelCount - 1)) * (data.length - 1));
    const d = data[idx];
    const dt = new Date(d.timestamp);
    const label = dt.toLocaleTimeString("fa-IR", {
      hour: "2-digit",
      minute: "2-digit",
    });
    xLabels.push({ x: points[idx].x, label });
  }

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="w-full"
      style={{ height }}
      preserveAspectRatio="none"
    >
      {/* Grid lines */}
      {yLabels.map((v) => {
        const y = padTop + chartH - ((v - minY) / (maxY - minY)) * chartH;
        return (
          <g key={v}>
            <line
              x1={padLeft}
              y1={y}
              x2={padLeft + chartW}
              y2={y}
              stroke="currentColor"
              className="text-gray-200 dark:text-gray-700"
              strokeWidth="0.5"
              strokeDasharray="3,3"
            />
            <text
              x={padLeft - 4}
              y={y + 3}
              textAnchor="end"
              className="fill-current text-gray-400"
              fontSize="8"
              fontFamily="Vazirmatn, sans-serif"
            >
              {v}
            </text>
          </g>
        );
      })}

      {/* Neutral zone highlight (40-60) */}
      <rect
        x={padLeft}
        y={padTop + chartH - ((60 - minY) / (maxY - minY)) * chartH}
        width={chartW}
        height={((60 - 40) / (maxY - minY)) * chartH}
        fill="currentColor"
        className="text-gray-100 dark:text-gray-800"
        opacity="0.5"
      />

      {/* Area fill */}
      <path d={areaPath} fill={lineColor} opacity="0.12" />

      {/* Line */}
      <path
        d={linePath}
        fill="none"
        stroke={lineColor}
        strokeWidth="2"
        strokeLinejoin="round"
        strokeLinecap="round"
      />

      {/* Data points (last point highlighted) */}
      {points.length > 0 && (
        <circle
          cx={points[points.length - 1].x}
          cy={points[points.length - 1].y}
          r="3.5"
          fill={lineColor}
          stroke="white"
          strokeWidth="1.5"
        />
      )}

      {/* X-axis labels */}
      {xLabels.map((xl, i) => (
        <text
          key={i}
          x={xl.x}
          y={height - 4}
          textAnchor="middle"
          className="fill-current text-gray-400"
          fontSize="7"
          fontFamily="Vazirmatn, sans-serif"
        >
          {xl.label}
        </text>
      ))}
    </svg>
  );
}
