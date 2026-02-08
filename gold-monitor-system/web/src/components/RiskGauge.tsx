"use client";

interface RiskGaugeProps {
  score: number; // 0-100
  size?: number;
}

export default function RiskGauge({ score, size = 160 }: RiskGaugeProps) {
  const clampedScore = Math.max(0, Math.min(100, score));
  const radius = (size - 20) / 2;
  const circumference = Math.PI * radius; // half circle
  const offset = circumference - (clampedScore / 100) * circumference;

  let color = "#22c55e"; // green
  if (clampedScore > 70) color = "#ef4444"; // red
  else if (clampedScore > 40) color = "#f59e0b"; // amber

  let label = "کم";
  if (clampedScore > 70) label = "بالا";
  else if (clampedScore > 40) label = "متوسط";

  return (
    <div className="flex flex-col items-center">
      <svg
        width={size}
        height={size / 2 + 20}
        viewBox={`0 0 ${size} ${size / 2 + 20}`}
      >
        {/* Background arc */}
        <path
          d={`M 10 ${size / 2 + 10} A ${radius} ${radius} 0 0 1 ${size - 10} ${size / 2 + 10}`}
          fill="none"
          stroke="currentColor"
          className="text-gray-200 dark:text-gray-700"
          strokeWidth="10"
          strokeLinecap="round"
        />
        {/* Score arc */}
        <path
          d={`M 10 ${size / 2 + 10} A ${radius} ${radius} 0 0 1 ${size - 10} ${size / 2 + 10}`}
          fill="none"
          stroke={color}
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          style={{ transition: "stroke-dashoffset 0.5s ease" }}
        />
        {/* Score text */}
        <text
          x={size / 2}
          y={size / 2}
          textAnchor="middle"
          className="fill-current text-gray-900 dark:text-gray-100"
          fontSize="28"
          fontWeight="bold"
          fontFamily="Vazirmatn, sans-serif"
        >
          {clampedScore}
        </text>
      </svg>
      <span className="mt-1 text-sm font-medium text-gray-600 dark:text-gray-400">
        ریسک: {label}
      </span>
    </div>
  );
}
