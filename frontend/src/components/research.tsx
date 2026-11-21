"use client";
// Ticker research panels. Every panel ends with a SourceLine naming where the numbers came from.
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useApi } from "@/lib/hooks";
import { ago, compact, num, pct, tone } from "@/lib/format";
import { Card, Skeleton, SourceBadge } from "@/components/ui";

type Src = { label: string; url?: string | null } | null | undefined;

export function SourceLine({ provider, source, extra, asOf }: { provider?: Src; source?: string; extra?: Src; asOf?: string | null }) {
  return (
    <p className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-muted">
      <span>Source:</span>
      {provider?.url ? <a href={provider.url} target="_blank" rel="noopener noreferrer" className="underline decoration-dotted hover:text-fg">{provider.label}</a> : <span>{provider?.label ?? "—"}</span>}
      {extra && <>· {extra.url ? <a href={extra.url} target="_blank" rel="noopener noreferrer" className="underline decoration-dotted hover:text-fg">{extra.label}</a> : extra.label}</>}
      {source && <SourceBadge source={source} />}
      {asOf && <span>· {ago(asOf)}</span>}
    </p>
  );
}

const Empty = ({ children }: { children: React.ReactNode }) => <p className="py-6 text-center text-sm text-muted">{children}</p>;

// ── Buzz ─────────────────────────────────────────────────────────────────────────────────────────
export interface Buzz {
  symbol: string; name: string; score: number; level: string; tone: number | null; tone_label: string | null; kind: string;
  components: Record<string, number | null>; inputs: Record<string, number | null>; headlines?: { title: string; url: string; published: string; source: string }[];
  providers: string[]; note: string; as_of: string; price_source: string;
}
const LEVEL_COLOR: Record<string, string> = { Quiet: "#64748b", Normal: "#2fbf8f", Elevated: "#f5a524", High: "#f07538", Extreme: "#f2545b" };

export function BuzzMeter({ score, level, compactView = false }: { score: number; level: string; compactView?: boolean }) {
  return (
    <div className={compactView ? "w-28" : ""}>
      <div className="flex items-center justify-between text-xs"><span className="font-semibold" style={{ color: LEVEL_COLOR[level] }}>{level}</span><span className="num text-muted">{score.toFixed(0)}/100</span></div>
      <div className="mt-1 h-2 rounded-full bg-accent" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={score} aria-label={`Buzz ${level}`}>
        <div className="h-2 rounded-full" style={{ width: `${Math.max(3, score)}%`, background: `linear-gradient(90deg, #2fbf8f, ${LEVEL_COLOR[level]})` }} />
      </div>
    </div>
  );
}

export function BuzzCard({ symbol, showHeadlines = true }: { symbol: string; showHeadlines?: boolean }) {
  const { data: b } = useApi<Buzz>(`/api/insight/${encodeURIComponent(symbol)}/buzz`);
  if (!b) return <Card className="p-5"><h2 className="font-semibold">Buzz</h2><Skeleton rows={3} /></Card>;
  const c = b.components;
  const bar = (label: string, v: number | null | undefined, detail: string) => (
    <div key={label} className="text-xs">
      <div className="flex justify-between"><span className="text-muted">{label}</span><span className="num">{detail}</span></div>
      <div className="mt-0.5 h-1 rounded bg-accent"><div className="h-1 rounded bg-primary" style={{ width: `${v ?? 0}%` }} /></div>
    </div>
  );
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between"><h2 className="font-semibold">Buzz</h2>{b.tone_label && <span className="text-xs text-muted">News tone: {b.tone_label}</span>}</div>
      <div className="mt-3"><BuzzMeter score={b.score} level={b.level} /></div>
      <div className="mt-4 space-y-2">
        {bar("News volume", c.news_volume, b.inputs.news_articles_today != null ? `${b.inputs.news_articles_today?.toFixed(0)} today vs ${b.inputs.news_daily_avg_30d?.toFixed(0)}/day` : "—")}
        {bar("Trading volume", c.trading_volume, b.inputs.volume_vs_average != null ? `${b.inputs.volume_vs_average?.toFixed(1)}× average` : "—")}
        {bar("Price move", c.price_move, b.inputs.move_in_sigmas != null ? `${b.inputs.move_in_sigmas?.toFixed(1)}σ today` : "—")}
        {bar("Filings (7 days)", c.filings, `${b.inputs.filings_7d ?? 0} 8-K / Form 4`)}
      </div>
      {showHeadlines && b.headlines && b.headlines.length > 0 && (
        <ul className="mt-4 space-y-2 border-t border-line pt-3 text-sm">
          {b.headlines.slice(0, 5).map(h => <li key={h.url}><a href={h.url} target="_blank" rel="noopener noreferrer" className="hover:text-primary">{h.title}</a><div className="text-[11px] text-muted">{h.source}{h.published ? ` · ${h.published.slice(0, 16)}` : ""}</div></li>)}
        </ul>
      )}
      <p className="mt-3 text-[11px] text-muted">{b.note}</p>
      <SourceLine provider={{ label: b.providers.join(" · ") }} source={b.price_source} asOf={b.as_of} />
    </Card>
  );
}

