"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { num, pct, tone } from "@/lib/format";
import { useAuth } from "@/components/AuthProvider";
import { Button, Card, ErrorNote, Skeleton, SourceBadge } from "@/components/ui";

type Tab = "tests" | "regimes" | "states" | "leadlag" | "micro";
const TABS: { id: Tab; label: string; blurb: string }[] = [
  { id: "tests", label: "Pattern tests", blurb: "Six precisely defined patterns, tested on every asset class and timeframe, and only called robust if they survive every stress test." },
  { id: "regimes", label: "Market regimes", blurb: "Which volatility regime the market is in, how long regimes usually last, and the odds of staying." },
  { id: "states", label: "Recurring states", blurb: "Today's cross-asset fingerprint matched against every past day, with what followed the closest matches." },
  { id: "leadlag", label: "Lead-lag map", blurb: "Which assets have moved first and which have followed, tested so chance correlations are filtered out." },
  { id: "micro", label: "Order-book pulse", blurb: "Live buy-versus-sell pressure in the crypto order book: imbalance, spread, microprice and aggressive flow." },
];
const REG_TONE: Record<string, string> = { Calm: "bg-up/70", Normal: "bg-primary/60", Stressed: "bg-down/70" };

export default function Patterns() {
  const { user, ready } = useAuth();
  const [tab, setTab] = useState<Tab>("tests");
  return (
    <div className="mx-auto max-w-7xl px-4 py-10">
      <div className="text-xs uppercase tracking-wide text-primary">Built by IRAI</div>
      <h1 className="text-3xl">Pattern Lab</h1>
      <p className="mt-1 max-w-3xl text-sm text-muted">See the structure under the noise. IRAI fits statistical models to five years of cleaned, versioned market data every night,
        so you can see which regime you are in, which past days looked most like today, and which markets have tended to move first.</p>
      <div className="mt-5 flex flex-wrap gap-2">{TABS.map(t => (
        <button key={t.id} onClick={() => setTab(t.id)} className={`rounded-full border px-3 py-1.5 text-sm ${tab === t.id ? "border-primary bg-primary/10" : "border-line text-muted hover:text-fg"}`}>{t.label}</button>))}</div>
      <p className="mt-2 text-xs text-muted">{TABS.find(t => t.id === tab)?.blurb}</p>
      {!ready ? <div className="mt-6"><Skeleton rows={6} /></div> : !user ? (
        <Card className="mt-6 p-8 text-center"><h2 className="text-lg font-semibold">Create a free account to open the Pattern Lab</h2>
          <p className="mx-auto mt-1 max-w-lg text-sm text-muted">Free members see today&apos;s market regime and state. Pro unlocks every symbol, the full lead-lag map, historical analogues and the live order-book ladder.</p>
          <Button className="mt-4" href="/signup?next=/patterns">Start free</Button></Card>
      ) : tab === "tests" ? <Tests /> : tab === "regimes" ? <Regimes /> : tab === "states" ? <States /> : tab === "leadlag" ? <LeadLag /> : <Micro />}
      <p className="mt-6 text-[11px] text-muted">Statistical patterns describe the past and can stop working without warning. Pattern Lab is research and education, not a recommendation to buy or sell anything.</p>
    </div>
  );
}

function Upgrade({ what }: { what: string }) {
  return <div className="mt-3 rounded-lg border border-primary/40 bg-primary/5 p-4 text-sm">{what} <Button className="ml-2" href="/pricing">Unlock with Pro</Button></div>;
}

interface RegResp { source?: string; symbol: string; as_of: string; locked: boolean; model: string; current: { state: string; probabilities: Record<string, number>; since: string; days_in_state: number; stay_probability: number };
  states: { name: string; annual_vol: number; annualised_return: number | null; share_of_days: number; expected_duration_days: number; avg_run_days: number | null }[];
  transition_matrix: { labels: string[]; matrix: number[][] }; series: { dates: string[]; state: number[]; close: number[] } }

