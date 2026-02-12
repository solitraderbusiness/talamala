"use client";

import { useEffect, useRef } from "react";

declare global {
  interface Window {
    TradingView?: {
      widget: new (config: Record<string, unknown>) => unknown;
    };
  }
}

export default function TradingViewChart() {
  const containerRef = useRef<HTMLDivElement>(null);
  const scriptRef = useRef<HTMLScriptElement | null>(null);

  useEffect(() => {
    if (scriptRef.current) return;

    const script = document.createElement("script");
    script.src = "https://s3.tradingview.com/tv.js";
    script.async = true;
    script.onload = () => {
      if (window.TradingView && containerRef.current) {
        new window.TradingView.widget({
          autosize: true,
          symbol: "OANDA:XAUUSD",
          interval: "60",
          timezone: "Asia/Tehran",
          theme: "dark",
          style: "1",
          locale: "fa_IR",
          toolbar_bg: "#111827",
          enable_publishing: false,
          hide_top_toolbar: false,
          hide_legend: false,
          save_image: false,
          container_id: containerRef.current.id,
          studies: [
            "MASimple@tv-basicstudies",
            "RSI@tv-basicstudies",
          ],
        });
      }
    };
    document.head.appendChild(script);
    scriptRef.current = script;

    return () => {
      if (script.parentNode) {
        script.parentNode.removeChild(script);
      }
      scriptRef.current = null;
    };
  }, []);

  return (
    <div className="card overflow-hidden p-0">
      <div
        id="tradingview_gold_chart"
        ref={containerRef}
        className="h-[350px] w-full sm:h-[500px]"
      />
    </div>
  );
}