// ── Ratings & consensus ─────────────────────────────────────────────────────────────────────────
interface Ratings { overall_grade: string | null; overall_label: string | null; factors: Record<string, { grade: string | null; score: number | null; inputs: Record<string, number | null> }>; note: string; source: string; as_of: string }
const gradeTone = (g: string | null) => !g ? "text-muted" : g.startsWith("A") ? "text-up" : g.startsWith("B") ? "text-data-1" : g.startsWith("C") ? "text-primary" : "text-down";

export function RatingsCard({ symbol }: { symbol: string }) {
  const { data: r } = useApi<Ratings>(`/api/insight/${encodeURIComponent(symbol)}/ratings`);
  const [open, setOpen] = useState<string | null>(null);
  if (!r) return <Card className="p-5"><h2 className="font-semibold">Quant ratings</h2><Skeleton rows={4} /></Card>;
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between"><h2 className="font-semibold">Irradiance quant ratings</h2>
        <span className={`stat text-2xl ${gradeTone(r.overall_grade)}`}>{r.overall_grade ?? "—"}</span></div>
      <p className="text-xs text-muted">{r.overall_label ?? "Not enough data"}</p>
      <ul className="mt-3 divide-y divide-line text-sm">
        {Object.entries(r.factors).map(([k, f]) => (
          <li key={k} className="py-1.5">
            <button onClick={() => setOpen(open === k ? null : k)} className="flex w-full items-center justify-between capitalize">
              <span>{k}</span><span className={`stat ${gradeTone(f.grade)}`}>{f.grade ?? "—"}</span></button>
            {open === k && <dl className="mt-1 grid grid-cols-2 gap-x-2 text-xs text-muted">{Object.entries(f.inputs).map(([n, v]) => <div key={n} className="contents"><dt>{n}</dt><dd className="text-right num">{v == null ? "—" : Math.abs(v) < 5 && !n.includes("Beta") && !n.includes("P/") && !n.includes("EV") && !n.includes("PEG") ? pct(v, 1, false) : num(v, 2)}</dd></div>)}</dl>}
          </li>
        ))}
      </ul>
      <p className="mt-2 text-[11px] text-muted">{r.note} <Link href="/methodology#ratings" className="underline">How grades work</Link></p>
      <SourceLine provider={{ label: "Computed by Irradiance from Yahoo Finance fundamentals and price history" }} source={r.source} asOf={r.as_of} />
    </Card>
  );
}

interface Consensus { analyst_count: number | null; sentiment: string | null; recommendation_mean: number | null; target_mean: number | null; target_high: number | null; target_low: number | null; target_median: number | null; price: number | null; implied_move: number | null; source: string; note: string }

export function ConsensusCard({ symbol }: { symbol: string }) {
  const { data: c } = useApi<Consensus>(`/api/insight/${encodeURIComponent(symbol)}/consensus`);
  if (!c) return null;
  if (!c.analyst_count && !c.target_mean) return null;
  const lo = c.target_low, hi = c.target_high, px = c.price;
  const pos = (v: number | null) => (lo != null && hi != null && v != null && hi > lo ? Math.max(0, Math.min(100, ((v - lo) / (hi - lo)) * 100)) : null);
  return (
    <Card className="p-5">
      <h2 className="font-semibold">Wall Street consensus</h2>
      <p className="mt-1 text-sm"><span className="font-medium">{c.sentiment ?? "—"}</span> <span className="text-muted">· {c.analyst_count ?? "—"} analysts · mean score {num(c.recommendation_mean, 2)} (1 = most positive, 5 = most negative)</span></p>
      {lo != null && hi != null && (
        <div className="mt-4">
          <div className="relative h-2 rounded bg-accent">
            {pos(c.target_mean) != null && <span className="absolute -top-1 h-4 w-0.5 bg-primary" style={{ left: `${pos(c.target_mean)}%` }} title="Mean target" />}
            {pos(px) != null && <span className="absolute -top-1.5 h-5 w-1 rounded bg-fg" style={{ left: `${pos(px)}%` }} title="Price" />}
          </div>
          <div className="mt-1 flex justify-between text-xs text-muted num"><span>Low {num(lo)}</span><span>Mean {num(c.target_mean)} ({pct(c.implied_move, 1)})</span><span>High {num(hi)}</span></div>
        </div>
      )}
      <p className="mt-2 text-[11px] text-muted">{c.note}</p>
      <SourceLine provider={{ label: "Yahoo Finance analyst estimates" }} source={c.source} />
    </Card>
  );
}

