"use client";

import { useCallback, useEffect, useState } from "react";
import { getToken } from "@/lib/auth";
import { cn } from "@/lib/utils";

/* ── Types ─────────────────────────────────────────────────────────── */

interface TableInfo {
  name: string;
  columns: number;
  rows: number;
  size_bytes: number;
  size_human: string;
  module: string;
}

interface SchemaOverview {
  tables: TableInfo[];
  total_tables: number;
  total_rows: number;
  total_size_bytes: number;
  total_size_human: string;
  modules: Record<string, string>;
}

interface ColumnInfo {
  name: string;
  type: string;
  nullable: boolean;
  default: string | null;
  max_length: number | null;
}

interface TableDetail {
  name: string;
  module: string;
  row_count: number;
  size_bytes: number;
  size_human: string;
  columns: ColumnInfo[];
  null_ratios: Record<string, number | null>;
  indexes: { name: string; definition: string }[];
  freshness: {
    column: string;
    oldest: string | null;
    newest: string | null;
  } | null;
}

interface HealthItem {
  table: string;
  module: string;
  rows: number;
  latest: string | null;
  ts_column: string;
  error?: boolean;
}

interface SizeInfo {
  database_size_bytes: number;
  database_size_human: string;
  top_tables: {
    name: string;
    size_bytes: number;
    size_human: string;
    pct: number;
  }[];
}

/* ── Helpers ───────────────────────────────────────────────────────── */

const MODULE_COLORS: Record<string, string> = {
  core: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
  signal: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400",
  analysis: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
  data_collection: "bg-cyan-100 text-cyan-700 dark:bg-cyan-900/30 dark:text-cyan-400",
  data_reliability: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
  articles: "bg-pink-100 text-pink-700 dark:bg-pink-900/30 dark:text-pink-400",
  videos: "bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-400",
  unknown: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-400",
};

function timeAgo(ts: string): string {
  const diff = (Date.now() - new Date(ts).getTime()) / 60000;
  if (diff < 1) return "همین الان";
  if (diff < 60) return `${Math.floor(diff)} دقیقه پیش`;
  if (diff < 1440) return `${Math.floor(diff / 60)} ساعت پیش`;
  return `${Math.floor(diff / 1440)} روز پیش`;
}

/* ── Component ─────────────────────────────────────────────────────── */

type Tab = "schema" | "health" | "size";

