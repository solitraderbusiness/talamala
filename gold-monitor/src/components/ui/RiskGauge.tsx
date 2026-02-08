'use client';

import { cn } from '@/lib/utils';

interface RiskGaugeProps {
  score: number; // 0-100
}

export default function RiskGauge({ score }: RiskGaugeProps) {
  const getColor = () => {
    if (score >= 70) return 'text-red-500';
    if (score >= 40) return 'text-amber-500';
    return 'text-emerald-500';
  };

  const getLabel = () => {
    if (score >= 70) return 'ریسک بالا';
    if (score >= 40) return 'ریسک متوسط';
    return 'ریسک پایین';
  };

  const getBgColor = () => {
    if (score >= 70) return 'from-red-500 to-red-400';
    if (score >= 40) return 'from-amber-500 to-amber-400';
    return 'from-emerald-500 to-emerald-400';
  };

  return (
    <div className="flex flex-col items-center gap-3">
      {/* Circular gauge */}
      <div className="relative h-32 w-32">
        <svg className="h-full w-full -rotate-90" viewBox="0 0 100 100">
          {/* Background circle */}
          <circle
            cx="50"
            cy="50"
            r="42"
            fill="none"
            stroke="currentColor"
            strokeWidth="8"
            className="text-gray-200 dark:text-gray-700"
          />
          {/* Progress circle */}
          <circle
            cx="50"
            cy="50"
            r="42"
            fill="none"
            stroke="url(#gaugeGradient)"
            strokeWidth="8"
            strokeLinecap="round"
            strokeDasharray={`${score * 2.64} ${264 - score * 2.64}`}
            className="transition-all duration-1000"
          />
          <defs>
            <linearGradient id="gaugeGradient" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" className={cn('transition-colors', score >= 70 ? 'stop-color-red-500' : score >= 40 ? 'stop-color-amber-500' : 'stop-color-emerald-500')} style={{ stopColor: score >= 70 ? '#ef4444' : score >= 40 ? '#f59e0b' : '#10b981' }} />
              <stop offset="100%" className="transition-colors" style={{ stopColor: score >= 70 ? '#f87171' : score >= 40 ? '#fbbf24' : '#34d399' }} />
            </linearGradient>
          </defs>
        </svg>
        {/* Score text */}
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className={cn('text-3xl font-bold', getColor())}>{score}</span>
          <span className="text-[10px] text-gray-400 dark:text-gray-500">از ۱۰۰</span>
        </div>
      </div>
      <span className={cn('text-sm font-medium', getColor())}>{getLabel()}</span>
      <p className="text-center text-[11px] leading-4 text-gray-400 dark:text-gray-500">
        این شاخص بر اساس تعداد و شدت هشدارهای فعال محاسبه شده و صرفاً یک معیار داخلی است.
      </p>
    </div>
  );
}
