"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import { api } from "@/lib/api";
import { setAssistantContext } from "@/lib/assistant";
import { num, pct, tone } from "@/lib/format";
import { useAuth } from "@/components/AuthProvider";
import { LineChart } from "@/components/Chart";
import { TickerInput } from "@/components/TickerInput";
import { Button, Card, ErrorNote, Skeleton, SourceBadge } from "@/components/ui";

interface H { symbol: string; quantity: number; cost_basis: number | null }
interface P { id: number; name: string; source: string; cash: number; benchmark: string; holdings: H[] }
interface Pos {
  symbol: string; name: string | null; quantity: number; price: number; currency: string; value: number; weight: number; cost_basis: number | null;
  unrealized: number | null; unrealized_pct: number | null; day_change: number; change_pct: number | null; ret_1m: number | null; ret_12m: number | null;
  volatility: number | null; sector: string; forward_pe: number | null; dividend_yield: number | null; beta: number | null;
  grade: { overall: string | null; label: string | null } | null; source: string;
}
interface A {
  summary: { total_value: number; invested: number; cash: number; day_change: number; unrealized: number | null; cost_value: number | null; positions: number; top_weight: number | null;
    top5_weight: number; effective_holdings: number | null; est_annual_income: number; yield: number | null; weighted_forward_pe: number | null; weighted_beta: number | null };
  positions: Pos[]; sectors: { sector: string; weight: number }[];
  risk: { volatility: number | null; max_drawdown: number | null; ret_1y: number | null; var95_1d: number | null; beta?: number | null; corr_vs_bench?: number | null;
    bench_ret_1y?: number | null; bench_volatility?: number | null; avg_correlation: number | null; most_correlated: { a: string; b: string; corr: number }[] };
  series: { date: string; portfolio: number; bench?: number }[]; flags: { level: string; kind: string; symbol?: string; text: string }[];
  missing: { symbol: string; reason: string }[]; benchmark: string; data_labels: string[]; method: string;
}
const usd = (x: number | null | undefined, d = 0) => x == null ? "—" : `${x < 0 ? "−" : ""}$${Math.abs(x).toLocaleString("en-US", { maximumFractionDigits: d, minimumFractionDigits: d })}`;
const SAMPLE = "Symbol,Quantity,Cost basis per share\nAAPL,25,150\nMSFT,10,320\nKO,40,58\nSCHD,60,26\n";