export default function DatabasePage() {
  const [tab, setTab] = useState<Tab>("schema");
  const [schema, setSchema] = useState<SchemaOverview | null>(null);
  const [health, setHealth] = useState<HealthItem[] | null>(null);
  const [sizeInfo, setSizeInfo] = useState<SizeInfo | null>(null);
  const [selectedTable, setSelectedTable] = useState<string | null>(null);
  const [tableDetail, setTableDetail] = useState<TableDetail | null>(null);
  const [filterModule, setFilterModule] = useState<string>("");
  const [loading, setLoading] = useState(true);

  const fetchSchema = useCallback(async () => {
    const token = getToken();
    if (!token) return;
    try {
      const res = await fetch("/api/admin/database/schema", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setSchema(await res.json());
    } catch { /* ignore */ }
    setLoading(false);
  }, []);

  const fetchHealth = useCallback(async () => {
    const token = getToken();
    if (!token) return;
    try {
      const res = await fetch("/api/admin/database/health", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setHealth(data.health);
      }
    } catch { /* ignore */ }
  }, []);

  const fetchSize = useCallback(async () => {
    const token = getToken();
    if (!token) return;
    try {
      const res = await fetch("/api/admin/database/size", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setSizeInfo(await res.json());
    } catch { /* ignore */ }
  }, []);

  const fetchTableDetail = useCallback(async (name: string) => {
    const token = getToken();
    if (!token) return;
    setTableDetail(null);
    try {
      const res = await fetch(`/api/admin/database/tables/${name}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setTableDetail(await res.json());
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    fetchSchema();
    fetchHealth();
    fetchSize();
  }, [fetchSchema, fetchHealth, fetchSize]);

  useEffect(() => {
    if (selectedTable) fetchTableDetail(selectedTable);
  }, [selectedTable, fetchTableDetail]);

  if (loading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <div className="h-10 w-10 animate-spin rounded-full border-4 border-gold-500 border-t-transparent" />
      </div>
    );
  }

  const tabs: { id: Tab; label: string }[] = [
    { id: "schema", label: "اسکیما" },
    { id: "health", label: "سلامت جداول" },
    { id: "size", label: "حجم ذخیره‌سازی" },
  ];

  return (
    <div className="space-y-5">
      {/* Header */}
      <div>
        <h1 className="text-lg font-bold text-gray-900 dark:text-gray-100">
          هوش پایگاه داده
        </h1>
        <p className="text-xs text-gray-500 dark:text-gray-400">
          اسکیمای جداول، سلامت داده‌ها و حجم ذخیره‌سازی
        </p>
      </div>

      {/* Summary Cards */}
      {schema && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="card">
            <div className="text-xs font-bold text-gray-500 dark:text-gray-400">جداول</div>
            <div className="mt-1 text-2xl font-bold text-gray-900 dark:text-gray-100">
              {schema.total_tables}
            </div>
          </div>
          <div className="card">
            <div className="text-xs font-bold text-gray-500 dark:text-gray-400">ردیف‌ها</div>
            <div className="mt-1 text-2xl font-bold text-gray-900 dark:text-gray-100">
              {schema.total_rows.toLocaleString("fa-IR")}
            </div>
          </div>
          <div className="card">
            <div className="text-xs font-bold text-gray-500 dark:text-gray-400">حجم کل</div>
            <div className="mt-1 text-2xl font-bold text-gray-900 dark:text-gray-100">
              {sizeInfo?.database_size_human || schema.total_size_human}
            </div>
          </div>
          <div className="card">
            <div className="text-xs font-bold text-gray-500 dark:text-gray-400">ماژول‌ها</div>
            <div className="mt-2 flex flex-wrap gap-1">
              {Object.entries(schema.modules).map(([key, label]) => (
                <button
                  key={key}
                  onClick={() => setFilterModule(filterModule === key ? "" : key)}
                  className={cn(
                    "rounded-full px-2 py-0.5 text-[10px] font-medium transition-colors",
                    filterModule === key
                      ? "bg-gold-200 text-gold-800 dark:bg-gold-900/50 dark:text-gold-300"
                      : MODULE_COLORS[key]
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 rounded-lg bg-gray-100 p-1 dark:bg-gray-800">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={cn(
              "flex-1 rounded-md px-4 py-1.5 text-xs font-medium transition-colors",
              tab === t.id
                ? "bg-white text-gray-900 shadow dark:bg-gray-700 dark:text-gray-100"
                : "text-gray-500 hover:text-gray-700 dark:text-gray-400"
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {tab === "schema" && schema && (
        <SchemaTab
          schema={schema}
          filterModule={filterModule}
          selectedTable={selectedTable}
          tableDetail={tableDetail}
          onSelectTable={setSelectedTable}
        />
      )}
      {tab === "health" && health && <HealthTab health={health} />}
      {tab === "size" && sizeInfo && <SizeTab sizeInfo={sizeInfo} />}
    </div>
  );
}

/* ── Schema Tab ────────────────────────────────────────────────────── */

function SchemaTab({
  schema,
  filterModule,
  selectedTable,
  tableDetail,
  onSelectTable,
}: {
  schema: SchemaOverview;
  filterModule: string;
  selectedTable: string | null;
  tableDetail: TableDetail | null;
  onSelectTable: (name: string | null) => void;
}) {
  const filtered = filterModule
    ? schema.tables.filter((t) => t.module === filterModule)
    : schema.tables;

  return (
    <div className="flex flex-col gap-4 lg:flex-row">
      {/* Table list */}
      <div className={cn("overflow-x-auto rounded-xl border border-gray-200 dark:border-gray-800", selectedTable ? "lg:w-1/2" : "w-full")}>
        <table className="w-full text-xs">
          <thead className="bg-gray-50 dark:bg-gray-800/50">
            <tr>
              <th className="px-3 py-2 text-right font-bold text-gray-500">جدول</th>
              <th className="px-3 py-2 text-right font-bold text-gray-500">ماژول</th>
              <th className="px-3 py-2 text-right font-bold text-gray-500">ستون‌ها</th>
              <th className="px-3 py-2 text-right font-bold text-gray-500">ردیف‌ها</th>
              <th className="px-3 py-2 text-right font-bold text-gray-500">حجم</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
            {filtered.map((t) => (
              <tr
                key={t.name}
                className={cn(
                  "cursor-pointer transition-colors hover:bg-gray-50 dark:hover:bg-gray-800/30",
                  selectedTable === t.name && "bg-gold-50 dark:bg-gold-900/10"
                )}
                onClick={() => onSelectTable(selectedTable === t.name ? null : t.name)}
              >
                <td className="px-3 py-2 font-mono text-gray-900 dark:text-gray-100">
                  {t.name}
                </td>
                <td className="px-3 py-2">
                  <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-medium", MODULE_COLORS[t.module])}>
                    {schema.modules[t.module] || t.module}
                  </span>
                </td>
                <td className="px-3 py-2 text-gray-600 dark:text-gray-400">{t.columns}</td>
                <td className="px-3 py-2 text-gray-600 dark:text-gray-400">
                  {t.rows.toLocaleString("fa-IR")}
                </td>
                <td className="px-3 py-2 text-gray-600 dark:text-gray-400">{t.size_human}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Table detail panel */}
      {selectedTable && tableDetail && (
        <div className="space-y-4 lg:w-1/2">
          <div className="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900">
            <div className="flex items-center justify-between">
              <h3 className="font-mono text-sm font-bold text-gray-900 dark:text-gray-100">
                {tableDetail.name}
              </h3>
              <button
                onClick={() => onSelectTable(null)}
                className="text-xs text-gray-400 hover:text-gray-600"
              >
                بستن
              </button>
            </div>
            <div className="mt-2 flex gap-4 text-xs text-gray-500">
              <span>{tableDetail.row_count.toLocaleString("fa-IR")} ردیف</span>
              <span>{tableDetail.size_human}</span>
              <span>{tableDetail.columns.length} ستون</span>
            </div>
            {tableDetail.freshness && (
              <div className="mt-2 rounded bg-gray-50 px-3 py-2 text-xs dark:bg-gray-800/50">
                <span className="font-medium text-gray-500">تازگی: </span>
                <span className="text-gray-700 dark:text-gray-300">
                  {tableDetail.freshness.newest
                    ? timeAgo(tableDetail.freshness.newest)
                    : "—"}
                </span>
              </div>
            )}
          </div>

          {/* Columns */}
          <div className="overflow-x-auto rounded-xl border border-gray-200 dark:border-gray-800">
            <table className="w-full text-xs">
              <thead className="bg-gray-50 dark:bg-gray-800/50">
                <tr>
                  <th className="px-3 py-2 text-right font-bold text-gray-500">ستون</th>
                  <th className="px-3 py-2 text-right font-bold text-gray-500">نوع</th>
                  <th className="px-3 py-2 text-right font-bold text-gray-500">Null</th>
                  <th className="px-3 py-2 text-right font-bold text-gray-500">% خالی</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                {tableDetail.columns.map((col) => {
                  const nullPct = tableDetail.null_ratios[col.name];
                  return (
                    <tr key={col.name}>
                      <td className="px-3 py-1.5 font-mono text-gray-900 dark:text-gray-100">
                        {col.name}
                      </td>
                      <td className="px-3 py-1.5 text-gray-500">{col.type}</td>
                      <td className="px-3 py-1.5">
                        {col.nullable ? (
                          <span className="text-amber-500">YES</span>
                        ) : (
                          <span className="text-emerald-500">NO</span>
                        )}
                      </td>
                      <td className="px-3 py-1.5">
                        {nullPct != null ? (
                          <span className={cn(
                            nullPct > 50 ? "text-red-500" : nullPct > 10 ? "text-amber-500" : "text-gray-400"
                          )}>
                            {nullPct}%
                          </span>
                        ) : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Indexes */}
          {tableDetail.indexes.length > 0 && (
            <div className="rounded-xl border border-gray-200 p-4 dark:border-gray-800">
              <h4 className="mb-2 text-xs font-bold text-gray-500">ایندکس‌ها ({tableDetail.indexes.length})</h4>
              <div className="space-y-1">
                {tableDetail.indexes.map((idx) => (
                  <div key={idx.name} className="text-[10px]">
                    <span className="font-mono font-medium text-gray-700 dark:text-gray-300">
                      {idx.name}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ── Health Tab ────────────────────────────────────────────────────── */

function HealthTab({ health }: { health: HealthItem[] }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-gray-200 dark:border-gray-800">
      <table className="w-full text-xs">
        <thead className="bg-gray-50 dark:bg-gray-800/50">
          <tr>
            <th className="px-3 py-2 text-right font-bold text-gray-500">جدول</th>
            <th className="px-3 py-2 text-right font-bold text-gray-500">ماژول</th>
            <th className="px-3 py-2 text-right font-bold text-gray-500">ردیف‌ها</th>
            <th className="px-3 py-2 text-right font-bold text-gray-500">آخرین رکورد</th>
            <th className="px-3 py-2 text-right font-bold text-gray-500">وضعیت</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
          {health.map((item) => {
            const diffMin = item.latest
              ? (Date.now() - new Date(item.latest).getTime()) / 60000
              : Infinity;
            const staleStatus =
              item.error ? "error" :
              !item.latest ? "no_data" :
              diffMin <= 30 ? "fresh" :
              diffMin <= 360 ? "ok" :
              diffMin <= 1440 ? "stale" :
              "very_stale";

            const statusColors: Record<string, string> = {
              fresh: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
              ok: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
              stale: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
              very_stale: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
              no_data: "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-500",
              error: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
            };
            const statusLabels: Record<string, string> = {
              fresh: "تازه",
              ok: "معمولی",
              stale: "کهنه",
              very_stale: "بسیار کهنه",
              no_data: "بدون داده",
              error: "خطا",
            };

            return (
              <tr key={item.table}>
                <td className="px-3 py-2 font-mono text-gray-900 dark:text-gray-100">
                  {item.table}
                </td>
                <td className="px-3 py-2">
                  <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-medium", MODULE_COLORS[item.module])}>
                    {item.module}
                  </span>
                </td>
                <td className="px-3 py-2 text-gray-600 dark:text-gray-400">
                  {item.rows.toLocaleString("fa-IR")}
                </td>
                <td className="px-3 py-2 text-gray-500">
                  {item.latest ? timeAgo(item.latest) : "—"}
                </td>
                <td className="px-3 py-2">
                  <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-medium", statusColors[staleStatus])}>
                    {statusLabels[staleStatus]}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/* ── Size Tab ──────────────────────────────────────────────────────── */

function SizeTab({ sizeInfo }: { sizeInfo: SizeInfo }) {
  const maxSize = sizeInfo.top_tables[0]?.size_bytes || 1;

  return (
    <div className="space-y-4">
      <div className="card">
        <div className="text-xs font-bold text-gray-500 dark:text-gray-400">
          حجم کل پایگاه داده
        </div>
        <div className="mt-1 text-2xl font-bold text-gray-900 dark:text-gray-100">
          {sizeInfo.database_size_human}
        </div>
      </div>

      <div className="rounded-xl border border-gray-200 p-4 dark:border-gray-800">
        <h3 className="mb-3 text-xs font-bold text-gray-500 dark:text-gray-400">
          بزرگ‌ترین جداول
        </h3>
        <div className="space-y-2">
          {sizeInfo.top_tables.map((t) => (
            <div key={t.name} className="flex items-center gap-3">
              <div className="w-40 shrink-0 font-mono text-xs text-gray-900 dark:text-gray-100">
                {t.name}
              </div>
              <div className="flex-1">
                <div className="h-4 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800">
                  <div
                    className="h-full rounded-full bg-gold-400 dark:bg-gold-600"
                    style={{ width: `${(t.size_bytes / maxSize) * 100}%` }}
                  />
                </div>
              </div>
              <div className="w-16 shrink-0 text-left text-xs text-gray-500">
                {t.size_human}
              </div>
              <div className="w-12 shrink-0 text-left text-xs text-gray-400">
                {t.pct}%
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
