"use client";

import { useEffect, useState } from "react";
import { getToken } from "@/lib/auth";

interface TableSchema {
  name: string;
  description: string;
  columns: string;
}

export default function SchemaViewer() {
  const [tables, setTables] = useState<TableSchema[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (isOpen && tables.length === 0) {
      setLoading(true);
      const token = getToken();
      fetch("/api/admin/workbench/schema", {
        headers: { Authorization: `Bearer ${token}` },
      })
        .then((r) => r.json())
        .then((data) => setTables(data.tables || []))
        .catch(() => {})
        .finally(() => setLoading(false));
    }
  }, [isOpen, tables.length]);

  return (
    <div className="border-t border-gray-200 dark:border-gray-800">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex w-full items-center justify-between px-3 py-2 text-xs font-medium text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
      >
        <span>راهنمای جداول دیتابیس</span>
        <svg
          className={`h-4 w-4 transition-transform ${isOpen ? "rotate-180" : ""}`}
          viewBox="0 0 20 20"
          fill="currentColor"
        >
          <path fillRule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clipRule="evenodd" />
        </svg>
      </button>

      {isOpen && (
        <div className="max-h-60 overflow-y-auto px-3 pb-3">
          {loading ? (
            <div className="text-center text-xs text-gray-400">در حال بارگذاری...</div>
          ) : (
            <div className="space-y-2">
              {tables.map((t) => (
                <div key={t.name} className="rounded-lg bg-gray-50 p-2 dark:bg-gray-800/50">
                  <div className="text-xs font-bold text-gray-700 dark:text-gray-300">
                    {t.name}
                  </div>
                  <div className="text-[10px] text-gray-500 dark:text-gray-400">
                    {t.description}
                  </div>
                  <div className="mt-1 text-[10px] font-mono text-gray-400 dark:text-gray-500">
                    {t.columns}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