function Regimes() {
  const [sym, setSym] = useState("SPY");
  const { data, error } = useApi<RegResp>(`/api/quant/regimes?symbol=${sym}`);
  const names = ["Calm", "Normal", "Stressed"];
  return (<div className="mt-5 space-y-4">
    <div className="flex flex-wrap gap-2 text-xs">{["SPY", "QQQ", "IWM", "TLT", "GLD", "BTC-USD", "NVDA"].map(s => <button key={s} onClick={() => setSym(s)} className={`rounded border px-2 py-1 ${sym === s ? "border-primary" : "border-line text-muted"}`}>{s}</button>)}</div>
    <ErrorNote error={error} />
    {error?.message?.includes("Pro") && <Upgrade what="Regimes for every symbol are part of Pro." />}
    {!data ? (!error && <Skeleton rows={6} />) : (<>
      <div className="grid gap-4 md:grid-cols-3">
        <Card className="p-5"><div className="flex items-center gap-2 text-xs text-muted">{data.symbol} regime today <SourceBadge source={data.source} /></div><div className="mt-1 text-3xl font-semibold">{data.current.state}</div>
          <div className="mt-1 text-sm text-muted">since {data.current.since} · {data.current.days_in_state} sessions</div>
          <div className="mt-3 text-sm">Historical chance of staying in this regime tomorrow: <b className="num">{pct(data.current.stay_probability, 0, false)}</b></div></Card>
        <Card className="p-5 md:col-span-2"><div className="text-xs text-muted">Model confidence today</div>
          {Object.entries(data.current.probabilities).map(([k, v]) => <div key={k} className="mt-2 flex items-center gap-3 text-sm"><span className="w-20">{k}</span><div className="h-2 flex-1 rounded bg-accent"><div className={`h-2 rounded ${REG_TONE[k]}`} style={{ width: `${v * 100}%` }} /></div><span className="w-12 text-right num">{pct(v, 0, false)}</span></div>)}</Card>
      </div>
      <Card className="p-5"><div className="text-xs text-muted">Regime history ({data.series.dates[0]} to {data.as_of})</div>
        <div className="mt-3 flex h-10 w-full overflow-hidden rounded">{data.series.state.map((s, i) => <div key={i} title={`${data.series.dates[i]}: ${names[s]}`} className={`h-full flex-1 ${REG_TONE[names[s]]}`} />)}</div>
        <div className="mt-2 flex gap-4 text-[11px] text-muted">{names.map(n => <span key={n} className="flex items-center gap-1"><span className={`inline-block h-2 w-3 rounded ${REG_TONE[n]}`} />{n}</span>)}</div></Card>
      <Card className="overflow-x-auto p-0"><table className="w-full min-w-[640px] text-sm"><thead className="text-xs text-muted"><tr>{["Regime", "Annual volatility", "Annualised return", "Share of days", "Typical run"].map(h => <th key={h} className="px-4 py-2 text-left font-normal">{h}</th>)}</tr></thead>
        <tbody className="divide-y divide-line num">{data.states.map(s => <tr key={s.name}><td className="px-4 py-2 font-sans font-medium">{s.name}</td><td className="px-4">{pct(s.annual_vol, 1, false)}</td>
          <td className={`px-4 ${tone(s.annualised_return)}`}>{pct(s.annualised_return, 1)}</td><td className="px-4">{pct(s.share_of_days, 0, false)}</td><td className="px-4">{num(s.avg_run_days, 0)} sessions</td></tr>)}</tbody></table></Card>
      {data.locked ? <Upgrade what="Pro shows the full transition matrix and regimes for any symbol in the research universe." /> : (
        <Card className="p-5"><div className="text-xs text-muted">Transition matrix: chance of moving from the row regime to the column regime the next day</div>
          <table className="mt-2 text-sm num"><thead><tr><th />{data.transition_matrix.labels.map(l => <th key={l} className="px-3 font-sans font-normal text-muted">{l}</th>)}</tr></thead>
            <tbody>{data.transition_matrix.matrix.map((r, i) => <tr key={i}><td className="pr-3 font-sans text-muted">{data.transition_matrix.labels[i]}</td>{r.map((v, j) => <td key={j} className="px-3 py-1 text-center" style={{ background: `rgb(var(--color-primary-rgb, 99 102 241) / ${v * 0.5})` }}>{pct(v, 1, false)}</td>)}</tr>)}</tbody></table></Card>)}
      <p className="text-[11px] text-muted">{data.model}.</p>
    </>)}
  </div>);
}

