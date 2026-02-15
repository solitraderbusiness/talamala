"use client";

import { cn } from "@/lib/utils";
import type { Message } from "@/hooks/useSSEChat";
import InlineChart from "./InlineChart";

interface WorkbenchMessageProps {
  message: Message;
  toolsUsed?: string[];
}

const TOOL_LABELS: Record<string, string> = {
  search_news: "جستجوی اخبار",
  get_calendar_events: "تقویم اقتصادی",
  get_price_data: "قیمت‌ها",
  get_news_summary: "خلاصه اخبار",
  get_sentiment: "احساسات",
  search_videos: "ویدیوها",
  get_macro_overview: "نمای کلان",
  get_money_flow: "جریان پول",
  get_real_rates: "نرخ بهره",
  get_correlations: "همبستگی",
  get_sentiment_gauge: "سنجش احساسات",
  get_regime_status: "رژیم بازار",
  execute_sql_query: "کوئری SQL",
  generate_chart: "نمودار",
};

export default function WorkbenchMessage({ message, toolsUsed }: WorkbenchMessageProps) {
  const isUser = message.role === "user";

  return (
    <div
      className={cn(
        "flex w-full",
        isUser ? "justify-start" : "justify-end"
      )}
    >
      <div
        className={cn(
          "max-w-[85%] rounded-2xl px-4 py-3",
          isUser
            ? "bg-gold-100 text-gray-900 dark:bg-gold-900/30 dark:text-gray-100"
            : "bg-gray-100 text-gray-900 dark:bg-gray-800 dark:text-gray-100"
        )}
      >
        {/* Tool badges for assistant messages */}
        {!isUser && toolsUsed && toolsUsed.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-1">
            {toolsUsed.map((tool) => (
              <span
                key={tool}
                className="inline-flex items-center rounded-full bg-blue-100 px-2 py-0.5 text-[10px] font-medium text-blue-700 dark:bg-blue-900/30 dark:text-blue-300"
              >
                {TOOL_LABELS[tool] || tool}
              </span>
            ))}
          </div>
        )}

        <div
          className="workbench-content prose prose-sm max-w-none dark:prose-invert prose-p:my-1 prose-headings:my-2 prose-table:text-xs prose-pre:bg-gray-900 prose-pre:text-gray-100"
          style={{ direction: "rtl" }}
          dangerouslySetInnerHTML={{
            __html: renderMarkdown(message.content),
          }}
        />

        {/* Inline charts */}
        {message.charts && message.charts.length > 0 && (
          <div className="mt-2 space-y-2">
            {message.charts.map((chart) => (
              <InlineChart key={chart.chart_id} spec={chart} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Simple markdown renderer — handles bold, tables, code blocks, lists.
 * We avoid a heavy dependency by doing basic rendering inline.
 */
function renderMarkdown(text: string): string {
  let html = escapeHtml(text);

  // Code blocks (```)
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_match, _lang, code) => {
    return `<pre class="overflow-x-auto rounded-lg bg-gray-900 p-3 text-xs text-gray-100"><code>${code.trim()}</code></pre>`;
  });

  // Inline code
  html = html.replace(/`([^`]+)`/g, '<code class="rounded bg-gray-200 px-1 py-0.5 text-xs dark:bg-gray-700">$1</code>');

  // Bold
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");

  // Tables
  html = html.replace(
    /^(\|.+\|)\n(\|[-| :]+\|)\n((?:\|.+\|\n?)+)/gm,
    (_match, headerRow, _separator, bodyRows) => {
      const headers = headerRow.split("|").filter((c: string) => c.trim()).map((c: string) => c.trim());
      const rows = bodyRows.trim().split("\n").map((row: string) =>
        row.split("|").filter((c: string) => c.trim()).map((c: string) => c.trim())
      );

      let table = '<div class="overflow-x-auto my-2"><table class="w-full border-collapse text-xs">';
      table += "<thead><tr>";
      for (const h of headers) {
        table += `<th class="border border-gray-300 bg-gray-100 px-2 py-1 text-right dark:border-gray-700 dark:bg-gray-800">${h}</th>`;
      }
      table += "</tr></thead><tbody>";
      for (const row of rows) {
        table += "<tr>";
        for (const cell of row) {
          table += `<td class="border border-gray-300 px-2 py-1 dark:border-gray-700">${cell}</td>`;
        }
        table += "</tr>";
      }
      table += "</tbody></table></div>";
      return table;
    }
  );

  // Headers
  html = html.replace(/^### (.+)$/gm, '<h3 class="text-sm font-bold mt-3 mb-1">$1</h3>');
  html = html.replace(/^## (.+)$/gm, '<h2 class="text-base font-bold mt-3 mb-1">$1</h2>');

  // Unordered lists
  html = html.replace(/^- (.+)$/gm, '<li class="mr-4">$1</li>');
  html = html.replace(/(<li[^>]*>.*<\/li>\n?)+/g, '<ul class="list-disc my-1">$&</ul>');

  // Line breaks
  html = html.replace(/\n/g, "<br />");

  return html;
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}
