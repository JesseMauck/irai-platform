"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { ago, compact, num, pct } from "@/lib/format";
import { useAuth } from "@/components/AuthProvider";
import { Button, Card, ErrorNote, PageHeader } from "@/components/ui";

interface Company {
  ticker: string; name: string; price: number; currency: string; sector: string | null; industry: string | null;
  market_cap: number | null; demo: boolean; suggested_method: string; method_reason: string;
  latest: { fiscal_year: number; revenue: number; revenue_growth: number; operating_margin: number; roic: number | null };
}
interface Run { id: string; ticker: string; status: string; value_per_share: number | null; price: number | null; upside: number | null; created_at: string }
const STORIES = [
  ["growth", "Growth", "How big can revenue get, and how fast?"],
  ["profitability", "Profitability", "What margins at scale, and why?"],
  ["efficiency", "Reinvestment", "How much capital does growth need?"],
  ["risk", "Risk", "What could go wrong; where is revenue earned?"],
  ["moat", "Competitive advantage", "How long can returns beat the cost of capital?"],
] as const;

function ValueBotForm() {
  const params = useSearchParams();
  const router = useRouter();
  const { user } = useAuth();
  const [ticker, setTicker] = useState(params.get("ticker")?.toUpperCase() ?? "");
  const [debounced, setDebounced] = useState(ticker);
  const [stance, setStance] = useState<"neutral" | "bullish" | "bearish">("neutral");
  const [thesis, setThesis] = useState("");
  const [stories, setStories] = useState<Record<string, string>>({});
  const [method, setMethod] = useState("auto");
  const [err, setErr] = useState<Error | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { const id = setTimeout(() => setDebounced(ticker.trim().toUpperCase()), 400); return () => clearTimeout(id); }, [ticker]);
  const { data: co, error: coErr, loading } = useApi<Company>(debounced ? `/api/valuebot/company/${encodeURIComponent(debounced)}` : null);
  const { data: usage } = useApi<{ used: number; limit: number | null; remaining: number | null }>(user ? "/api/valuebot/usage" : null);
  const { data: runs } = useApi<Run[]>(user ? "/api/valuebot/jobs" : null);

  const draft = async () => {
    if (!co) return;
    setBusy(true); setErr(null);
    try {
      const d = await api<{ thesis: string; stories?: Record<string, string> }>("/api/valuebot/thesis", { method: "POST", json: { ticker: co.ticker, stance } });
      setThesis(d.thesis); if (d.stories) setStories(d.stories);
    } catch (e) { setErr(e as Error); } finally { setBusy(false); }
  };
  const submit = async () => {
    if (!user) { router.push("/login?next=/valuebot"); return; }
    setBusy(true); setErr(null);
    try {
      const r = await api<{ id: string }>("/api/valuebot/jobs", { method: "POST", json: { ticker: debounced, stance, thesis, stories, method } });
      router.push(`/valuebot/${r.id}`);
    } catch (e) { setErr(e as Error); setBusy(false); }
  };

  return (
    <div className="mx-auto max-w-6xl px-4 py-12">
      <PageHeader title="ValueBot" intro="Pick a public company, tell its story, and get a Damodaran-style narrative-and-numbers valuation: a written report, an editable Excel model with live formulas, and bull, bear and market-implied scenarios.">
        {usage && <div className="text-sm text-muted">{usage.limit == null ? "Unlimited runs" : `${usage.remaining} of ${usage.limit} runs left this month`}</div>}
      </PageHeader>
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card className="p-6">
            <label className="text-sm font-medium" htmlFor="tk">1 · Company</label>
            <input id="tk" value={ticker} onChange={e => setTicker(e.target.value)} placeholder="Ticker, e.g. AAPL, MSFT, JPM, TM (or DEMO)"
              className="mt-2 w-full rounded-lg border border-line bg-bg px-4 py-3 text-lg uppercase outline-none focus:border-primary" />
            {loading && debounced && <p className="mt-3 text-sm text-muted">Looking up {debounced} in SEC filings and market data…</p>}
            {coErr && <p className="mt-3 text-sm text-down">{coErr.message}</p>}
            {co && (
              <div className="mt-4 grid gap-3 rounded-lg bg-accent/50 p-4 text-sm md:grid-cols-2">
                <div><div className="text-base font-semibold">{co.name} {co.demo && <span className="text-xs text-muted">(fictional demo)</span>}</div>
                  <div className="text-muted">{[co.sector, co.industry].filter(Boolean).join(" · ")}</div>
                  <div className="mt-1 num">{num(co.price)} {co.currency} · mkt cap {compact(co.market_cap)}</div></div>
                <div className="num text-muted">FY{co.latest.fiscal_year}: revenue {compact(co.latest.revenue)} ({pct(co.latest.revenue_growth, 1)}) · op. margin {pct(co.latest.operating_margin, 1, false)}
                  <div className="mt-1 text-fg">Suggested method: <b>{co.suggested_method.toUpperCase()}</b></div><div className="text-xs">{co.method_reason}</div></div>
              </div>
            )}
          </Card>
          <Card className="p-6">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">2 · The story</span>
              <div className="flex gap-1 rounded-lg border border-line p-1 text-xs">
                {(["bearish", "neutral", "bullish"] as const).map(s => <button key={s} onClick={() => setStance(s)} className={`rounded px-3 py-1 capitalize ${stance === s ? "bg-accent text-fg" : "text-muted"}`}>{s}</button>)}
              </div>
            </div>
            <textarea value={thesis} onChange={e => setThesis(e.target.value)} rows={4} placeholder="Your investment thesis in a few sentences. Leave blank and ValueBot drafts one for the stance you picked."
              className="mt-3 w-full rounded-lg border border-line bg-bg p-3 text-sm outline-none focus:border-primary" />
            <div className="mt-2"><Button variant="ghost" onClick={draft} disabled={!co || busy}>✦ Draft a {stance} thesis for me</Button></div>
            <div className="mt-4 grid gap-3 md:grid-cols-2">
              {STORIES.map(([k, label, hint]) => (
                <div key={k}><label className="text-xs text-muted">{label}</label>
                  <textarea rows={2} value={stories[k] ?? ""} onChange={e => setStories(s => ({ ...s, [k]: e.target.value }))} placeholder={hint}
                    className="mt-1 w-full rounded-lg border border-line bg-bg p-2 text-sm outline-none focus:border-primary" /></div>
              ))}
            </div>
          </Card>
          <Card className="flex flex-col gap-4 p-6 md:flex-row md:items-center md:justify-between">
            <div>
              <span className="text-sm font-medium">3 · Method</span>
              <select value={method} onChange={e => setMethod(e.target.value)} className="ml-3 rounded-lg border border-line bg-bg px-3 py-2 text-sm">
                <option value="auto">Auto</option><option value="fcff">FCFF DCF</option><option value="excess_return">Excess return (financials)</option><option value="ddm">Dividend discount</option>
              </select>
            </div>
            <Button onClick={submit} disabled={!co || busy}>{busy ? "Starting…" : user ? "Run valuation →" : "Sign in to run →"}</Button>
          </Card>
          <ErrorNote error={err} />
        </div>
        <Card className="h-fit p-5">
          <h2 className="font-semibold">Your runs</h2>
          {!user && <p className="mt-2 text-sm text-muted"><Link href="/login" className="text-primary">Sign in</Link> to run valuations and keep their reports and models.</p>}
          <ul className="mt-3 divide-y divide-line text-sm">
            {(runs ?? []).map(r => (
              <li key={r.id} className="py-2"><Link href={`/valuebot/${r.id}`} className="flex justify-between hover:text-primary">
                <span className="font-semibold">{r.ticker}</span><span className="num text-muted">{r.status === "done" ? `${num(r.value_per_share)} (${pct(r.upside, 0)})` : r.status}</span></Link>
                <div className="text-xs text-muted">{ago(r.created_at)}</div></li>
            ))}
            {user && runs?.length === 0 && <li className="py-2 text-muted">No runs yet.</li>}
          </ul>
          <p className="mt-4 text-xs text-muted">Output is an AI-assisted starting point for your own analysis, not investment advice.</p>
        </Card>
      </div>
    </div>
  );
}

export default function Page() { return <Suspense><ValueBotForm /></Suspense>; }
