"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { ago, num, pct, tone } from "@/lib/format";
import { LineChart } from "@/components/Chart";
import { fmt, type Metric, REASON, type Stats, TearSheet, usd } from "@/components/Bots";
import { Button, Card, ErrorNote, Skeleton } from "@/components/ui";

interface Detail {
  id: number; name: string; description: string | null; mode: string; strategy: string | null; params: Record<string, number>; symbols: string[]; status: string;
  capital: number; equity: number; return: number | null; max_position_pct: number; stop_loss_pct: number | null; take_profit_pct: number | null; daily_auto_close: boolean;
  webhook_path: string; last_eval_on: string | null; market_open: boolean;
  strategy_schema: { title: string; description: string; params: { key: string; label: string }[] } | null;
  sleeves: { account_id: number; account: string | null; capital: number; cash: number; equity: number }[];
  positions: { account_id: number; symbol: string; quantity: number; avg_cost: number; price: number; value: number; unrealized: number; return: number }[];
  trades: { id: number; symbol: string; side: string; quantity: number; price: number; realized_pnl: number | null; reason: string; at: string | null }[];
  signals: { id: number; source: string; action: string; symbol: string | null; status: string; detail: string | null; at: string | null }[];
  live: { stats: Stats; series: { dates: string[]; equity: number[] }; days: number };
  backtest: { stats: Stats; start: string; end: string; series: { dates: string[]; equity: number[]; bench: number[] | null } } | null;
  comparison: { key: string; label: string; format: Metric["format"]; backtest: number | null; live: number | null; difference: number | null }[];
}