export default function PortfolioPage() {
  const { user, ready } = useAuth();
  const [list, setList] = useState<{ id: number; name: string; positions: number }[] | null>(null);
  const [cur, setCur] = useState<P | null>(null);
  const [edit, setEdit] = useState<{ symbol: string; quantity: string; cost_basis: string }[]>([]);
  const [a, setA] = useState<A | null>(null);
  const [rev, setRev] = useState<{ markdown: string; engine: string; disclaimer: string; note?: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<Error | null>(null);
  const [editing, setEditing] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const pro = user?.plan === "pro";

  const load = useCallback(async (id?: number) => {
    setErr(null);
    try {
      const l = await api<{ id: number; name: string; positions: number }[]>("/api/portfolio");
      setList(l);
      const pick = id ?? l[0]?.id;
      if (pick) {
        const p = await api<P>(`/api/portfolio/${pick}`);
        setCur(p); setEdit(p.holdings.map(h => ({ symbol: h.symbol, quantity: String(h.quantity), cost_basis: h.cost_basis == null ? "" : String(h.cost_basis) })));
        setRev(null); setA(null);
        if (p.holdings.length) { setBusy("analysis"); setA(await api<A>(`/api/portfolio/${pick}/analysis`)); } else setEditing(true);
      } else { setCur(null); setA(null); }
    } catch (e) { setErr(e as Error); } finally { setBusy(null); }
  }, []);
  useEffect(() => { if (pro) load(); }, [pro, load]);
  useEffect(() => { setAssistantContext({ portfolio_id: cur?.id ?? null }); return () => setAssistantContext({}); }, [cur?.id]);

  if (!ready) return null;
  if (!user || !pro) return (
    <div className="mx-auto max-w-3xl px-4 py-20 text-center">
      <span className="rounded-full border border-primary/40 px-3 py-1 text-xs text-primary">Pro</span>
      <h1 className="mt-4 text-4xl">Portfolio analysis</h1>
      <p className="mt-3 text-muted">Enter or import your holdings and see value, P&amp;L, concentration, sector mix, risk, income and quant grades in one place, plus an AI-written review. Part of Irradiance Pro, and the foundation of IRAI AlgoTrader.</p>
      <div className="mt-6 flex justify-center gap-3">{user ? <Button href="/pricing">Upgrade to Pro</Button> : <Button href="/login?next=/portfolio">Sign in</Button>}<Button variant="outline" href="/algotrader">About AlgoTrader</Button></div>
    </div>);

  const create = async () => {
    const name = prompt("Portfolio name", list?.length ? `Portfolio ${list.length + 1}` : "My portfolio"); if (!name) return;
    try { const p = await api<P>("/api/portfolio", { method: "POST", json: { name } }); await load(p.id); setEditing(true); } catch (e) { setErr(e as Error); }
  };
  const saveHoldings = async () => {
    if (!cur) return; setErr(null); setBusy("save");
    try {
      const body = edit.filter(r => r.symbol.trim() && parseFloat(r.quantity)).map(r => ({ symbol: r.symbol.trim().toUpperCase(), quantity: parseFloat(r.quantity), cost_basis: r.cost_basis.trim() ? parseFloat(r.cost_basis) : null }));
      await api(`/api/portfolio/${cur.id}/holdings`, { method: "PUT", json: body });
      setEditing(false); await load(cur.id);
    } catch (e) { setErr(e as Error); setBusy(null); }
  };
  const importFile = async (f: File) => {
    if (!cur) return; setErr(null); setBusy("import");
    try {
      const r = await api<{ imported: number; warnings: string[] }>(`/api/portfolio/${cur.id}/import`, { method: "POST", json: { csv: await f.text(), mode: "replace" } });
      setMsg(`Imported ${r.imported} holdings.${r.warnings.length ? ` ${r.warnings.length} rows skipped.` : ""}`); setEditing(false); await load(cur.id);
    } catch (e) { setErr(e as Error); setBusy(null); }
  };
  const patch = async (b: Partial<P>) => { if (!cur) return; try { await api(`/api/portfolio/${cur.id}`, { method: "PATCH", json: b }); await load(cur.id); } catch (e) { setErr(e as Error); } };
  const del = async () => { if (!cur || !confirm(`Delete “${cur.name}”?`)) return; try { await api(`/api/portfolio/${cur.id}`, { method: "DELETE" }); await load(); } catch (e) { setErr(e as Error); } };
  const review = async () => { if (!cur) return; setBusy("review"); setErr(null); try { setRev(await api(`/api/portfolio/${cur.id}/review`, { method: "POST" })); } catch (e) { setErr(e as Error); } finally { setBusy(null); } };
  const mcHref = a ? `/lab/montecarlo?symbols=${a.positions.slice(0, 10).map(p => p.symbol).join(",")}&weights=${a.positions.slice(0, 10).map(p => p.weight.toFixed(4)).join(",")}&start=${Math.round(a.summary.invested)}` : "#";
  const s = a?.summary, r = a?.risk;

  return (
    <div className="mx-auto max-w-7xl px-4 py-10">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><div className="text-xs uppercase tracking-wide text-primary">IRAI AlgoTrader · Portfolio</div><h1 className="text-3xl">Portfolio analysis</h1>
          <p className="mt-1 max-w-2xl text-sm text-muted">Enter or import your holdings for a full analysis. Broker connections are coming soon; until then, export positions from your broker as CSV and import them here.</p></div>
        <div className="flex flex-wrap items-center gap-2">
          {list && list.length > 0 && <select value={cur?.id ?? ""} onChange={e => load(parseInt(e.target.value))} className="rounded border border-line bg-bg px-2 py-1.5 text-sm">{list.map(p => <option key={p.id} value={p.id}>{p.name} ({p.positions})</option>)}</select>}
          <Button variant="outline" onClick={create}>New portfolio</Button>
        </div>
      </div>
      <ErrorNote error={err} />
      {msg && <p className="mt-2 text-sm text-primary">{msg}</p>}

      {list && list.length === 0 && (
        <Card className="mt-6 p-10 text-center"><h2 className="text-xl">Start with your first portfolio</h2><p className="mt-2 text-sm text-muted">Add holdings by hand or import a CSV export from your broker.</p><Button className="mt-4" onClick={create}>Create portfolio</Button></Card>)}

      {cur && <>
        <div className="mt-5 flex flex-wrap items-center gap-2 text-sm">
          <b className="text-lg">{cur.name}</b><span className="rounded bg-accent px-2 py-0.5 text-[11px] text-muted">{cur.source === "csv" ? "Imported from CSV" : cur.source === "broker" ? "Broker sync" : "Entered by hand"}</span>
          <span className="ml-2 text-muted">Benchmark</span>
          <select value={cur.benchmark} onChange={e => patch({ benchmark: e.target.value })} className="rounded border border-line bg-bg px-1.5 py-0.5 text-xs">{["SPY", "QQQ", "IWM", "DIA", "ACWI", "VT", "AGG"].map(b => <option key={b}>{b}</option>)}</select>
          <span className="ml-2 text-muted">Cash</span>
          <input defaultValue={cur.cash || ""} placeholder="0" onBlur={e => { const v = parseFloat(e.target.value || "0"); if (v !== cur.cash) patch({ cash: v }); }} className="w-28 rounded border border-line bg-bg px-2 py-0.5 text-xs num" />
          <div className="ml-auto flex flex-wrap gap-2">
            <Button variant="outline" onClick={() => setEditing(x => !x)}>{editing ? "Close editor" : "Edit holdings"}</Button>
            <label className="cursor-pointer rounded-lg border border-line px-3 py-1.5 text-sm hover:border-primary">{busy === "import" ? "Importing…" : "Import CSV"}<input type="file" accept=".csv,text/csv" className="hidden" onChange={e => e.target.files?.[0] && importFile(e.target.files[0])} /></label>
            <Button variant="ghost" onClick={() => patch({ name: prompt("Rename portfolio", cur.name) ?? cur.name })}>Rename</Button>
            <Button variant="ghost" onClick={del}>Delete</Button>
          </div>
        </div>

        {editing && (
          <Card className="mt-4 p-5">
            <h2 className="font-semibold">Holdings</h2>
            <p className="text-xs text-muted">Cost basis is per share, in the security&apos;s own currency (optional, used for P&amp;L). Up to 60 holdings.</p>
            <div className="mt-3 space-y-2">{edit.map((row, i) => (
              <div key={i} className="grid grid-cols-[1fr_120px_140px_32px] items-center gap-2">
                <TickerInput value={row.symbol} onChange={v => setEdit(e => e.map((x, j) => j === i ? { ...x, symbol: v } : x))} />
                <input placeholder="Shares" value={row.quantity} onChange={e => setEdit(x => x.map((y, j) => j === i ? { ...y, quantity: e.target.value } : y))} className="rounded border border-line bg-bg px-2 py-1.5 text-sm num" />
                <input placeholder="Cost / share" value={row.cost_basis} onChange={e => setEdit(x => x.map((y, j) => j === i ? { ...y, cost_basis: e.target.value } : y))} className="rounded border border-line bg-bg px-2 py-1.5 text-sm num" />
                <button onClick={() => setEdit(x => x.filter((_, j) => j !== i))} className="text-muted hover:text-down" aria-label="Remove">×</button>
              </div>))}</div>
            <div className="mt-3 flex flex-wrap gap-2">
              <Button variant="outline" onClick={() => setEdit(x => [...x, { symbol: "", quantity: "", cost_basis: "" }])} disabled={edit.length >= 60}>+ Add holding</Button>
              <Button onClick={saveHoldings} disabled={busy === "save"}>{busy === "save" ? "Saving…" : "Save and analyze"}</Button>
            </div>
            <details className="mt-4 text-xs text-muted"><summary className="cursor-pointer">CSV format</summary>
              <p className="mt-2">Most broker &ldquo;positions&rdquo; exports work as-is (Schwab, Fidelity, E*TRADE, Robinhood, Webull, Interactive Brokers). The minimum is a Symbol and a Quantity column; a cost basis column (per share or total) adds P&amp;L. Repeated symbols across accounts are combined.</p>
              <pre className="mt-2 rounded bg-accent p-2 font-mono">{SAMPLE}</pre></details>
          </Card>)}

        {busy === "analysis" && !a && <div className="mt-6"><Skeleton rows={10} /></div>}
        {a && s && r && <>
          <div className="mt-5 grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-8">
            <Kpi k="Total value" v={usd(s.total_value)} sub={`${s.positions} positions${s.cash ? ` · cash ${usd(s.cash)}` : ""}`} />
            <Kpi k="Today" v={usd(s.day_change)} c={tone(s.day_change)} sub={pct(s.invested ? s.day_change / s.invested : null)} />
            <Kpi k="Unrealized P&L" v={usd(s.unrealized)} c={tone(s.unrealized)} sub={s.cost_value ? pct((s.unrealized ?? 0) / s.cost_value, 1) : "add cost basis"} />
            <Kpi k="1-year (today's mix)" v={pct(r.ret_1y, 1)} c={tone(r.ret_1y)} sub={`${a.benchmark} ${pct(r.bench_ret_1y, 1)}`} />
            <Kpi k="Volatility" v={pct(r.volatility, 0, false)} sub={`${a.benchmark} ${pct(r.bench_volatility, 0, false)}`} />
            <Kpi k="Beta · max drawdown" v={`${num(r.beta, 2)} · ${pct(r.max_drawdown, 0)}`} sub={`1-day VaR 95% ${pct(r.var95_1d, 1, false)}`} />
            <Kpi k="Income (est.)" v={usd(s.est_annual_income)} sub={`yield ${pct(s.yield, 2, false)}`} />
            <Kpi k="Diversification" v={num(s.effective_holdings, 1)} sub={`effective holdings · corr ${num(r.avg_correlation, 2)}`} />
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-3">
            <Card className="p-5 lg:col-span-2">
              <div className="flex items-baseline justify-between"><h2 className="font-semibold">Today&apos;s mix over the past year vs {a.benchmark}</h2><span className="text-xs text-muted">rebased to 100</span></div>
              {a.series.length > 1 && <LineChart height={230} dates={a.series.map(x => x.date)} format={x => x.toFixed(1)}
                series={[{ values: a.series.map(x => x.portfolio), color: "#E0605A", label: "Portfolio" }, { values: a.series.map(x => x.bench ?? null), color: "#8a94a6", dashed: true, label: a.benchmark }]} />}
              <p className="mt-2 text-[11px] text-muted">{a.method}</p>
            </Card>
            <Card className="p-5">
              <h2 className="font-semibold">Health check</h2>
              <ul className="mt-3 space-y-2 text-sm">{a.flags.map((f, i) => (
                <li key={i} className="flex gap-2"><span className={`mt-1.5 inline-block h-2 w-2 shrink-0 rounded-full ${f.level === "warn" ? "bg-down" : f.level === "ok" ? "bg-up" : "bg-primary"}`} />
                  <span>{f.symbol ? <><Link href={`/ticker/${f.symbol}`} className="font-medium hover:text-primary">{f.symbol}</Link>{f.text.slice(f.symbol.length)}</> : f.text}</span></li>))}</ul>
              <div className="mt-4 flex flex-wrap gap-2"><Button variant="outline" href={mcHref}>Monte Carlo this portfolio</Button>
                <Button variant="outline" href={`/compare?symbols=${a.positions.slice(0, 8).map(p => p.symbol).join(",")}`}>Compare holdings</Button></div>
            </Card>
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-3">
            <Card className="p-5"><h2 className="font-semibold">Sector exposure</h2>
              <ul className="mt-3 space-y-2 text-sm">{a.sectors.map(x => (
                <li key={x.sector}><div className="flex justify-between"><span>{x.sector}</span><span className="num">{pct(x.weight, 1, false)}</span></div>
                  <div className="mt-1 h-1.5 rounded bg-accent"><div className="h-1.5 rounded bg-primary" style={{ width: `${Math.min(100, x.weight * 100)}%` }} /></div></li>))}</ul></Card>
            <Card className="p-5"><h2 className="font-semibold">Portfolio character</h2>
              <dl className="mt-3 grid grid-cols-2 gap-y-2 text-sm num">
                {([["Largest position", pct(s.top_weight, 1, false)], ["Top 5", pct(s.top5_weight, 1, false)], ["Weighted forward P/E", num(s.weighted_forward_pe, 1)], ["Weighted beta", num(s.weighted_beta, 2)],
                  ["Correlation to " + a.benchmark, num(r.corr_vs_bench, 2)], ["Avg pairwise correlation", num(r.avg_correlation, 2)]] as [string, string][]).map(([k, v]) => <div key={k} className="contents"><dt className="text-muted">{k}</dt><dd className="text-right">{v}</dd></div>)}
              </dl></Card>
            <Card className="p-5"><h2 className="font-semibold">Most correlated pairs <span className="text-xs font-normal text-muted">6 months</span></h2>
              {!r.most_correlated.length ? <p className="mt-2 text-sm text-muted">Needs two or more holdings with price history.</p> :
                <ul className="mt-3 space-y-1.5 text-sm">{r.most_correlated.map(c => <li key={c.a + c.b} className="flex justify-between"><span>{c.a} · {c.b}</span><span className="num">{num(c.corr, 2)}</span></li>)}</ul>}
              <p className="mt-3 text-[11px] text-muted">Pairs near 1.0 tend to rise and fall together.</p></Card>
          </div>

          <Card className="mt-4 p-5">
            <h2 className="font-semibold">Positions</h2>
            <div className="mt-3 overflow-x-auto"><table className="w-full min-w-[980px] text-sm">
              <thead className="text-xs text-muted"><tr>{["Holding", "Weight", "Shares", "Price", "Value", "Cost", "Unrealized", "Day", "1M", "12M", "Volatility", "Fwd P/E", "Yield", "Rating", ""].map((h, i) => <th key={h + i} className={`py-1 font-normal ${i ? "text-right" : "text-left"}`}>{h}</th>)}</tr></thead>
              <tbody className="divide-y divide-line">{a.positions.map(p => (
                <tr key={p.symbol}>
                  <td className="py-1.5"><Link href={`/ticker/${encodeURIComponent(p.symbol)}`} className="font-medium hover:text-primary">{p.symbol}</Link> <span className="text-xs text-muted">{p.name}</span><div className="text-[11px] text-muted">{p.sector}</div></td>
                  <td className="text-right num"><div>{pct(p.weight, 1, false)}</div><div className="ml-auto mt-0.5 h-1 w-16 rounded bg-accent"><div className="h-1 rounded bg-primary" style={{ width: `${Math.min(100, p.weight * 100 * 2)}%` }} /></div></td>
                  <td className="text-right num">{num(p.quantity, p.quantity % 1 ? 3 : 0)}</td>
                  <td className="text-right num">{num(p.price)}{p.currency !== "USD" && <span className="text-[10px] text-muted"> {p.currency}</span>}</td>
                  <td className="text-right num">{usd(p.value)}</td>
                  <td className="text-right num">{p.cost_basis == null ? "—" : num(p.cost_basis)}</td>
                  <td className={`text-right num ${tone(p.unrealized)}`}>{p.unrealized == null ? "—" : <>{usd(p.unrealized)}<div className="text-[11px]">{pct(p.unrealized_pct, 1)}</div></>}</td>
                  <td className={`text-right num ${tone(p.change_pct)}`}>{pct(p.change_pct)}</td>
                  <td className={`text-right num ${tone(p.ret_1m)}`}>{pct(p.ret_1m, 1)}</td>
                  <td className={`text-right num ${tone(p.ret_12m)}`}>{pct(p.ret_12m, 1)}</td>
                  <td className="text-right num">{pct(p.volatility, 0, false)}</td>
                  <td className="text-right num">{num(p.forward_pe, 1)}</td>
                  <td className="text-right num">{pct(p.dividend_yield, 2, false)}</td>
                  <td className="text-right">{p.grade?.overall ?? "—"}</td>
                  <td className="text-right"><SourceBadge source={p.source} /></td>
                </tr>))}</tbody></table></div>
            {a.missing.length > 0 && <p className="mt-2 text-xs text-down">Not priced: {a.missing.map(m => `${m.symbol} (${m.reason})`).join(", ")}</p>}
            <p className="mt-2 text-[11px] text-muted">Values in USD at the latest FX rate. Prices: market feed ({a.data_labels.join(", ") || "n/a"}); ratings computed by Irradiance; statistics from Yahoo Finance.</p>
          </Card>

          <Card className="mt-4 p-5">
            <div className="flex flex-wrap items-center justify-between gap-2"><div><h2 className="font-semibold">IRAI portfolio review</h2><p className="text-sm text-muted">An AI-written read of the figures above: what stands out, the risk profile, and questions to research.</p></div>
              <Button onClick={review} disabled={busy === "review"}>{busy === "review" ? "Writing…" : rev ? "Rewrite review" : "Write my review"}</Button></div>
            {rev && <><div className="prose-irai mt-4"><ReactMarkdown>{rev.markdown}</ReactMarkdown></div>
              <p className="mt-3 text-[11px] text-muted">{rev.engine === "claude" ? "Written by Claude." : "Rules-based summary (the AI writer is not configured)."} {rev.disclaimer}</p></>}
          </Card>
        </>}
      </>}
      <p className="mt-6 text-[11px] text-muted">Portfolio analytics are research and education, not personalized investment advice, and do not consider your goals, taxes or circumstances. Irradiance does not hold funds or place trades. Your holdings are private to your account and are included in your data export.</p>
    </div>
  );
}

function Kpi({ k, v, sub, c = "" }: { k: string; v: string; sub?: string; c?: string }) {
  return <Card className="p-3"><div className="text-[11px] text-muted">{k}</div><div className={`stat mt-0.5 text-lg num ${c}`}>{v}</div>{sub && <div className="text-[11px] text-muted num">{sub}</div>}</Card>;
}
