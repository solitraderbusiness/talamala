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
  section?: string;
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

/* ---------- Monitoring types ---------- */

export interface MonitoringOverview {
  jobs_healthy: number;
  jobs_warning: number;
  jobs_error: number;
  jobs_stale: number;
  total_jobs: number;
  total_runs_24h: number;
  success_rate_24h: number;
  last_check_at: string;
}

export interface SystemJob {
  id: string;
  job_name: string;
  job_label_fa: string | null;
  job_category: string;
  schedule: string | null;
  last_run_at: string | null;
  last_success_at: string | null;
  last_failure_at: string | null;
  last_error: string | null;
  last_duration_ms: number | null;
  items_processed: number;
  status: "healthy" | "warning" | "error" | "stale";
  expected_interval_minutes: number;
  enabled: boolean;
  success_rate_24h: number | null;
  runs_24h: number;
  created_at: string;
  updated_at: string;
}

export interface JobRun {
  id: string;
  job_id: string;
  job_name: string | null;
  started_at: string;
  finished_at: string | null;
  status: "success" | "failure" | "timeout";
  items_processed: number;
  error_message: string | null;
  duration_ms: number | null;
  metadata: Record<string, unknown>;
}

export interface FailedRun {
  id: string;
  job_id: string;
  job_name: string;
  job_label_fa: string | null;
  started_at: string;
  finished_at: string | null;
  error_message: string | null;
  duration_ms: number | null;
  items_processed: number;
}

export interface ActivityEntry {
  id: string;
  job_id: string;
  job_name: string;
  job_label_fa: string | null;
  job_category: string;
  started_at: string;
  finished_at: string | null;
  status: "success" | "failure" | "timeout";
  items_processed: number;
  duration_ms: number | null;
  error_message: string | null;
}

export interface SystemHealthExternal {
  status: "healthy" | "degraded" | "down";
  jobs_healthy: number;
  jobs_warning: number;
  jobs_error: number;
  oldest_stale_job: string | null;
  timestamp: string;
}

export interface DataFreshness {
  last_news_fetch: string | null;
  last_price_update: string | null;
  last_sentiment_update: string | null;
  last_worker_run: string | null;
}

/* ---------- Monitoring API ---------- */

export function getMonitoringOverview(
  token: string
): Promise<MonitoringOverview> {
  return authRequest<MonitoringOverview>(
    "/api/admin/monitoring/overview",
    token
  );
}

export function getMonitoringJobs(token: string): Promise<SystemJob[]> {
  return authRequest<SystemJob[]>("/api/admin/monitoring/jobs", token);
}

export function getJobRuns(
  token: string,
  jobId: string,
  limit: number = 50
): Promise<JobRun[]> {
  return authRequest<JobRun[]>(
    `/api/admin/monitoring/jobs/${jobId}/runs?limit=${limit}`,
    token
  );
}

export function toggleJob(
  token: string,
  jobId: string
): Promise<{ id: string; enabled: boolean }> {
  return authRequest<{ id: string; enabled: boolean }>(
    `/api/admin/monitoring/jobs/${jobId}/toggle`,
    token,
    { method: "PUT" }
  );
}

export function getRecentFailures(
  token: string,
  limit: number = 20
): Promise<FailedRun[]> {
  return authRequest<FailedRun[]>(
    `/api/admin/monitoring/recent-failures?limit=${limit}`,
    token
  );
}

export function getActivityTimeline(
  token: string,
  hours: number = 24,
  category?: string
): Promise<ActivityEntry[]> {
  const params = new URLSearchParams({ hours: String(hours) });
  if (category) params.set("category", category);
  return authRequest<ActivityEntry[]>(
    `/api/admin/monitoring/activity?${params}`,
    token
  );
}

export function getSystemHealthExternal(
  token: string
): Promise<SystemHealthExternal> {
  return authRequest<SystemHealthExternal>("/api/admin/health", token);
}

export function getDataFreshness(): Promise<DataFreshness> {
  return request<DataFreshness>("/api/admin/data-freshness");
}

/* ---------- Chat Analytics types ---------- */

