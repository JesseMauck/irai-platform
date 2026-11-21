"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useAuth } from "@/components/AuthProvider";
import { BrokerStrip, type StrategySchema, usd } from "@/components/Bots";
import { TickerInput } from "@/components/TickerInput";
import { Button, Card, ErrorNote } from "@/components/ui";

interface Acct { id: number; name: string; cash: number; equity: number }
interface Draft { strategy: string; params: Record<string, number>; symbols: string[]; stop_loss_pct: number | null; take_profit_pct: number | null; daily_auto_close: boolean; name?: string | null; explanation: string; engine: string }
const IDEAS = [
  "Golden cross on SPY and QQQ: buy when the 50-day crosses above the 200-day, 10% stop-loss",
  "Buy mega-cap tech (AAPL, MSFT, NVDA, GOOGL) when RSI is oversold, take profit at 15%",
  "Breakout strategy on energy stocks XOM and CVX with an 8% stop",
  "Day-trade NVDA on TradingView alerts and close everything at the end of each day",
];
const STEPS = ["Create", "Connect", "Send"] as const;

export default function NewBot() {
  const { user, ready } = useAuth();
  const router = useRouter();
  const pro = user?.plan === "pro";
  const { data: meta } = useApi<{ strategies: StrategySchema[] }>(pro ? "/api/bots/strategies" : null);
  const { data: accts, reload: ra } = useApi<Acct[]>(pro ? "/api/paper/accounts" : null);
  const [step, setStep] = useState(0);
  const [idea, setIdea] = useState("");
  const [draft, setDraft] = useState<Draft | null>(null);
  const [mode, setMode] = useState<"strategy" | "webhook">("strategy");
  const [name, setName] = useState("");
  const [strategy, setStrategy] = useState("sma_cross");
  const [params, setParams] = useState<Record<string, number>>({});
  const [symbols, setSymbols] = useState<string[]>([]);
  const [add, setAdd] = useState("");
  const [risk, setRisk] = useState({ stop: "", tp: "", cap: "100", auto: false });
  const [alloc, setAlloc] = useState<Record<number, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<Error | null>(null);
  const schema = meta?.strategies.find(s => s.key === strategy);
  useEffect(() => { if (schema && !Object.keys(params).length) setParams(Object.fromEntries(schema.params.map(p => [p.key, p.default]))); }, [schema, params]);
  if (!ready) return null;
  if (!pro) return <div className="mx-auto max-w-md px-4 py-20 text-center"><p>Trading bots are part of Irradiance Pro.</p><Button href="/pricing" className="mt-4">See Pro</Button></div>;

  const runDraft = async () => {
    setBusy("draft"); setErr(null);
    try {
      const d = await api<Draft>("/api/bots/draft", { method: "POST", json: { prompt: idea } });
      setDraft(d); setStrategy(d.strategy); setParams(d.params); if (d.symbols.length) setSymbols(d.symbols);
      setRisk(r => ({ ...r, stop: d.stop_loss_pct ? String(+(d.stop_loss_pct * 100).toFixed(2)) : "", tp: d.take_profit_pct ? String(+(d.take_profit_pct * 100).toFixed(2)) : "", auto: d.daily_auto_close }));
      if (/alert|webhook|tradingview|signal/i.test(idea)) setMode("webhook");
      if (!name) setName(d.name || idea.slice(0, 60));
    } catch (e) { setErr(e as Error); } finally { setBusy(null); }
  };
  const addSym = (s: string) => { const x = s.trim().toUpperCase(); if (x && !symbols.includes(x) && symbols.length < 20) setSymbols([...symbols, x]); setAdd(""); };
  const newAcct = async () => { try { await api("/api/paper/accounts", { method: "POST", json: { name: "Paper account", starting_cash: 100000 } }); ra(); } catch (e) { setErr(e as Error); } };
  const funding = Object.entries(alloc).map(([id, v]) => ({ account_id: parseInt(id), capital: parseFloat(v.replace(/[,$]/g, "")) })).filter(f => f.capital > 0);
  const canCreate = name.trim() && funding.length && (mode === "webhook" || symbols.length);
  const create = async () => {
    setBusy("create"); setErr(null);
    const f = (s: string) => (s.trim() ? parseFloat(s) / 100 : null);
    try {
      const b = await api<{ id: number }>("/api/bots", { method: "POST", json: {
        name: name.trim(), description: idea || null, mode, strategy: mode === "strategy" ? strategy : null, params, symbols,
        max_position_pct: Math.min(1, Math.max(0.01, (parseFloat(risk.cap) || 100) / 100)), stop_loss_pct: f(risk.stop), take_profit_pct: f(risk.tp),
        daily_auto_close: risk.auto, accounts: funding } });
      router.push(`/bots/${b.id}?new=1`);
    } catch (e) { setErr(e as Error); setBusy(null); }
  };

  return (
    <div className="mx-auto max-w-4xl px-4 py-10">
      <Link href="/bots" className="text-sm text-muted hover:text-fg">← Bots</Link>
      <h1 className="mt-3 text-3xl">Create a bot</h1>
      <ol className="mt-5 flex gap-2">{STEPS.map((s, i) => (
        <li key={s}><button onClick={() => i <= step && setStep(i)} className={`flex items-center gap-2 rounded-full border px-4 py-1.5 text-sm ${i === step ? "border-primary bg-primary/10" : i < step ? "border-line" : "border-line text-muted"}`}>
          <span className="stat">{i + 1}</span>{s}</button></li>))}</ol>
      <ErrorNote error={err} />

      {step === 0 && (
        <div className="mt-6 space-y-4">
          <Card className="p-5">
            <h2 className="font-semibold">Describe your strategy</h2>
            <p className="text-sm text-muted">Plain English is fine. IRAI matches it to a tested rule, sets the parameters and risk controls, and shows you exactly what it built.</p>
            <textarea value={idea} onChange={e => setIdea(e.target.value)} rows={3} placeholder="e.g. Buy SPY when the 50-day average crosses above the 200-day; 10% stop-loss" className="mt-3 w-full rounded-lg border border-line bg-bg p-3 text-sm" />
            <div className="mt-2 flex flex-wrap gap-1.5">{IDEAS.map(x => <button key={x} onClick={() => setIdea(x)} className="rounded-full border border-line px-2.5 py-0.5 text-[11px] text-muted hover:border-primary hover:text-fg">{x.slice(0, 48)}…</button>)}</div>
            <Button className="mt-3" onClick={runDraft} disabled={idea.trim().length < 3 || busy === "draft"}>{busy === "draft" ? "Building…" : "Build it"}</Button>
            {draft && <p className="mt-3 rounded-lg border border-primary/30 bg-primary/5 p-3 text-sm">{draft.explanation} <span className="text-[11px] text-muted">({draft.engine === "claude" ? "AI-drafted" : "keyword match"})</span></p>}
          </Card>
          <Card className="p-5">
            <div className="flex flex-wrap items-center justify-between gap-2"><h2 className="font-semibold">Bot</h2>
              <div className="flex gap-1 rounded bg-accent p-0.5 text-xs">{(["strategy", "webhook"] as const).map(m => <button key={m} onClick={() => setMode(m)} className={`rounded px-3 py-1 ${mode === m ? "bg-card shadow-sm" : "text-muted"}`}>{m === "strategy" ? "Strategy rule" : "Webhook signals"}</button>)}</div></div>
            <input value={name} onChange={e => setName(e.target.value)} placeholder="Bot name" className="mt-3 w-full rounded border border-line bg-bg px-3 py-2 text-sm" maxLength={80} />
            {mode === "strategy" ? <>
              <select value={strategy} onChange={e => { setStrategy(e.target.value); setParams({}); }} className="mt-3 w-full rounded border border-line bg-bg px-2 py-2 text-sm">{meta?.strategies.map(s => <option key={s.key} value={s.key}>{s.title}</option>)}</select>
              {schema && <p className="mt-1 text-xs text-muted">{schema.description}</p>}
              <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-4">{schema?.params.map(p => (
                <label key={p.key} className="text-xs text-muted">{p.label}<input type="number" min={p.min} max={p.max} step={p.step} value={params[p.key] ?? p.default}
                  onChange={e => setParams({ ...params, [p.key]: parseFloat(e.target.value) })} className="mt-1 w-full rounded border border-line bg-bg px-2 py-1 text-sm text-fg num" /></label>))}</div>
            </> : <p className="mt-3 text-sm text-muted">Webhook bots trade when you send a signal, for example a TradingView alert. You&apos;ll get a private URL in step 3.</p>}
            <div className="mt-4"><div className="text-xs text-muted">Symbols {mode === "webhook" && "(optional: restrict which tickers signals may trade)"}</div>
              <div className="mt-1.5 flex flex-wrap gap-1.5">{symbols.map(s => <span key={s} className="flex items-center gap-1 rounded-full bg-accent px-2.5 py-0.5 text-sm num">{s}<button onClick={() => setSymbols(symbols.filter(x => x !== s))} className="text-muted hover:text-down">×</button></span>)}</div>
              <div className="mt-2 flex max-w-sm gap-2"><div className="flex-1"><TickerInput value={add} onChange={setAdd} onPick={addSym} placeholder="Add a ticker" /></div><Button variant="outline" onClick={() => addSym(add)} disabled={!add}>Add</Button></div></div>
          </Card>
          <Card className="p-5">
            <h2 className="font-semibold">Risk controls</h2>
            <div className="mt-3 grid gap-3 md:grid-cols-4">
              <label className="text-xs text-muted">Max per position (% of the bot&apos;s capital)<input value={risk.cap} onChange={e => setRisk({ ...risk, cap: e.target.value })} className="mt-1 w-full rounded border border-line bg-bg px-2 py-1 text-sm text-fg num" /></label>
              <label className="text-xs text-muted">Stop-loss % (blank = none)<input value={risk.stop} onChange={e => setRisk({ ...risk, stop: e.target.value })} placeholder="e.g. 8" className="mt-1 w-full rounded border border-line bg-bg px-2 py-1 text-sm text-fg num" /></label>
              <label className="text-xs text-muted">Take-profit % (blank = none)<input value={risk.tp} onChange={e => setRisk({ ...risk, tp: e.target.value })} placeholder="e.g. 20" className="mt-1 w-full rounded border border-line bg-bg px-2 py-1 text-sm text-fg num" /></label>
              <label className="flex items-end gap-2 pb-1 text-sm"><input type="checkbox" checked={risk.auto} onChange={e => setRisk({ ...risk, auto: e.target.checked })} /> Close all positions daily (15:55 ET)</label>
            </div>
            <p className="mt-2 text-[11px] text-muted">With several symbols, each gets an equal share of the bot&apos;s capital, up to the per-position cap. Stops and targets are checked every 5 minutes during market hours against each position&apos;s average cost.</p>
          </Card>
          <div className="flex justify-end"><Button onClick={() => setStep(1)} disabled={!name.trim() || (mode === "strategy" && !symbols.length)}>Next: connect accounts →</Button></div>
        </div>)}

      {step === 1 && (
        <div className="mt-6 space-y-4">
          <Card className="p-5">
            <h2 className="font-semibold">Fund the bot from your paper accounts</h2>
            <p className="text-sm text-muted">One bot can feed several accounts. Each account gives it a separate allocation and keeps its own positions.</p>
            {!accts?.length ? <div className="mt-3 text-sm"><p>You don&apos;t have a paper account yet.</p><Button className="mt-2" onClick={newAcct}>Create a $100,000 paper account</Button></div> : (
              <ul className="mt-3 divide-y divide-line">{accts.map(a => (
                <li key={a.id} className="flex flex-wrap items-center justify-between gap-3 py-2.5">
                  <div><div className="font-medium">{a.name}</div><div className="text-xs text-muted num">{usd(a.cash)} unallocated of {usd(a.equity)}</div></div>
                  <div className="flex items-center gap-2"><span className="text-xs text-muted">Allocate</span>
                    <input value={alloc[a.id] ?? ""} onChange={e => setAlloc({ ...alloc, [a.id]: e.target.value })} placeholder="$0" className="w-32 rounded border border-line bg-bg px-2 py-1 text-sm num" />
                    <button onClick={() => setAlloc({ ...alloc, [a.id]: String(Math.floor(a.cash * 0.25)) })} className="text-xs text-muted hover:text-fg">25%</button>
                    <button onClick={() => setAlloc({ ...alloc, [a.id]: String(Math.floor(a.cash)) })} className="text-xs text-muted hover:text-fg">All</button></div>
                </li>))}</ul>)}
            {accts && accts.length > 0 && accts.length < 5 && <button onClick={newAcct} className="mt-2 text-xs text-primary">+ New paper account</button>}
          </Card>
          <Card className="p-5"><h2 className="font-semibold">Live brokers</h2><p className="mb-3 text-sm text-muted">Coming soon: route the same bot to your real brokerage account, with every order confirmed by you.</p><BrokerStrip /></Card>
          <div className="flex justify-between"><Button variant="ghost" onClick={() => setStep(0)}>← Back</Button><Button onClick={() => setStep(2)} disabled={!funding.length}>Next: signals →</Button></div>
        </div>)}

      {step === 2 && (
        <div className="mt-6 space-y-4">
          <Card className="p-5">
            <h2 className="font-semibold">{mode === "webhook" ? "Send signals" : "How it trades"}</h2>
            {mode === "webhook" ? <>
              <p className="mt-1 text-sm text-muted">After you create the bot you&apos;ll get a private webhook URL. Paste it into a TradingView alert (Notifications → Webhook URL) with a message like:</p>
              <pre className="mt-3 overflow-x-auto rounded-lg bg-accent p-3 text-xs">{`{"ticker": "{{ticker}}", "action": "{{strategy.order.action}}"}`}</pre>
              <p className="mt-2 text-xs text-muted">Actions: <code>buy</code>, <code>sell</code> or <code>exit</code>. Optional <code>quantity</code> (shares) or <code>percent</code> (of the bot&apos;s capital in each account). Every signal is applied to all funded accounts and logged.</p>
            </> : <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
              <li>The rule runs on daily closes {risk.auto ? "each morning at 09:35 ET (because the bot closes out daily)" : "each trading day around 15:45 ET"}, and positions move to its target.</li>
              <li>Risk controls are checked every 5 minutes while the market is open.</li>
              <li>You can also send webhook signals to a strategy bot, pause it, or run it on demand.</li>
              <li>On creation IRAI backtests the rule over two years so you can track live results against it.</li></ul>}
          </Card>
          <Card className="p-5 text-sm">
            <h2 className="font-semibold">Summary</h2>
            <dl className="mt-2 grid grid-cols-2 gap-y-1"><dt className="text-muted">Bot</dt><dd>{name}</dd><dt className="text-muted">Type</dt><dd>{mode === "webhook" ? "Webhook signals" : schema?.title}</dd>
              <dt className="text-muted">Symbols</dt><dd>{symbols.join(", ") || "any"}</dd>
              <dt className="text-muted">Risk</dt><dd>cap {risk.cap || 100}% · stop {risk.stop ? `${risk.stop}%` : "none"} · target {risk.tp ? `${risk.tp}%` : "none"}{risk.auto ? " · daily auto-close" : ""}</dd>
              <dt className="text-muted">Capital</dt><dd className="num">{usd(funding.reduce((a, f) => a + f.capital, 0))} across {funding.length} account{funding.length === 1 ? "" : "s"}</dd></dl>
          </Card>
          <div className="flex justify-between"><Button variant="ghost" onClick={() => setStep(1)}>← Back</Button><Button onClick={create} disabled={!canCreate || busy === "create"}>{busy === "create" ? "Backtesting and creating…" : "Create bot"}</Button></div>
          <p className="text-[11px] text-muted">Paper trading only: simulated money, no real orders. Hypothetical results don&apos;t predict live performance. Irradiance doesn&apos;t hold funds or give advice; you decide what your bots do.</p>
        </div>)}
    </div>
  );
}
