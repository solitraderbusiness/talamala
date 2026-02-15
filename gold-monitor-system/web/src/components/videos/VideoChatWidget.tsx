"use client";

import { useState } from "react";
import { sendVideoChat } from "@/lib/api";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

const SUGGESTED_QUESTIONS = [
  "خلاصه این ویدیو چیست؟",
  "نکته کلیدی درباره طلا چیست؟",
  "تاثیر این موضوع بر قیمت طلا؟",
];

export default function VideoChatWidget({ videoId }: { videoId: number }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSend(question?: string) {
    const q = question || input.trim();
    if (!q || loading) return;

    setInput("");
    setError(null);

    const userMsg: ChatMessage = { role: "user", content: q };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);

    try {
      const result = await sendVideoChat(videoId, q);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: result.answer },
      ]);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "خطا در ارسال";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="rounded-xl border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900">
      <div className="border-b border-gray-200 px-4 py-3 dark:border-gray-800">
        <h3 className="text-sm font-bold text-gray-700 dark:text-gray-300">
          سوال از ویدیو
        </h3>
        <p className="text-xs text-gray-400">
          از محتوای این ویدیو سوال بپرسید
        </p>
      </div>

      {/* Messages */}
      <div className="max-h-64 space-y-3 overflow-y-auto p-4">
        {messages.length === 0 && (
          <div className="space-y-2">
            <p className="text-xs text-gray-400">پیشنهاد سوال:</p>
            {SUGGESTED_QUESTIONS.map((sq) => (
              <button
                key={sq}
                onClick={() => handleSend(sq)}
                className="block w-full rounded-lg border border-gray-200 px-3 py-2 text-right text-xs text-gray-600 transition-colors hover:border-gold-300 hover:bg-gold-50 dark:border-gray-700 dark:text-gray-400 dark:hover:border-gold-600 dark:hover:bg-gold-900/20"
              >
                {sq}
              </button>
            ))}
          </div>
        )}

        {messages.map((msg, i) => (
          <div
            key={i}
            className={`rounded-lg px-3 py-2 text-sm ${
              msg.role === "user"
                ? "bg-gold-50 text-gray-800 dark:bg-gold-900/20 dark:text-gray-200"
                : "bg-gray-50 text-gray-700 dark:bg-gray-800 dark:text-gray-300"
            }`}
          >
            <p className="whitespace-pre-line">{msg.content}</p>
          </div>
        ))}

        {loading && (
          <div className="flex items-center gap-2 text-xs text-gray-400">
            <div className="h-3 w-3 animate-spin rounded-full border-2 border-gold-500 border-t-transparent" />
            در حال پاسخ‌دهی...
          </div>
        )}

        {error && (
          <p className="text-xs text-red-500 dark:text-red-400">{error}</p>
        )}
      </div>

      {/* Input */}
      <div className="border-t border-gray-200 p-3 dark:border-gray-800">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSend()}
            placeholder="سوال خود را بنویسید..."
            className="flex-1 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-700 outline-none focus:border-gold-500 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300"
            disabled={loading}
          />
          <button
            onClick={() => handleSend()}
            disabled={loading || !input.trim()}
            className="rounded-lg bg-gold-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-gold-700 disabled:opacity-50"
          >
            ارسال
          </button>
        </div>
      </div>
    </div>
  );
}
