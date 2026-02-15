"use client";

import type { ShanghaiPremiumResponse } from "@/lib/api";
import DataPending from "./DataPending";
import SkeletonCard from "./SkeletonCard";
import InfoTip from "@/components/InfoTip";

interface Props {
  data: ShanghaiPremiumResponse | null;
  loading: boolean;
}

export default function ShanghaiPremium({ data, loading }: Props) {
  return (
    <div>
      <div className="mb-4 flex items-center gap-2">
        <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100">
          &#x1F1E8;&#x1F1F3; حق بیمه شانگهای
        </h2>
        <InfoTip term="shanghai_premium" />
      </div>

      {loading ? (
        <SkeletonCard />
      ) : !data || data.status === "pending" ? (
        <DataPending
          title="به زودی"
          message={data?.message_fa || "داده‌های بورس طلای شانگهای (SGE) به زودی اضافه خواهند شد."}
        />
      ) : (
        <div className="card">
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="text-center">
              <p className="text-xs text-gray-500 dark:text-gray-400">حق بیمه (دلار)</p>
              <p className="mt-1 text-2xl font-bold text-gray-900 dark:text-gray-100" dir="ltr">
                ${data.premium_usd?.toFixed(2) || "---"}
              </p>
            </div>
            <div className="text-center">
              <p className="text-xs text-gray-500 dark:text-gray-400">حق بیمه (درصد)</p>
              <p className="mt-1 text-2xl font-bold text-gray-900 dark:text-gray-100" dir="ltr">
                {data.premium_pct != null ? `${data.premium_pct.toFixed(2)}%` : "---"}
              </p>
            </div>
          </div>

          <div className="mt-4 rounded-lg border border-blue-500/20 bg-blue-500/5 p-3">
            <p className="text-xs text-blue-600 dark:text-blue-400">
              <span className="ml-1 font-bold">&#x26A1; چرا مهم است؟</span>
              حق بیمه شانگهای (SGE Premium) نشان‌دهنده تقاضای فیزیکی طلا در چین است.
              حق بیمه بالا (بیش از $30/اونس) نشان‌دهنده تقاضای قوی فیزیکی و حمایت از قیمت جهانی است.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
