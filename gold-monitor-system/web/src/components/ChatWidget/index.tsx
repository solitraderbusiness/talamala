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
      .then((res) => {
        if (!res.ok) throw new Error("status check failed");
        return res.json();
      })
      .then((data) => {
        setEnabled(data.enabled);
        if (data.welcome_message) {
          setWelcomeMessage(data.welcome_message);
        }
      })
      .catch(() => {
        // If status check fails, still show widget
      });
  }, []);

  // Save session to localStorage
  useEffect(() => {
    if (sessionId) {
      localStorage.setItem(SESSION_STORAGE_KEY, sessionId);
    }
  }, [sessionId]);

  const addErrorMessage = useCallback((text: string) => {
    const errorMsg: Message = {
      id: `error-${Date.now()}`,
      role: "assistant",
      content: text,
    };
    setMessages((prev) => [...prev, errorMsg]);
    setStreamingContent("");
  }, []);

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

        // Handle HTTP errors first
        if (!response.ok) {
          // Try to parse JSON error body
          try {
            const errorData = await response.json();
            addErrorMessage(
              errorData.message || errorData.detail || "خطایی رخ داد. لطفاً دوباره تلاش کنید."
            );
          } catch {
            addErrorMessage("خطایی رخ داد. لطفاً دوباره تلاش کنید.");
          }
          setIsLoading(false);
          return;
        }

        // Check for JSON error responses (200 status but JSON body = not SSE)
        const contentType = response.headers.get("content-type") || "";
        if (contentType.includes("application/json")) {
          const errorData = await response.json();
          addErrorMessage(
            errorData.message || "خطایی رخ داد. لطفاً دوباره تلاش کنید."
          );
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
          addErrorMessage("خطا در دریافت پاسخ.");
          setIsLoading(false);
          return;
        }

        const decoder = new TextDecoder();
        let accumulated = "";
        let buffer = ""; // Buffer for incomplete SSE lines

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });

          // Process complete lines from buffer
          const lines = buffer.split("\n");
          // Keep the last potentially incomplete line in buffer
          buffer = lines.pop() || "";

          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;

            try {
              const data = JSON.parse(line.slice(6));

              if (data.type === "content") {
                accumulated += data.content;
                setStreamingContent(accumulated);
              } else if (data.type === "done") {
                if (accumulated) {
                  const assistantMsg: Message = {
                    id: `assistant-${Date.now()}`,
                    role: "assistant",
                    content: accumulated,
                  };
                  setMessages((prev) => [...prev, assistantMsg]);
                }
                setStreamingContent("");
                if (data.session_id) {
                  setSessionId(data.session_id);
                }
              } else if (data.type === "error") {
                addErrorMessage(data.content || "خطایی رخ داد.");
              }
            } catch {
              // Skip malformed SSE lines
            }
          }
        }

        // If stream ended without a 'done' event, finalize any accumulated content
        if (accumulated && !messages.some((m) => m.content === accumulated)) {
          const assistantMsg: Message = {
            id: `assistant-${Date.now()}`,
            role: "assistant",
            content: accumulated,
          };
          setMessages((prev) => [...prev, assistantMsg]);
          setStreamingContent("");
        }
      } catch (err: unknown) {
        if (err instanceof DOMException && err.name === "AbortError") {
          // Request was aborted, ignore
        } else {
          console.error("Chat error:", err);
          addErrorMessage("متأسفانه سرویس در دسترس نیست. لطفاً بعداً تلاش کنید.");
        }
      } finally {
        setIsLoading(false);
      }
    },
    [isLoading, sessionId, addErrorMessage, messages]
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
