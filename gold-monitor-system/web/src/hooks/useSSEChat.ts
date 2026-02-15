"use client";

import { useCallback, useRef, useState } from "react";

export interface ChartSpec {
  chart_id: string;
  chart_type: "line" | "bar" | "area";
  title_fa: string;
  x_key: string;
  y_keys: string[];
  y_labels: Record<string, string>;
  data: Record<string, unknown>[];
  unit?: string;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  toolCalls?: Array<{ name: string; arguments: Record<string, unknown>; result_preview?: string }>;
  charts?: ChartSpec[];
}

interface SSEOptions {
  url: string;
  headers?: Record<string, string>;
  sessionStorageKey?: string;
}

interface SSEState {
  messages: Message[];
  isLoading: boolean;
  streamingContent: string;
  statusText: string;
  suggestions: string[];
  sessionId: string | null;
  toolsUsed: string[];
}

export function useSSEChat(options: SSEOptions) {
  const { url, headers = {}, sessionStorageKey } = options;

  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const [statusText, setStatusText] = useState("");
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(() => {
    if (typeof window !== "undefined" && sessionStorageKey) {
      return localStorage.getItem(sessionStorageKey);
    }
    return null;
  });
  const [toolsUsed, setToolsUsed] = useState<string[]>([]);

  const abortRef = useRef<AbortController | null>(null);
  const pendingChartsRef = useRef<ChartSpec[]>([]);

  const updateSessionId = useCallback(
    (id: string | null) => {
      setSessionId(id);
      if (sessionStorageKey && typeof window !== "undefined") {
        if (id) {
          localStorage.setItem(sessionStorageKey, id);
        } else {
          localStorage.removeItem(sessionStorageKey);
        }
      }
    },
    [sessionStorageKey]
  );

  const setExternalMessages = useCallback((msgs: Message[]) => {
    setMessages(msgs);
  }, []);

  const sendMessage = useCallback(
    async (content: string, extraBody: Record<string, unknown> = {}) => {
      if (isLoading || !content.trim()) return;

      const userMsg: Message = {
        id: `user-${Date.now()}`,
        role: "user",
        content: content.trim(),
      };
      setMessages((prev) => [...prev, userMsg]);
      setIsLoading(true);
      setStreamingContent("");
      setSuggestions([]);
      setToolsUsed([]);

      abortRef.current?.abort();
      pendingChartsRef.current = [];
      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const response = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...headers },
          body: JSON.stringify({
            messages: [{ role: "user", content: content.trim() }],
            session_id: sessionId,
            ...extraBody,
          }),
          signal: controller.signal,
        });

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          const errorMsg: Message = {
            id: `error-${Date.now()}`,
            role: "assistant",
            content: errorData.message || "خطایی رخ داد.",
          };
          setMessages((prev) => [...prev, errorMsg]);
          setIsLoading(false);
          return;
        }

        const contentType = response.headers.get("content-type") || "";
        if (contentType.includes("application/json")) {
          const errorData = await response.json();
          const errorMsg: Message = {
            id: `error-${Date.now()}`,
            role: "assistant",
            content: errorData.message || "خطایی رخ داد.",
          };
          setMessages((prev) => [...prev, errorMsg]);
          setIsLoading(false);
          return;
        }

        const newSid = response.headers.get("X-Chat-Session-Id");
        if (newSid) updateSessionId(newSid);

        const reader = response.body?.getReader();
        if (!reader) {
          setIsLoading(false);
          return;
        }

        const decoder = new TextDecoder();
        let accumulated = "";
        let buffer = "";
        let finalized = false;

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;

            try {
              const data = JSON.parse(line.slice(6));

              if (data.type === "status") {
                const labels: Record<string, string> = {
                  thinking: "در حال فکر کردن...",
                  searching: "در حال جستجو...",
                  generating: "در حال نوشتن پاسخ...",
                };
                setStatusText(labels[data.content] || "");
              } else if (data.type === "tools") {
                if (Array.isArray(data.content)) {
                  setToolsUsed(data.content);
                }
              } else if (data.type === "content") {
                setStatusText("");
                accumulated += data.content;
                setStreamingContent(accumulated);
              } else if (data.type === "chart") {
                if (data.content) {
                  pendingChartsRef.current.push(data.content as ChartSpec);
                }
              } else if (data.type === "done") {
                const charts = pendingChartsRef.current.length > 0
                  ? [...pendingChartsRef.current]
                  : undefined;
                pendingChartsRef.current = [];
                if (accumulated && !finalized) {
                  finalized = true;
                  const assistantMsg: Message = {
                    id: `assistant-${Date.now()}`,
                    role: "assistant",
                    content: accumulated,
                    charts,
                  };
                  setMessages((prev) => [...prev, assistantMsg]);
                } else if (charts) {
                  // Charts arrived but no new text — attach to last assistant message
                  setMessages((prev) => {
                    const last = prev[prev.length - 1];
                    if (last?.role === "assistant") {
                      return [...prev.slice(0, -1), { ...last, charts }];
                    }
                    return prev;
                  });
                }
                setStreamingContent("");
                if (data.session_id) updateSessionId(data.session_id);
              } else if (data.type === "suggestions") {
                if (Array.isArray(data.content)) {
                  setSuggestions(data.content);
                }
              } else if (data.type === "error") {
                const errorMsg: Message = {
                  id: `error-${Date.now()}`,
                  role: "assistant",
                  content: data.content || "خطایی رخ داد.",
                };
                setMessages((prev) => [...prev, errorMsg]);
              }
            } catch {
              // Skip malformed lines
            }
          }
        }

        if (accumulated && !finalized) {
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
          // Aborted
        } else {
          const errorMsg: Message = {
            id: `error-${Date.now()}`,
            role: "assistant",
            content: "متأسفانه سرویس در دسترس نیست.",
          };
          setMessages((prev) => [...prev, errorMsg]);
        }
      } finally {
        setIsLoading(false);
        setStatusText("");
      }
    },
    [isLoading, sessionId, url, headers, updateSessionId]
  );

  const clearChat = useCallback(() => {
    setMessages([]);
    setStreamingContent("");
    setSuggestions([]);
    setToolsUsed([]);
    updateSessionId(null);
    abortRef.current?.abort();
  }, [updateSessionId]);

  return {
    messages,
    isLoading,
    streamingContent,
    statusText,
    suggestions,
    sessionId,
    toolsUsed,
    sendMessage,
    clearChat,
    setMessages: setExternalMessages,
    setSessionId: updateSessionId,
  };
}
