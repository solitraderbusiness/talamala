"use client";

import DataPending from "./DataPending";
import InfoTip from "@/components/InfoTip";

/* ── Types ── */

interface RegimeData {
  ts: string;
  liquidity_stress_index: number | null;
  usd_pressure_index: number | null;
  real_yield_pressure_index: number | null;
  p_expansion: number | null;
  p_tightening: number | null;
  p_stress: number | null;
  p_recovery: number | null;
  smoothed_p_expansion: number | null;
  smoothed_p_tightening: number | null;
  smoothed_p_stress: number | null;
  smoothed_p_recovery: number | null;
  chosen_regime: string | null;
  real_yield_source: string | null;
  credit_proxy_source: string | null;
  status?: string;
}

interface Props {
  data: RegimeData | null;
  loading: boolean;
}

/* ── Constants ── */

const REGIME_INFO: Record<
  string,
  { label: string; en: string; color: string; bg: string; border: string; description: string }
> = {
  expansion: {
    label: "انبساطی",
    en: "EXPANSION",
    color: "text-emerald-500",
    bg: "bg-emerald-500",
    border: "border-emerald-500/30",
    description:
      "در رژیم انبساطی، نرخ بهره واقعی پایین و دلار ضعیف، محیط مساعدی برای طلا ایجاد می‌کند. انتظار رشد قیمت طلا وجود دارد.",
  },
  tightening: {
    label: "انقباضی",
    en: "TIGHTENING",
    color: "text-amber-500",
    bg: "bg-amber-500",
    border: "border-amber-500/30",
    description:
      "در رژیم انقباضی، نرخ بهره واقعی بالا و دلار قوی فشار نزولی بر طلا وارد می‌کند. معمولا رشد طلا محدود یا منفی است.",
  },
  stress: {
    label: "بحرانی",
    en: "STRESS",
    color: "text-red-500",
    bg: "bg-red-500",
    border: "border-red-500/30",
    description:
      "در رژیم بحرانی، استرس بازار بالا (VIX بالا، اسپرد اعتباری گسترده) تقاضای پناهگاه امن را افزایش می‌دهد. طلا معمولا رشد تند دارد.",
  },
  recovery: {
    label: "بازیابی",
    en: "RECOVERY",
    color: "text-blue-500",
    bg: "bg-blue-500",
    border: "border-blue-500/30",
    description:
      "در رژیم بازیابی، استرس بازار کاهش یافته ولی هنوز ناپایدار است. طلا ممکن است کمی تثبیت یا اصلاح شود.",
  },
};

const BAR_COLORS: Record<string, string> = {
  expansion: "bg-emerald-500",
  tightening: "bg-amber-500",
  stress: "bg-red-500",
  recovery: "bg-blue-500",
};

const INDEX_LABELS: Record<string, string> = {
  lsi: "فشار نقدینگی",
  usdx: "فشار دلار",
  rypi: "فشار بهره واقعی",
};

/* ── Helpers ── */

function pct(v: number | null): string {
  if (v == null) return "—";
  return `${Math.round(v * 100)}%`;
}

function fmtIndex(v: number | null): string {
  if (v == null) return "—";
  return v.toFixed(2);
}

/** Map -3..+3 to 0..100% for gauge bar positioning */
function indexPct(v: number | null): number {
  if (v == null) return 50;
  return Math.max(0, Math.min(100, ((v + 3) / 6) * 100));
}

/* ── Component ── */

