"use client";
import Link from "next/link";
import { useState } from "react";
import { useApi } from "@/lib/hooks";
import { pct, tone } from "@/lib/format";
import { useAuth } from "@/components/AuthProvider";
import { Button, Card, Skeleton } from "@/components/ui";

export interface Listing { id: number; title: string; summary: string; category: string; price_monthly: number; copies: number; status: string;
  author: { handle: string; verified: boolean }; config: { mode: string; strategy: string | null; symbols: string[] } & Record<string, unknown>;
  backtest: Record<string, number | null>; live: { days: number; total_return: number | null; max_drawdown: number | null; since: string; sharpe: number | null } | null; created_at: string }
const CATS = ["all", "trend", "momentum", "mean-reversion", "breakout", "income", "signals", "other"];

export default function Marketplace() {
  const { user } = useAuth();
  const [cat, setCat] = useState("all");
  const [sort, setSort] = useState("popular");
  const [free, setFree] = useState(false);
  const { data } = useApi<Listing[]>(`/api/marketplace?sort=${sort}${cat !== "all" ? `&category=${cat}` : ""}${free ? "&free=true" : ""}`);
  return (
    <div className="mx-auto max-w-7xl px-4 py-10">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><div className="text-xs uppercase tracking-wide text-primary">Community</div><h1 className="text-3xl">Strategy marketplace</h1>
          <p className="mt-1 max-w-2xl text-sm text-muted">Bots configured and published by members, each with its backtest and, where the author runs it, a live paper track record. Copy one into your own paper account and adjust it.</p></div>
        {user?.plan === "pro" && <Button variant="outline" href="/bots">Publish one of your bots</Button>}
      </div>
      <div className="mt-6 flex flex-wrap items-center gap-2 text-xs">
        <div className="flex flex-wrap gap-1 rounded-lg bg-accent p-1">{CATS.map(c => <button key={c} onClick={() => setCat(c)} className={`rounded-md px-2.5 py-1 capitalize ${cat === c ? "bg-card text-fg shadow-sm" : "text-muted"}`}>{c.replace("-", " ")}</button>)}</div>
        <select value={sort} onChange={e => setSort(e.target.value)} className="rounded border border-line bg-bg px-2 py-1"><option value="popular">Most copied</option><option value="new">Newest</option></select>
        <label className="flex items-center gap-1"><input type="checkbox" checked={free} onChange={e => setFree(e.target.checked)} /> Free only</label>
      </div>
      {!data ? <div className="mt-6"><Skeleton rows={6} /></div> : !data.length ? (
        <Card className="mt-6 p-8 text-center text-sm"><p>No strategies published here yet.</p><p className="mt-1 text-muted">Pro members can publish any of their bots from its page.</p></Card>) : (
        <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-3">{data.map(x => (
          <Link key={x.id} href={`/strategies/${x.id}`} className="flex flex-col rounded-xl border border-line bg-card p-5 hover:border-primary">
            <div className="flex items-center justify-between text-[11px]"><span className="rounded bg-accent px-2 py-0.5 uppercase tracking-wide text-muted">{x.category.replace("-", " ")}</span>
              <span className={x.price_monthly ? "font-semibold" : "text-up"}>{x.price_monthly ? `$${x.price_monthly}/mo` : "Free"}</span></div>
            <h3 className="mt-2 text-lg">{x.title}</h3>
            <div className="text-[11px] text-muted">by @{x.author.handle}{x.author.verified && " ✓"} · {x.copies} cop{x.copies === 1 ? "y" : "ies"} · {x.config.symbols?.join(", ") || "signals"}</div>
            <p className="mt-2 flex-1 text-sm text-muted">{x.summary}</p>
            <div className="mt-3 grid grid-cols-3 gap-2 text-center text-xs num">
              <div><div className="text-[10px] text-muted">Backtest CAGR</div><div className={tone(x.backtest.cagr)}>{pct(x.backtest.cagr, 1)}</div></div>
              <div><div className="text-[10px] text-muted">Max DD</div><div className="text-down">{pct(x.backtest.max_drawdown, 1)}</div></div>
              <div><div className="text-[10px] text-muted">Live ({x.live?.days ?? 0}d)</div><div className={tone(x.live?.total_return)}>{x.live ? pct(x.live.total_return, 1) : "—"}</div></div>
            </div>
          </Link>))}</div>)}
      <p className="mt-6 text-[11px] text-muted">Strategies are published by members, not Irradiance, and are not recommendations. Backtests and paper results are hypothetical. Listings may not promise returns. Paid strategies open when creator payouts launch; free strategies can be copied now.</p>
    </div>
  );
}
