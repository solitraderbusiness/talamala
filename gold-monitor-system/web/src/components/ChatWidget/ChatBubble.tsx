"use client";

interface ChatBubbleProps {
  isOpen: boolean;
  onClick: () => void;
}

export default function ChatBubble({ isOpen, onClick }: ChatBubbleProps) {
  return (
    <button
      onClick={onClick}
      className={`fixed bottom-4 left-4 z-50 flex items-center justify-center rounded-full bg-gold-600 text-white shadow-lg transition-all duration-300 hover:bg-gold-500 hover:shadow-xl sm:bottom-5 sm:left-5 ${
        isOpen ? "scale-0 opacity-0" : "scale-100 opacity-100"
      } h-12 w-12 sm:h-14 sm:w-14`}
      aria-label="Open chat"
      title="با طلاملا حرف بزن"
    >
      <svg
        xmlns="http://www.w3.org/2000/svg"
        className="h-6 w-6 sm:h-7 sm:w-7"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
      </svg>

      {/* Pulse animation ring */}
      {!isOpen && (
        <span className="absolute inset-0 animate-ping rounded-full bg-gold-500 opacity-20" />
      )}
    </button>
  );
}