// ── TradingView ──────────────────────────────────────────────────────────────────────────────────
const TV_SUFFIX: Record<string, string> = { T: "TSE", L: "LSE", HK: "HKEX", TW: "TWSE", DE: "XETR", PA: "EURONEXT", AS: "EURONEXT", SW: "SIX", NS: "NSE",
  SA: "BMFBOVESPA", CO: "OMXCOP", MC: "BME", MI: "MIL", ST: "OMXSTO", HE: "OMXHEX", OL: "OSL", KS: "KRX", AX: "ASX", MX: "BMV", TA: "TASE", JO: "JSE", TO: "TSX" };
const TV_INDEX: Record<string, string> = { "^GSPC": "SP:SPX", "^IXIC": "NASDAQ:IXIC", "^DJI": "DJ:DJI", "^N225": "TVC:NI225", "^STOXX50E": "TVC:SX5E", "^TNX": "TVC:US10Y" };

export function tvSymbol(s: string): string {
  if (TV_INDEX[s]) return TV_INDEX[s];
  if (s.endsWith("=X")) return `FX:${s.length === 8 ? s.slice(0, 6) : "USD" + s.slice(0, 3)}`;
  if (s.endsWith("-USD")) return `COINBASE:${s.replace("-", "")}`;
  const m = s.match(/^(.+)\.([A-Z]{1,2})$/);
  if (m && TV_SUFFIX[m[2]]) return `${TV_SUFFIX[m[2]]}:${m[1].replace(/^0+(?=\d)/, "")}`;
  return s.replace("-P", "/P");
}

export function TradingViewChart({ symbol, height = 520, tall = false }: { symbol: string; height?: number; tall?: boolean }) {
  const wrap = useRef<HTMLDivElement>(null);
  const ref = useRef<HTMLDivElement>(null);
  const [full, setFull] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.innerHTML = '<div class="tradingview-widget-container__widget" style="height:100%;width:100%"></div>';
    const s = document.createElement("script");
    s.src = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
    s.async = true;
    const dark = document.documentElement.dataset.theme !== "light";
    s.innerHTML = JSON.stringify({ autosize: true, symbol: tvSymbol(symbol), interval: "D", timezone: "Etc/UTC", theme: dark ? "dark" : "light",
      style: "1", locale: "en", allow_symbol_change: true, withdateranges: true, hide_side_toolbar: false, details: true,
      hotlist: false, calendar: false, studies: ["STD;SMA", "STD;RSI"], support_host: "https://www.tradingview.com",
      backgroundColor: dark ? "#0b1220" : "#ffffff" });
    el.appendChild(s);
    return () => { el.innerHTML = ""; };
  }, [symbol]);
  useEffect(() => {
    const on = () => setFull(document.fullscreenElement === wrap.current);
    document.addEventListener("fullscreenchange", on);
    return () => document.removeEventListener("fullscreenchange", on);
  }, []);
  const [pseudo, setPseudo] = useState(false); // fallback "full window" where the Fullscreen API is unavailable (iOS)
  const toggleFull = () => {
    if (pseudo) { setPseudo(false); return; }
    if (document.fullscreenElement) { document.exitFullscreen?.(); return; }
    if (wrap.current?.requestFullscreen) wrap.current.requestFullscreen().catch(() => setPseudo(true));
    else setPseudo(true);
  };
  const expanded = full || pseudo;
  // "tall" fills the window under the header; full screen takes the whole display.
  const h = expanded ? "100vh" : tall ? "max(640px, calc(100vh - 230px))" : `${height}px`;
  return (
    <div>
      <div ref={wrap} className={`relative bg-bg ${pseudo ? "fixed inset-0 z-50" : ""}`}>
        <button onClick={toggleFull} className="absolute right-2 top-2 z-10 rounded-md border border-line bg-card/90 px-2 py-1 text-xs hover:bg-accent"
          aria-label={expanded ? "Exit full screen" : "Full screen chart"}>{expanded ? "✕ Exit full screen" : "⤢ Full screen"}</button>
        <div ref={ref} className="tradingview-widget-container overflow-hidden rounded-lg border border-line" style={{ height: h, width: "100%" }} />
      </div>
      <p className="mt-2 text-[11px] text-muted">Interactive chart by <a href={`https://www.tradingview.com/symbols/${tvSymbol(symbol).replace(":", "-")}/`} target="_blank" rel="noopener noreferrer" className="underline">TradingView</a>: use the left toolbar to draw trend lines, Fibonacci levels and notes, and the Indicators button to add studies. Save layouts with a free TradingView account. Build and backtest your own rules in the <Link href={`/lab?symbol=${encodeURIComponent(symbol)}`} className="underline">Strategy Lab</Link>.</p>
    </div>
  );
}

// ── Statements ───────────────────────────────────────────────────────────────────────────────────
interface Stmt { periods: string[]; rows: { item: string; values: (number | null)[] }[]; key_items: string[] }
interface Statements { period: string; income: Stmt | null; balance: Stmt | null; cashflow: Stmt | null; source: string; provider?: Src; verify?: Src; note?: string }

