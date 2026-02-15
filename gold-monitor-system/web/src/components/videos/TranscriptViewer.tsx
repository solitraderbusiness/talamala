"use client";

import { useState } from "react";

interface TranscriptViewerProps {
  transcript: string;
  onAskAI?: () => void;
}

export default function TranscriptViewer({ transcript, onAskAI }: TranscriptViewerProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="rounded-xl border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900">
      <div className="flex items-center justify-between p-4">
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-2 text-sm font-bold text-gray-700 transition-colors hover:text-gray-900 dark:text-gray-300 dark:hover:text-gray-100"
        >
          <span className={`inline-block transition-transform ${expanded ? "rotate-90" : ""}`}>
            ▶
          </span>
          متن ویدیو (Transcript)
        </button>
        {onAskAI && (
          <button
            onClick={onAskAI}
            className="inline-flex items-center gap-1.5 rounded-lg bg-gold-100 px-3 py-1.5 text-xs font-medium text-gold-700 transition-colors hover:bg-gold-200 dark:bg-gold-900/30 dark:text-gold-400 dark:hover:bg-gold-900/50"
          >
            از هوش مصنوعی بپرس
          </button>
        )}
      </div>
      {expanded && (
        <div className="border-t border-gray-100 p-4 dark:border-gray-800">
          <div
            dir="ltr"
            className="max-h-96 overflow-y-auto whitespace-pre-line text-sm leading-relaxed text-gray-600 dark:text-gray-400"
          >
            {transcript}
          </div>
        </div>
      )}
    </div>
  );
}