export interface ChatDashboard {
  messages_today: number;
  messages_this_week: number;
  messages_this_month: number;
  sessions_today: number;
  avg_messages_per_session: number;
  total_tokens_today: number;
  total_sessions: number;
}

export interface ChatOverview {
  total_messages: number;
  prev_total_messages: number;
  unique_sessions: number;
  prev_unique_sessions: number;
  avg_messages_per_session: number;
  api_cost_estimate: number;
  unanswered_count: number;
}

export interface ChatSessionSummary {
  id: string;
  messages_count: number;
  first_message: string | null;
  ip_address: string;
  primary_intent: string | null;
  had_answer_rate: number | null;
  created_at: string;
  last_active_at: string;
}

export interface ChatConversation {
  session: ChatSessionSummary;
  messages: Array<{
    id: string;
    role: string;
    content: string;
    tool_calls: unknown;
    tokens_used: number | null;
    created_at: string;
    analytics?: {
      intent: string;
      topics: string[];
      had_answer: boolean;
      missing_feature: string | null;
    } | null;
  }>;
}

export interface ChatSettingsData {
  enabled: string;
  model: string;
  rate_limit_ip: string;
  rate_limit_global: string;
  welcome_message: string;
  system_prompt: string;
}

export interface IntentCount {
  intent: string;
  count: number;
}

export interface TopicCount {
  topic: string;
  count: number;
}

export interface AssetCount {
  asset: string;
  label: string;
  count: number;
}

export interface FeatureGap {
  feature: string;
  count: number;
  example: string;
}

export interface UsageHour {
  dow: number;
  hour: number;
  count: number;
}

export interface SessionDepthBucket {
  bucket: string;
  count: number;
}

export interface ConversationsPage {
  items: ChatSessionSummary[];
  total: number;
  page: number;
  pages: number;
}

/* ---------- Chat Analytics API ---------- */

export function getChatDashboard(token: string): Promise<ChatDashboard> {
  return authRequest<ChatDashboard>("/api/admin/chat/dashboard", token);
}

export function getChatOverview(
  token: string,
  period: string = "today",
): Promise<ChatOverview> {
  return authRequest<ChatOverview>(
    `/api/admin/chat/overview?period=${period}`,
    token,
  );
}

export function getChatSessions(
  token: string,
  limit: number = 20,
  offset: number = 0,
): Promise<ChatSessionSummary[]> {
  return authRequest<ChatSessionSummary[]>(
    `/api/admin/chat/sessions?limit=${limit}&offset=${offset}`,
    token,
  );
}

export function getChatConversation(
  token: string,
  sessionId: string,
): Promise<ChatConversation> {
  return authRequest<ChatConversation>(
    `/api/admin/chat/conversations/${sessionId}`,
    token,
  );
}

export function getChatSettings(token: string): Promise<ChatSettingsData> {
  return authRequest<ChatSettingsData>("/api/admin/chat/settings", token);
}