interface StatesResp { source?: string; as_of: string; current_state: number; locked: boolean; method: string; current_vector: Record<string, number>;
  states: { id: number; description: string; share_of_days: number; episodes: number; avg_run_days: number | null; spy_fwd_21d_median: number | null; spy_fwd_21d_positive: number | null; last_seen: string | null }[];
  analogs: { date: string; distance: number; state: number; spy_fwd_21d: number | null }[];
  analog_summary: { median_spy_fwd_21d: number | null; share_positive: number | null; range: [number, number] | null } }

function States() {
  const { data, error } = useApi<StatesResp>("/api/quant/states");
  if (error) return <div className="mt-5"><ErrorNote error={error} /></div>;
  if (!data) return <div className="mt-5"><Skeleton rows={8} /></div>;
  const cur = data.states[data.current_state];
  return (<div className="mt-5 space-y-4">
    <div className="grid gap-4 md:grid-cols-3">
      <Card className="p-5 md:col-span-2"><div className="flex items-center gap-2 text-xs text-muted">Today&apos;s market state ({data.as_of}) <SourceBadge source={data.source} /></div><div className="mt-1 text-xl font-semibold">State {cur.id + 1}: {cur.description}</div>
        <div className="mt-1 text-sm text-muted">Seen on {pct(cur.share_of_days, 0, false)} of days across {cur.episodes} separate episodes; a typical episode lasts {num(cur.avg_run_days, 0)} sessions.</div>
        <div className="mt-4 grid grid-cols-2 gap-x-6 gap-y-1 text-xs md:grid-cols-2">{Object.entries(data.current_vector).map(([k, v]) => (
          <div key={k} className="flex items-center gap-2"><span className="w-44 truncate text-muted">{k}</span><div className="relative h-1.5 flex-1 rounded bg-accent"><div className={`absolute top-0 h-1.5 rounded ${v >= 0 ? "left-1/2 bg-up/70" : "right-1/2 bg-down/70"}`} style={{ width: `${Math.min(50, Math.abs(v) * 15)}%` }} /></div><span className="w-10 text-right num">{v > 0 ? "+" : ""}{v}σ</span></div>))}</div></Card>
      <Card className="p-5"><div className="text-xs text-muted">After the closest historical matches, the S&amp;P 500 over the next 21 sessions</div>
        <div className={`mt-2 text-3xl num ${tone(data.analog_summary.median_spy_fwd_21d)}`}>{pct(data.analog_summary.median_spy_fwd_21d, 1)}</div><div className="text-xs text-muted">median</div>
        <div className="mt-2 text-sm">Higher in <b>{pct(data.analog_summary.share_positive, 0, false)}</b> of matches</div>
        {data.analog_summary.range && <div className="text-xs text-muted num">Range {pct(data.analog_summary.range[0], 1)} to {pct(data.analog_summary.range[1], 1)}</div>}</Card>
    </div>
    <Card className="overflow-x-auto p-0"><div className="px-4 pt-3 text-xs text-muted">Closest historical analogues</div><table className="w-full min-w-[520px] text-sm"><thead className="text-xs text-muted"><tr>{["Date", "Similarity distance", "State", "S&P 500 next 21 sessions"].map(h => <th key={h} className="px-4 py-2 text-left font-normal">{h}</th>)}</tr></thead>
      <tbody className="divide-y divide-line num">{data.analogs.map(a => <tr key={a.date}><td className="px-4 py-2">{a.date}</td><td className="px-4">{a.distance}</td><td className="px-4">{a.state + 1}</td><td className={`px-4 ${tone(a.spy_fwd_21d)}`}>{pct(a.spy_fwd_21d, 1)}</td></tr>)}</tbody></table></Card>
    {data.locked && <Upgrade what="Pro shows all ten analogues and the full state history." />}
    <Card className="overflow-x-auto p-0"><table className="w-full min-w-[720px] text-sm"><thead className="text-xs text-muted"><tr>{["State", "What defines it", "Share of days", "Typical run", "S&P 500 next 21d (median)", "Last seen"].map(h => <th key={h} className="px-4 py-2 text-left font-normal">{h}</th>)}</tr></thead>
      <tbody className="divide-y divide-line">{data.states.map(s => <tr key={s.id} className={s.id === data.current_state ? "bg-primary/5" : ""}><td className="px-4 py-2 num">{s.id + 1}</td><td className="px-4">{s.description}</td><td className="px-4 num">{pct(s.share_of_days, 0, false)}</td><td className="px-4 num">{num(s.avg_run_days, 0)}</td><td className={`px-4 num ${tone(s.spy_fwd_21d_median)}`}>{pct(s.spy_fwd_21d_median, 1)}</td><td className="px-4 num">{s.last_seen}</td></tr>)}</tbody></table></Card>
    <p className="text-[11px] text-muted">{data.method}</p>
  </div>);
}

