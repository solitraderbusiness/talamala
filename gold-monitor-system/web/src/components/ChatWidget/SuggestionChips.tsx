"use client";

interface SuggestionChipsProps {
  suggestions: string[];
  onSelect: (suggestion: string) => void;
}

export default function SuggestionChips({ suggestions, onSelect }: SuggestionChipsProps) {
  if (!suggestions.length) return null;

  return (
    <div className="flex flex-wrap gap-2 px-4 py-2">
      {suggestions.map((suggestion, i) => (
        <button
          key={i}
          onClick={() => onSelect(suggestion)}
          className="rounded-full border border-gray-700 bg-gray-800/50 px-3 py-1.5 text-xs text-gray-300 transition-colors hover:border-gold-500 hover:bg-gray-700 hover:text-gold-400"
        >
          {suggestion}
        </button>
      ))}
    </div>
  );
}