export default function RegimeMonitor({ data, loading }: Props) {
  // Loading skeleton
  if (loading) {
    return (
      <div className="card animate-pulse space-y-4 p-6">
        <div className="h-6 w-40 rounded bg-gray-200 dark:bg-gray-700" />
        <div className="h-20 rounded bg-gray-200 dark:bg-gray-700" />
        <div className="h-16 rounded bg-gray-200 dark:bg-gray-700" />
      </div>
    );
  }

  // No data / pending
  if (!data || data.status === "pending" || !data.chosen_regime) {
    return <DataPending title="رژیم کلان" />;
  }

  const regime = data.chosen_regime;
  const info = REGIME_INFO[regime] || REGIME_INFO.expansion;

  const probabilities = [
    { key: "expansion", label: "انبساطی", value: data.smoothed_p_expansion },
    { key: "tightening", label: "انقباضی", value: data.smoothed_p_tightening },
    { key: "stress", label: "بحرانی", value: data.smoothed_p_stress },
    { key: "recovery", label: "بازیابی", value: data.smoothed_p_recovery },
  ];

  const dominantProb = probabilities.find((p) => p.key === regime)?.value ?? 0;

  const indices = [
    { key: "lsi", value: data.liquidity_stress_index },
    { key: "usdx", value: data.usd_pressure_index },
    { key: "rypi", value: data.real_yield_pressure_index },
  ];

  return (
    <div className={`card overflow-hidden border ${info.border}`}>
      {/* ── Header ── */}
      <div className="border-b border-gray-100 bg-gray-50/50 px-6 py-4 dark:border-gray-800 dark:bg-gray-900/50">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className="text-lg font-bold text-gray-900 dark:text-gray-100">
              رژیم کلان:{" "}
              <span className={info.color}>{info.label}</span>
              <InfoTip term={`regime_${regime}`} />
            </h3>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Macro Regime: {info.en}
            </p>
          </div>
          <div className="text-left">
            <span className={`text-3xl font-black ${info.color}`}>
              {pct(dominantProb)}
            </span>
            <p className="text-xs text-gray-400">احتمال</p>
          </div>
        </div>
      </div>

      <div className="space-y-5 p-6">
        {/* ── Probability Bars ── */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {probabilities.map((p) => {
            const isActive = p.key === regime;
            const w = Math.round((p.value ?? 0) * 100);
            return (
              <div
                key={p.key}
                className={`rounded-lg border p-3 transition-colors ${
                  isActive
                    ? `${REGIME_INFO[p.key]?.border || ""} bg-gray-50 dark:bg-gray-800/50`
                    : "border-gray-100 dark:border-gray-800"
                }`}
              >
                <div className="mb-1 flex items-center justify-between">
                  <span className="text-xs font-medium text-gray-600 dark:text-gray-300">
                    {p.label}
                  </span>
                  <span
                    className={`text-sm font-bold ${
                      isActive
                        ? REGIME_INFO[p.key]?.color || "text-gray-500"
                        : "text-gray-500 dark:text-gray-400"
                    }`}
                  >
                    {pct(p.value)}
                  </span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${
                      BAR_COLORS[p.key] || "bg-gray-400"
                    } ${isActive ? "opacity-100" : "opacity-40"}`}
                    style={{ width: `${w}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>

        {/* ── Index Gauges ── */}
        <div className="space-y-3">
          <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
            شاخص‌های ورودی
            <InfoTip term="regime" />
          </h4>
          {indices.map((idx) => (
            <div key={idx.key} className="flex items-center gap-3">
              <span className="w-32 text-xs text-gray-500 dark:text-gray-400">
                {INDEX_LABELS[idx.key]}
                <InfoTip term={idx.key} />
              </span>
              <div className="relative flex-1">
                <div className="h-3 rounded-full bg-gray-200 dark:bg-gray-700">
                  {/* Center marker at 0 */}
                  <div className="absolute top-0 left-1/2 h-3 w-px bg-gray-400 dark:bg-gray-500" />
                  {/* Value marker */}
                  <div
                    className={`absolute top-0 h-3 w-2 rounded-full ${
                      (idx.value ?? 0) > 0 ? "bg-red-500" : "bg-emerald-500"
                    }`}
                    style={{
                      left: `calc(${indexPct(idx.value)}% - 4px)`,
                    }}
                  />
                </div>
              </div>
              <span className="w-12 text-left text-xs font-mono text-gray-600 dark:text-gray-300">
                {fmtIndex(idx.value)}
              </span>
            </div>
          ))}
          <div className="flex justify-between text-[10px] text-gray-400">
            <span>-3</span>
            <span>0</span>
            <span>+3</span>
          </div>
        </div>

        {/* ── Info Box ── */}
        <div className={`rounded-lg border p-3 ${info.border} bg-gray-50/50 dark:bg-gray-800/30`}>
          <p className="text-xs leading-relaxed text-gray-600 dark:text-gray-300">
            {info.description}
          </p>
        </div>
      </div>
    </div>
  );
}