interface LLResp { source?: string; symbols: string[]; correlation: (number | null)[][]; locked: boolean; hidden?: number; method: string;
  pairs: { leader: string; follower: string; lag_days: number; lagged_corr: number; same_day_corr: number; p_value: number; significant: boolean }[] }

function LeadLag() {
  const [u, setU] = useState("macro");
  const { data, error } = useApi<LLResp>(`/api/quant/leadlag?universe=${u}`);
  return (<div className="mt-5 space-y-4">
    <div className="flex items-center gap-2 text-xs">{data?.source && <SourceBadge source={data.source} />}{[["macro", "Cross-asset"], ["sectors", "Sectors"], ["megacaps", "Mega-caps"]].map(([k, l]) => <button key={k} onClick={() => setU(k)} className={`rounded border px-2 py-1 ${u === k ? "border-primary" : "border-line text-muted"}`}>{l}</button>)}</div>
    <ErrorNote error={error} />
    {!data ? (!error && <Skeleton rows={8} />) : (<>
      <Card className="overflow-x-auto p-0"><table className="w-full min-w-[640px] text-sm"><thead className="text-xs text-muted"><tr>{["Moves first", "Follows", "Lag", "Lagged correlation", "Same-day correlation", "Confidence"].map(h => <th key={h} className="px-4 py-2 text-left font-normal">{h}</th>)}</tr></thead>
        <tbody className="divide-y divide-line">{data.pairs.slice(0, 25).map((p, i) => <tr key={i} className={p.significant ? "" : "text-muted"}><td className="px-4 py-2 font-medium">{p.leader}</td><td className="px-4">{p.follower}</td><td className="px-4 num">{p.lag_days}d</td>
          <td className={`px-4 num ${tone(p.lagged_corr)}`}>{num(p.lagged_corr, 3)}</td><td className="px-4 num">{num(p.same_day_corr, 2)}</td><td className="px-4 text-xs">{p.significant ? <span className="text-up">Significant (p {p.p_value < 0.0001 ? "< 0.0001" : num(p.p_value, 4)})</span> : "Not significant"}</td></tr>)}</tbody></table>
        {data.pairs.length === 0 && <p className="p-5 text-sm text-muted">No relationship passed the significance test in this window.</p>}</Card>
      {data.locked && <Upgrade what={`Pro shows ${data.hidden ? `${data.hidden} more significant relationships, ` : ""}every tested pair and the full correlation matrix.`} />}
      {!data.locked && <Card className="overflow-x-auto p-4"><div className="text-xs text-muted">Same-day correlation of daily returns</div>
        <table className="mt-2 text-[11px] num"><thead><tr><th />{data.symbols.map(s => <th key={s} className="px-1 font-sans font-normal text-muted">{s}</th>)}</tr></thead>
          <tbody>{data.correlation.map((r, i) => <tr key={i}><td className="pr-2 font-sans text-muted">{data.symbols[i]}</td>{r.map((v, j) => <td key={j} className="h-7 w-12 text-center" style={{ background: v == null ? undefined : v >= 0 ? `rgba(34,197,94,${Math.abs(v) * 0.6})` : `rgba(239,68,68,${Math.abs(v) * 0.6})` }}>{v == null ? "" : v.toFixed(2)}</td>)}</tr>)}</tbody></table></Card>}
      <p className="text-[11px] text-muted">{data.method}</p>
    </>)}
  </div>);
}

