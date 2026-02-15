"use client";

import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

export interface PageContext {
  type: "video" | "article" | "page";
  videoId?: number;
  articleId?: number;
  title?: string;
  summary?: string;
  channel?: string;
  url?: string;
}

interface ChatContextValue {
  /** Current page context (what the user is viewing) */
  pageContext: PageContext | null;
  /** Set the page context (call from pages) */
  setPageContext: (ctx: PageContext | null) => void;
  /** Message to auto-send when chat opens */
  pendingMessage: string | null;
  /** Whether the chat should open */
  requestOpen: boolean;
  /** Open the chat with optional context and initial message */
  openWithContext: (ctx: PageContext, initialMessage?: string) => void;
  /** Clear pending message after it's been consumed */
  clearPendingMessage: () => void;
  /** Clear requestOpen after it's been consumed */
  clearRequestOpen: () => void;
}

const ChatContext = createContext<ChatContextValue | null>(null);

export function ChatContextProvider({ children }: { children: ReactNode }) {
  const [pageContext, setPageContext] = useState<PageContext | null>(null);
  const [pendingMessage, setPendingMessage] = useState<string | null>(null);
  const [requestOpen, setRequestOpen] = useState(false);

  const openWithContext = useCallback((ctx: PageContext, initialMessage?: string) => {
    setPageContext(ctx);
    if (initialMessage) {
      setPendingMessage(initialMessage);
    }
    setRequestOpen(true);
  }, []);

  const clearPendingMessage = useCallback(() => setPendingMessage(null), []);
  const clearRequestOpen = useCallback(() => setRequestOpen(false), []);

  return (
    <ChatContext.Provider
      value={{
        pageContext,
        setPageContext,
        pendingMessage,
        requestOpen,
        openWithContext,
        clearPendingMessage,
        clearRequestOpen,
      }}
    >
      {children}
    </ChatContext.Provider>
  );
}

export function useChatContext(): ChatContextValue {
  const ctx = useContext(ChatContext);
  if (!ctx) {
    throw new Error("useChatContext must be used within ChatContextProvider");
  }
  return ctx;
}
