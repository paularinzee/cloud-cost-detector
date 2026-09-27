const TOKEN_KEY = "ccd_token";

export const auth = {
  get token() { return localStorage.getItem(TOKEN_KEY); },
  set(token: string) { localStorage.setItem(TOKEN_KEY, token); },
  clear() { localStorage.removeItem(TOKEN_KEY); },
  isAuthed() { return !!localStorage.getItem(TOKEN_KEY); },
};

async function request<T>(
  path: string,
  options: RequestInit = {},
  withAuth = true
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (withAuth && auth.token) {
    headers["Authorization"] = `Bearer ${auth.token}`;
  }

  const res = await fetch(path, { ...options, headers });

  if (res.status === 401) {
    auth.clear();
    if (!window.location.pathname.startsWith("/login")) {
      window.location.href = "/login";
    }
    throw new Error("Unauthorized");
  }

  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body?.detail || `Request failed (${res.status})`);
  }
  return body as T;
}

export const api = {
  signup: (email: string, password: string) =>
    request<{ access_token: string }>(
      "/api/auth/signup",
      { method: "POST", body: JSON.stringify({ email, password }) },
      false
    ),
  login: (email: string, password: string) =>
    request<{ access_token: string }>(
      "/api/auth/login",
      { method: "POST", body: JSON.stringify({ email, password }) },
      false
    ),
  resourceGroups: () => request<ResourceGroup[]>("/api/resource-groups"),
  analyze: (resource_group: string) =>
    request<AnalyzeAccepted>("/api/analyze", {
      method: "POST",
      body: JSON.stringify({ resource_group }),
    }),
  history: () => request<HistoryItem[]>("/api/history"),
  getAnalysis: (id: number) => request<HistoryItem>(`/api/analyses/${id}`),
};

export type AnalyzeAccepted = {
  analysis_id: number;
  status: string;
  resource_group: string;
};

export type ResourceGroup = {
  name: string;
  location?: string;
  id?: string;
  tags?: Record<string, string>;
  provisioning_state?: string;
};

export type Issue = {
  resource_name: string;
  resource_type: string;
  severity: "high" | "medium" | "low";
  category: string;
  title: string;
  description: string;
  estimated_monthly_savings_usd: number;
  fix_command: string;
};

export type AnalysisResultPayload = {
  resource_group?: string;
  resource_count?: number;
  resources?: Array<Record<string, unknown>>;
  summary_by_type?: Record<string, number>;
  summary?: string;
  estimated_monthly_savings_usd?: number;
  issues?: Issue[];
  quick_wins?: string[];
};

export type HistoryItem = {
  id: number;
  resource_group: string;
  resources_scanned: number;
  issues_found: number;
  estimated_savings: string;
  status: string;
  created_at: string;
  analysis_result: AnalysisResultPayload;
};

/**
 * Opens the live progress WebSocket for an analysis.
 *
 * Uses window.location.host so Vite's dev proxy (see vite.config.ts) forwards
 * to the backend on :8000 — this avoids CORS/Origin issues and works when the
 * app is deployed behind a single domain.
 *
 * The JWT is passed as a query param because browsers can't set custom headers
 * on the WebSocket handshake.
 */
export function openProgressSocket(analysisId: number): Promise<WebSocket> {
  return new Promise((resolve, reject) => {
    const token = auth.token;
    if (!token) {
      reject(new Error("Not authenticated"));
      return;
    }

    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const url = `${proto}://${window.location.host}/ws/progress/${analysisId}?token=${encodeURIComponent(token)}`;

    const ws = new WebSocket(url);
    ws.onopen = () => resolve(ws);
    ws.onerror = () => reject(new Error("WebSocket connection failed"));
    ws.onclose = (ev) => {
      if (ev.code === 1008) {
        reject(new Error("WebSocket authentication failed"));
      }
    };
  });
}