interface MicroResp { pair: string; available: boolean; note: string; as_of?: string; mid?: number; spread_bps?: number; microprice?: number; microprice_vs_mid_bps?: number;
  imbalance_10bps?: number | null; imbalance_50bps?: number | null; imbalance_100bps?: number | null; depth_usd_10bps?: number; depth_usd_100bps?: number;
  flow_imbalance?: number | null; aggressive_buy_usd?: number; aggressive_sell_usd?: number; trades?: number; locked?: boolean;
  ladder?: { bids: [number, number][]; asks: [number, number][] } | null; recent?: { t: string; imb: number | null; flow: number | null }[]; provider?: { label: string } }

function Gauge({ label, v }: { label: string; v: number | null | undefined }) {
  const x = v ?? 0;
  return <div><div className="flex justify-between text-xs"><span className="text-muted">{label}</span><span className={`num ${tone(v)}`}>{v == null ? "n/a" : `${x > 0 ? "+" : ""}${(x * 100).toFixed(0)}%`}</span></div>
    <div className="relative mt-1 h-2 rounded bg-accent"><div className="absolute left-1/2 top-0 h-2 w-px bg-line" /><div className={`absolute top-0 h-2 rounded ${x >= 0 ? "left-1/2 bg-up/70" : "right-1/2 bg-down/70"}`} style={{ width: `${Math.abs(x) * 50}%` }} /></div></div>;
}

function Micro() {
  const [pair, setPair] = useState("BTC-USD");
  const { data, error } = useApi<MicroResp>(`/api/quant/micro?pair=${pair}`, 15_000, [pair]);
  return (<div className="mt-5 space-y-4">
    <div className="flex gap-2 text-xs">{["BTC-USD", "ETH-USD", "SOL-USD"].map(p => <button key={p} onClick={() => setPair(p)} className={`rounded border px-2 py-1 ${pair === p ? "border-primary" : "border-line text-muted"}`}>{p}</button>)}
      <span className="ml-auto self-center text-muted">Refreshes every 15 seconds</span></div>
    <ErrorNote error={error} />
    {!data ? (!error && <Skeleton rows={6} />) : !data.available ? <Card className="p-5 text-sm text-muted">{data.note}</Card> : (<>
      <div className="grid gap-4 md:grid-cols-3">
        <Card className="p-5"><div className="text-xs text-muted">{data.pair} mid <span className="rounded bg-up/15 px-1 text-[10px] text-up">LIVE</span></div><div className="mt-1 text-3xl num">{num(data.mid, 2)}</div>
          <div className="mt-1 text-xs text-muted num">Spread {num(data.spread_bps, 2)} bps · microprice {num(data.microprice_vs_mid_bps, 2)} bps vs mid</div></Card>
        <Card className="space-y-3 p-5 md:col-span-2"><Gauge label="Book imbalance within 0.1% of mid" v={data.imbalance_10bps} /><Gauge label="Book imbalance within 0.5%" v={data.imbalance_50bps} />
          <Gauge label="Book imbalance within 1%" v={data.imbalance_100bps} /><Gauge label={`Aggressive trade flow (last ${data.trades} trades)`} v={data.flow_imbalance} /></Card>
      </div>
      {data.recent && data.recent.length > 1 && <Card className="p-5"><div className="text-xs text-muted">Imbalance readings this session (green above the line means more resting bids)</div>
        <div className="mt-3 flex h-16 items-center gap-px">{data.recent.map((p, i) => <div key={i} className="flex h-full flex-1 flex-col justify-center"><div className={`${(p.imb ?? 0) >= 0 ? "self-end bg-up/70" : "bg-down/70"} w-full`} style={{ height: `${Math.abs(p.imb ?? 0) * 50}%`, marginTop: (p.imb ?? 0) >= 0 ? undefined : "50%" }} /></div>)}</div></Card>}
      {data.locked ? <Upgrade what="Pro shows the live depth ladder and the full session history." /> : data.ladder && (
        <Card className="grid grid-cols-2 gap-4 p-5 text-xs num"><div><div className="mb-1 font-sans text-muted">Bids</div>{data.ladder.bids.map(([p, s], i) => <div key={i} className="flex justify-between text-up"><span>{num(p, 2)}</span><span>{num(s, 4)}</span></div>)}</div>
          <div><div className="mb-1 font-sans text-muted">Asks</div>{data.ladder.asks.map(([p, s], i) => <div key={i} className="flex justify-between text-down"><span>{num(p, 2)}</span><span>{num(s, 4)}</span></div>)}</div></Card>)}
      <p className="text-[11px] text-muted">{data.note} Source: {data.provider?.label}. Stocks and ETFs need a licensed depth-of-book feed, which IRAI can add.</p>
    </>)}
  </div>);
}

