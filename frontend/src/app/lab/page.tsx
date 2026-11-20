"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { ago, num, pct, tone } from "@/lib/format";
import { useAuth } from "@/components/AuthProvider";
import { LineChart } from "@/components/Chart";
import { Button, Card, ErrorNote, PageHeader, SourceBadge } from "@/components/ui";

interface Param { key: string; label: string; default: number; min: number; max: number; step: number; kind: string }
interface StrategyDef { key: string; title: string; description: string; params: Param[] }
interface Stats { [k: string]: number | string | null }
interface Roundtrip { direction: string; entry_date: string; entry_price: number; exit_date: string | null; exit_price: number | null; pnl: number; return_pct: number | null; bars: number }
interface BacktestOut {
  symbol: string; strategy: StrategyDef; params: Record<string, number>; data_source: string; statistics: Stats;
  series: { dates: string[]; equity: number[]; benchmark: number[]; drawdown: number[]; close: number[]; indicators: Record<string, number | null>[] };
  roundtrips: Roundtrip[];
}
interface OptRow { params: Record<string, number>; return: number; sharpe: number | null; max_relative_drawdown: number; roundtrips: number; win_rate: number | null }
interface OptOut { metric: string; keys: string[]; combinations: number; results: OptRow[]; best: OptRow; in_sample: { start: string; end: string };
  out_of_sample: { return: number; buy_hold_return: number; start: string; end: string } | null; warning: string }
interface Run { id: number; kind: string; symbol: string; strategy: string; params: Record<string, number>; return: number | null; sharpe: number | null; created_at: string }

const IND_COLORS = ["#56b4e9", "#cc79a7", "#e69f00", "#2fbf8f"];

