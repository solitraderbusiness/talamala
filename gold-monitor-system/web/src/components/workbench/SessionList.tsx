"use client";

import { useEffect, useState } from "react";
import { getToken } from "@/lib/auth";
import { cn } from "@/lib/utils";

interface Session {
  id: string;
  first_message: string | null;
  messages_count: number;
  created_at: string | null;
  last_active_at: string | null;
}

interface SessionListProps {
  currentSessionId: string | null;
  onSelect: (sessionId: string) => void;
  onNew: () => void;
  refreshTrigger?: number;
}

export default function SessionList({
  currentSessionId,
  onSelect,
  onNew,
  refreshTrigger,
}: SessionListProps) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    const token = getToken();
    fetch("/api/admin/workbench/sessions?limit=20", {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.json())
      .then((data) => setSessions(data.sessions || []))
      .catch(() => {});
  }, [isOpen, refreshTrigger]);

  const handleDelete = async (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation();
    const token = getToken();
    try {
      await fetch(`/api/admin/workbench/sessions/${sessionId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      setSessions((prev) => prev.filter((s) => s.id !== sessionId));
    } catch {
      // Ignore
    }
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return "";
    const d = new Date(dateStr);
    return d.toLocaleDateString("fa-IR", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  };

  return (
    <div className="border-b border-gray-200 dark:border-gray-800">
      <div className="flex items-center gap-2 px-3 py-2">
        <button
          onClick={() => setIsOpen(!isOpen)}
          className="flex items-center gap-1 text-xs font-medium text-gray-500 hover:text-gray-700 dark:text-gray-400"
        >
          <svg
            className={`h-4 w-4 transition-transform ${isOpen ? "rotate-180" : ""}`}
            viewBox="0 0 20 20"
            fill="currentColor"
          >
            <path fillRule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clipRule="evenodd" />
          </svg>
          <span>مکالمات قبلی</span>
        </button>
        <button
          onClick={onNew}
          className="mr-auto rounded-lg bg-gold-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-gold-700"
        >
          مکالمه جدید
        </button>
      </div>

      {isOpen && (
        <div className="max-h-48 overflow-y-auto px-3 pb-2">
          {sessions.length === 0 ? (
            <div className="text-center text-xs text-gray-400 py-2">هنوز مکالمه‌ای وجود ندارد</div>
          ) : (
            <div className="space-y-1">
              {sessions.map((s) => (
                <button
                  key={s.id}
                  onClick={() => { onSelect(s.id); setIsOpen(false); }}
                  className={cn(
                    "flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-right text-xs transition-colors",
                    s.id === currentSessionId
                      ? "bg-gold-100 text-gold-800 dark:bg-gold-900/30 dark:text-gold-300"
                      : "text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800"
                  )}
                >
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-medium">
                      {s.first_message || "مکالمه بدون عنوان"}
                    </div>
                    <div className="text-[10px] text-gray-400">
                      {s.messages_count} پیام · {formatDate(s.last_active_at)}
                    </div>
                  </div>
                  <button
                    onClick={(e) => handleDelete(e, s.id)}
                    className="mr-2 rounded p-0.5 text-gray-400 hover:bg-red-100 hover:text-red-500 dark:hover:bg-red-900/20"
                    title="حذف"
                  >
                    <svg className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor">
                      <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                    </svg>
                  </button>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
