"use client";
import Link from "next/link";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { compact, num, pct } from "@/lib/format";
import { useAuth } from "@/components/AuthProvider";
import { Button, Card, ErrorNote, PageHeader, SourceBadge } from "@/components/ui";
import { TickerInput } from "@/components/TickerInput";

interface MC {
  mode: "price" | "portfolio"; symbols: string[]; weights: number[]; start_value: number; horizon_days: number; paths: number; method: string;
  fan: Record<string, number[]>; terminal: Record<string, number>; expected_terminal: number; prob_gain: number; var_95: number; cvar_95: number;
  ann_vol_hist: number; ann_return_hist: number; histogram: { counts: number[]; edges: number[] }; sample_paths: number[][];
  prob_touch_target?: number; prob_end_above_target?: number; prob_touch_stop?: number; source: string; history_days: number;
  history_start: string; history_end: string; paths_capped: boolean; note: string;
}

function Fan({ mc }: { mc: MC }) {
  const W = 760, H = 300, P = { l: 56, r: 12, t: 10, b: 24 };
  const n = mc.fan["50"].length;
  const all = [...mc.fan["5"], ...mc.fan["95"], mc.start_value];
  const lo = Math.min(...all), hi = Math.max(...all);
  const x = (i: number) => P.l + (i / Math.max(1, n - 1)) * (W - P.l - P.r);
  const y = (v: number) => P.t + (1 - (v - lo) / (hi - lo || 1)) * (H - P.t - P.b);
  const band = (a: string, b: string) => `${mc.fan[a].map((v, i) => `${i ? "L" : "M"}${x(i)},${y(v)}`).join("")}${mc.fan[b].map((_, i) => `L${x(n - 1 - i)},${y(mc.fan[b][n - 1 - i])}`).join("")}Z`;
  const line = (vs: number[]) => vs.map((v, i) => `${i ? "L" : "M"}${x(i)},${y(v)}`).join("");
  const ticks = [lo, (lo + hi) / 2, hi];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Monte Carlo fan chart">
      {ticks.map(t => <g key={t}><line x1={P.l} x2={W - P.r} y1={y(t)} y2={y(t)} stroke="var(--color-line)" /><text x={P.l - 6} y={y(t) + 4} fontSize={11} textAnchor="end" fill="var(--color-muted)">{compact(t)}</text></g>)}
      <defs><clipPath id="mc-plot"><rect x={P.l} y={P.t} width={W - P.l - P.r} height={H - P.t - P.b} /></clipPath></defs>
      <g clipPath="url(#mc-plot)">{mc.sample_paths.slice(0, 15).map((p, i) => <path key={i} d={line(p)} fill="none" stroke="var(--color-muted)" strokeOpacity={0.18} />)}</g>
      <path d={band("5", "95")} fill="#f5a524" fillOpacity={0.14} />
      <path d={band("25", "75")} fill="#f5a524" fillOpacity={0.28} />
      <path d={line(mc.fan["50"])} fill="none" stroke="#f5a524" strokeWidth={2} />
      <line x1={P.l} x2={W - P.r} y1={y(mc.start_value)} y2={y(mc.start_value)} stroke="var(--color-fg)" strokeDasharray="4 4" strokeOpacity={0.5} />
      <text x={W - P.r} y={H - 6} fontSize={11} textAnchor="end" fill="var(--color-muted)">{mc.horizon_days} trading days</text>
      <text x={P.l} y={H - 6} fontSize={11} fill="var(--color-muted)">today</text>
    </svg>
  );
}

function Hist({ mc }: { mc: MC }) {
  const max = Math.max(...mc.histogram.counts);
  return (
    <div className="flex h-40 items-end gap-px">
      {mc.histogram.counts.map((c, i) => {
        const mid = (mc.histogram.edges[i] + mc.histogram.edges[i + 1]) / 2;
        return <div key={i} title={`${compact(mc.histogram.edges[i])}–${compact(mc.histogram.edges[i + 1])}: ${c} paths`} className="flex-1 rounded-t"
          style={{ height: `${(c / max) * 100}%`, background: mid >= mc.start_value ? "var(--color-up)" : "var(--color-down)", opacity: 0.75 }} />;
      })}
    </div>
  );
}