function Lab() {
  const qs = useSearchParams();
  const router = useRouter();
  const { user } = useAuth();
  const { data: catalog } = useApi<StrategyDef[]>("/api/lab/strategies");
  const [symbol, setSymbol] = useState((qs.get("symbol") ?? "SPY").toUpperCase());
  const [range, setRange] = useState("5y");
  const [key, setKey] = useState(qs.get("strategy") ?? "sma_cross");
  const [params, setParams] = useState<Record<string, number>>({});
  const [settings, setSettings] = useState({ initial_capital: 100000, commission_bps: 1, slippage_bps: 2, allow_short: false });
  const [res, setRes] = useState<BacktestOut | null>(null);
  const [opt, setOpt] = useState<OptOut | null>(null);
  const [grid, setGrid] = useState<Record<string, [number, number, number]>>({});
  const [metric, setMetric] = useState("sharpe");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<Error | null>(null);
  const { data: runs, reload: reloadRuns } = useApi<Run[]>(user ? "/api/lab/runs" : null);
  const def = useMemo(() => catalog?.find(s => s.key === key), [catalog, key]);

  useEffect(() => {
    if (!def) return;
    setParams(Object.fromEntries(def.params.map(p => [p.key, p.default])));
    setGrid(Object.fromEntries(def.params.slice(0, 2).map(p => [p.key, [Math.max(p.min, p.default / 2), Math.min(p.max, p.default * 2), p.kind === "int" ? Math.max(1, Math.round(p.default / 4)) : p.step]])));
    setOpt(null);
  }, [def]);

  const run = async () => {
    if (!user) { router.push("/login?next=/lab"); return; }
    setBusy(true); setErr(null);
    try {
      setRes(await api<BacktestOut>("/api/lab/backtest", { method: "POST", json: { symbol, strategy: key, params, range, settings } }));
      reloadRuns();
    } catch (e) { setErr(e as Error); } finally { setBusy(false); }
  };
  const optimize = async () => {
    setBusy(true); setErr(null);
    try { setOpt(await api<OptOut>("/api/lab/optimize", { method: "POST", json: { symbol, strategy: key, params, range, settings, grid, metric } })); reloadRuns(); }
    catch (e) { setErr(e as Error); } finally { setBusy(false); }
  };

  const s = res?.statistics;
  const indKeys = res ? Object.keys(res.series.indicators.find(i => Object.values(i).some(v => v != null)) ?? {}).filter(k => k !== "date" && !["rsi", "macd", "signal"].includes(k)) : [];

  return (
    <div className="mx-auto max-w-7xl px-4 py-12">
      <PageHeader title="Strategy Lab" intro={<>Backtest rules-based strategies on live daily history for any ticker. The engine is a port of the open-source <b>StockSharp</b> strategy, indicator, history-emulation and statistics model. Orders fill on the next bar, after commission and slippage.</>}>
        <span className="text-xs text-muted">Research and education only. Backtests are hypothetical and ignore taxes, borrow and liquidity.</span>
      </PageHeader>
      <div className="grid gap-6 lg:grid-cols-4">
        <Card className="h-fit space-y-4 p-5">
          <div><label className="text-xs text-muted">Ticker</label>
            <input value={symbol} onChange={e => setSymbol(e.target.value.toUpperCase())} className="mt-1 w-full rounded-lg border border-line bg-bg px-3 py-2 uppercase" /></div>
          <div><label className="text-xs text-muted">History</label>
            <div className="mt-1 flex gap-1">{["1y", "2y", "5y"].map(r => <button key={r} onClick={() => setRange(r)} className={`flex-1 rounded px-2 py-1 text-sm ${r === range ? "bg-accent text-fg" : "text-muted"}`}>{r}</button>)}</div></div>
          <div><label className="text-xs text-muted">Strategy</label>
            <select value={key} onChange={e => setKey(e.target.value)} className="mt-1 w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm">
              {(catalog ?? []).map(c => <option key={c.key} value={c.key}>{c.title}</option>)}</select>
            {def && <p className="mt-2 text-xs text-muted">{def.description}</p>}</div>
          {def?.params.map(p => (
            <label key={p.key} className="flex items-center justify-between text-sm"><span className="text-muted">{p.label}</span>
              <input type="number" min={p.min} max={p.max} step={p.step} value={params[p.key] ?? p.default}
                onChange={e => setParams({ ...params, [p.key]: parseFloat(e.target.value) })} className="w-24 rounded border border-line bg-bg px-2 py-1 text-right num" /></label>
          ))}
          <details className="text-sm"><summary className="cursor-pointer text-muted">Execution settings</summary>
            <div className="mt-2 space-y-2">
              {([["initial_capital", "Capital"], ["commission_bps", "Commission (bps)"], ["slippage_bps", "Slippage (bps)"]] as const).map(([k, l]) => (
                <label key={k} className="flex items-center justify-between"><span className="text-muted">{l}</span>
                  <input type="number" value={settings[k]} onChange={e => setSettings({ ...settings, [k]: parseFloat(e.target.value) })} className="w-28 rounded border border-line bg-bg px-2 py-1 text-right num" /></label>
              ))}
              <label className="flex items-center gap-2"><input type="checkbox" checked={settings.allow_short} onChange={e => setSettings({ ...settings, allow_short: e.target.checked })} /> Allow short positions</label>
            </div></details>
          <Button onClick={run} disabled={busy || !symbol} className="w-full">{busy ? "Running…" : user ? "Run backtest" : "Sign in to backtest"}</Button>
          <ErrorNote error={err} />
          {user && runs && runs.length > 0 && (
            <div className="border-t border-line pt-3"><div className="text-xs text-muted">Recent runs</div>
              <ul className="mt-1 space-y-1 text-xs">{runs.slice(0, 6).map(r => (
                <li key={r.id} className="flex justify-between"><button className="hover:text-primary" onClick={() => { setSymbol(r.symbol); setKey(r.strategy); }}>{r.symbol} · {r.strategy}{r.kind === "optimize" ? " (opt)" : ""}</button>
                  <span className={`num ${tone(r.return)}`}>{pct(r.return, 0)} · {ago(r.created_at)}</span></li>))}</ul></div>
          )}
        </Card>

        <div className="space-y-4 lg:col-span-3">
          {!res && <Card className="p-10 text-center text-muted">Pick a ticker and a strategy, then run a backtest. Every result is compared with buy-and-hold over the same period.</Card>}
          {res && s && <>
            <div className="flex items-center gap-3 text-sm text-muted"><span className="font-semibold text-fg">{res.symbol}</span>{res.strategy.title}
              <span>{String(s.start)} → {String(s.end)}</span><SourceBadge source={res.data_source} /></div>
            <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
              {([["Return", pct(s.return as number, 1)], ["Buy & hold", pct(s.buy_hold_return as number, 1)], ["CAGR", pct(s.cagr as number, 1)],
                 ["Sharpe", num(s.sharpe as number, 2)], ["Max drawdown", pct(-(s.max_relative_drawdown as number), 1)], ["Win rate", pct(s.win_rate as number, 0, false)]] as [string, string][]).map(([k, v]) => (
                <Card key={k} className="p-3"><div className="text-xs text-muted">{k}</div><div className="text-xl font-semibold num">{v}</div></Card>))}
            </div>
            <Card className="p-4">
              <h3 className="mb-2 text-sm font-semibold">Equity vs buy-and-hold</h3>
              <LineChart dates={res.series.dates} height={260} format={v => `$${(v / 1000).toFixed(0)}k`}
                series={[{ values: res.series.equity, color: "#f5a524", label: "Strategy" }, { values: res.series.benchmark, color: "var(--color-muted)", dashed: true, label: "Buy & hold" }]} />
            </Card>
            <div className="grid gap-4 md:grid-cols-2">
              <Card className="p-4"><h3 className="mb-2 text-sm font-semibold">Price and indicators</h3>
                <LineChart dates={res.series.dates} height={200} format={v => num(v, 2)}
                  series={[{ values: res.series.close, color: "var(--color-fg)", label: res.symbol },
                    ...indKeys.map((k, i) => ({ values: res.series.indicators.map(x => x[k] ?? null), color: IND_COLORS[i % 4], label: k }))]} /></Card>
              <Card className="p-4"><h3 className="mb-2 text-sm font-semibold">Drawdown</h3>
                <LineChart dates={res.series.dates} height={200} format={v => `${(v * 100).toFixed(0)}%`} series={[{ values: res.series.drawdown, color: "var(--color-down)", label: "Drawdown" }]} /></Card>
            </div>
            <Card className="p-5">
              <h3 className="font-semibold">Statistics</h3>
              <dl className="mt-3 grid gap-x-8 gap-y-1 text-sm sm:grid-cols-2 lg:grid-cols-3 num">
                {([["Net profit", num(s.net_profit as number, 0)], ["Max drawdown ($)", num(s.max_drawdown as number, 0)], ["Recovery factor", num(s.recovery_factor as number, 2)],
                   ["Round trips", String(s.roundtrip_count)], ["Winning / losing", `${s.winning_trades} / ${s.losing_trades}`], ["Profit factor", num(s.profit_factor as number, 2)],
                   ["Average trade", num(s.average_trade as number, 0)], ["Average win", num(s.average_win as number, 0)], ["Average loss", num(s.average_loss as number, 0)],
                   ["Volatility", pct(s.volatility as number, 1, false)], ["Sortino", num(s.sortino as number, 2)], ["Calmar", num(s.calmar as number, 2)],
                   ["Time in market", pct(s.exposure as number, 0, false)], ["Commission paid", num(s.commission_paid as number, 0)], ["Excess vs buy & hold", pct(s.excess_return as number, 1)]] as [string, string][]).map(([k, v]) => (
                  <div key={k} className="flex justify-between border-b border-line/60 py-1"><dt className="text-muted">{k}</dt><dd>{v}</dd></div>))}
              </dl>
            </Card>
            <Card>
              <div className="border-b border-line p-4 font-semibold">Round trips</div>
              <div className="max-h-80 overflow-y-auto"><table className="w-full text-sm num">
                <thead className="sticky top-0 bg-card text-left text-xs uppercase text-muted"><tr>{["Side", "Entry", "Exit", "Bars", "P&L", "Return"].map(h => <th key={h} className="px-3 py-2">{h}</th>)}</tr></thead>
                <tbody className="divide-y divide-line">{res.roundtrips.slice().reverse().map((r, i) => (
                  <tr key={i}><td className="px-3 py-1.5 capitalize">{r.direction}</td><td className="px-3 py-1.5">{r.entry_date} @ {num(r.entry_price)}</td>
                    <td className="px-3 py-1.5">{r.exit_date ? `${r.exit_date} @ ${num(r.exit_price)}` : "open"}</td><td className="px-3 py-1.5">{r.bars}</td>
                    <td className={`px-3 py-1.5 ${tone(r.pnl)}`}>{num(r.pnl, 0)}</td><td className={`px-3 py-1.5 ${tone(r.return_pct)}`}>{pct(r.return_pct, 1)}</td></tr>))}
                  {res.roundtrips.length === 0 && <tr><td colSpan={6} className="p-4 text-center text-muted">No trades in this period.</td></tr>}</tbody></table></div>
            </Card>
          </>}

          {def && def.params.length > 0 && (
            <Card className="p-5">
              <div className="flex items-center justify-between"><h3 className="font-semibold">Optimise parameters <span className="ml-2 rounded bg-primary/15 px-2 py-0.5 text-xs text-primary">Pro</span></h3>
                <select value={metric} onChange={e => setMetric(e.target.value)} className="rounded border border-line bg-bg px-2 py-1 text-sm">
                  <option value="sharpe">Maximise Sharpe</option><option value="return">Maximise return</option><option value="max_relative_drawdown">Minimise drawdown</option><option value="win_rate">Maximise win rate</option></select></div>
              <p className="mt-1 text-xs text-muted">Grid search on the first 70% of history, then the best set is tested on the remaining 30%. This mirrors StockSharp&apos;s batch emulation.</p>
              <div className="mt-3 grid gap-2 md:grid-cols-2">
                {Object.entries(grid).map(([k, [lo, hi, st]]) => (
                  <div key={k} className="flex items-center gap-2 text-sm"><span className="w-24 text-muted">{def.params.find(p => p.key === k)?.label}</span>
                    {[lo, hi, st].map((v, i) => <input key={i} type="number" value={v} onChange={e => { const g = [...grid[k]] as [number, number, number]; g[i] = parseFloat(e.target.value); setGrid({ ...grid, [k]: g }); }}
                      className="w-20 rounded border border-line bg-bg px-2 py-1 text-right num" placeholder={["min", "max", "step"][i]} />)}</div>))}
              </div>
              <div className="mt-3"><Button variant="outline" onClick={optimize} disabled={busy || user?.plan !== "pro"}>{user?.plan === "pro" ? "Run optimisation" : "Optimisation needs Pro"}</Button>
                {user?.plan !== "pro" && <Link href="/pricing" className="ml-3 text-sm text-primary">See plans</Link>}</div>
              {opt && (
                <div className="mt-4">
                  <p className="text-sm text-muted">{opt.combinations} combinations · in-sample {opt.in_sample.start} → {opt.in_sample.end}</p>
                  {opt.out_of_sample && <div className="mt-2 rounded-lg bg-accent/60 p-3 text-sm">Best set {JSON.stringify(opt.best.params)} out of sample ({opt.out_of_sample.start} → {opt.out_of_sample.end}):
                    <b className={`ml-1 ${tone(opt.out_of_sample.return)}`}>{pct(opt.out_of_sample.return, 1)}</b> vs buy &amp; hold {pct(opt.out_of_sample.buy_hold_return, 1)}</div>}
                  <p className="mt-2 text-xs text-down">{opt.warning}</p>
                  <div className="mt-2 max-h-72 overflow-y-auto"><table className="w-full text-sm num">
                    <thead className="sticky top-0 bg-card text-left text-xs uppercase text-muted"><tr><th className="px-2 py-1">Params</th><th className="px-2 py-1">Return</th><th className="px-2 py-1">Sharpe</th><th className="px-2 py-1">Max DD</th><th className="px-2 py-1">Trades</th><th /></tr></thead>
                    <tbody className="divide-y divide-line">{opt.results.slice(0, 30).map((r, i) => (
                      <tr key={i}><td className="px-2 py-1">{Object.entries(r.params).map(([k, v]) => `${k}=${v}`).join(", ")}</td><td className={`px-2 py-1 ${tone(r.return)}`}>{pct(r.return, 1)}</td>
                        <td className="px-2 py-1">{num(r.sharpe, 2)}</td><td className="px-2 py-1">{pct(-r.max_relative_drawdown, 1)}</td><td className="px-2 py-1">{r.roundtrips}</td>
                        <td className="px-2 py-1"><button onClick={() => setParams({ ...params, ...r.params })} className="text-xs text-primary">Use</button></td></tr>))}</tbody></table></div>
                </div>
              )}
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

export default function Page() { return <Suspense><Lab /></Suspense>; }