export default function BotPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const { data: b, reload, setData, error } = useApi<Detail>(`/api/bots/${id}`, 30_000);
  const { data: meta } = useApi<{ metrics: Metric[] }>("/api/bots/strategies");
  const [err, setErr] = useState<Error | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [risk, setRisk] = useState<{ stop: string; tp: string; cap: string; auto: boolean } | null>(null);
  const [origin, setOrigin] = useState("");
  const [tab, setTab] = useState<"live" | "backtest">("live");
  useEffect(() => { setOrigin(window.location.origin); }, []);
  useEffect(() => { if (b && !risk) setRisk({ stop: b.stop_loss_pct ? String(+(b.stop_loss_pct * 100).toFixed(2)) : "", tp: b.take_profit_pct ? String(+(b.take_profit_pct * 100).toFixed(2)) : "", cap: String(Math.round(b.max_position_pct * 100)), auto: b.daily_auto_close }); }, [b, risk]);
  if (error) return <div className="mx-auto max-w-3xl px-4 py-16 text-center text-muted">{error.message}</div>;
  if (!b || !risk) return <div className="mx-auto max-w-6xl px-4 py-12"><Skeleton rows={12} /></div>;
  const act = async (label: string, fn: () => Promise<unknown>) => { setBusy(label); setErr(null); try { await fn(); } catch (e) { setErr(e as Error); } finally { setBusy(null); } };
  const patch = (body: object) => act("patch", async () => setData(await api<Detail>(`/api/bots/${id}`, { method: "PATCH", json: body })));
  const saveRisk = () => patch({ stop_loss_pct: risk.stop ? parseFloat(risk.stop) / 100 : 0, take_profit_pct: risk.tp ? parseFloat(risk.tp) / 100 : 0,
    max_position_pct: Math.min(1, Math.max(0.01, (parseFloat(risk.cap) || 100) / 100)), daily_auto_close: risk.auto });
  const hook = `${origin}${b.webhook_path}`;
  const bt = b.backtest;
  const mcHref = `/lab/montecarlo?symbols=${b.symbols.join(",")}&start=${Math.round(b.equity)}`;
  return (
    <div className="mx-auto max-w-7xl px-4 py-10">
      <Link href="/bots" className="text-sm text-muted hover:text-fg">← Bots</Link>
      <div className="mt-3 flex flex-wrap items-start justify-between gap-3">
        <div><h1 className="text-3xl">{b.name} <span className={`ml-2 rounded px-2 py-0.5 align-middle text-xs ${b.status === "running" ? "bg-up/15 text-up" : "bg-accent text-muted"}`}>{b.status}</span></h1>
          <p className="mt-1 text-sm text-muted">{b.mode === "webhook" ? "Webhook signals" : b.strategy_schema?.title} · {b.symbols.join(", ") || "any symbol"} · paper trading{b.description && <> · “{b.description}”</>}</p></div>
        <div className="flex flex-wrap gap-2">
          {b.mode === "strategy" && <Button variant="outline" onClick={() => act("run", async () => { const r = await api<{ bot: Detail }>(`/api/bots/${id}/run`, { method: "POST" }); setData(r.bot); })} disabled={!!busy}>{busy === "run" ? "Running…" : "Run now"}</Button>}
          <Button variant="outline" onClick={() => patch({ status: b.status === "running" ? "paused" : "running" })}>{b.status === "running" ? "Pause" : "Resume"}</Button>
          <Button variant="outline" onClick={() => confirm("Sell all of this bot's positions?") && act("close", async () => setData(await api<Detail>(`/api/bots/${id}/close`, { method: "POST" })))}>Close positions</Button>
          <Button variant="outline" onClick={async () => {
            const title = prompt("Title for the marketplace listing", b.name); if (!title) return;
            const summary = prompt("Describe how it works and its risks (40+ characters). No promises of returns.", b.description ?? ""); if (!summary) return;
            const price = prompt("Monthly price in USD (0 = free; paid listings open when payouts launch)", "0") ?? "0";
            act("publish", async () => { const l = await api<{ id: number }>("/api/marketplace", { method: "POST", json: { bot_id: b.id, title, summary, category: b.mode === "webhook" ? "signals" : "other", price_monthly: parseFloat(price) || 0 } }); router.push(`/strategies/${l.id}`); });
          }}>Publish</Button>
          <Button variant="ghost" onClick={() => confirm("Delete this bot? Positions are sold and its cash returns to the accounts.") && act("del", async () => { await api(`/api/bots/${id}`, { method: "DELETE" }); router.push("/bots"); })}>Delete</Button>
        </div>
      </div>
      <ErrorNote error={err} />

      <div className="mt-5 grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-6">
        {([["Equity", usd(b.equity), ""], ["Return", pct(b.return, 2), tone(b.return)], ["Capital", usd(b.capital), ""], ["Open positions", String(b.positions.length), ""],
          ["Backtest CAGR", pct(bt?.stats.cagr ?? null, 1), ""], ["Live Sharpe", num(b.live.stats.sharpe, 2), ""]] as [string, string, string][]).map(([k, v, c]) =>
          <Card key={k} className="p-3"><div className="text-[11px] text-muted">{k}</div><div className={`stat mt-0.5 text-lg num ${c}`}>{v}</div></Card>)}
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card className="p-5 lg:col-span-2">
          <div className="flex items-center justify-between"><h2 className="font-semibold">Track record</h2>
            <div className="flex gap-1 rounded bg-accent p-0.5 text-xs">{(["live", "backtest"] as const).map(t => <button key={t} onClick={() => setTab(t)} className={`rounded px-3 py-1 ${tab === t ? "bg-card shadow-sm" : "text-muted"}`}>{t === "live" ? `Live paper (${b.live.days} days)` : "Backtest (2 years)"}</button>)}</div></div>
          {tab === "live" ? (b.live.series.dates.length > 1 ? <LineChart height={220} dates={b.live.series.dates} format={x => usd(x)} series={[{ values: b.live.series.equity, color: "#E0605A", label: "Live equity" }]} />
            : <p className="mt-6 text-sm text-muted">The live track record builds from end-of-day snapshots.</p>)
            : bt ? <LineChart height={220} dates={bt.series.dates} format={x => usd(x)} series={[{ values: bt.series.equity, color: "#E0605A", label: "Strategy ($100k)" }, ...(bt.series.bench ? [{ values: bt.series.bench, color: "#8a94a6", dashed: true, label: "SPY" }] : [])]} />
            : <p className="mt-6 text-sm text-muted">Webhook bots have no backtest; their record is built live.</p>}
          {b.comparison.length > 0 && <div className="mt-4 overflow-x-auto"><table className="w-full min-w-[520px] text-sm num">
            <thead className="text-xs text-muted"><tr><th className="text-left font-normal">Live vs backtest</th><th className="text-right font-normal">Live</th><th className="text-right font-normal">Backtest</th><th className="text-right font-normal">Difference</th></tr></thead>
            <tbody className="divide-y divide-line">{b.comparison.map(r => <tr key={r.key}><td className="py-1 font-sans">{r.label}</td><td className="text-right">{fmt(r.live, r.format)}</td><td className="text-right text-muted">{fmt(r.backtest, r.format)}</td>
              <td className={`text-right ${tone(r.difference)}`}>{r.difference == null ? "—" : fmt(r.difference, r.format)}</td></tr>)}</tbody></table>
            <p className="mt-1 text-[11px] text-muted">Live figures need several weeks of history to be meaningful. Backtest {bt?.start} to {bt?.end}, equal-weight across symbols, with the same costs.</p></div>}
        </Card>
        <Card className="p-5">
          <h2 className="font-semibold">Risk controls</h2>
          <div className="mt-3 grid grid-cols-2 gap-3">
            <label className="text-xs text-muted">Max per position %<input value={risk.cap} onChange={e => setRisk({ ...risk, cap: e.target.value })} className="mt-1 w-full rounded border border-line bg-bg px-2 py-1 text-sm text-fg num" /></label>
            <label className="text-xs text-muted">Stop-loss %<input value={risk.stop} onChange={e => setRisk({ ...risk, stop: e.target.value })} placeholder="none" className="mt-1 w-full rounded border border-line bg-bg px-2 py-1 text-sm text-fg num" /></label>
            <label className="text-xs text-muted">Take-profit %<input value={risk.tp} onChange={e => setRisk({ ...risk, tp: e.target.value })} placeholder="none" className="mt-1 w-full rounded border border-line bg-bg px-2 py-1 text-sm text-fg num" /></label>
            <label className="flex items-end gap-2 pb-1 text-sm"><input type="checkbox" checked={risk.auto} onChange={e => setRisk({ ...risk, auto: e.target.checked })} /> Daily auto-close</label>
          </div>
          <Button className="mt-3" variant="outline" onClick={saveRisk} disabled={busy === "patch"}>Save risk controls</Button>
          <div className="mt-5 border-t border-line pt-4"><h3 className="text-sm font-semibold">Webhook</h3>
            <div className="mt-1 flex gap-2"><input readOnly value={hook} className="w-full rounded border border-line bg-bg px-2 py-1 text-[11px]" onFocus={e => e.target.select()} />
              <Button variant="outline" onClick={() => navigator.clipboard?.writeText(hook)}>Copy</Button></div>
            <pre className="mt-2 overflow-x-auto rounded bg-accent p-2 text-[11px]">{`{"ticker": "{{ticker}}", "action": "{{strategy.order.action}}"}`}</pre>
            <button onClick={() => confirm("Create a new URL? The old one stops working.") && act("rotate", async () => { await api(`/api/bots/${id}/webhook/rotate`, { method: "POST" }); reload(); })} className="mt-1 text-[11px] text-muted hover:text-fg">Rotate URL</button>
            <p className="mt-1 text-[11px] text-muted">Keep the URL private: anyone with it can send signals to this paper bot.</p></div>
          <div className="mt-4 flex flex-wrap gap-2"><Button variant="outline" href={mcHref}>Monte Carlo</Button>{b.symbols[0] && <Button variant="outline" href={`/lab?symbol=${b.symbols[0]}`}>Open in Strategy Lab</Button>}</div>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card className="p-5 lg:col-span-2"><h2 className="font-semibold">Positions</h2>
          {!b.positions.length ? <p className="mt-2 text-sm text-muted">Flat. {b.mode === "strategy" ? `The rule last ran ${b.last_eval_on ?? "never"}.` : "Waiting for a signal."}</p> : (
            <div className="mt-2 overflow-x-auto"><table className="w-full min-w-[560px] text-sm num"><thead className="text-xs text-muted"><tr>{["Account", "Symbol", "Shares", "Avg cost", "Price", "Value", "Unrealized"].map((h, i) => <th key={h} className={`py-1 font-normal ${i ? "text-right" : "text-left"}`}>{h}</th>)}</tr></thead>
              <tbody className="divide-y divide-line">{b.positions.map(p => <tr key={p.account_id + p.symbol}><td className="py-1.5 font-sans text-xs">{b.sleeves.find(s => s.account_id === p.account_id)?.account}</td>
                <td className="text-right font-sans"><Link href={`/ticker/${p.symbol}`} className="hover:text-primary">{p.symbol}</Link></td><td className="text-right">{num(p.quantity, 2)}</td><td className="text-right">{num(p.avg_cost)}</td>
                <td className="text-right">{num(p.price)}</td><td className="text-right">{usd(p.value)}</td><td className={`text-right ${tone(p.unrealized)}`}>{usd(p.unrealized)} <span className="text-[11px]">{pct(p.return, 1)}</span></td></tr>)}</tbody></table></div>)}
        </Card>
        <Card className="p-5"><h2 className="font-semibold">Accounts fed</h2>
          <ul className="mt-2 space-y-2 text-sm">{b.sleeves.map(s => <li key={s.account_id} className="flex justify-between"><span>{s.account}</span><span className="num">{usd(s.equity)} <span className="text-[11px] text-muted">of {usd(s.capital)}</span></span></li>)}</ul>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card className="p-5"><h2 className="font-semibold">Trades</h2>
          {!b.trades.length ? <p className="mt-2 text-sm text-muted">No trades yet.</p> : <ul className="mt-2 max-h-80 divide-y divide-line overflow-y-auto text-sm">{b.trades.map(t => (
            <li key={t.id} className="flex justify-between gap-2 py-1.5"><span><b className={t.side === "buy" ? "text-up" : "text-down"}>{t.side}</b> {num(t.quantity, 2)} {t.symbol} @ {num(t.price)} <span className="text-[11px] text-muted">{REASON[t.reason] ?? t.reason}</span></span>
              <span className="text-right text-[11px] text-muted">{t.realized_pnl != null && <span className={`mr-2 num ${tone(t.realized_pnl)}`}>{usd(t.realized_pnl)}</span>}{t.at && ago(t.at)}</span></li>))}</ul>}
        </Card>
        <Card className="p-5"><h2 className="font-semibold">Signal log</h2>
          <ul className="mt-2 max-h-80 divide-y divide-line overflow-y-auto text-sm">{b.signals.map(s => (
            <li key={s.id} className="py-1.5"><div className="flex justify-between"><span><span className="rounded bg-accent px-1.5 text-[10px] uppercase">{s.source}</span> {s.action}{s.symbol && ` ${s.symbol}`}</span>
              <span className={`text-[11px] ${s.status === "error" ? "text-down" : s.status === "executed" ? "text-up" : "text-muted"}`}>{s.status} · {s.at && ago(s.at)}</span></div>
              {s.detail && <div className="text-[11px] text-muted">{s.detail}</div>}</li>))}</ul>
        </Card>
      </div>

      {meta && <Card className="mt-4 p-5"><h2 className="font-semibold">Tear sheet</h2><p className="mb-4 text-xs text-muted">{meta.metrics.length} statistics for the live paper record, next to the backtest.{b.live.stats.insufficient_history ? " Annualised and ratio figures appear once the bot has 20 trading days of history." : ""}</p>
        <TearSheet metrics={meta.metrics} stats={b.live.stats} compare={bt?.stats ?? null} /></Card>}
      <p className="mt-6 text-[11px] text-muted">Paper trading with simulated money. Fills use the latest quoted price with 2 bps slippage and 1 bp commission; {b.market_open ? "the market is open." : "the market is closed, so fills use the last price."} Hypothetical results don&apos;t predict future performance. Not investment advice.</p>
    </div>
  );
}