export function StatementsPanel({ symbol }: { symbol: string }) {
  const [period, setPeriod] = useState<"annual" | "quarterly">("annual");
  const [which, setWhich] = useState<"income" | "balance" | "cashflow">("income");
  const [all, setAll] = useState(false);
  const { data } = useApi<Statements>(`/api/insight/${encodeURIComponent(symbol)}/statements?period=${period}`, undefined, [period]);
  const st = data?.[which];
  const rows = st ? (all ? st.rows : st.rows.filter(r => st.key_items.includes(r.item))) : [];
  const isPerShare = (item: string) => /EPS/.test(item);
  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex rounded-lg border border-line p-0.5 text-sm">
          {([["income", "Income statement"], ["balance", "Balance sheet"], ["cashflow", "Cash flow"]] as const).map(([k, l]) =>
            <button key={k} onClick={() => setWhich(k)} className={`rounded-md px-3 py-1 ${which === k ? "bg-accent text-fg" : "text-muted"}`}>{l}</button>)}
        </div>
        <div className="flex items-center gap-3 text-sm">
          <label className="flex items-center gap-1 text-muted"><input type="checkbox" checked={all} onChange={e => setAll(e.target.checked)} /> All line items</label>
          <div className="flex rounded-lg border border-line p-0.5">
            {(["annual", "quarterly"] as const).map(p => <button key={p} onClick={() => setPeriod(p)} className={`rounded-md px-3 py-1 capitalize ${period === p ? "bg-accent text-fg" : "text-muted"}`}>{p}</button>)}
          </div>
        </div>
      </div>
      {!data ? <Skeleton rows={8} /> : !st || !st.rows.length ? <Empty>{data.note ?? "No statement data for this security."}</Empty> : (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm">
            <thead className="text-xs text-muted"><tr><th className="py-2 text-left font-normal">{period === "annual" ? "Fiscal year ending" : "Quarter ending"}</th>{st.periods.map(p => <th key={p} className="py-2 text-right font-normal">{p}</th>)}</tr></thead>
            <tbody className="divide-y divide-line">
              {rows.map(r => (
                <tr key={r.item}><td className="py-1.5 pr-4">{r.item}</td>
                  {r.values.map((v, i) => <td key={i} className={`py-1.5 text-right num ${v != null && v < 0 ? "text-down" : ""}`}>{v == null ? "—" : isPerShare(r.item) ? num(v, 2) : Math.abs(v) >= 1e3 ? compact(v) : num(v, 2)}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <SourceLine provider={data?.provider} extra={data?.verify ? { label: "verify in SEC filings", url: data.verify.url } : undefined} source={data?.source} />
    </Card>
  );
}

// ── Earnings ─────────────────────────────────────────────────────────────────────────────────────
interface Earnings {
  quarterly: { date: string; eps_estimate: number | null; eps_actual: number | null; surprise_pct: number | null; upcoming: boolean }[];
  quarterly_financials?: { period_end: string; revenue: number | null; net_income: number | null; diluted_eps: number | null }[];
  annual: { fiscal_year_end: string; diluted_eps: number | null; net_income: number | null; revenue: number | null; source: string; source_url?: string }[];
  source: string; provider?: Src; annual_provider?: string | null; note?: string;
}

export function EarningsPanel({ symbol }: { symbol: string }) {
  const { data: e } = useApi<Earnings>(`/api/insight/${encodeURIComponent(symbol)}/earnings`);
  if (!e) return <Card className="p-5"><Skeleton rows={8} /></Card>;
  const next = e.quarterly.filter(q => q.upcoming).at(-1);
  const past = e.quarterly.filter(q => !q.upcoming);
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card className="p-5">
        <h2 className="font-semibold">Quarterly earnings</h2>
        {next && <p className="mt-1 text-sm">Next report <span className="font-medium">{next.date}</span>{next.eps_estimate != null && <> · EPS estimate {num(next.eps_estimate)}</>}</p>}
        {!past.length ? <Empty>{e.note ?? "No quarterly earnings history."}</Empty> : (
          <table className="mt-3 w-full text-sm">
            <thead className="text-xs text-muted"><tr><th className="py-1 text-left font-normal">Reported</th><th className="text-right font-normal">EPS est.</th><th className="text-right font-normal">EPS actual</th><th className="text-right font-normal">Surprise</th></tr></thead>
            <tbody className="divide-y divide-line">{past.slice(0, 12).map(q => <tr key={q.date}><td className="py-1.5">{q.date}</td><td className="text-right num">{num(q.eps_estimate)}</td><td className="text-right num">{num(q.eps_actual)}</td>
              <td className={`text-right num ${tone(q.surprise_pct)}`}>{q.surprise_pct == null ? "—" : `${q.surprise_pct > 0 ? "+" : ""}${q.surprise_pct.toFixed(1)}%`}</td></tr>)}</tbody>
          </table>
        )}
        {e.quarterly_financials && e.quarterly_financials.length > 0 && (
          <table className="mt-4 w-full text-sm">
            <thead className="text-xs text-muted"><tr><th className="py-1 text-left font-normal">Quarter ending</th><th className="text-right font-normal">Revenue</th><th className="text-right font-normal">Net income</th><th className="text-right font-normal">Diluted EPS</th></tr></thead>
            <tbody className="divide-y divide-line">{e.quarterly_financials.map(q => <tr key={q.period_end}><td className="py-1.5">{q.period_end}</td><td className="text-right num">{compact(q.revenue)}</td><td className="text-right num">{compact(q.net_income)}</td><td className="text-right num">{num(q.diluted_eps)}</td></tr>)}</tbody>
          </table>
        )}
        <SourceLine provider={e.provider ?? { label: "Yahoo Finance" }} source={e.source} />
      </Card>
      <Card className="p-5">
        <h2 className="font-semibold">Annual earnings history</h2>
        {!e.annual.length ? <Empty>No annual earnings history.</Empty> : (
          <table className="mt-3 w-full text-sm">
            <thead className="text-xs text-muted"><tr><th className="py-1 text-left font-normal">Fiscal year end</th><th className="text-right font-normal">Revenue</th><th className="text-right font-normal">Net income</th><th className="text-right font-normal">Diluted EPS</th><th className="text-right font-normal">EPS growth</th></tr></thead>
            <tbody className="divide-y divide-line">{e.annual.map((a, i) => {
              const prev = e.annual[i + 1]?.diluted_eps;
              const g = prev && a.diluted_eps != null && prev > 0 ? a.diluted_eps / prev - 1 : null;
              return <tr key={a.fiscal_year_end}><td className="py-1.5">{a.fiscal_year_end}</td><td className="text-right num">{compact(a.revenue)}</td><td className="text-right num">{compact(a.net_income)}</td><td className="text-right num">{num(a.diluted_eps)}</td><td className={`text-right num ${tone(g)}`}>{pct(g, 1)}</td></tr>;
            })}</tbody>
          </table>
        )}
        <SourceLine provider={e.annual[0]?.source_url ? { label: e.annual[0].source, url: e.annual[0].source_url } : { label: e.annual_provider ?? "Yahoo Finance" }} source={e.source} />
      </Card>
    </div>
  );
}

// ── Dividends ────────────────────────────────────────────────────────────────────────────────────
interface Dividends { history: { date: string; amount: number }[]; annual?: { year: number; total: number }[]; ttm_per_share?: number | null; yield_ttm?: number | null; forward_rate?: number | null;
  forward_yield?: number | null; payout_ratio?: number | null; ex_dividend_date?: string | null; five_year_growth?: number | null; consecutive_increases?: number; source: string; provider?: Src; note?: string; fund_note?: string | null }

export function DividendsPanel({ symbol }: { symbol: string }) {
  const { data: d } = useApi<Dividends>(`/api/insight/${encodeURIComponent(symbol)}/dividends`);
  if (!d) return <Card className="p-5"><Skeleton rows={6} /></Card>;
  if (!d.history.length) return <Card className="p-5"><h2 className="font-semibold">Dividends</h2><Empty>{d.note ?? `${symbol} has no dividend history.`}</Empty><SourceLine provider={d.provider} source={d.source} /></Card>;
  const fy = d.forward_yield != null ? (d.forward_yield > 1 ? d.forward_yield / 100 : d.forward_yield) : null;
  const maxA = Math.max(...(d.annual ?? []).map(a => a.total), 0);
  return (
    <Card className="p-5">
      <h2 className="font-semibold">Dividends</h2>
      <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-4">
        {([["Trailing 12m / share", num(d.ttm_per_share, 4)], ["Trailing yield", pct(d.yield_ttm, 2, false)], ["Forward yield", pct(fy, 2, false)],
           ["Payout ratio", pct(d.payout_ratio, 0, false)], ["Ex-dividend date", d.ex_dividend_date ?? "—"], ["5-year growth (CAGR)", pct(d.five_year_growth, 1)],
           ["Consecutive annual increases", String(d.consecutive_increases ?? "—")], ["Forward annual rate", num(d.forward_rate, 2)]] as [string, string][]).map(([k, v]) =>
          <div key={k} className="rounded-lg border border-line p-3"><div className="text-xs text-muted">{k}</div><div className="stat mt-1 text-lg">{v}</div></div>)}
      </div>
      {d.annual && d.annual.length > 0 && (
        <div className="mt-5"><div className="mb-2 text-xs text-muted">Dividends per share by calendar year</div>
          <div className="flex h-32 items-end gap-1">{d.annual.map(a => <div key={a.year} className="flex flex-1 flex-col items-center gap-1" title={`${a.year}: ${a.total.toFixed(4)}`}>
            <div className="w-full rounded-t bg-primary/80" style={{ height: `${maxA ? (a.total / maxA) * 100 : 0}%` }} /><span className="text-[10px] text-muted">{String(a.year).slice(2)}</span></div>)}</div></div>
      )}
      <details className="mt-4 text-sm"><summary className="cursor-pointer text-muted">Payment history ({d.history.length})</summary>
        <ul className="mt-2 grid grid-cols-2 gap-x-6 md:grid-cols-4">{[...d.history].reverse().slice(0, 40).map(h => <li key={h.date} className="flex justify-between border-b border-line py-1"><span>{h.date}</span><span className="num">{num(h.amount, 4)}</span></li>)}</ul></details>
      {d.fund_note && <p className="mt-2 text-xs text-muted">{d.fund_note}</p>}
      <SourceLine provider={d.provider} source={d.source} />
    </Card>
  );
}

// ── Peers & ratios ───────────────────────────────────────────────────────────────────────────────
interface Peers { group: string; columns: { key: string; label: string }[]; rows: Record<string, number | string | null>[]; peer_median: Record<string, number | null>; provider: Src; note: string }
const PCT_KEYS = new Set(["gross_margin", "operating_margin", "profit_margin", "roe", "revenue_growth", "earnings_growth", "dividend_yield"]);
export const fmtRatio = (k: string, v: unknown) => typeof v !== "number" ? "—" : k === "market_cap" ? compact(v)
  : k === "dividend_yield" ? pct(v > 1 ? v / 100 : v, 2, false) : PCT_KEYS.has(k) ? pct(v, 1, false) : num(v, k === "beta" ? 2 : 1);

export function PeersPanel({ symbol }: { symbol: string }) {
  const [add, setAdd] = useState(""); const [extra, setExtra] = useState("");
  const { data: p } = useApi<Peers>(`/api/insight/${encodeURIComponent(symbol)}/peers${extra ? `?add=${encodeURIComponent(extra)}` : ""}`, undefined, [extra]);
  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">Peers &amp; ratios <span className="text-xs font-normal text-muted">{p?.group}</span></h2>
        <form onSubmit={e => { e.preventDefault(); setExtra(add.toUpperCase()); }} className="flex gap-2">
          <input value={add} onChange={e => setAdd(e.target.value)} placeholder="Add tickers, e.g. ORCL,CRM" className="w-52 rounded border border-line bg-bg px-2 py-1 text-sm" />
          <button className="rounded border border-line px-3 text-sm">Add</button>
          <Link href={`/compare?symbols=${[symbol, ...(p?.rows ?? []).slice(1, 4).map(r => r.symbol)].join(",")}`} className="rounded border border-line px-3 py-1 text-sm hover:bg-accent">Compare in depth →</Link>
        </form>
      </div>
      {!p ? <Skeleton rows={6} /> : (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[1100px] text-sm">
            <thead className="text-xs text-muted"><tr><th className="sticky left-0 bg-card py-2 text-left font-normal">Company</th><th className="text-right font-normal">Price</th>{p.columns.map(c => <th key={c.key} className="px-2 text-right font-normal">{c.label}</th>)}</tr></thead>
            <tbody className="divide-y divide-line">
              {p.rows.map((r, i) => (
                <tr key={String(r.symbol)} className={i === 0 ? "bg-primary/5" : ""}>
                  <td className="sticky left-0 bg-card py-1.5"><Link href={`/ticker/${r.symbol}`} className="font-medium hover:text-primary">{r.symbol}</Link><div className="max-w-40 truncate text-[11px] text-muted">{r.name}</div></td>
                  <td className="text-right num">{num(r.price as number)}</td>
                  {p.columns.map(c => <td key={c.key} className="px-2 text-right num">{fmtRatio(c.key, r[c.key])}</td>)}
                </tr>
              ))}
              <tr className="text-muted"><td className="sticky left-0 bg-card py-1.5 text-xs">Peer median</td><td />{p.columns.map(c => <td key={c.key} className="px-2 text-right num">{fmtRatio(c.key, p.peer_median[c.key])}</td>)}</tr>
            </tbody>
          </table>
        </div>
      )}
      <p className="mt-2 text-[11px] text-muted">{p?.note}</p>
      <SourceLine provider={p?.provider} />
    </Card>
  );
}

// ── Technicals ───────────────────────────────────────────────────────────────────────────────────
interface Tech { price: number; sma: Record<string, number | null>; distance_from_sma: Record<string, number | null>; rsi14: number | null; macd: { macd: number; signal: number; histogram: number };
  bollinger: { middle: number | null; upper: number | null; lower: number | null }; volatility_20d_ann: number | null; high_52w: number; low_52w: number; from_high_52w: number; from_low_52w: number;
  performance: Record<string, number | null>; trend: string; signals: string[]; source: string; provider: Src; note: string }

export function TechnicalsPanel({ symbol }: { symbol: string }) {
  const { data: t } = useApi<Tech>(`/api/insight/${encodeURIComponent(symbol)}/technicals`);
  if (!t) return <Card className="p-5"><Skeleton rows={6} /></Card>;
  if (!t.sma) return <Card className="p-5"><Empty>{t.note}</Empty></Card>;
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between"><h2 className="font-semibold">Technicals</h2>
        <span className={`rounded-full px-3 py-1 text-sm ${t.trend === "Uptrend" ? "bg-up/15 text-up" : t.trend === "Downtrend" ? "bg-down/15 text-down" : "bg-accent text-muted"}`}>{t.trend}</span></div>
      <div className="mt-4 grid gap-4 md:grid-cols-3">
        <div><div className="text-xs text-muted">Moving averages</div>
          <table className="mt-1 w-full text-sm"><tbody>{Object.entries(t.sma).map(([n, v]) => <tr key={n}><td className="py-0.5">{n}-day</td><td className="text-right num">{num(v)}</td><td className={`text-right num ${tone(t.distance_from_sma[n])}`}>{pct(t.distance_from_sma[n], 1)}</td></tr>)}</tbody></table></div>
        <div><div className="text-xs text-muted">Momentum</div>
          <table className="mt-1 w-full text-sm"><tbody>
            <tr><td className="py-0.5">RSI (14)</td><td className="text-right num">{num(t.rsi14, 1)}</td></tr>
            <tr><td className="py-0.5">MACD (12,26,9)</td><td className="text-right num">{num(t.macd.macd, 2)}</td></tr>
            <tr><td className="py-0.5">Signal / histogram</td><td className={`text-right num ${tone(t.macd.histogram)}`}>{num(t.macd.signal, 2)} / {num(t.macd.histogram, 2)}</td></tr>
            <tr><td className="py-0.5">Bollinger (20, 2σ)</td><td className="text-right num">{num(t.bollinger.lower)} – {num(t.bollinger.upper)}</td></tr>
            <tr><td className="py-0.5">Volatility (20d, ann.)</td><td className="text-right num">{pct(t.volatility_20d_ann, 1, false)}</td></tr>
          </tbody></table></div>
        <div><div className="text-xs text-muted">Range &amp; performance</div>
          <table className="mt-1 w-full text-sm"><tbody>
            <tr><td className="py-0.5">52-week range</td><td className="text-right num">{num(t.low_52w)} – {num(t.high_52w)}</td></tr>
            <tr><td className="py-0.5">From 52-week high</td><td className={`text-right num ${tone(t.from_high_52w)}`}>{pct(t.from_high_52w, 1)}</td></tr>
            {Object.entries(t.performance).map(([k, v]) => <tr key={k}><td className="py-0.5">{k} return</td><td className={`text-right num ${tone(v)}`}>{pct(v, 1)}</td></tr>)}
          </tbody></table></div>
      </div>
      {t.signals.length > 0 && <ul className="mt-4 space-y-1 text-sm">{t.signals.map(s => <li key={s}>• {s}</li>)}</ul>}
      <p className="mt-3 text-[11px] text-muted">{t.note}</p>
      <SourceLine provider={t.provider} source={t.source} />
    </Card>
  );
}

// ── Filings, news, preferreds, analysis ─────────────────────────────────────────────────────────
interface Filings { filings: { form: string; label: string; date: string; url: string }[]; source: string; note?: string; edgar_url?: string; company?: string }

export function FilingsPanel({ symbol, limit = 25 }: { symbol: string; limit?: number }) {
  const { data: f } = useApi<Filings>(`/api/insight/${encodeURIComponent(symbol)}/filings`);
  const [form, setForm] = useState("All");
  if (!f) return <Card className="p-5"><Skeleton rows={6} /></Card>;
  const forms = ["All", ...Array.from(new Set(f.filings.map(x => x.form))).slice(0, 8)];
  const rows = f.filings.filter(x => form === "All" || x.form === form).slice(0, limit);
  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-center justify-between gap-2"><h2 className="font-semibold">SEC filings</h2>
        <div className="flex flex-wrap gap-1">{forms.map(x => <button key={x} onClick={() => setForm(x)} className={`rounded px-2 py-0.5 text-xs ${form === x ? "bg-accent text-fg" : "text-muted"}`}>{x}</button>)}</div></div>
      {!rows.length ? <Empty>{f.note ?? "No filings."}</Empty> : (
        <ul className="mt-3 divide-y divide-line text-sm">{rows.map(x => <li key={x.url} className="flex items-center justify-between gap-3 py-1.5">
          <a href={x.url} target="_blank" rel="noopener noreferrer" className="hover:text-primary"><span className="mr-2 rounded bg-accent px-1.5 py-0.5 text-[11px]">{x.form}</span>{x.label}</a><span className="shrink-0 text-xs text-muted">{x.date}</span></li>)}</ul>
      )}
      <SourceLine provider={{ label: "SEC EDGAR", url: f.edgar_url ?? "https://www.sec.gov/edgar/search/" }} source={f.source} />
    </Card>
  );
}

export function NewsPanel({ symbol }: { symbol: string }) {
  const { data } = useApi<{ title: string; url: string; published: string; source: string }[]>(`/api/insight/${encodeURIComponent(symbol)}/headlines`);
  return (
    <Card className="p-5">
      <h2 className="font-semibold">News</h2>
      {!data ? <Skeleton rows={6} /> : !data.length ? <Empty>No recent headlines (headlines need live mode).</Empty> : (
        <ul className="mt-3 divide-y divide-line">{data.map(h => <li key={h.url} className="py-2"><a href={h.url} target="_blank" rel="noopener noreferrer" className="text-sm hover:text-primary">{h.title}</a>
          <div className="text-[11px] text-muted">{h.source}{h.published ? ` · ${h.published.slice(0, 22)}` : ""}</div></li>)}</ul>
      )}
      <SourceLine provider={{ label: "Yahoo Finance RSS, GDELT Project" }} />
      <p className="text-[11px] text-muted">Headlines link to the original publishers; Irradiance does not edit or endorse them.</p>
    </Card>
  );
}

export function PreferredsPanel({ symbol }: { symbol: string }) {
  const { data: p } = useApi<{ preferreds: { symbol: string; name: string; price: number | null; change_pct: number | null; yield: number | null; source: string }[]; provider?: Src; note?: string; source: string }>(`/api/insight/${encodeURIComponent(symbol)}/preferreds`);
  return (
    <Card className="p-5">
      <h2 className="font-semibold">Preferred securities</h2>
      {!p ? <Skeleton rows={3} /> : !p.preferreds.length ? <Empty>{p.note ?? "No exchange-listed preferreds found."}</Empty> : (
        <table className="mt-3 w-full text-sm"><thead className="text-xs text-muted"><tr><th className="py-1 text-left font-normal">Security</th><th className="text-right font-normal">Price</th><th className="text-right font-normal">Day</th><th className="text-right font-normal">Yield</th></tr></thead>
          <tbody className="divide-y divide-line">{p.preferreds.map(r => <tr key={r.symbol}><td className="py-1.5"><Link href={`/ticker/${encodeURIComponent(r.symbol)}`} className="font-medium hover:text-primary">{r.symbol}</Link><div className="text-[11px] text-muted">{r.name}</div></td>
            <td className="text-right num">{num(r.price)}</td><td className={`text-right num ${tone(r.change_pct)}`}>{pct(r.change_pct)}</td><td className="text-right num">{fmtRatio("dividend_yield", r.yield)}</td></tr>)}</tbody></table>
      )}
      {p?.preferreds.length ? <p className="mt-2 text-[11px] text-muted">{p.note}</p> : null}
      <SourceLine provider={p?.provider} source={p?.source} />
    </Card>
  );
}

interface ThreadRow { id: number; title: string; author: string; kind: string; outlook: string | null; score: number; replies: number; excerpt: string; created_at: string }
const OUTLOOK = { bullish: "text-up", neutral: "text-muted", bearish: "text-down" } as Record<string, string>;

export function AnalysisPanel({ symbol }: { symbol: string }) {
  const { data } = useApi<ThreadRow[]>(`/api/community/threads?ticker=${encodeURIComponent(symbol)}`);
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between"><h2 className="font-semibold">Member analysis</h2>
        <Link href={`/community/write?ticker=${encodeURIComponent(symbol)}`} className="rounded-lg border border-line px-3 py-1 text-sm hover:bg-accent">Write analysis</Link></div>
      {!data ? <Skeleton rows={4} /> : !data.length ? <Empty>No member analysis on {symbol} yet. Be the first to publish your thesis.</Empty> : (
        <ul className="mt-3 divide-y divide-line">{data.map(t => <li key={t.id} className="py-3">
          <Link href={`/community/threads/${t.id}`} className="font-medium hover:text-primary">{t.title}</Link>
          <div className="mt-0.5 flex flex-wrap gap-2 text-xs text-muted"><span>@{t.author}</span><span className="capitalize">{t.kind}</span>{t.outlook && <span className={`capitalize ${OUTLOOK[t.outlook]}`}>{t.outlook}</span>}<span>▲ {t.score}</span><span>{t.replies} comments</span><span>{ago(t.created_at)}</span></div>
          {t.excerpt && <p className="mt-1 line-clamp-2 text-sm text-fg-2">{t.excerpt}</p>}</li>)}</ul>
      )}
      <p className="mt-2 text-[11px] text-muted">Member posts are the authors&rsquo; own views and must disclose positions. Not investment advice.</p>
    </Card>
  );
}