export function updateChatSettings(
  token: string,
  data: Partial<ChatSettingsData>,
): Promise<{ status: string }> {
  return authRequest<{ status: string }>("/api/admin/chat/settings", token, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export function getPopularQuestions(
  token: string,
  limit: number = 10,
): Promise<Array<{ question: string; count: number }>> {
  return authRequest<Array<{ question: string; count: number }>>(
    `/api/admin/chat/popular-questions?limit=${limit}`,
    token,
  );
}

export function getChatIntents(
  token: string,
  period?: string,
): Promise<IntentCount[]> {
  const params = period ? `?period=${period}` : "";
  return authRequest<IntentCount[]>(
    `/api/admin/chat/insights/intents${params}`,
    token,
  );
}

export function getChatTopics(
  token: string,
  period?: string,
  limit: number = 20,
): Promise<TopicCount[]> {
  const params = new URLSearchParams();
  if (period) params.set("period", period);
  params.set("limit", String(limit));
  return authRequest<TopicCount[]>(
    `/api/admin/chat/insights/topics?${params}`,
    token,
  );
}

export function getChatAssets(
  token: string,
  period?: string,
): Promise<AssetCount[]> {
  const params = period ? `?period=${period}` : "";
  return authRequest<AssetCount[]>(
    `/api/admin/chat/insights/assets${params}`,
    token,
  );
}

export function getChatFeatureGaps(
  token: string,
  period?: string,
  limit: number = 20,
): Promise<FeatureGap[]> {
  const params = new URLSearchParams();
  if (period) params.set("period", period);
  params.set("limit", String(limit));
  return authRequest<FeatureGap[]>(
    `/api/admin/chat/insights/feature-gaps?${params}`,
    token,
  );
}

export function getChatUsageHours(
  token: string,
  period?: string,
): Promise<UsageHour[]> {
  const params = period ? `?period=${period}` : "";
  return authRequest<UsageHour[]>(
    `/api/admin/chat/insights/usage-hours${params}`,
    token,
  );
}

export function getChatSessionDepth(
  token: string,
  period?: string,
): Promise<SessionDepthBucket[]> {
  const params = period ? `?period=${period}` : "";
  return authRequest<SessionDepthBucket[]>(
    `/api/admin/chat/insights/session-depth${params}`,
    token,
  );
}

export function getChatConversations(
  token: string,
  params?: {
    page?: number;
    limit?: number;
    intent?: string;
    had_answer?: boolean;
    period?: string;
  },
): Promise<ConversationsPage> {
  const sp = new URLSearchParams();
  if (params?.page) sp.set("page", String(params.page));
  if (params?.limit) sp.set("limit", String(params.limit));
  if (params?.intent) sp.set("intent", params.intent);
  if (params?.had_answer !== undefined) sp.set("had_answer", String(params.had_answer));
  if (params?.period) sp.set("period", params.period);
  return authRequest<ConversationsPage>(
    `/api/admin/chat/conversations?${sp}`,
    token,
  );
}

/* ---------- Fundamental Analysis types ---------- */

export interface MacroCard {
  id: string;
  title_fa: string;
  status: "ready" | "pending";
  impact?: "bullish" | "bearish" | "neutral";
  data: Record<string, number | string | null> | null;
}

export interface MacroOverviewResponse {
  cards: MacroCard[];
}

export interface MoneyFlowResponse {
  etf_holdings: Record<string, Array<{ date: string; total_tonnes: number; change_tonnes: number | null }>>;
  cot_positions: Array<{
    date: string;
    non_commercial_net: number | null;
    open_interest: number | null;
    change: number | null;
  }>;
  period_days: number;
}

export interface RealRatesIndicator {
  series_id: string;
  label_en: string;
  label_fa: string;
  latest_value: number | null;
  latest_date: string | null;
  history: Array<{ date: string; value: number }>;
}

export interface RealRatesResponse {
  indicators: RealRatesIndicator[];
  period_days: number;
}

export interface CorrelationPair {
  pair_a: string;
  pair_b: string;
  label_fa: string;
  correlation: number;
  impact: "bullish" | "bearish" | "neutral";
  window_days: number;
}

export interface CorrelationsResponse {
  pairs: CorrelationPair[];
  computed_date: string | null;
}

export interface SentimentComponent {
  name: string;
  label_fa: string;
  score: number;
  weight: number;
}

export interface SentimentGaugeResponse {
  composite_score: number | null;
  label: string;
  label_fa: string;
  components: SentimentComponent[];
  component_count: number;
  max_components: number;
}

export interface ShanghaiPremiumResponse {
  status: "ready" | "pending";
  premium_usd: number | null;
  premium_pct: number | null;
  message_fa?: string;
}

export interface MarketEvent {
  id: string;
  event_type: string;
  title: string;
  title_fa: string | null;
  description: string | null;
  description_fa: string | null;
  impact: "bullish" | "bearish" | "neutral";
  magnitude: number | null;
  data: Record<string, unknown> | null;
  created_at: string | null;
}

export interface MarketActivityResponse {
  events: MarketEvent[];
  total: number;
  period_hours: number;
}

/* ---------- AI Analysis (Signal Aggregator) types ---------- */

export interface ConsensusCard {
  consensus_view: string;
  consensus_direction: string;
  consensus_strength: number;
  signals_count: number;
  buy_count: number;
  sell_count: number;
  weighted_buy_score: number;
  weighted_sell_score: number;
  avg_entry_price: number | null;
  avg_stop_loss: number | null;
  avg_take_profit: number | null;
  dominant_timeframe: string | null;
  dominant_reasons: string[] | null;
  timeframe_alignment: Record<string, string> | null;
  generated_at: string;
}

export interface ConsensusLatestResponse {
  consensuses: ConsensusCard[];
  updated_at: string;
  current_price: number | null;
}

export interface SignalItem {
  id: string;
  source_name: string;
  source_accuracy: number | null;
  source_type: string;
  direction: string;
  entry_price: number | null;
  stop_loss: number | null;
  take_profit_1: number | null;
  timeframe: string;
  analysis_type: string;
  confidence_raw: number;
  key_reasons: string[] | null;
  status: string;
  outcome_pips: number | null;
  parsed_at: string;
  valid_until: string | null;
}

export interface SignalsRecentResponse {
  items: SignalItem[];
  total: number;
}

export interface PerformanceSummary {
  total_signals: number;
  overall_win_rate: number | null;
  net_pips_all_time: number;
  profit_factor: number | null;
  avg_pips_per_signal: number | null;
  max_drawdown_pips: number | null;
  active_sources: number;
  avg_signals_per_day: number | null;
}

export interface DailyPerfItem {
  date: string;
  total_signals: number;
  closed_signals: number;
  winning_signals: number;
  losing_signals: number;
  win_rate: number | null;
  net_pips: number;
  cumulative_pips: number;
  best_signal_pips: number | null;
  worst_signal_pips: number | null;
  scalp_win_rate: number | null;
  intraday_win_rate: number | null;
  swing_win_rate: number | null;
  position_win_rate: number | null;
}

export interface MonthlyPerfItem {
  year: number;
  month: number;
  total_signals: number;
  closed_signals: number;
  win_rate: number | null;
  net_pips: number;
  cumulative_pips: number;
  profit_factor: number | null;
  max_drawdown_pips: number | null;
  best_day_pips: number | null;
  worst_day_pips: number | null;
  consensus_accuracy: number | null;
}

export interface SourceLeaderboardItem {
  id: string;
  name: string;
  type: string;
  total_signals: number;
  correct_signals: number;
  wrong_signals: number;
  accuracy_rate: number | null;
  avg_profit_pips: number | null;
  avg_loss_pips: number | null;
  profit_factor: number | null;
  current_weight: number;
  active: boolean;
  last_signal_at: string | null;
}

export interface JournalEntry {
  date: string;
  summary: string;
  total_signals: number;
  closed_signals: number;
  winning_signals: number;
  losing_signals: number;
  net_pips: number;
  cumulative_pips: number;
  win_rate: number | null;
}

export interface CurrentPriceResponse {
  asset: string;
  price: number | null;
  source: string | null;
  checked_at: string | null;
}

/* ---------- AI Analysis API ---------- */

export function getAiConsensusLatest(): Promise<ConsensusLatestResponse> {
  return request<ConsensusLatestResponse>("/api/ai-analysis/consensus/latest");
}

export function getAiSignalsRecent(params?: {
  limit?: number;
  offset?: number;
  status?: string;
  timeframe?: string;
  source_id?: string;
}): Promise<SignalsRecentResponse> {
  const sp = new URLSearchParams();
  if (params?.limit) sp.set("limit", String(params.limit));
  if (params?.offset) sp.set("offset", String(params.offset));
  if (params?.status && params.status !== "all") sp.set("status", params.status);
  if (params?.timeframe && params.timeframe !== "all") sp.set("timeframe", params.timeframe);
  if (params?.source_id && params.source_id !== "all") sp.set("source_id", params.source_id);
  return request<SignalsRecentResponse>(`/api/ai-analysis/signals/recent?${sp}`);
}

export function getAiPerformanceSummary(): Promise<PerformanceSummary> {
  return request<PerformanceSummary>("/api/ai-analysis/performance/summary");
}

export function getAiPerformanceDaily(params?: {
  from?: string;
  to?: string;
}): Promise<{ items: DailyPerfItem[] }> {
  const sp = new URLSearchParams();
  if (params?.from) sp.set("from", params.from);
  if (params?.to) sp.set("to", params.to);
  return request<{ items: DailyPerfItem[] }>(`/api/ai-analysis/performance/daily?${sp}`);
}

export function getAiPerformanceMonthly(): Promise<{ items: MonthlyPerfItem[] }> {
  return request<{ items: MonthlyPerfItem[] }>("/api/ai-analysis/performance/monthly");
}

export function getAiSourcesLeaderboard(): Promise<{ items: SourceLeaderboardItem[] }> {
  return request<{ items: SourceLeaderboardItem[] }>("/api/ai-analysis/sources/leaderboard");
}

export function getAiCurrentPrice(): Promise<CurrentPriceResponse> {
  return request<CurrentPriceResponse>("/api/ai-analysis/price/current");
}

export function getAiJournalRecent(limit: number = 7): Promise<{ items: JournalEntry[] }> {
  return request<{ items: JournalEntry[] }>(`/api/ai-analysis/journal/recent?limit=${limit}`);
}

/* ---------- Signal Source Admin API ---------- */

export interface SignalSourceAdmin {
  id: string;
  name: string;
  type: string;
  telegram_channel_id: string | null;
  telegram_channel_name: string | null;
  url: string | null;
  active: boolean;
  added_at: string;
  total_signals: number;
  correct_signals: number;
  wrong_signals: number;
  expired_signals: number;
  accuracy_rate: number | null;
  avg_profit_pips: number | null;
  avg_loss_pips: number | null;
  profit_factor: number | null;
  current_weight: number;
  last_signal_at: string | null;
}

export function getSignalSources(token: string): Promise<{ items: SignalSourceAdmin[]; total: number }> {
  return authRequest<{ items: SignalSourceAdmin[]; total: number }>("/api/ai-analysis/sources/admin", token);
}

export function createSignalSource(
  token: string,
  data: Partial<SignalSourceAdmin>
): Promise<SignalSourceAdmin> {
  return authRequest<SignalSourceAdmin>("/api/ai-analysis/sources/admin", token, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function updateSignalSource(
  token: string,
  id: string,
  data: Partial<SignalSourceAdmin>
): Promise<SignalSourceAdmin> {
  return authRequest<SignalSourceAdmin>(`/api/ai-analysis/sources/admin/${id}`, token, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export function deleteSignalSource(token: string, id: string): Promise<{ status: string }> {
  return authRequest<{ status: string }>(`/api/ai-analysis/sources/admin/${id}`, token, {
    method: "DELETE",
  });
}

/* ---------- Data Health types ---------- */

export interface DataHealthOverview {
  snapshot_coverage_pct: number | null;
  alerts_24h: number;
  snapshots_24h: number;
  complete_snapshots_24h: number;
  outcome_pipeline: Record<string, number>;
  sentiment_last_recorded: string | null;
  price_data_last_update: string | null;
  outcome_errors: number;
}

export interface SnapshotStats {
  period: string;
  alerts_count: number;
  snapshots_count: number;
  complete_count: number;
  missing_count: number;
  completeness_pct: number | null;
  top_missing_fields: Array<{ field: string; count: number }>;
}

export interface OutcomePipeline {
  counts: Record<string, number>;
  total: number;
  completed: number;
  completion_rate: number | null;
  recent_errors: Array<{
    alert_id: string;
    status: string;
    errors: unknown;
    updated_at: string | null;
  }>;
}

export interface SentimentTimelinePoint {
  recorded_at: string;
  composite_score: number | null;
  direction: string | null;
  gold_price: number | null;
  gold_change_1h_pct: number | null;
  alerts_active_24h: number | null;
}

export interface SentimentTimelineResponse {
  data: SentimentTimelinePoint[];
  count: number;
  period_hours: number;
}

export interface PriceStatusItem {
  symbol: string;
  timeframe: string;
  last_update: string | null;
  record_count: number;
  last_price: number | null;
}

export interface PriceStatusResponse {
  symbols: PriceStatusItem[];
}

export interface CorrelationItem {
  lag: string;
  correlation: number;
  interpretation: string;
}

export interface SentimentCorrelationResponse {
  correlations: CorrelationItem[];
  data_points: number;
  period_days?: number;
  message_fa?: string;
}

/* ---------- Data Health API ---------- */

export function getDataHealthOverview(token: string): Promise<DataHealthOverview> {
  return authRequest<DataHealthOverview>("/api/admin/data-health/overview", token);
}

export function getSnapshotStats(
  token: string,
  period: string = "today"
): Promise<SnapshotStats> {
  return authRequest<SnapshotStats>(
    `/api/admin/data-health/snapshot-stats?period=${period}`,
    token
  );
}

export function getOutcomePipeline(token: string): Promise<OutcomePipeline> {
  return authRequest<OutcomePipeline>("/api/admin/data-health/outcome-pipeline", token);
}

export function getSentimentTimeline(
  token: string,
  hours: number = 168
): Promise<SentimentTimelineResponse> {
  return authRequest<SentimentTimelineResponse>(
    `/api/admin/data-health/sentiment-timeline?hours=${hours}`,
    token
  );
}

export function getPriceStatus(token: string): Promise<PriceStatusResponse> {
  return authRequest<PriceStatusResponse>("/api/admin/data-health/price-status", token);
}

export function getSentimentCorrelation(
  token: string,
  days: number = 7
): Promise<SentimentCorrelationResponse> {
  return authRequest<SentimentCorrelationResponse>(
    `/api/admin/data-health/correlation?days=${days}`,
    token
  );
}

/* ---------- Gold Articles types ---------- */

export interface GoldArticle {
  id: number;
  title_fa: string | null;
  title_original: string;
  source_name: string;
  source_name_fa: string;
  source_url: string;
  source_logo: string | null;
  author: string | null;
  published_at: string | null;
  summary_fa: string | null;
  key_takeaways_fa: string[];
  gold_outlook: "bullish" | "bearish" | "neutral" | "mixed" | null;
  gold_outlook_fa: string;
  time_horizon: "short_term" | "medium_term" | "long_term" | null;
  time_horizon_fa: string;
  topics: string[];
  topics_fa: string[];
  affected_assets: string[];
  affected_assets_fa: string[];
  importance_score: number | null;
  is_featured: boolean;
  is_published: boolean;
  original_language: string | null;
  created_at: string | null;
  related_articles?: GoldArticle[];
  related_alert?: { id: string; title: string } | null;
}

export interface GoldArticlesResponse {
  articles: GoldArticle[];
  total: number;
  page: number;
  per_page: number;
  today_count: number;
  today_outlook_summary: {
    bullish: number;
    bearish: number;
    neutral: number;
    mixed: number;
  };
}

export interface GoldArticlesDailyDigest {
  featured: GoldArticle | null;
  today_articles: GoldArticle[];
  by_topic: Record<string, GoldArticle[]>;
  today_count: number;
}

/* ---------- Gold Articles API ---------- */

export function getGoldArticles(params?: {
  page?: number;
  per_page?: number;
  topic?: string;
  outlook?: string;
  asset?: string;
  source?: string;
  featured?: boolean;
  from?: string;
  to?: string;
}): Promise<GoldArticlesResponse> {
  const sp = new URLSearchParams();
  if (params?.page) sp.set("page", String(params.page));
  if (params?.per_page) sp.set("per_page", String(params.per_page));
  if (params?.topic) sp.set("topic", params.topic);
  if (params?.outlook) sp.set("outlook", params.outlook);
  if (params?.asset) sp.set("asset", params.asset);
  if (params?.source) sp.set("source", params.source);
  if (params?.featured) sp.set("featured", "true");
  if (params?.from) sp.set("from", params.from);
  if (params?.to) sp.set("to", params.to);
  const qs = sp.toString();
  return request<GoldArticlesResponse>(`/api/analysis/articles${qs ? `?${qs}` : ""}`);
}

export function getGoldArticle(id: number): Promise<GoldArticle> {
  return request<GoldArticle>(`/api/analysis/articles/${id}`);
}

export function getGoldArticlesDailyDigest(): Promise<GoldArticlesDailyDigest> {
  return request<GoldArticlesDailyDigest>("/api/analysis/articles/daily-digest");
}
