"use client";

interface TypingIndicatorProps {
  statusText?: string;
}

export default function TypingIndicator({ statusText }: TypingIndicatorProps) {
  return (
    <div className="flex items-center gap-2 px-4 py-3">
      <div className="flex items-center gap-1 rounded-2xl rounded-br-sm bg-gray-800 px-4 py-3">
        <span className="inline-block h-2 w-2 animate-bounce rounded-full bg-gray-400" style={{ animationDelay: "0ms" }} />
        <span className="inline-block h-2 w-2 animate-bounce rounded-full bg-gray-400" style={{ animationDelay: "150ms" }} />
        <span className="inline-block h-2 w-2 animate-bounce rounded-full bg-gray-400" style={{ animationDelay: "300ms" }} />
      </div>
      {statusText && (
        <span className="text-xs text-gray-500">{statusText}</span>
      )}
    </div>
  );
}
