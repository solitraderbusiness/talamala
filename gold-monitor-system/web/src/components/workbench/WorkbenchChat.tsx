"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getToken } from "@/lib/auth";
import { useSSEChat, type Message } from "@/hooks/useSSEChat";
import WorkbenchMessage from "./WorkbenchMessage";
import SchemaViewer from "./SchemaViewer";
import SessionList from "./SessionList";

interface WorkbenchChatProps {
  activePanels: Set<string>;
}

const SESSION_KEY = "talamala_workbench_session_id";

export default function WorkbenchChat({ activePanels }: WorkbenchChatProps) {
  const token = getToken() || "";
  const [input, setInput] = useState("");
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const {
    messages,
    isLoading,
    streamingContent,
    statusText,
    toolsUsed,
    sessionId,
    sendMessage,
    clearChat,
    setMessages,
    setSessionId,
  } = useSSEChat({
    url: "/api/admin/workbench/chat",
    headers: { Authorization: `Bearer ${token}` },
    sessionStorageKey: SESSION_KEY,
  });

  // Auto-scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingContent]);

  // Load history on mount or session change
  useEffect(() => {
    if (!sessionId) return;
    fetch(`/api/admin/workbench/history?session_id=${sessionId}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.json())
      .then((data) => {
        if (data?.messages?.length) {
          setMessages(
            data.messages.map((m: { id: string; role: string; content: string }) => ({
              id: m.id,
              role: m.role as "user" | "assistant",
              content: m.content,
            }))
          );
        }
      })
      .catch(() => {});
  }, [sessionId, token, setMessages]);

  const handleSend = useCallback(() => {
    if (!input.trim() || isLoading) return;
    const content = input;
    setInput("");
    sendMessage(content, { active_panels: Array.from(activePanels) });
  }, [input, isLoading, sendMessage, activePanels]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleNewSession = () => {
    clearChat();
    setRefreshTrigger((n) => n + 1);
  };

  const handleSelectSession = (sid: string) => {
    setSessionId(sid);
    setMessages([]);
  };

  const handleQuickSend = useCallback((text: string) => {
    if (isLoading) return;
    sendMessage(text, { active_panels: Array.from(activePanels) });
  }, [isLoading, sendMessage, activePanels]);

  return (
    <div className="flex h-full flex-col rounded-xl border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900">
      {/* Session list */}
      <SessionList
        currentSessionId={sessionId}
        onSelect={handleSelectSession}
        onNew={handleNewSession}
        refreshTrigger={refreshTrigger}
      />

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.length === 0 && !streamingContent && (
          <WorkbenchTutorial onSend={handleQuickSend} />
        )}

        {messages.map((msg, idx) => (
          <WorkbenchMessage
            key={msg.id}
            message={msg}
            toolsUsed={msg.role === "assistant" && idx === messages.length - 1 ? toolsUsed : undefined}
          />
        ))}

        {/* Streaming content */}
        {streamingContent && (
          <WorkbenchMessage
            message={{ id: "streaming", role: "assistant", content: streamingContent }}
            toolsUsed={toolsUsed}
          />
        )}

        {/* Status */}
        {statusText && (
          <div className="flex items-center gap-2 text-xs text-gray-400">
            <div className="h-2 w-2 animate-pulse rounded-full bg-gold-500" />
            {statusText}
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Schema viewer */}
      <SchemaViewer />

      {/* Input area */}
      <div className="border-t border-gray-200 p-3 dark:border-gray-800">
        <div className="flex items-end gap-2">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="سوال خود را بنویسید... (مثلاً: میانگین قیمت طلا در ۳۰ روز گذشته؟)"
            className="flex-1 resize-none rounded-xl border border-gray-300 bg-gray-50 px-4 py-2.5 text-sm outline-none placeholder:text-gray-400 focus:border-gold-500 focus:ring-1 focus:ring-gold-500 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:placeholder:text-gray-500"
            rows={2}
            maxLength={2000}
            dir="rtl"
          />
          <button
            onClick={handleSend}
            disabled={isLoading || !input.trim()}
            className="rounded-xl bg-gold-600 p-2.5 text-white transition-colors hover:bg-gold-700 disabled:opacity-50"
          >
            <svg className="h-5 w-5 rotate-180" viewBox="0 0 20 20" fill="currentColor">
              <path d="M10.894 2.553a1 1 0 00-1.788 0l-7 14a1 1 0 001.169 1.409l5-1.429A1 1 0 009 15.571V11a1 1 0 112 0v4.571a1 1 0 00.725.962l5 1.428a1 1 0 001.17-1.408l-7-14z" />
            </svg>
          </button>
        </div>
        <div className="mt-1 text-[10px] text-gray-400">
          {input.length}/2000 · Enter ارسال · Shift+Enter خط جدید
        </div>
      </div>
    </div>
  );
}

/* ── Tutorial / onboarding shown when chat is empty ─────────────── */

const TUTORIAL_SECTIONS = [
  {
    icon: "📊",
    title: "وضعیت کلی بازار",
    description: "از ابزارهای آماده برای دریافت سریع وضعیت بازار استفاده کنید",
    examples: [
      "وضعیت کلان بازار طلا چطوره؟",
      "سنتیمنت فعلی بازار رو نشون بده",
      "رژیم فعلی بازار چیه و احتمالاتش چقدره؟",
      "همبستگی طلا با دلار و بورس چطوره؟",
    ],
  },
  {
    icon: "🔍",
    title: "تحلیل داده‌ها با SQL",
    description: "مستقیم از دیتابیس کوئری بزنید — هوش مصنوعی SQL می‌نویسه و اجرا می‌کنه",
    examples: [
      "میانگین قیمت طلا در ۳۰ روز گذشته چقدر بوده؟",
      "۱۰ روزی که بیشترین حجم معاملات طلا رو داشتن نشون بده",
      "روند تغییرات موجودی ETF طلا (GLD) در ۳ ماه گذشته",
      "آخرین ۵ هشدار با شدت critical رو نشون بده",
    ],
  },
  {
    icon: "📈",
    title: "پنل‌ها + چت",
    description: "پنل‌های بالا رو فعال کنید تا هوش مصنوعی داده‌هاشون رو ببینه و تحلیل‌شون کنه",
    examples: [
      "با توجه به داده‌های پنل‌ها، وضعیت کلی بازار طلا رو تحلیل کن",
      "آیا جریان پول نهادی و سنتیمنت هم‌جهت هستن؟",
      "بر اساس نرخ بهره واقعی، طلا احتمالاً به کدوم سمت میره؟",
    ],
  },
  {
    icon: "🧩",
    title: "کراس‌رفرنس و الگویابی",
    description: "از هوش مصنوعی بخواید داده‌ها رو با هم مقایسه کنه و الگو پیدا کنه",
    examples: [
      "روزهایی که VIX بالای ۲۵ بوده، طلا چه عملکردی داشته؟",
      "وقتی COT نت پوزیشن منفی شده، قیمت طلا بعدش چی شده؟",
      "رابطه تغییرات CPI با قیمت طلا رو بررسی کن",
    ],
  },
];

function WorkbenchTutorial({ onSend }: { onSend: (text: string) => void }) {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className="flex flex-col h-full" dir="rtl">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-lg">🔬</span>
          <div>
            <h3 className="text-sm font-bold text-gray-800 dark:text-gray-200">
              میز تحلیل — راهنمای استفاده
            </h3>
            <p className="text-[10px] text-gray-400">
              روی هر نمونه سوال کلیک کنید تا مستقیم ارسال شود
            </p>
          </div>
        </div>
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="text-[10px] text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
        >
          {collapsed ? "نمایش راهنما" : "بستن"}
        </button>
      </div>

      {!collapsed && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 overflow-y-auto">
          {TUTORIAL_SECTIONS.map((section) => (
            <div
              key={section.title}
              className="rounded-xl border border-gray-200 bg-gray-50 p-3 dark:border-gray-700 dark:bg-gray-800/50"
            >
              <div className="flex items-center gap-1.5 mb-1.5">
                <span className="text-sm">{section.icon}</span>
                <h4 className="text-xs font-bold text-gray-700 dark:text-gray-300">
                  {section.title}
                </h4>
              </div>
              <p className="text-[10px] text-gray-400 mb-2 leading-relaxed">
                {section.description}
              </p>
              <div className="space-y-1.5">
                {section.examples.map((example) => (
                  <button
                    key={example}
                    onClick={() => onSend(example)}
                    className="block w-full rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-right text-[11px] text-gray-600 transition-all hover:border-gold-400 hover:bg-gold-50 hover:text-gold-800 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-400 dark:hover:border-gold-600 dark:hover:bg-gold-900/20 dark:hover:text-gold-300"
                  >
                    {example}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* How it works — always visible */}
      <div className="mt-3 rounded-lg bg-gold-50 border border-gold-200 p-3 dark:bg-gold-900/10 dark:border-gold-800/30">
        <h4 className="text-[11px] font-bold text-gold-800 dark:text-gold-300 mb-1.5">
          نحوه کار
        </h4>
        <div className="grid grid-cols-3 gap-2 text-[10px] text-gold-700 dark:text-gold-400">
          <div className="text-center">
            <div className="text-base mb-0.5">1️⃣</div>
            <div>پنل‌های تحلیلی مورد نظر رو از بالا فعال کنید</div>
          </div>
          <div className="text-center">
            <div className="text-base mb-0.5">2️⃣</div>
            <div>سوال خود رو بپرسید — فارسی یا انگلیسی</div>
          </div>
          <div className="text-center">
            <div className="text-base mb-0.5">3️⃣</div>
            <div>هوش مصنوعی از ابزارها و SQL برای پاسخ استفاده می‌کنه</div>
          </div>
        </div>
      </div>
    </div>
  );
}
