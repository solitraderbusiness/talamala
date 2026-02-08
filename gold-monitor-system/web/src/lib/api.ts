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

export interface ExpectedImpact {
  [asset: string]: {
    direction: "up" | "down" | "mixed";
    mechanism: string;
  };
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
  expected_impact: ExpectedImpact;
  severity: "high" | "medium" | "low";
  time_horizon: "immediate" | "short" | "medium" | "long";
  confidence: number;
  follow_up_questions: string[];
  dedupe_key: string;
  match_evidence: Record<string, unknown>;
  created_at: string;
}

export interface AlertStats {
  top_alerts: Alert[];
  risk_score: number;
  counts: {
    high: number;
    medium: number;
    low: number;
  };
}

export interface AlertsResponse {
  items: Alert[];
  total: number;
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

export function getRulesLibrary(): Promise<RulesLibrary> {
  return request<RulesLibrary>("/api/rules/library");
}

export function getRuleById(ruleId: string): Promise<Rule> {
  return request<Rule>(`/api/rules/${ruleId}`);
}

export function getHealth(): Promise<{ status: string }> {
  return request<{ status: string }>("/api/health");
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

export function getAdminSettings(token: string): Promise<AdminSettings> {
  return authRequest<AdminSettings>("/api/admin/settings", token);
}

export function updateAdminSettings(
  token: string,
  data: AdminSettings
): Promise<AdminSettings> {
  return authRequest<AdminSettings>("/api/admin/settings", token, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}