function MonteCarlo() {
  const sp = useSearchParams();
  const { user } = useAuth();
  const [rows, setRows] = useState<{ symbol: string; weight: string }[]>([{ symbol: sp.get("symbol") ?? "AAPL", weight: "1" }]);
  const [cfg, setCfg] = useState({ method: "bootstrap", drift: "historical", horizon: "252", paths: "2000", range: "5y", start: "", target: "", stop: "" });
  const [mc, setMc] = useState<MC | null>(null);
  const [busy, setBusy] = useState(false); const [err, setErr] = useState<Error | null>(null);
  const portfolio = rows.length > 1;
  // Pick up ?symbol= (and ?symbols=A,B) on first load and on client-side navigation from a ticker page.
  const qsSym = sp.get("symbol"), qsSyms = sp.get("symbols"), qsW = sp.get("weights"), qsStart = sp.get("start");
  useEffect(() => {
    const ws = (qsW ?? "").split(",");
    if (qsSyms) setRows(qsSyms.split(",").filter(Boolean).slice(0, 10).map((s, i) => ({ symbol: s.toUpperCase(), weight: ws[i] && parseFloat(ws[i]) > 0 ? ws[i] : "1" })));
    else if (qsSym) setRows([{ symbol: qsSym.toUpperCase(), weight: "1" }]);
    if (qsStart && parseFloat(qsStart) > 0) setCfg(c => ({ ...c, start: String(Math.round(parseFloat(qsStart))) }));
  }, [qsSym, qsSyms, qsW, qsStart]);
  const run = async () => {
    setBusy(true); setErr(null);
    const f = (s: string) => (s.trim() ? parseFloat(s) : null);
    try {
      setMc(await api<MC>("/api/lab/montecarlo", { method: "POST", json: {
        holdings: rows.filter(r => r.symbol.trim()).map(r => ({ symbol: r.symbol.trim().toUpperCase(), weight: parseFloat(r.weight) || 1 })),
        method: cfg.method, drift: cfg.drift, horizon_days: parseInt(cfg.horizon), paths: parseInt(cfg.paths), range: cfg.range,
        start_value: portfolio ? (f(cfg.start) ?? 10000) : f(cfg.start), target: f(cfg.target), stop: f(cfg.stop) } }));
    } catch (e) { setErr(e as Error); } finally { setBusy(false); }
  };
  const sel = (k: keyof typeof cfg, opts: [string, string][]) => (
    <select value={cfg[k]} onChange={e => setCfg({ ...cfg, [k]: e.target.value })} className="w-full rounded border border-line bg-bg px-2 py-1.5 text-sm">{opts.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>);
  return (
    <div className="mx-auto max-w-7xl px-4 py-10">
      <Link href="/lab" className="text-sm text-muted hover:text-fg">← Strategy Lab</Link>
      <PageHeader title="Monte Carlo simulator" intro="Simulate thousands of possible future paths for a stock or a weighted portfolio from its own history: the range of outcomes, the odds of reaching a target or a stop, and the tail risk." />
      <div className="mt-6 grid gap-6 lg:grid-cols-[340px_1fr]">
        <Card className="h-fit space-y-4 p-5">
          <div><div className="mb-1 text-xs text-muted">Holdings {portfolio && "(weights are normalised)"}</div>
            {rows.map((r, i) => (
              <div key={i} className="mb-2 flex gap-2">
                <TickerInput value={r.symbol} onChange={v => setRows(rs => rs.map((x, j) => j === i ? { ...x, symbol: v } : x))} />
                {portfolio && <input value={r.weight} onChange={e => setRows(rows.map((x, j) => j === i ? { ...x, weight: e.target.value } : x))} aria-label="Weight" className="w-20 rounded border border-line bg-bg px-2 py-1.5 text-right text-sm" />}
                {rows.length > 1 && <button onClick={() => setRows(rows.filter((_, j) => j !== i))} aria-label="Remove" className="text-muted hover:text-down">×</button>}
              </div>))}
            {rows.length < 10 && <button onClick={() => setRows([...rows, { symbol: "", weight: "1" }])} className="text-xs text-primary">+ Add holding (portfolio)</button>}
          </div>
          <label className="block text-xs text-muted">Method{sel("method", [["bootstrap", "Historical bootstrap (fat tails, keeps correlation)"], ["gbm", "Geometric Brownian motion (normal)"], ["student_t", "Student-t shocks (fatter tails)"]])}</label>
          <label className="block text-xs text-muted">Drift{sel("drift", [["historical", "Historical average return"], ["zero", "Zero expected return (pure risk view)"]])}</label>
          <div className="grid grid-cols-2 gap-2">
            <label className="text-xs text-muted">Horizon{sel("horizon", [["21", "1 month"], ["63", "3 months"], ["126", "6 months"], ["252", "1 year"], ["756", "3 years"], ["1260", "5 years"]])}</label>
            <label className="text-xs text-muted">History{sel("range", [["1y", "1 year"], ["2y", "2 years"], ["5y", "5 years"]])}</label>
            <label className="text-xs text-muted">Paths{sel("paths", [["1000", "1,000"], ["2000", "2,000"], ["5000", "5,000"], ["10000", "10,000"]])}</label>
            <label className="text-xs text-muted">{portfolio ? "Start value ($)" : "Start (blank = price)"}<input value={cfg.start} onChange={e => setCfg({ ...cfg, start: e.target.value })} className="w-full rounded border border-line bg-bg px-2 py-1.5 text-sm" /></label>
            <label className="text-xs text-muted">Target level<input value={cfg.target} onChange={e => setCfg({ ...cfg, target: e.target.value })} className="w-full rounded border border-line bg-bg px-2 py-1.5 text-sm" /></label>
            <label className="text-xs text-muted">Stop level<input value={cfg.stop} onChange={e => setCfg({ ...cfg, stop: e.target.value })} className="w-full rounded border border-line bg-bg px-2 py-1.5 text-sm" /></label>
          </div>
          <Button onClick={run} disabled={busy || !user} className="w-full">{busy ? "Simulating…" : "Run simulation"}</Button>
          {!user && <p className="text-xs text-muted"><Link href="/login?next=/lab/montecarlo" className="text-primary">Sign in</Link> to run simulations (free plan: 2,000 paths).</p>}
          <ErrorNote error={err} />
        </Card>
        <div className="space-y-4">
          {!mc ? <Card className="p-10 text-center text-muted">Choose a ticker (or several, with weights) and run the simulation.</Card> : <>
            <div className="grid gap-3 md:grid-cols-4">
              {([["Median outcome", num(mc.terminal["50"]), pct(mc.terminal["50"] / mc.start_value - 1, 1)], ["Range (5th–95th)", `${compact(mc.terminal["5"])} – ${compact(mc.terminal["95"])}`, ""],
                 ["Probability of a gain", pct(mc.prob_gain, 0, false), ""], ["95% VaR / CVaR", `${pct(mc.var_95, 1, false)} / ${pct(mc.cvar_95, 1, false)}`, "loss at horizon"]] as [string, string, string][]).map(([k, v, s]) =>
                <Card key={k} className="p-4"><div className="text-xs text-muted">{k}</div><div className="stat mt-1 text-xl">{v}</div>{s && <div className="text-xs text-muted">{s}</div>}</Card>)}
            </div>
            {(mc.prob_touch_target != null || mc.prob_touch_stop != null) && (
              <Card className="flex flex-wrap gap-6 p-4 text-sm">
                {mc.prob_touch_target != null && <span>Touches target: <b>{pct(mc.prob_touch_target, 0, false)}</b> · ends above it: <b>{pct(mc.prob_end_above_target ?? null, 0, false)}</b></span>}
                {mc.prob_touch_stop != null && <span>Touches stop: <b>{pct(mc.prob_touch_stop, 0, false)}</b></span>}
              </Card>)}
            <Card className="p-5"><div className="mb-2 flex items-center justify-between"><h2 className="font-semibold">Simulated paths</h2><span className="text-xs text-muted">median, 25–75% and 5–95% bands</span></div><Fan mc={mc} /></Card>
            <Card className="p-5"><h2 className="mb-2 font-semibold">Distribution at the horizon</h2><Hist mc={mc} />
              <div className="mt-1 flex justify-between text-[11px] text-muted"><span>{compact(mc.histogram.edges[0])}</span><span>{compact(mc.histogram.edges[mc.histogram.edges.length - 1])}</span></div></Card>
            <Card className="p-5 text-sm text-fg-2">
              <p>{mc.paths.toLocaleString()} paths · {mc.method} · {mc.horizon_days} days · history {mc.history_start} to {mc.history_end} ({mc.history_days} shared days) · historical annual return {pct(mc.ann_return_hist, 1)}, volatility {pct(mc.ann_vol_hist, 1, false)}{portfolio && ` · weights ${mc.symbols.map((s, i) => `${s} ${pct(mc.weights[i], 0, false)}`).join(", ")}`}{mc.paths_capped && " · paths capped by your plan"}</p>
              <p className="mt-2 text-xs text-muted">{mc.note}</p>
              <p className="mt-2 flex items-center gap-2 text-[11px] text-muted">Source: computed by Irradiance from daily closes (market feed) <SourceBadge source={mc.source} /></p>
            </Card>
          </>}
        </div>
      </div>
    </div>
  );
}

export default function Page() { return <Suspense><MonteCarlo /></Suspense>; }