interface Check { pass: boolean; text: string }
interface Stat { n: number; mean_r?: number; hit_rate?: number | null; t?: number; profit_factor?: number | null }
interface Result { pattern: string; asset_class: string; timeframe: string; verdict?: string; checks_passed?: number; checks_total?: number; events?: number; status: string; definition: string;
  reasons?: Check[]; all?: Stat; baseline?: Stat; train?: Stat; holdout?: Stat; edge_vs_random?: number; horizon?: number; cost_bps?: number; q_value?: number;
  permutation?: { p_value: number; random_mean: number; random_p95: number; draws: number }; walk_forward?: { folds: { fold: number; n: number; mean_r: number | null }[] };
  regimes?: { regime: string; n: number; mean_r: number }[]; years?: { year: string; n: number; mean_r: number }[]; sensitivity?: Record<string, number | null>;
  logistic?: { test_auc: number | null; coefficients: { feature: string; weight: number }[]; base_probability: number; mean_score_on_events: number } | null;
  data?: { symbol: string; source: string; bars: number; from: string; to: string; events: number; hash: string }[]; live?: string[] }
interface Overview { catalog: { patterns: { id: string; name: string; family: string; direction: string; definition: string; params: Record<string, number> }[];
  asset_classes: Record<string, { label: string; symbols: string[]; cost_bps: number }>; timeframes: Record<string, { label: string; horizon: number }>; method: Record<string, string> };
  grid: { created_at: string; n_tests: number; robust: number; source: string; hurdle: number; results: Result[] } | null; locked: boolean; running: boolean; progress: string | null; note: string | null }
const VERDICT: Record<string, string> = { Robust: "bg-up/20 text-up", Promising: "bg-primary/15 text-primary", "Not robust": "bg-accent text-muted", "Insufficient evidence": "bg-accent text-muted" };
const STEPS = ["Define a measurable pattern", "Scale-invariant features", "Point-in-time data & labels", "Interpretable baselines", "Overfitting & regime stress tests"];

