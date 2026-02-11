"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import ChatBubble from "./ChatBubble";
import ChatPanel from "./ChatPanel";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
}

const SESSION_STORAGE_KEY = "talamala_chat_session_id";

export default function ChatWidget() {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [enabled, setEnabled] = useState(true);
  const [welcomeMessage, setWelcomeMessage] = useState(
    "سلام! من دستیار هوشمند طلامالا هستم. هر سوالی درباره اخبار، قیمت‌ها، تقویم اقتصادی و تحلیل بازار طلا دارید، بپرسید!"
  );

  const abortRef = useRef<AbortController | null>(null);

  // Load session from localStorage on mount
  useEffect(() => {
    const savedSessionId = localStorage.getItem(SESSION_STORAGE_KEY);
    if (savedSessionId) {
      setSessionId(savedSessionId);
    }

    // Check chat status
    fetch("/api/chat/status")
      .then((res) => res.json())
      .then((data) => {
        setEnabled(data.enabled);
        if (data.welcome_message) {
          setWelcomeMessage(data.welcome_message);
        }
      })
      .catch(() => {
        // If status check fails, still show widget but disable sending
      });
  }, []);

  // Save session to localStorage
  useEffect(() => {
    if (sessionId) {
      localStorage.setItem(SESSION_STORAGE_KEY, sessionId);
    }
  }, [sessionId]);

  const handleSend = useCallback(
    async (content: string) => {
      if (isLoading || !content.trim()) return;

      // Add user message
      const userMsg: Message = {
        id: `user-${Date.now()}`,
        role: "user",
        content: content.trim(),
      };
      setMessages((prev) => [...prev, userMsg]);
      setIsLoading(true);
      setStreamingContent("");

      // Abort any existing request
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const response = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            messages: [{ role: "user", content: content.trim() }],
            session_id: sessionId,
          }),
          signal: controller.signal,
        });

        // Check for non-SSE error responses
        const contentType = response.headers.get("content-type") || "";
        if (contentType.includes("application/json")) {
          const errorData = await response.json();
          const errorMsg: Message = {
            id: `error-${Date.now()}`,
            role: "assistant",
            content: errorData.message || "خطایی رخ داد. لطفاً دوباره تلاش کنید.",
          };
          setMessages((prev) => [...prev, errorMsg]);
          setIsLoading(false);
          return;
        }

        // Get session ID from response header
        const newSessionId = response.headers.get("X-Chat-Session-Id");
        if (newSessionId) {
          setSessionId(newSessionId);
        }

        // Process SSE stream
        const reader = response.body?.getReader();
        if (!reader) {
          throw new Error("No response body");
        }

        const decoder = new TextDecoder();
        let accumulated = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const chunk = decoder.decode(value, { stream: true });
          const lines = chunk.split("\n");

          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;

            try {
              const data = JSON.parse(line.slice(6));

              if (data.type === "content") {
                accumulated += data.content;
                setStreamingContent(accumulated);
              } else if (data.type === "done") {
                // Streaming complete — finalize message
                if (accumulated) {
                  const assistantMsg: Message = {
                    id: `assistant-${Date.now()}`,
                    role: "assistant",
                    content: accumulated,
                  };
                  setMessages((prev) => [...prev, assistantMsg]);
                }
                setStreamingContent("");

                // Update session ID if returned
                if (data.session_id) {
                  setSessionId(data.session_id);
                }
              } else if (data.type === "error") {
                const errorMsg: Message = {
                  id: `error-${Date.now()}`,
                  role: "assistant",
                  content: data.content || "خطایی رخ داد.",
                };
                setMessages((prev) => [...prev, errorMsg]);
                setStreamingContent("");
              }
            } catch {
              // Skip malformed SSE lines
            }
          }
        }
      } catch (err: unknown) {
        if (err instanceof DOMException && err.name === "AbortError") {
          // Request was aborted, ignore
        } else {
          const errorMsg: Message = {
            id: `error-${Date.now()}`,
            role: "assistant",
            content: "متأسفانه سرویس در دسترس نیست. لطفاً بعداً تلاش کنید.",
          };
          setMessages((prev) => [...prev, errorMsg]);
          setStreamingContent("");
        }
      } finally {
        setIsLoading(false);
      }
    },
    [isLoading, sessionId]
  );

  const handleClear = useCallback(() => {
    setMessages([]);
    setStreamingContent("");
    setSessionId(null);
    localStorage.removeItem(SESSION_STORAGE_KEY);
    abortRef.current?.abort();
  }, []);

  if (!enabled) return null;

  return (
    <>
      <ChatBubble isOpen={isOpen} onClick={() => setIsOpen(true)} />
      <ChatPanel
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        messages={messages}
        isLoading={isLoading}
        streamingContent={streamingContent}
        onSend={handleSend}
        welcomeMessage={welcomeMessage}
        onClear={handleClear}
      />
      {/* Mobile backdrop */}
      {isOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/30 backdrop-blur-sm sm:hidden"
          onClick={() => setIsOpen(false)}
        />
      )}
    </>
  );
}
