"use client";
import Link from "next/link";
import { useState } from "react";
import { useApi } from "@/lib/hooks";
import { pct, tone } from "@/lib/format";
import { useAuth } from "@/components/AuthProvider";
import { BrokerTile } from "@/components/Bots";
import { Sparkline } from "@/components/Chart";
import { Button, Card, Skeleton } from "@/components/ui";

interface Tpl { key: string; title: string; category: string; audience: string; summary: string; strategy_title: string;
  config: { mode: string; symbols: string[]; stop_loss_pct?: number | null; take_profit_pct?: number | null; daily_auto_close?: boolean };
  backtest: { stats: Record<string, number | null>; start: string; end: string; spark: number[] } | null }
interface Brokers { brokers: { key: string; name: string; url?: string; status: string }[]; note: string }
const CATS = ["all", "trend", "momentum", "mean-reversion", "breakout", "income", "signals"];

export default function Trade() {
  const { user } = useAuth();
  const { data: tpls } = useApi<Tpl[]>("/api/trade/templates");
  const { data: br } = useApi<Brokers>("/api/trade/brokers");
  const [cat, setCat] = useState("all");
  const pro = user?.plan === "pro";
  const shown = (tpls ?? []).filter(t => cat === "all" || t.category === cat);
  const use = (k: string) => (pro ? `/bots/new?template=${k}` : user ? "/pricing" : `/signup?next=${encodeURIComponent(`/bots/new?template=${k}`)}`);
  return (
    <div className="mx-auto max-w-7xl px-4 py-10">
      <div className="text-xs uppercase tracking-wide text-primary">IRAI AlgoTrader</div>
      <h1 className="text-3xl">Trade</h1>
      <p className="mt-1 max-w-2xl text-sm text-muted">Start from a ready-made strategy, see how it would have done, and launch it as a paper-trading bot with your own risk controls. Or connect a brokerage account.</p>

      <div className="mt-8 flex flex-wrap items-end justify-between gap-3">
        <h2 className="text-xl">Ready-made strategies</h2>
        <div className="flex flex-wrap gap-1 rounded-lg bg-accent p-1 text-xs">{CATS.map(c => <button key={c} onClick={() => setCat(c)} className={`rounded-md px-2.5 py-1 capitalize ${cat === c ? "bg-card text-fg shadow-sm" : "text-muted"}`}>{c.replace("-", " ")}</button>)}</div>
      </div>
      {!tpls ? <div className="mt-4"><Skeleton rows={6} /></div> : (
        <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-4">{shown.map(t => {
          const s = t.backtest?.stats;
          return (
            <Card key={t.key} className="flex flex-col p-5">
              <div className="flex items-start justify-between gap-2"><span className="rounded bg-accent px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted">{t.category.replace("-", " ")}</span><span className="text-[11px] text-muted">{t.audience}</span></div>
              <h3 className="mt-2 text-lg">{t.title}</h3>
              <p className="mt-1 flex-1 text-sm text-muted">{t.summary}</p>
              {t.backtest?.spark && t.backtest.spark.length > 3 && <div className="mt-3"><Sparkline values={t.backtest.spark} width={260} height={44} /></div>}
              {s ? <div className="mt-3 grid grid-cols-3 gap-2 text-center text-xs num">
                <div><div className="text-[10px] text-muted">CAGR</div><div className={tone(s.cagr)}>{pct(s.cagr, 1)}</div></div>
                <div><div className="text-[10px] text-muted">Sharpe</div><div>{s.sharpe?.toFixed(2) ?? "—"}</div></div>
                <div><div className="text-[10px] text-muted">Max DD</div><div className="text-down">{pct(s.max_drawdown, 1)}</div></div>
              </div> : <p className="mt-3 text-xs text-muted">Trades on your own signals, so there&apos;s no backtest.</p>}
              <div className="mt-3 text-[11px] text-muted">{t.strategy_title} · {t.config.symbols.join(", ") || "your alerts"}{t.config.stop_loss_pct ? ` · ${Math.round(t.config.stop_loss_pct * 100)}% stop` : ""}{t.config.daily_auto_close ? " · daily close" : ""}</div>
              <Button className="mt-4" href={use(t.key)}>Use this strategy</Button>
            </Card>);
        })}</div>)}
      <p className="mt-2 text-[11px] text-muted">Backtests: two years of daily data, equal weight across symbols, 2 bps slippage and 1 bp commission. Hypothetical results; examples, not recommendations. Want more? <Link href="/strategies" className="text-primary">Browse the community strategy marketplace</Link>.</p>

      <h2 className="mt-12 text-xl">Connect a brokerage</h2>
      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card className="p-5"><div className="flex items-center justify-between"><h3 className="font-semibold">IRAI paper trading</h3><span className="rounded bg-up/15 px-2 py-0.5 text-[11px] text-up">Connected</span></div>
          <p className="mt-1 text-sm text-muted">Simulated accounts for testing bots with realistic costs. Up to five accounts.</p>
          <Button className="mt-3" variant="outline" href={pro ? "/bots" : "/pricing"}>Open paper accounts</Button></Card>
        <Card className="p-5 lg:col-span-2"><div className="flex items-center justify-between"><h3 className="font-semibold">Live brokers</h3><span className="rounded bg-accent px-2 py-0.5 text-[11px] text-muted">Coming soon</span></div>
          <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3">{(br?.brokers ?? []).map(b => (
            <div key={b.key} className="rounded-xl border border-line p-2"><BrokerTile k={b.key} name={b.name} size="sm" />
              <Link href="/algotrader#waitlist" className="mt-2 block text-center text-[11px] text-primary">Notify me</Link></div>))}</div>
          <p className="mt-3 text-[11px] text-muted">{br?.note} Live orders will always need your confirmation. Irradiance is non-custodial and never holds your funds. Broker names and marks are trademarks of their respective owners; no affiliation or endorsement is implied.</p></Card>
      </div>
    </div>
  );
}
