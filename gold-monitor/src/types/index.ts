// ========================================
// Core Data Types for Gold Market Monitor
// Based on gold_monitor_rules_fa.yaml
// ========================================

export type Severity = 'high' | 'medium' | 'low';
export type Direction = 'bullish' | 'bearish' | 'mixed' | 'unclear';
export type TimeHorizon = 'immediate' | 'short' | 'medium' | 'long';
export type AssetId = 'global_gold' | 'iran_gold' | 'coin' | 'gold_funds';
export type ViewMode = 'quick' | 'professional';
export type ThemeMode = 'light' | 'dark';

export type RuleSection = 'global_gold' | 'iran_gold' | 'coin' | 'gold_funds';

export interface AssetImpact {
  asset: AssetId;
  direction: Direction;
  mechanism: string; // Persian explanation
}

export interface Alert {
  id: string;
  title: string;
  timestamp_utc: string;
  source_name: string;
  source_url: string;
  matched_rule_ids: string[];
  summary_fa: string;
  why_important_fa: string;
  expected_impact: AssetImpact[];
  severity: Severity;
  time_horizon: TimeHorizon;
  confidence: number; // 0-100
  follow_up_questions: string[];
  // UI-specific fields
  group?: string; // For smart grouping
}

export interface CauseEffect {
  trigger: string;
  mechanism: string;
  effect: string;
}

export interface Rule {
  id: string;
  section: RuleSection;
  title: string;
  what_it_is: string;
  watch_for: {
    keywords: string[];
    signals: string[];
  };
  why_important: string;
  importance_criteria: {
    high_if?: string[];
    medium_if?: string[];
    low_if?: string[];
  };
  horizon: TimeHorizon;
}

export interface TechnicalSignal {
  id: string;
  name: string;
  what_to_compute: string;
  alert_when?: string[];
  importance: Severity;
}

export interface MarketInfo {
  id: AssetId;
  name: string;
  nameEn: string;
  price: string;
  change: string;
  changePercent: string;
  trend: string;
  isPositive: boolean;
}

export interface RuleCategory {
  id: string;
  title: string;
  section: RuleSection;
  rules: Rule[];
}

export interface FilterState {
  severities: Severity[];
  assets: AssetId[];
  horizons: TimeHorizon[];
  searchQuery: string;
  timeRange: 'today' | '24h' | '7d' | '30d';
  selectedMarket: AssetId | 'all';
}

export interface WatchlistItem {
  id: string;
  name: string;
  filters: Partial<FilterState>;
}
