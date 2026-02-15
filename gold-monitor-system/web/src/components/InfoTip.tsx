"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { createPortal } from "react-dom";
import { termDefinitions } from "@/lib/term-definitions";

interface InfoTipProps {
  term: string;
}

const POPOVER_WIDTH = 288; // w-72
const POPOVER_GAP = 8;

export default function InfoTip({ term }: InfoTipProps) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number; above: boolean }>({
    top: 0,
    left: 0,
    above: true,
  });
  const btnRef = useRef<HTMLButtonElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);

  const def = termDefinitions[term];

  const toggle = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    setOpen((prev) => !prev);
  }, []);

  // Click-outside to dismiss (check both button and popover)
  useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      const target = e.target as Node;
      if (
        btnRef.current?.contains(target) ||
        popoverRef.current?.contains(target)
      ) {
        return;
      }
      setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  // Compute position relative to viewport when opening
  useEffect(() => {
    if (!open || !btnRef.current) return;
    const rect = btnRef.current.getBoundingClientRect();
    const above = rect.top > 180;

    // Horizontal: try to center on the button, clamp to viewport
    let left = rect.left + rect.width / 2 - POPOVER_WIDTH / 2;
    left = Math.max(8, Math.min(left, window.innerWidth - POPOVER_WIDTH - 8));

    const top = above
      ? rect.top - POPOVER_GAP + window.scrollY
      : rect.bottom + POPOVER_GAP + window.scrollY;

    setPos({ top, left, above });
  }, [open]);

  // Close on scroll/resize (position would be stale)
  useEffect(() => {
    if (!open) return;
    const close = () => setOpen(false);
    window.addEventListener("scroll", close, { passive: true, capture: true });
    window.addEventListener("resize", close);
    return () => {
      window.removeEventListener("scroll", close, { capture: true });
      window.removeEventListener("resize", close);
    };
  }, [open]);

  if (!def) return null;

  return (
    <>
      <button
        ref={btnRef}
        type="button"
        onClick={toggle}
        className="mr-1 inline-flex h-4 w-4 flex-shrink-0 items-center justify-center rounded-full text-gray-400 transition-colors hover:text-amber-500 focus:outline-none"
        aria-label={`توضیح ${def.title}`}
      >
        <svg viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4">
          <path
            fillRule="evenodd"
            d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a.75.75 0 000 1.5h.253a.25.25 0 01.244.304l-.459 2.066A1.75 1.75 0 0010.747 15H11a.75.75 0 000-1.5h-.253a.25.25 0 01-.244-.304l.459-2.066A1.75 1.75 0 009.253 9H9z"
            clipRule="evenodd"
          />
        </svg>
      </button>

      {open &&
        createPortal(
          <div
            ref={popoverRef}
            className="fixed z-[9999] w-72 rounded-xl border border-gray-200 bg-white p-3 shadow-lg dark:border-gray-700 dark:bg-gray-800"
            style={{
              top: pos.above ? undefined : pos.top - window.scrollY,
              bottom: pos.above
                ? window.innerHeight - (pos.top - window.scrollY)
                : undefined,
              left: pos.left,
            }}
            dir="rtl"
          >
            <div className="text-sm font-bold text-gray-900 dark:text-gray-100">
              {def.title}
            </div>
            <div className="mt-1 text-xs leading-relaxed text-gray-600 dark:text-gray-400">
              {def.body}
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}
