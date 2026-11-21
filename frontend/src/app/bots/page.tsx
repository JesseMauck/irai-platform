"use client";
import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { pct, tone } from "@/lib/format";
import { useAuth } from "@/components/AuthProvider";
import { usd } from "@/components/Bots";
import { Button, Card, ErrorNote, Skeleton } from "@/components/ui";

interface Acct { id: number; name: string; starting_cash: number; cash: number; equity: number; return: number | null; bots: { bot_id: number; name: string; capital: number; equity: number }[] }
interface BotRow { id: number; name: string; mode: string; strategy: string | null; symbols: string[]; status: string; capital: number; equity: number; return: number | null; accounts: number; positions: number; backtest_cagr: number | null }

export default function BotsPage() {
  const { user, ready } = useAuth();
  const pro = user?.plan === "pro";
  const { data: accts, reload: ra } = useApi<Acct[]>(pro ? "/api/paper/accounts" : null, 60_000);
  const { data: bots, reload: rb } = useApi<BotRow[]>(pro ? "/api/bots" : null, 60_000);
  const [err, setErr] = useState<Error | null>(null);
  if (!ready) return null;
  if (!pro) return (
    <div className="mx-auto max-w-3xl px-4 py-20 text-center">
      <span className="rounded-full border border-primary/40 px-3 py-1 text-xs text-primary">Pro · paper trading</span>
      <h1 className="mt-4 text-4xl">Trading bots</h1>
      <p className="mt-3 text-muted">Build a bot in plain English, test it on years of history, then run it on paper accounts with stop-loss, take-profit and daily auto-close controls. Track live results against the backtest.</p>
      <div className="mt-6 flex justify-center gap-3">{user ? <Button href="/pricing">Upgrade to Pro</Button> : <Button href="/login?next=/bots">Sign in</Button>}<Button variant="outline" href="/algotrader">How it works</Button></div>
    </div>);
  const newAcct = async () => {
    const amt = prompt("Starting cash for the new paper account (USD)", "100000"); if (!amt) return;
    try { await api("/api/paper/accounts", { method: "POST", json: { name: `Paper account ${(accts?.length ?? 0) + 1}`, starting_cash: parseFloat(amt.replace(/[,$]/g, "")) } }); ra(); } catch (e) { setErr(e as Error); }
  };
  const delAcct = async (a: Acct) => { if (!confirm(`Delete ${a.name}? Its bots' capital in this account is deleted with it.`)) return; try { await api(`/api/paper/accounts/${a.id}`, { method: "DELETE" }); ra(); rb(); } catch (e) { setErr(e as Error); } };
  return (
    <div className="mx-auto max-w-7xl px-4 py-10">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><div className="text-xs uppercase tracking-wide text-primary">IRAI AlgoTrader · paper trading</div><h1 className="text-3xl">Trading bots</h1>
          <p className="mt-1 max-w-2xl text-sm text-muted">Bots trade simulated money in your paper accounts. One bot can feed several accounts, each with its own allocation.</p></div>
        <div className="flex gap-2"><Button variant="outline" onClick={newAcct}>New paper account</Button><Button href="/bots/new">Create a bot</Button></div>
      </div>
      <ErrorNote error={err} />

      <h2 className="mt-8 font-semibold">Paper accounts</h2>
      {!accts ? <Skeleton rows={2} /> : !accts.length ? (
        <Card className="mt-3 p-6 text-sm"><p>Start with a paper account: simulated cash your bots can trade.</p><Button className="mt-3" onClick={newAcct}>Create paper account</Button></Card>) : (
        <div className="mt-3 grid gap-3 md:grid-cols-2 lg:grid-cols-3">{accts.map(a => (
          <Card key={a.id} className="p-4">
            <div className="flex items-start justify-between"><div className="font-medium">{a.name}</div><button onClick={() => delAcct(a)} className="text-xs text-muted hover:text-down">Delete</button></div>
            <div className="stat mt-1 text-2xl num">{usd(a.equity)}</div>
            <div className={`text-sm num ${tone(a.return)}`}>{pct(a.return, 2)} since start ({usd(a.starting_cash)})</div>
            <div className="mt-2 text-xs text-muted num">Unallocated cash {usd(a.cash)} · {a.bots.length} bot{a.bots.length === 1 ? "" : "s"}</div>
            {a.bots.length > 0 && <ul className="mt-2 space-y-0.5 text-xs">{a.bots.map(b => <li key={b.bot_id} className="flex justify-between"><Link href={`/bots/${b.bot_id}`} className="hover:text-primary">{b.name}</Link><span className="num text-muted">{usd(b.equity)}</span></li>)}</ul>}
          </Card>))}</div>)}

      <h2 className="mt-8 font-semibold">Bots</h2>
      {!bots ? <Skeleton rows={3} /> : !bots.length ? (
        <Card className="mt-3 p-6 text-sm"><p>No bots yet. Describe a strategy in plain English and IRAI will build it.</p><Button className="mt-3" href="/bots/new">Create a bot</Button></Card>) : (
        <Card className="mt-3 overflow-x-auto p-0"><table className="w-full min-w-[760px] text-sm">
          <thead className="text-xs text-muted"><tr>{["Bot", "Type", "Symbols", "Accounts", "Capital", "Equity", "Return", "Backtest CAGR", "Status"].map((h, i) => <th key={h} className={`px-4 py-2 font-normal ${i ? "text-right" : "text-left"}`}>{h}</th>)}</tr></thead>
          <tbody className="divide-y divide-line">{bots.map(b => (
            <tr key={b.id}><td className="px-4 py-2"><Link href={`/bots/${b.id}`} className="font-medium hover:text-primary">{b.name}</Link></td>
              <td className="px-4 text-right text-xs text-muted">{b.mode === "webhook" ? "Webhook" : b.strategy}</td>
              <td className="px-4 text-right text-xs">{b.symbols.join(", ") || "any"}</td><td className="px-4 text-right num">{b.accounts}</td>
              <td className="px-4 text-right num">{usd(b.capital)}</td><td className="px-4 text-right num">{usd(b.equity)}</td>
              <td className={`px-4 text-right num ${tone(b.return)}`}>{pct(b.return, 2)}</td><td className="px-4 text-right num text-muted">{pct(b.backtest_cagr, 1)}</td>
              <td className="px-4 text-right"><span className={`rounded px-2 py-0.5 text-[11px] ${b.status === "running" ? "bg-up/15 text-up" : "bg-accent text-muted"}`}>{b.status}</span></td></tr>))}</tbody></table></Card>)}
      <p className="mt-6 text-[11px] text-muted">Paper trading uses simulated money and fills at the latest quoted price with modelled slippage and commission; real fills can differ. Results are hypothetical and don&apos;t predict live performance. Irradiance does not hold funds, place real orders or give advice.</p>
    </div>
  );
}
