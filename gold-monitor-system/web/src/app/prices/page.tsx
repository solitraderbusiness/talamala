"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import Link from "next/link";
import { getAllPrices, type AllPriceItem, type AllPricesResponse } from "@/lib/api";

const REFRESH_INTERVAL_MS = 60_000;

type Category = "gold" | "currency" | "cryptocurrency";

const CATEGORY_META: Record<Category, { label: string; icon: string }> = {
  gold: { label: "طلا و سکه", icon: "🪙" },
  currency: { label: "ارز", icon: "💵" },
  cryptocurrency: { label: "رمزارز", icon: "₿" },
};

const CATEGORY_ORDER: Category[] = ["gold", "currency", "cryptocurrency"];

function formatPrice(price: number, unit: string): string {
  if (unit === "دلار") {
    // Crypto or gold ounce — show with appropriate decimals
    if (price < 0.01) return price.toFixed(8);
    if (price < 1) return price.toFixed(4);
    if (price < 100) return price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    return price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  // Toman
  return price.toLocaleString("en-US", { maximumFractionDigits: 0 });
}

function PriceCard({ item }: { item: AllPriceItem }) {
  const isUp = item.direction === "up";
  const isDown = item.direction === "down";
  const changeColor = isUp
    ? "text-green-500"
    : isDown
      ? "text-red-500"
      : "text-gray-400";

  return (
    <div className="card flex items-center justify-between gap-3 py-3 px-4">
      <div className="flex items-center gap-3 min-w-0">
        {item.icon_url && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={item.icon_url}
            alt={item.name}
            className="h-7 w-7 flex-shrink-0 rounded-full"
          />
        )}
        <div className="min-w-0">
          <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
            {item.name}
          </p>
          <p className="text-xs text-gray-400 truncate" dir="ltr">
            {item.symbol}
          </p>
        </div>
      </div>

      <div className="text-left flex-shrink-0">
        <p className="text-sm font-bold text-gray-900 dark:text-gray-100" dir="ltr">
          {formatPrice(item.price, item.unit)}
        </p>
        <div className="flex items-center justify-end gap-1.5">
          <span className="text-[11px] text-gray-400">{item.unit}</span>
          {item.change_percent !== undefined && (
            <span className={`text-xs font-medium ${changeColor}`} dir="ltr">
              {item.change_percent > 0 ? "+" : ""}
              {item.change_percent.toFixed(2)}%
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

export default function PricesPage() {
  const [data, setData] = useState<AllPricesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeCategory, setActiveCategory] = useState<Category>("gold");
  const [search, setSearch] = useState("");
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchData = useCallback(async (showSpinner = false) => {
    if (showSpinner) setLoading(true);
    try {
      const result = await getAllPrices();
      setData(result);
      setLastUpdated(new Date());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "خطا در بارگذاری قیمت‌ها");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData(true);
  }, [fetchData]);

  // Auto-refresh every 60s
  useEffect(() => {
    timerRef.current = setInterval(() => fetchData(false), REFRESH_INTERVAL_MS);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [fetchData]);

  const items: AllPriceItem[] = data?.[activeCategory] || [];

  const filtered = search.trim()
    ? items.filter(
        (item) =>
          item.name.includes(search) ||
          item.name_en.toLowerCase().includes(search.toLowerCase()) ||
          item.symbol.toLowerCase().includes(search.toLowerCase())
      )
    : items;

  if (loading && !data) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="text-center">
          <div className="mx-auto h-10 w-10 animate-spin rounded-full border-4 border-gold-500 border-t-transparent" />
          <p className="mt-3 text-gray-500">در حال بارگذاری قیمت‌ها...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Link
              href="/"
              className="text-gray-400 transition-colors hover:text-gray-600 dark:hover:text-gray-300"
            >
              داشبورد
            </Link>
            <span className="text-gray-300 dark:text-gray-600">/</span>
            <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100">
              قیمت‌ها
            </h1>
          </div>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            قیمت لحظه‌ای طلا، ارز و رمزارز
          </p>
        </div>
        <div className="flex items-center gap-3 text-sm">
          {lastUpdated && (
            <span className="text-gray-400">
              {lastUpdated.toLocaleTimeString("fa-IR", {
                hour: "2-digit",
                minute: "2-digit",
              })}
            </span>
          )}
          <button
            onClick={() => fetchData(false)}
            className="btn-secondary inline-flex items-center gap-1 px-3 py-1.5 text-xs"
          >
            &#x21bb; به‌روزرسانی
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-lg bg-red-50 p-4 text-sm text-red-700 dark:bg-red-900/20 dark:text-red-400">
          {error}
        </div>
      )}

      {/* Category tabs */}
      <div className="flex gap-2">
        {CATEGORY_ORDER.map((cat) => {
          const meta = CATEGORY_META[cat];
          const count = data?.[cat]?.length || 0;
          return (
            <button
              key={cat}
              onClick={() => {
                setActiveCategory(cat);
                setSearch("");
              }}
              className={`inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
                activeCategory === cat
                  ? "bg-gold-600 text-white"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700"
              }`}
            >
              <span>{meta.icon}</span>
              <span>{meta.label}</span>
              <span
                className={`rounded-full px-1.5 text-[11px] ${
                  activeCategory === cat
                    ? "bg-white/20"
                    : "bg-black/10 dark:bg-white/10"
                }`}
              >
                {count}
              </span>
            </button>
          );
        })}
      </div>

      {/* Search */}
      <input
        type="text"
        placeholder="جستجو (نام، نماد)..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="input-field max-w-sm"
      />

      {/* Price grid */}
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {filtered.length > 0 ? (
          filtered.map((item) => (
            <PriceCard key={item.symbol} item={item} />
          ))
        ) : (
          <div className="col-span-full card py-12 text-center">
            <p className="text-gray-400">
              {search ? "نتیجه‌ای یافت نشد" : "داده‌ای موجود نیست"}
            </p>
          </div>
        )}
      </div>

      {/* Data source attribution */}
      {data?.source && data.source !== "unavailable" && (
        <p className="text-center text-xs text-gray-400">
          منبع داده: {data.source}
        </p>
      )}
    </div>
  );
}