function Tests() {
  const { data, error } = useApi<Overview>("/api/quant/patterns");
  const [tf, setTf] = useState("1d");
  const [sel, setSel] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  if (error) return <div className="mt-5"><ErrorNote error={error} /></div>;
  if (!data) return <div className="mt-5"><Skeleton rows={8} /></div>;
  const cat = data.catalog;
  const acs = Object.keys(cat.asset_classes);
  const cell = (p: string, ac: string) => data.grid?.results.find(o => o.pattern === p && o.asset_class === ac && o.timeframe === tf);
  async function open(p: string, ac: string) {
    setErr(null);
    if (data!.locked) { setSel(cell(p, ac) ?? null); return; }
    setBusy(true);
    try {
      const fromGrid = cell(p, ac);
      if (fromGrid) setSel(await api<Result>(`/api/quant/patterns/result?pattern=${p}&asset_class=${ac}&timeframe=${tf}`));
      else { const r = await api<{ results: Result[] }>("/api/quant/patterns/test", { method: "POST", json: { pattern: p, asset_class: ac, timeframe: tf } }); setSel(r.results[0] ?? null); }
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  }
  return (<div className="mt-5 space-y-4">
    <Card className="p-5"><div className="grid gap-3 md:grid-cols-5">{STEPS.map((s, i) => <div key={s}><div className="text-xs text-primary">Step {i + 1}</div><div className="text-sm font-medium">{s}</div><p className="mt-1 text-[11px] leading-snug text-muted">{cat.method[String(i + 1)]}</p></div>)}</div></Card>
    <div className="flex flex-wrap items-center gap-2 text-xs">{Object.entries(cat.timeframes).map(([k, v]) => <button key={k} onClick={() => { setTf(k); setSel(null); }} className={`rounded border px-2 py-1 ${tf === k ? "border-primary" : "border-line text-muted"}`}>{v.label}</button>)}
      {data.grid && <span className="ml-auto text-muted">Last study {data.grid.created_at.slice(0, 16).replace("T", " ")} UTC · {data.grid.n_tests} tests · {data.grid.robust} robust <SourceBadge source={data.grid.source} /></span>}</div>
    {data.running && <p className="text-xs text-primary">Study running: {data.progress}</p>}
    {data.note && <Card className="p-4 text-sm text-muted">{data.note}</Card>}
    <Card className="overflow-x-auto p-0"><table className="w-full min-w-[900px] text-sm"><thead className="text-xs text-muted"><tr><th className="px-4 py-2 text-left font-normal">Pattern</th>{acs.map(a => <th key={a} className="px-2 py-2 text-left font-normal">{cat.asset_classes[a].label}</th>)}</tr></thead>
      <tbody className="divide-y divide-line">{cat.patterns.map(p => <tr key={p.id}><td className="px-4 py-2"><div className="font-medium">{p.name}</div><div className="text-[11px] text-muted">{p.family} · {p.direction}</div></td>
        {acs.map(a => { const c = cell(p.id, a); return <td key={a} className="px-2"><button onClick={() => open(p.id, a)} className={`w-full rounded px-2 py-1.5 text-left text-xs hover:ring-1 hover:ring-primary ${c?.verdict ? VERDICT[c.verdict] : "bg-accent/50 text-muted"}`}>
          {c?.verdict ?? (data.locked ? "Not yet tested" : "Run test")}{c?.checks_total ? <span className="block text-[10px] opacity-80">{c.checks_passed}/{c.checks_total} checks · {c.events} events</span> : null}</button></td>; })}</tr>)}</tbody></table></Card>
    {busy && <Skeleton rows={6} />}
    {err && <p className="text-sm text-down">{err}</p>}
    {sel && !busy && <Detail r={sel} locked={data.locked} name={cat.patterns.find(p => p.id === sel.pattern)?.name ?? sel.pattern} ac={cat.asset_classes[sel.asset_class]?.label} tf={cat.timeframes[sel.timeframe]?.label} />}
    <p className="text-[11px] text-muted"><b>Robust</b> means it passed every check, including a holdout it never saw and corrections for how many patterns were tried. <b>Promising</b> means positive but it failed one or two checks, so it is not proven. Outcomes are in R: one expected move (trailing volatility × √horizon), after asset-class trading costs.</p>
  </div>);
}

function Detail({ r, locked, name, ac, tf }: { r: Result; locked: boolean; name: string; ac?: string; tf?: string }) {
  const R = (x: number | null | undefined) => x == null ? "n/a" : `${x >= 0 ? "+" : ""}${x.toFixed(2)} R`;
  return (<Card className="space-y-4 p-5">
    <div className="flex flex-wrap items-start justify-between gap-3"><div><div className="text-xs text-muted">{ac} · {tf}{r.horizon ? ` · ${r.horizon}-bar horizon` : ""}</div><h3 className="text-xl font-semibold">{name}</h3><p className="mt-1 max-w-3xl text-sm">{r.definition}</p></div>
      {r.verdict && <span className={`rounded-full px-3 py-1 text-sm font-medium ${VERDICT[r.verdict]}`}>{r.verdict}</span>}</div>
    {locked ? <Upgrade what="Pro shows the full evidence for every cell: baselines, holdout, permutation test, walk-forward folds, regimes, sensitivity and the data used, and lets you run your own tests." /> : r.status !== "ok" ? <p className="text-sm text-muted">{r.reasons ? (r.reasons as unknown as string[]).join(" ") : "Not enough events to test."}</p> : (<>
      <div className="grid gap-3 md:grid-cols-4">{[["All events", r.all], ["Random entries (base rate)", r.baseline], ["Before holdout", r.train], ["Untouched holdout", r.holdout]].map(([l, s]) => { const st = s as Stat; return (
        <div key={l as string} className="rounded-lg border border-line p-3"><div className="text-xs text-muted">{l as string}</div><div className={`text-lg num ${tone(st?.mean_r)}`}>{R(st?.mean_r)}</div>
          <div className="text-[11px] text-muted num">{st?.n ?? 0} trades · hit {pct(st?.hit_rate, 0, false)} · t {num(st?.t, 2)}</div></div>); })}</div>
      <div><div className="text-xs font-medium">Stress tests</div><ul className="mt-1 grid gap-1 text-sm md:grid-cols-2">{r.reasons?.map((c, i) => <li key={i} className="flex gap-2"><span className={c.pass ? "text-up" : "text-down"}>{c.pass ? "✓" : "✗"}</span><span>{c.text}</span></li>)}</ul></div>
      <div className="grid gap-4 md:grid-cols-3">
        <div><div className="text-xs font-medium">Walk-forward folds (purged)</div><div className="mt-2 flex gap-1">{r.walk_forward?.folds.map(f => <div key={f.fold} className="flex flex-1 flex-col items-center">
          <div className="relative h-16 w-full"><div className="absolute inset-x-0 top-1/2 h-px bg-line" /><div className={`absolute inset-x-1 ${(f.mean_r ?? 0) >= 0 ? "bottom-1/2 rounded-t bg-up/70" : "top-1/2 rounded-b bg-down/70"}`} style={{ height: `${Math.max(2, Math.min(50, Math.abs(f.mean_r ?? 0) * 100))}%` }} /></div>
          <span className="text-[10px] text-muted num">{f.mean_r == null ? "n/a" : `${f.mean_r >= 0 ? "+" : ""}${f.mean_r.toFixed(2)}`}</span><span className="text-[10px] text-muted">fold {f.fold} · {f.n}</span></div>)}</div></div>
        <div><div className="text-xs font-medium">By market regime</div><table className="mt-1 w-full text-xs num"><tbody>{r.regimes?.map(g => <tr key={g.regime}><td className="font-sans text-muted">{g.regime}</td><td className="text-right">{g.n}</td><td className={`text-right ${tone(g.mean_r)}`}>{R(g.mean_r)}</td></tr>)}</tbody></table></div>
        <div><div className="text-xs font-medium">Threshold sensitivity (±20%)</div><table className="mt-1 w-full text-xs num"><tbody>{Object.entries(r.sensitivity ?? {}).map(([k, v]) => <tr key={k}><td className="font-sans text-muted">{k}</td><td className={`text-right ${tone(v)}`}>{R(v)}</td></tr>)}</tbody></table></div>
      </div>
      {r.logistic && <div><div className="text-xs font-medium">Interpretable baseline: logistic regression on the same features (trained before the holdout)</div>
        <p className="text-[11px] text-muted">Holdout AUC {num(r.logistic.test_auc, 3)} (0.5 is a coin flip). Base chance of hitting the profit barrier first {pct(r.logistic.base_probability, 0, false)}; the model&apos;s average estimate on this pattern&apos;s events {pct(r.logistic.mean_score_on_events, 0, false)}.</p>
        <div className="mt-1 flex flex-wrap gap-2 text-[11px]">{r.logistic.coefficients.map(c => <span key={c.feature} className={`rounded border border-line px-2 py-0.5 ${tone(c.weight)}`}>{c.feature} {c.weight > 0 ? "+" : ""}{c.weight}</span>)}</div></div>}
      <div className="text-[11px] text-muted">Permutation test: {r.permutation?.draws} random-entry samples averaged {R(r.permutation?.random_mean)}; 95th percentile {R(r.permutation?.random_p95)}. Costs: {r.cost_bps} bps round trip.
        {r.years && <> By year: {r.years.map(y => `${y.year} ${R(y.mean_r)} (${y.n})`).join(" · ")}.</>}</div>
      <details className="text-xs"><summary className="cursor-pointer text-muted">Data used (point-in-time snapshot)</summary><table className="mt-1 w-full num"><tbody>{r.data?.map(d => <tr key={d.symbol}><td className="font-sans">{d.symbol}</td><td>{d.from} to {d.to}</td><td>{d.bars} bars</td><td>{d.events} events</td><td>{d.source}</td><td className="text-muted">{d.hash}</td></tr>)}</tbody></table></details>
      {r.live && r.live.length > 0 && r.verdict === "Robust" && <p className="text-sm">On the latest bar this pattern is present in: <b>{r.live.join(", ")}</b>.</p>}
    </>)}
  </Card>);
}
