// Typed client for the IRAI FastAPI backend. All calls go to same-origin /api (proxied by Next).
export type Source = "LIVE" | "PROXY" | "STALE" | "DEMO" | "ERROR";

export interface Quote {
  symbol: string; name: string; price: number; prev_close: number | null; change: number | null;
  change_pct: number | null; currency: string | null; exchange: string | null; market_time: string | null;
  market_open: boolean; day_high: number | null; day_low: number | null; volume: number | null;
  fifty_two_week_high: number | null; fifty_two_week_low: number | null; source: Source;
}
export interface HistoryPoint { date: string; close: number }
export interface TickerBarItem { symbol: string; label: string; price: number; change_pct: number | null; source: Source }

export interface AdrRow {
  adr_symbol: string; local_symbol: string; name: string; country: string; ratio: number;
  local_market_open?: boolean; adr_price?: number; local_price?: number; local_currency?: string; fx?: number;
  implied_usd?: number; premium?: number | null; basis?: number | null; deviation?: number | null; z?: number | null;
  half_life_days?: number | null; history_days?: number; source: Source; confidence?: number; tradable: boolean;
  reasons: string[]; as_of?: string | null; error?: string;
  premium_history?: { date: string; premium: number }[];
}
export interface EtfRow {
  symbol: string; name: string; category: string; price?: number; change_pct?: number | null; nav?: number | null;
  premium?: number | null; tier?: string; expense_ratio?: number | null; total_assets?: number | null;
  ytd_return?: number | null; source: Source; flags: string[]; error?: string;
}
export interface RvRow {
  symbol: string; name: string; peer_group: string; sector?: string | null; multiple: number | null; multiple_name: string;
  peer_median_multiple: number | null; rv_percentile: number | null; quality_percentile: number; grade: string;
  coverage: string; peer_count: number; source: Source; roe?: number | null; operating_margin?: number | null;
  revenue_growth?: number | null; fitted_multiple?: number; residual?: number | null; residual_sigma?: number | null; locked?: boolean;
}
export interface Gated<T> { rows: T[]; total: number; locked: number; plan: string }

export interface Plan {
  key: "free" | "essential" | "pro"; name: string; monthly: number; annual: number; tagline: string; cta: string;
  note: string; badge: string | null; features: string[]; limits: Record<string, number | string | boolean | null>;
}
export interface User {
  id: number; email: string; handle: string; display_name: string; plan: Plan["key"]; is_admin: boolean;
  verified_trader: boolean; limits: Plan["limits"];
}
export interface ArticleCard {
  slug: string; title: string; category: string; tickers: string[]; summary: string; author: string;
  published_at: string; read_minutes: number; premium: boolean;
}
export interface Article extends ArticleCard { body_md: string; locked: boolean; lock_reason: string | null; free_remaining: number | null }
export interface ThreadRow {
  id: number; title: string; community: string; community_slug: string; author: string; score: number; replies: number;
  tickers: string[]; created_at: string; last_activity_at: string;
}
export interface Trade {
  id: number; author: string; long: string; short: string | null; thesis: string; entry_long: number;
  entry_short: number | null; entry_source: Source; verification: string; status: "open" | "closed";
  exit_long: number | null; exit_short: number | null; return_pct: number | null; score: number; created_at: string;
  closed_at: string | null;
}
export interface TickerPage {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  quote: Quote; history: HistoryPoint[]; info: Record<string, any>;
  grade: (RvRow & { peers: { symbol: string; grade: string; multiple?: number | null; rv_percentile?: number | null }[] }) | null;
  grade_history: { as_of: string; grade: string; rv_percentile: number }[];
}

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

const TOKEN_KEY = "irai_token";
export const token = {
  get: () => { try { return localStorage.getItem(TOKEN_KEY); } catch { return null; } },
  set: (t: string | null) => { try { if (t) localStorage.setItem(TOKEN_KEY, t); else localStorage.removeItem(TOKEN_KEY); } catch {} },
};

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const t = typeof window !== "undefined" ? token.get() : null;
  if (t) headers.set("Authorization", `Bearer ${t}`);
  let body = init.body;
  if (init.json !== undefined) { headers.set("Content-Type", "application/json"); body = JSON.stringify(init.json); }
  const res = await fetch(path, { ...init, headers, body, credentials: "include" });
  if (!res.ok) {
    let msg = res.statusText;
    try { const j = await res.json(); msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j); } catch {}
    throw new ApiError(res.status, msg);
  }
  return res.json() as Promise<T>;
}
