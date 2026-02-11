"use client";

import { useEffect, useRef, useState, KeyboardEvent } from "react";
import MessageBubble from "./MessageBubble";
import SuggestionChips from "./SuggestionChips";
import TypingIndicator from "./TypingIndicator";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
}

interface ChatPanelProps {
  isOpen: boolean;
  onClose: () => void;
  messages: Message[];
  isLoading: boolean;
  streamingContent: string;
  statusText?: string;
  onSend: (message: string) => void;
  welcomeMessage: string;
  onClear: () => void;
  dynamicSuggestions?: string[];
}

const DEFAULT_SUGGESTIONS = [
  "مهمترین خبر امروز چیه؟",
  "تقویم اقتصادی این هفته",
  "قیمت طلا و سکه",
  "سنتیمنت بازار طلا چطوره؟",
];

export default function ChatPanel({
  isOpen,
  onClose,
  messages,
  isLoading,
  streamingContent,
  onSend,
  welcomeMessage,
  onClear,
  statusText,
  dynamicSuggestions,
}: ChatPanelProps) {
  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingContent, isLoading]);

  // Focus input when panel opens
  useEffect(() => {
    if (isOpen) {
      setTimeout(() => textareaRef.current?.focus(), 300);
    }
  }, [isOpen]);

  const handleSend = () => {
    const trimmed = input.trim();
    if (!trimmed || isLoading) return;
    onSend(trimmed);
    setInput("");
    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleTextareaInput = () => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = Math.min(el.scrollHeight, 80) + "px";
    }
  };

  const showWelcome = messages.length === 0 && !isLoading;

  return (
    <div
      className={`fixed bottom-20 left-4 z-50 flex flex-col overflow-hidden rounded-2xl border border-gray-700 bg-gray-900 shadow-2xl transition-all duration-300 sm:left-5 ${
        isOpen
          ? "pointer-events-auto translate-y-0 opacity-100"
          : "pointer-events-none translate-y-4 opacity-0"
      } w-[calc(100vw-2rem)] sm:w-[380px] h-[85vh] sm:h-[500px]`}
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-gray-700 bg-gray-800/80 px-4 py-3">
        <div className="flex items-center gap-2">
          <button
            onClick={onClose}
            className="rounded-lg p-1 text-gray-400 transition-colors hover:bg-gray-700 hover:text-white"
            aria-label="Close chat"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
            </svg>
          </button>
          {messages.length > 0 && (
            <button
              onClick={onClear}
              className="rounded-lg p-1 text-gray-400 transition-colors hover:bg-gray-700 hover:text-white"
              aria-label="Clear conversation"
              title="پاک کردن مکالمه"
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z" clipRule="evenodd" />
              </svg>
            </button>
          )}
        </div>
        <div className="flex items-center gap-2 text-sm font-medium text-gray-200">
          <span>با طلاملا حرف بزن</span>
          <span className="text-lg">🤖</span>
        </div>
      </div>

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto py-4">
        {showWelcome && (
          <div className="px-4 py-2">
            {/* Welcome message */}
            <div className="mb-4 flex justify-end">
              <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-gray-800 px-4 py-3 text-sm leading-relaxed text-gray-100">
                {welcomeMessage}
              </div>
            </div>

            {/* Suggestion chips */}
            <div className="mb-2 text-right text-xs text-gray-500">
              سوال‌های پیشنهادی:
            </div>
            <SuggestionChips
              suggestions={DEFAULT_SUGGESTIONS}
              onSelect={onSend}
            />
          </div>
        )}

        {messages.map((msg) => (
          <MessageBubble key={msg.id} role={msg.role} content={msg.content} />
        ))}

        {/* Streaming content */}
        {streamingContent && (
          <MessageBubble role="assistant" content={streamingContent} />
        )}

        {/* Typing indicator with status */}
        {isLoading && !streamingContent && (
          <TypingIndicator statusText={statusText} />
        )}

        {/* Dynamic suggestion chips after assistant response */}
        {!isLoading && !streamingContent && dynamicSuggestions && dynamicSuggestions.length > 0 && messages.length > 0 && (
          <div className="px-4 pt-2">
            <SuggestionChips suggestions={dynamicSuggestions} onSelect={onSend} />
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div className="border-t border-gray-700 bg-gray-800/50 p-3">
        <div className="flex items-end gap-2">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onInput={handleTextareaInput}
            onKeyDown={handleKeyDown}
            placeholder="سوالتون رو بپرسید..."
            dir="rtl"
            rows={1}
            className="flex-1 resize-none rounded-xl border border-gray-600 bg-gray-700 px-4 py-2.5 text-sm text-gray-100 placeholder-gray-400 outline-none transition-colors focus:border-gold-500 focus:ring-1 focus:ring-gold-500"
            disabled={isLoading}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || isLoading}
            className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl bg-gold-600 text-white transition-colors hover:bg-gold-500 disabled:cursor-not-allowed disabled:opacity-40"
            aria-label="Send message"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 rotate-180" viewBox="0 0 20 20" fill="currentColor">
              <path d="M10.894 2.553a1 1 0 00-1.788 0l-7 14a1 1 0 001.169 1.409l5-1.429A1 1 0 009 15.571V11a1 1 0 112 0v4.571a1 1 0 00.725.962l5 1.428a1 1 0 001.17-1.408l-7-14z" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}
