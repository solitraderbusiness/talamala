const API_URL = "";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_URL}${path}`;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };

  const res = await fetch(url, {
    ...options,
    headers,
  });

  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new ApiError(
      body || `Request failed with status ${res.status}`,
      res.status
    );
  }

  if (res.status === 204) {
    return undefined as T;
  }

  return res.json();
}

function authRequest<T>(
  path: string,
  token: string,
  options: RequestInit = {}
): Promise<T> {
  return request<T>(path, {
    ...options,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(options.headers as Record<string, string>),
    },
  });
}

/* ---------- Alert types ---------- */

export interface ImpactItem {
  asset: string;
  direction: string;
  mechanism: string;
}

/** Expected impact: array of {asset, direction, mechanism} from backend. */
export type ExpectedImpact = ImpactItem[];

export interface Alert {
  id: string;
  title: string;
  timestamp_utc: string;
  source_name: string;
  source_url: string;
  matched_rule_ids: string[];
  summary_fa: string;
  why_important_fa: string;
  expected_impact: ExpectedImpact;
  severity: "critical" | "high" | "medium" | "low";
  time_horizon: "immediate" | "short" | "medium" | "long";
  confidence: number;
  direction?: "bullish" | "bearish" | "neutral" | "pending_llm";
  direction_confidence?: number;
  direction_method?: string;
  alert_score?: number;
  news_type?: "price_report" | "causal_event" | "mixed" | "background_context";
  follow_up_questions: string[];
  dedupe_key: string;
  match_evidence: Record<string, unknown>;
  created_at: string;
  section?: string;
}

export interface SectionSummary {
  id: string;
  label: string;
  icon: string;
  total: number;
  high: number;
  medium: number;
  alerts: Alert[];
}

export interface AlertStats {
  top_alerts: Alert[];
  risk_score: number;
  counts: {
    critical: number;
    high: number;
    medium: number;
    low: number;
  };
  sections?: SectionSummary[];
}

export interface AlertsResponse {
  items: Alert[];
  total: number;
}

/* ---------- Sentiment types ---------- */

export interface SentimentDriver {
  title: string;
  impact: "bullish" | "bearish" | "neutral";
  weight: "high" | "medium" | "low";
}

export interface TimeframeSentiment {
  sentiment: string;
  sentiment_label: string;
  summary: string;
  key_drivers: SentimentDriver[];
  outlook: string;
  alert_count: number;
  label: string;
  score?: number; // 0-100 numeric sentiment score
}

export interface SentimentHistoryPoint {
  score: number;
  sentiment: string;
  sentiment_label: string;
  alert_count: number;
  timestamp: string;
}

export interface SentimentHistoryResponse {
  timeframe: string;
  hours: number;
  data: SentimentHistoryPoint[];
}

export interface SentimentResponse {
  timeframes: {
    "1h"?: TimeframeSentiment;
    "4h"?: TimeframeSentiment;
    "24h"?: TimeframeSentiment;
  };
  updated_at: string;
  alert_count_24h: number;
}

/* ---------- Prices types ---------- */

export interface PriceItem {
  value: number;
  formatted: string;
  label: string;
  unit: string;
  icon: string;
  change?: string;
  change_pct?: string;
  direction?: "up" | "down" | "flat";
}

export interface PricesResponse {
  prices: { [key: string]: PriceItem };
  updated_at: number;
  source: string;
}

/* ---------- All-Prices types ---------- */

export interface AllPriceItem {
  symbol: string;
  name: string;
  name_en: string;
  price: number;
  unit: string;
  date: string;
  time: string;
  change_percent?: number;
  change_value?: number;
  direction?: "up" | "down" | "flat";
  description?: string;
  icon_url?: string;
}

export interface AllPricesResponse {
  gold: AllPriceItem[];
  currency: AllPriceItem[];
  cryptocurrency: AllPriceItem[];
  updated_at: number;
  source: string;
}

/* ---------- Rules types ---------- */

export interface Rule {
  id: string;
  title: string;
  section: string;
  what_it_is: string;
  why_important: string;
  keywords: string[];
  signals: string[];
  importance: string;
}

export interface RulesLibrary {
  [section: string]: Rule[];
}

/* ---------- Admin types ---------- */

export interface Source {
  id: string;
  name: string;
  type: string;
  base_url: string;
  endpoints?: string[];
  enabled: boolean;
  poll_interval_seconds: number;
  categories?: string[];
  rule_bindings?: string[];
  reliability_score?: number | null;
  notes?: string | null;
  last_fetched_at?: string | null;
  last_success_at?: string | null;
  last_error?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface FetchLog {
  id: string;
  source_id: string;
  started_at: string;
  finished_at: string;
  status: string;
  items_fetched_count: number;
  error_message?: string;
  duration_ms?: number;
}

export interface AdminSettings {
  openrouter_model: string;
  temperature: number;
  max_tokens: number;
  enable_llm: boolean;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

/* ---------- Public API ---------- */

export function getAlerts(params?: {
  severity?: string;
  time_horizon?: string;
  q?: string;
  asset?: string;
  from_date?: string;
  to_date?: string;
  limit?: number;
  offset?: number;
}): Promise<AlertsResponse> {
  const searchParams = new URLSearchParams();
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== "") {
        searchParams.set(key, String(value));
      }
    });
  }
  const qs = searchParams.toString();
  return request<AlertsResponse>(`/api/alerts${qs ? `?${qs}` : ""}`);
}

export function getAlertById(id: string): Promise<Alert> {
  return request<Alert>(`/api/alerts/${id}`);
}

export function getAlertStats(): Promise<AlertStats> {
  return request<AlertStats>("/api/alerts/stats/today");
}

export function getPrices(): Promise<PricesResponse> {
  return request<PricesResponse>("/api/prices");
}

export function getAllPrices(): Promise<AllPricesResponse> {
  return request<AllPricesResponse>("/api/prices/all");
}

export function getRulesLibrary(): Promise<RulesLibrary> {
  return request<RulesLibrary>("/api/rules/library");
}

export function getRuleById(ruleId: string): Promise<Rule> {
  return request<Rule>(`/api/rules/${ruleId}`);
}

export function getSentiment(): Promise<SentimentResponse> {
  return request<SentimentResponse>("/api/sentiment");
}

export function getSentimentHistory(
  timeframe: string = "4h",
  hours: number = 48,
): Promise<SentimentHistoryResponse> {
  return request<SentimentHistoryResponse>(
    `/api/sentiment/history?timeframe=${timeframe}&hours=${hours}`,
  );
}

export function getHealth(): Promise<{ status: string }> {
  return request<{ status: string }>("/api/health");
}

/* ---------- Calendar types ---------- */

export interface GoldImpactNote {
  above_forecast?: string;
  below_forecast?: string;
  hawkish?: string;
  dovish?: string;
}

export interface CalendarEvent {
  id: string;
  event_name: string;
  event_name_fa: string;
  country: string;
  currency: string;
  category: string;
  datetime_utc: string;
  datetime_tehran: string;
  impact: "high" | "medium" | "low";
  actual: string | null;
  forecast: string | null;
  previous: string | null;
  source: string;
  affected_assets: string[];
  is_upcoming: boolean;
  time_until: string | null;
  gold_impact_note?: GoldImpactNote;
}

export interface CalendarResponse {
  events: CalendarEvent[];
  counts: {
    total: number;
    high: number;
    medium: number;
    low: number;
  };
  from: string;
  to: string;
}

export interface UpcomingEventsResponse {
  events: CalendarEvent[];
  countdown: {
    event_name: string;
    event_name_fa: string;
    time_until: string;
    datetime_utc: string;
    datetime_tehran: string;
    impact: string;
  } | null;
  last_synced: string;
}

/* ---------- Calendar API ---------- */

export function getCalendarEvents(params?: {
  from?: string;
  to?: string;
  asset?: string;
  impact?: string;
}): Promise<CalendarResponse> {
  const searchParams = new URLSearchParams();
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== "") {
        searchParams.set(key, String(value));
      }
    });
  }
  const qs = searchParams.toString();
  return request<CalendarResponse>(`/api/calendar${qs ? `?${qs}` : ""}`);
}

export function getUpcomingEvents(
  limit: number = 5,
  impact: string = "high",
): Promise<UpcomingEventsResponse> {
  return request<UpcomingEventsResponse>(
    `/api/calendar/upcoming?limit=${limit}&impact=${impact}`,
  );
}

/* ---------- Admin API ---------- */

export function adminLogin(
  email: string,
  password: string
): Promise<LoginResponse> {
  return request<LoginResponse>("/api/admin/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function getSources(token: string): Promise<Source[]> {
  return authRequest<Source[]>("/api/sources", token);
}

export function createSource(
  token: string,
  data: Partial<Source>
): Promise<Source> {
  return authRequest<Source>("/api/sources", token, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function updateSource(
  token: string,
  id: string,
  data: Partial<Source>
): Promise<Source> {
  return authRequest<Source>(`/api/sources/${id}`, token, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export function deleteSource(token: string, id: string): Promise<void> {
  return authRequest<void>(`/api/sources/${id}`, token, {
    method: "DELETE",
  });
}

export function fetchSourceNow(
  token: string,
  id: string
): Promise<{ status: string }> {
  return authRequest<{ status: string }>(`/api/sources/${id}/fetch`, token, {
    method: "POST",
  });
}

export function getSourceLogs(
  token: string,
  sourceId: string
): Promise<FetchLog[]> {
  return authRequest<FetchLog[]>(`/api/sources/${sourceId}/logs`, token);
}

export async function getAdminSettings(
  token: string
): Promise<AdminSettings> {
  // Backend returns [{key, value}, ...] — transform to flat object
  const raw = await authRequest<
    Array<{ key: string; value: unknown }> | Record<string, unknown>
  >("/api/admin/settings", token);

  const defaults: AdminSettings = {
    openrouter_model: "anthropic/claude-sonnet-4",
    temperature: 0.3,
    max_tokens: 4096,
    enable_llm: false,
  };

  if (Array.isArray(raw)) {
    for (const item of raw) {
      const k = item.key as keyof AdminSettings;
      if (k in defaults) {
        (defaults as unknown as Record<string, unknown>)[k] = item.value;
      }
    }
  } else if (typeof raw === "object" && raw !== null) {
    Object.assign(defaults, raw);
  }

  // Coerce types
  defaults.temperature = Number(defaults.temperature) || 0.3;
  defaults.max_tokens = Number(defaults.max_tokens) || 4096;
  defaults.enable_llm =
    defaults.enable_llm === true ||
    String(defaults.enable_llm).toLowerCase() === "true";

  return defaults;
}

export function updateAdminSettings(
  token: string,
  data: AdminSettings
): Promise<AdminSettings> {
  return authRequest<Record<string, unknown>>(
    "/api/admin/settings",
    token,
    {
      method: "PUT",
      body: JSON.stringify(data),
    }
  ).then((raw) => {
    // Transform bulk response {key: value, ...} back to AdminSettings
    return {
      openrouter_model:
        String(raw.openrouter_model ?? data.openrouter_model),
      temperature: Number(raw.temperature ?? data.temperature),
      max_tokens: Number(raw.max_tokens ?? data.max_tokens),
      enable_llm:
        raw.enable_llm === true ||
        String(raw.enable_llm ?? data.enable_llm).toLowerCase() === "true",
    };
  });
}
