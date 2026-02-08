import { Alert, Severity, AssetId, TimeHorizon, FilterState } from '@/types';

export function cn(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(' ');
}

export function filterAlerts(alerts: Alert[], filters: FilterState): Alert[] {
  return alerts.filter((alert) => {
    // Severity filter
    if (filters.severities.length > 0 && !filters.severities.includes(alert.severity)) {
      return false;
    }

    // Asset filter
    if (filters.assets.length > 0) {
      const alertAssets = alert.expected_impact.map((i) => i.asset);
      if (!filters.assets.some((a) => alertAssets.includes(a))) {
        return false;
      }
    }

    // Horizon filter
    if (filters.horizons.length > 0 && !filters.horizons.includes(alert.time_horizon)) {
      return false;
    }

    // Market filter
    if (filters.selectedMarket !== 'all') {
      const alertAssets = alert.expected_impact.map((i) => i.asset);
      if (!alertAssets.includes(filters.selectedMarket)) {
        return false;
      }
    }

    // Search filter
    if (filters.searchQuery.trim()) {
      const q = filters.searchQuery.trim().toLowerCase();
      return (
        alert.title.toLowerCase().includes(q) ||
        alert.summary_fa.includes(q) ||
        alert.matched_rule_ids.some((r) => r.toLowerCase().includes(q))
      );
    }

    return true;
  });
}

export function groupAlertsByTopic(alerts: Alert[]): Record<string, Alert[]> {
  const groups: Record<string, Alert[]> = {};
  for (const alert of alerts) {
    const group = alert.group || 'سایر';
    if (!groups[group]) groups[group] = [];
    groups[group].push(alert);
  }
  return groups;
}

export function sortAlertsBySeverity(alerts: Alert[]): Alert[] {
  const order: Record<Severity, number> = { high: 0, medium: 1, low: 2 };
  return [...alerts].sort((a, b) => order[a.severity] - order[b.severity]);
}

export function getTopAlerts(alerts: Alert[], count: number = 3): Alert[] {
  return sortAlertsBySeverity(alerts).slice(0, count);
}

export function calculateRiskScore(alerts: Alert[]): number {
  let score = 0;
  for (const alert of alerts) {
    if (alert.severity === 'high') score += 15;
    else if (alert.severity === 'medium') score += 7;
    else score += 2;

    // Extra weight for geopolitical and dollar-related
    if (alert.matched_rule_ids.some((r) => r.includes('GEOPOL') || r.includes('FX') || r.includes('RATE'))) {
      score += 5;
    }
  }
  return Math.min(100, score);
}

export function formatPersianDate(isoDate: string): string {
  const date = new Date(isoDate);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);

  if (diffMins < 1) return 'همین الان';
  if (diffMins < 60) return `${diffMins} دقیقه پیش`;
  if (diffHours < 24) return `${diffHours} ساعت پیش`;

  const diffDays = Math.floor(diffMs / 86400000);
  if (diffDays < 7) return `${diffDays} روز پیش`;

  return date.toLocaleDateString('fa-IR');
}

export function highlightGlossaryTerms(text: string, glossary: Record<string, string>): { text: string; term?: string; tooltip?: string }[] {
  const segments: { text: string; term?: string; tooltip?: string }[] = [];
  let remaining = text;

  const terms = Object.keys(glossary).sort((a, b) => b.length - a.length);

  while (remaining.length > 0) {
    let earliestIndex = remaining.length;
    let matchedTerm = '';

    for (const term of terms) {
      const idx = remaining.indexOf(term);
      if (idx !== -1 && idx < earliestIndex) {
        earliestIndex = idx;
        matchedTerm = term;
      }
    }

    if (matchedTerm) {
      if (earliestIndex > 0) {
        segments.push({ text: remaining.slice(0, earliestIndex) });
      }
      segments.push({
        text: matchedTerm,
        term: matchedTerm,
        tooltip: glossary[matchedTerm],
      });
      remaining = remaining.slice(earliestIndex + matchedTerm.length);
    } else {
      segments.push({ text: remaining });
      remaining = '';
    }
  }

  return segments;
}

export function getDefaultFilters(): FilterState {
  return {
    severities: ['high', 'medium'],
    assets: [],
    horizons: [],
    searchQuery: '',
    timeRange: 'today',
    selectedMarket: 'all',
  };
}
