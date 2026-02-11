/**
 * Format a date string to Persian-friendly format.
 */
export function formatDate(dateStr: string): string {
  try {
    const date = new Date(dateStr);
    return new Intl.DateTimeFormat("fa-IR", {
      year: "numeric",
      month: "long",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(date);
  } catch {
    return dateStr;
  }
}

/**
 * Format a date string to a short relative format.
 */
export function timeAgo(dateStr: string): string {
  try {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMin = Math.floor(diffMs / 60000);
    const diffHour = Math.floor(diffMin / 60);
    const diffDay = Math.floor(diffHour / 24);

    if (diffMin < 1) return "همین الان";
    if (diffMin < 60) return `${diffMin} دقیقه پیش`;
    if (diffHour < 24) return `${diffHour} ساعت پیش`;
    if (diffDay < 7) return `${diffDay} روز پیش`;
    return formatDate(dateStr);
  } catch {
    return dateStr;
  }
}

/**
 * Severity label in Persian.
 */
export function severityLabel(severity: string): string {
  const map: Record<string, string> = {
    critical: "بحرانی",
    high: "بالا",
    medium: "متوسط",
    low: "پایین",
  };
  return map[severity] || severity;
}

/**
 * Time horizon label in Persian.
 */
export function timeHorizonLabel(horizon: string): string {
  const map: Record<string, string> = {
    immediate: "فوری",
    short: "کوتاه‌مدت",
    medium: "میان‌مدت",
    long: "بلندمدت",
  };
  return map[horizon] || horizon;
}

/**
 * Direction label in Persian.
 */
export function directionLabel(direction: string): string {
  const map: Record<string, string> = {
    up: "صعودی",
    down: "نزولی",
    bullish: "صعودی",
    bearish: "نزولی",
    neutral: "خنثی",
    mixed: "ترکیبی",
  };
  return map[direction] || direction;
}

/**
 * Section label in Persian.
 */
export function sectionLabel(section: string): string {
  const map: Record<string, string> = {
    global_gold: "طلای جهانی",
    iran_gold: "طلا و ارز ایران",
    coin: "سکه",
    gold_funds: "صندوق‌های طلا",
    geopolitics: "ژئوپلیتیک",
  };
  return map[section] || section;
}

/**
 * Confidence percentage display.
 */
export function confidencePercent(confidence: number): string {
  return `${Math.round(confidence * 100)}%`;
}

/**
 * Join class names, filtering out falsy values.
 */
export function cn(...classes: (string | false | undefined | null)[]): string {
  return classes.filter(Boolean).join(" ");
}
