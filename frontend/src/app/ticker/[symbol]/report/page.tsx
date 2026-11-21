"use client";
/* eslint-disable @typescript-eslint/no-explicit-any */
import Link from "next/link";
import { use } from "react";
import { type TickerPage } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { compact, num, pct, tone } from "@/lib/format";
import { LogoMark } from "@/components/Header";
import { Cites, ProgressSteps, useAnalystRun, type AnalystSource } from "@/components/Analyst";
import { useAuth } from "@/components/AuthProvider";
import { Button, Skeleton } from "@/components/ui";
import { GroupedBars, Histogram, Oscillator, PriceChart, RangeBar, RegimeStrip, ScoreDots, SeriesChart, SignedBars } from "@/components/ReportCharts";

interface Ratings { overall_grade: string; overall_label: string; factors: Record<string, { grade: string | null; score: number | null }> }
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const SECTIONS: [string, string][] = [
  ["Executive summary", "Headline view, key takeaways and a five-factor scorecard."],
  ["Price action & trend structure", "Two-year chart with 50/200-day averages, the moving-average stack, ADX and key support and resistance."],
  ["Momentum", "RSI(14), MACD histogram, rate of change and 12-1 month momentum."],
  ["Relative performance", "Returns against SPY and the sector ETF, and the relative-strength line."],
  ["Volatility & risk", "Realised-vol term structure, ATR, beta, drawdowns, VaR/CVaR, return distribution and the volatility regime."],
  ["Statistical ranges & scenarios", "Volatility-implied ranges and the conditions behind upside, base and downside paths."],
  ["Valuation & fundamentals", "Multiples, profitability, growth and balance sheet, peer comparison and quant ratings."],
  ["Earnings & dividends", "EPS beats and misses, the next report date and dividend profile."],
  ["Options, positioning & seasonality", "Implied vs realised vol, expected move, put/call, ownership and calendar tendencies."],
  ["Sentiment, news & the Street", "Consensus target range, news flow, filings and attention."],
  ["Pattern Lab read-through", "Which stress-tested setups are present today, and how they have tested."],
  ["Bull case, bear case & catalysts", "Both sides from the same facts, dated catalysts, risks and open questions."],
];

const p0 = (x: number | null | undefined, d = 1) => pct(x, d, false);
const ps = (x: number | null | undefined, d = 1) => pct(x, d);

function H2({ n, title, sub, brk = false }: { n: number; title: string; sub?: string; brk?: boolean }) {
  return <div className={`mt-9 border-t-2 pt-3 print-avoid-break ${brk ? "print:break-before-page print:mt-0" : ""}`} style={{ borderColor: "#E0605A" }}>
    <div className="flex items-baseline gap-3"><span className="stat text-sm" style={{ color: "#E0605A" }}>{String(n).padStart(2, "0")}</span><h2 className="text-xl">{title}</h2></div>
    {sub && <p className="mt-0.5 text-xs text-muted">{sub}</p>}</div>;
}
function KV({ rows, cols = 2 }: { rows: [string, React.ReactNode][]; cols?: number }) {
  return <dl className={`grid gap-x-6 gap-y-1 text-xs ${cols === 3 ? "grid-cols-3" : cols === 1 ? "grid-cols-1" : "grid-cols-2"}`}>{rows.map(([k, v]) => <div key={k} className="flex justify-between gap-2 border-b border-line/60 py-1"><dt className="text-muted">{k}</dt><dd className="num text-right font-medium">{v ?? "—"}</dd></div>)}</dl>;
}
function Table({ head, rows, right = [] }: { head: string[]; rows: React.ReactNode[][]; right?: number[] }) {
  return <table className="print-avoid-break w-full text-xs"><thead><tr className="border-b border-line text-muted">{head.map((h, i) => <th key={i} className={`py-1.5 font-medium ${right.includes(i) ? "text-right" : "text-left"}`}>{h}</th>)}</tr></thead>
    <tbody>{rows.map((r, i) => <tr key={i} className="border-b border-line/60">{r.map((c, j) => <td key={j} className={`py-1.5 ${right.includes(j) ? "num text-right" : ""}`}>{c}</td>)}</tr>)}</tbody></table>;
}
function Prose({ title = "Analyst read", children, ids, src }: { title?: string; children?: React.ReactNode; ids?: string[]; src?: AnalystSource[] }) {
  if (!children) return null;
  return <div className="print-avoid-break rounded-md border-l-2 bg-accent/40 p-3 text-sm leading-relaxed" style={{ borderColor: "#E0605A" }}><div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted">{title}</div>{children}{ids && src && <Cites ids={ids} sources={src} />}</div>;
}

export default function TickerReport({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol: raw } = use(params);
  const symbol = decodeURIComponent(raw).toUpperCase();
  const { user } = useAuth();
  const { data } = useApi<TickerPage>(`/api/market/ticker/${encodeURIComponent(symbol)}`);
  const { data: rt } = useApi<Ratings>(`/api/insight/${encodeURIComponent(symbol)}/ratings`);
  const { report, running, start, err } = useAnalystRun(symbol);
  const ready = report?.status === "done" && report.result ? report.result : null;
  const { data: live } = useApi<any>(ready?.quant ? null : `/api/insight/${encodeURIComponent(symbol)}/profile`);
  const today = new Date().toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" });
  if (!data) return <div className="mx-auto max-w-4xl px-4 py-12"><Skeleton rows={10} /></div>;
  const q = data.quote, info: any = data.info ?? {};
  const Q: any = ready?.quant ?? live;
  const a = ready?.analysis, src = ready?.sources ?? [];
  const snap = ready?.snapshot;
  const fund: any = ready?.fundamentals_full ?? info;
  const lv = Q?.levels, tr = Q?.trend, mo = Q?.momentum, rk = Q?.risk, rg = Q?.regime, vol = Q?.volume, op = Q?.options, pos = Q?.positioning;
  const perf: any[] = Q?.performance?.rows ?? [];
  const cons: any = snap?.consensus ?? {};
  const keyLevels = lv ? (lv.rows as any[]).filter(r => /Swing|52-week/.test(r.level)).slice(0, 6).map(r => ({ label: r.level.replace("Swing ", ""), price: r.price })) : [];
  const generated = ready?.generated_at ? new Date(ready.generated_at).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" }) : null;
  const sec = Q?.performance?.sector_etf;

  return (
    <div className="report mx-auto max-w-4xl px-4 py-6 print:max-w-none print:px-0 print:py-0">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2 print:hidden">
        <Link href={`/ticker/${encodeURIComponent(symbol)}`} className="text-sm text-muted hover:text-fg">← Back to {symbol}</Link>
        <div className="flex gap-2">
          {user && <Button variant="outline" onClick={() => start(!!ready)} disabled={running}>{running ? "Analyzing…" : ready ? "Refresh analysis" : "Run AI analysis"}</Button>}
          <Button onClick={() => window.print()}>Print / save as PDF</Button>
        </div>
      </div>
      {err && <p className="mb-3 text-sm text-down print:hidden">{err.message}</p>}
      {report && running && <div className="mb-4 rounded border border-line p-4 print:hidden"><ProgressSteps r={report} /></div>}

      <article className="rounded-lg border border-line bg-card p-8 print:border-0 print:p-0">
        {/* ── cover ── */}
        <header className="flex items-start justify-between border-b-2 pb-4" style={{ borderColor: "#E0605A" }}>
          <div className="flex items-center gap-3">
            <LogoMark className="h-10 w-auto" />
            <div><div className="text-xl font-bold tracking-wide" style={{ fontFamily: "var(--font-display)" }}>IRRADIANCE<span className="logo-ai">.AI</span></div>
              <div className="text-[11px] uppercase tracking-[0.2em] text-muted">Equity research report · IRAI Analyst Bot</div></div>
          </div>
          <div className="text-right text-xs text-muted"><div>{today}</div><div>irradiance.ai/ticker/{symbol}</div>{generated && <div>Analysis generated {generated}</div>}</div>
        </header>

        <section className="mt-5 flex flex-wrap items-end justify-between gap-3">
          <div><h1 className="text-3xl">{q.name ?? symbol} <span className="text-muted">({symbol})</span></h1>
            <p className="text-sm text-muted">{[info.sector, info.industry, q.exchange].filter(Boolean).join(" · ")}</p></div>
          <div className="text-right"><div className="stat text-3xl num">{num(q.price)} <span className="text-base text-muted">{q.currency}</span></div>
            <div className={`text-sm num ${tone(q.change_pct)}`}>{ps(q.change_pct, 2)} today · data {q.source}</div></div>
        </section>

        <section className="mt-5 grid gap-6 md:grid-cols-[1.25fr_1fr] print:mt-3 print:gap-4 print:grid-cols-[1.25fr_1fr]">
          <div>
            {a ? <>
              <div className="text-[10px] font-semibold uppercase tracking-wide" style={{ color: "#E0605A" }}>Headline</div>
              <h2 className="mt-1 text-lg leading-snug">{a.headline}</h2>
              <p className="mt-2 text-sm leading-relaxed print:text-[12px] print:leading-snug">{a.summary}</p>
            </> : <p className="rounded border border-line p-3 text-sm text-muted">The written analysis appears here after an Analyst Bot run. {user ? "Use “Run AI analysis” above, then print." : "Sign in to run one."} Every chart and table in this report is computed from market data and prints on its own.</p>}
            <div className="mt-4 rounded-md border border-line p-3">
              <div className="text-[10px] font-semibold uppercase tracking-wide text-muted">What this report covers</div>
              <ol className="mt-1.5 grid gap-x-4 gap-y-0.5 text-[11px] sm:grid-cols-2 print:grid-cols-2 print:text-[10px]">{SECTIONS.map(([t], i) => <li key={t}><span className="num mr-1" style={{ color: "#E0605A" }}>{String(i + 1).padStart(2, "0")}</span>{t}</li>)}</ol>
            </div>
          </div>
          <div className="rounded-md border border-line p-3">
            <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted">Snapshot</div>
            <KV cols={1} rows={[
              ["Market cap", info.market_cap ? `$${compact(info.market_cap)}` : "—"], ["52-week range", q.fifty_two_week_low ? `${num(q.fifty_two_week_low)} – ${num(q.fifty_two_week_high)}` : "—"],
              ["Position in 52-week range", lv ? p0(lv.pct_of_52w_range, 0) : "—"], ["12-month return", <span key="r" className={tone(perf.find(r => r.period === "1Y")?.stock)}>{ps(perf.find(r => r.period === "1Y")?.stock)}</span>],
              ["Forward P/E · EV/EBITDA", `${num(fund.forward_pe, 1)} · ${num(fund.ev_ebitda, 1)}`], ["Beta (1y vs SPY)", num(rk?.beta_1y ?? info.beta, 2)],
              ["20-day realised vol", p0(rk?.vol_20d, 0)], ["Volatility regime", rg ? `${rg.current} (${rg.days_in_regime} sessions)` : "—"],
              ["Quant rating", rt ? `${rt.overall_grade} · ${rt.overall_label}` : "—"], ["Street", cons.analyst_count ? `${cons.sentiment ?? "—"} · ${cons.analyst_count} analysts` : "—"],
              ["Dividend yield", p0(fund.dividend_yield, 2)], ["Next earnings", snap?.next_earnings?.date ?? "—"],
            ]} />
          </div>
        </section>

        {a?.key_takeaways && a.key_takeaways.length > 0 && <section className="mt-5 print-avoid-break print:mt-3">
          <div className="text-[10px] font-semibold uppercase tracking-wide text-muted">Key takeaways</div>
          <ul className="mt-1.5 space-y-1.5 text-sm print:space-y-1 print:text-[11.5px] print:leading-snug">{a.key_takeaways.map((k, i) => <li key={i} className="flex gap-2"><span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: "#E0605A" }} /><span>{k.point}<Cites ids={k.sources} sources={src} /></span></li>)}</ul>
        </section>}

        {Q?.scorecard && <section className="mt-5 print-avoid-break print:mt-3">
          <div className="text-[10px] font-semibold uppercase tracking-wide text-muted">Factor scorecard (descriptive read of the data, not a rating)</div>
          <Table head={["Factor", "Read", "", "Evidence"]} rows={(Q.scorecard as any[]).map(s => [<b key="f">{s.factor}</b>, s.read, <ScoreDots key="d" read={s.read} />, <span key="e" className="text-muted">{s.evidence}</span>])} />
        </section>}

        {!Q && <div className="mt-8"><Skeleton rows={6} /></div>}
        {Q && <>
          {/* ── 2 price action ── */}
          <section className="rsec"><H2 n={2} title={SECTIONS[1][0]} sub={SECTIONS[1][1]} />
          <div className="mt-3"><PriceChart dates={Q.chart.dates} close={Q.chart.close} sma50={Q.chart.sma50} sma200={Q.chart.sma200} volume={Q.chart.volume} levels={keyLevels.slice(0, 3)} /></div>
          <div className="mt-4 grid gap-6 md:grid-cols-2 print:grid-cols-2">
            <div><div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted">Trend structure</div>
              <KV cols={1} rows={[["MA stack", tr.ma_stack], ["vs 20-day", <span key="a" className={tone(tr.vs_sma20)}>{ps(tr.vs_sma20)}</span>], ["vs 50-day", <span key="b" className={tone(tr.vs_sma50)}>{ps(tr.vs_sma50)}</span>],
                ["vs 200-day", <span key="c" className={tone(tr.vs_sma200)}>{ps(tr.vs_sma200)}</span>], ["200-day slope (1 month)", ps(tr.sma200_slope_1m, 2)],
                ["Last 50/200 cross", tr.last_cross ? `${tr.last_cross.type}, ${tr.last_cross.date} (${tr.last_cross.sessions_ago} sessions)` : "none in window"],
                ["ADX(14) · +DI / −DI", tr.adx14 ? `${num(tr.adx14, 0)} (${tr.trend_strength}) · ${num(tr.plus_di, 0)} / ${num(tr.minus_di, 0)}` : "—"]]} />
              {vol && <><div className="mb-1 mt-3 text-[10px] font-semibold uppercase tracking-wide text-muted">Volume & participation</div>
                <KV cols={1} rows={[["Relative volume (today vs 20-day)", `${num(vol.relative_volume, 2)}x`], ["20-day vs 3-month volume", `${num(vol.rvol_20_vs_3m, 2)}x`],
                  ["Up/down volume (20 days)", num(vol.up_down_volume_20d, 2)], ["On-balance volume, 1 month", vol.obv_trend_1m], ["Avg dollar volume (20 days)", `$${compact(vol.dollar_volume_20d)}`]]} /></>}
            </div>
            <div><div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted">Key levels</div>
              <Table head={["Level", "Price", "Distance"]} right={[1, 2]} rows={(lv.rows as any[]).map(r => [r.level === "Last close" ? <b key="l">Last close</b> : r.level, num(r.price), <span key="d" className={r.level === "Last close" ? "" : tone(r.distance)}>{r.level === "Last close" ? "—" : ps(r.distance)}</span>])} />
            </div>
          </div>
          <div className="mt-4"><Prose src={src}>{a?.price_action}</Prose></div>

          </section>
          {/* ── 3 momentum ── */}
          <section className="rsec"><H2 n={3} title={SECTIONS[2][0]} sub={SECTIONS[2][1]} />
          <div className="mt-3 space-y-3">
            <Oscillator kind="rsi" title={`RSI(14) · ${num(mo.rsi14, 0)} (${mo.rsi_state})`} dates={mo.series.dates} values={mo.series.rsi} />
            <Oscillator kind="hist" title={`MACD histogram · ${mo.macd_state}`} dates={mo.series.dates} values={mo.series.macd_hist} />
          </div>
          <div className="mt-3"><KV cols={3} rows={[["RSI(14)", num(mo.rsi14, 1)], ["MACD / signal", `${num(mo.macd, 2)} / ${num(mo.macd_signal, 2)}`], ["Histogram", num(mo.macd_hist, 2)],
            ["Rate of change, 1 month", ps(mo.roc_21)], ["Rate of change, 3 months", ps(mo.roc_63)], ["12-1 month momentum", ps(mo.mom_12_1)]]} /></div>
          <div className="mt-3"><Prose src={src}>{a?.technical}</Prose></div>

          </section>
          {/* ── 4 relative ── */}
          <section className="rsec"><H2 n={4} title={SECTIONS[3][0]} sub={SECTIONS[3][1]} />
          <div className="mt-3"><GroupedBars title="Total price return by period" groups={perf.filter(r => r.spy != null || r.period === "YTD").map(r => r.period)}
            series={[{ label: symbol, color: "#E0605A", values: perf.filter(r => r.spy != null || r.period === "YTD").map(r => r.stock) },
              { label: "SPY", color: "var(--color-data-1)", values: perf.filter(r => r.spy != null || r.period === "YTD").map(r => r.spy) },
              ...(sec ? [{ label: sec, color: "var(--color-data-2)", values: perf.filter(r => r.spy != null || r.period === "YTD").map(r => r.sector) }] : [])]} /></div>
          {Q.relative_strength && <div className="mt-3"><SeriesChart title={`Relative strength vs SPY (rebased to 1.0) · 3-month change ${ps(Q.relative_strength.change_3m)}`} dates={Q.relative_strength.dates} values={Q.relative_strength.ratio} baseline={1} color="#E0605A" /></div>}
          <div className="mt-3"><Table head={["Period", symbol, "SPY", "Excess vs SPY", ...(sec ? [sec] : [])]} right={[1, 2, 3, 4]} rows={perf.map(r => [r.period, <span key="s" className={tone(r.stock)}>{ps(r.stock)}</span>, ps(r.spy),
            <span key="e" className={tone(r.stock != null && r.spy != null ? r.stock - r.spy : null)}>{r.stock != null && r.spy != null ? ps(r.stock - r.spy) : "—"}</span>, ...(sec ? [ps(r.sector)] : [])])} /></div>
          <div className="mt-3"><Prose src={src}>{a?.relative_performance}</Prose></div>

          </section>
          {/* ── 5 volatility & risk ── */}
          <section className="rsec"><H2 n={5} title={SECTIONS[4][0]} sub={SECTIONS[4][1]} />
          <div className="mt-3 grid gap-6 md:grid-cols-2 print:grid-cols-2">
            <div><div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted">Risk metrics (trailing 1 year)</div>
              <KV cols={1} rows={[["Realised vol: 10d / 20d / 60d / 1y", `${p0(rk.vol_10d, 0)} / ${p0(rk.vol_20d, 0)} / ${p0(rk.vol_60d, 0)} / ${p0(rk.vol_1y, 0)}`],
                ["20-day vol percentile (1y)", p0(rk.vol_percentile_1y, 0)], ["ATR(14)", `${num(rk.atr14, 2)} (${p0(rk.atr_pct, 1)} of price)`],
                ["Beta · correlation to SPY", rk.beta_1y != null ? `${num(rk.beta_1y, 2)} · ${num(rk.correlation_1y, 2)}` : "—"],
                ["Upside / downside capture", rk.upside_capture != null ? `${num(rk.upside_capture, 2)} / ${num(rk.downside_capture, 2)}` : "—"],
                ["Max drawdown · current", `${ps(rk.max_drawdown_1y)} · ${ps(rk.current_drawdown)}`], ["1-day VaR(95) · CVaR(95)", `${p0(rk.var95_1d, 2)} · ${p0(rk.cvar95_1d, 2)}`],
                ["Best · worst day", `${ps(rk.best_day_1y)} · ${ps(rk.worst_day_1y)}`], ["Sharpe · Sortino (rf = 0)", `${num(rk.sharpe_1y, 2)} · ${num(rk.sortino_1y, 2)}`],
                ["Skew · excess kurtosis", `${num(rk.skew_1y, 2)} · ${num(rk.kurtosis_1y, 2)}`], ["Up days", p0(rk.up_days_1y, 0)]]} /></div>
            <div className="space-y-3">
              <SeriesChart title="Drawdown from trailing 1-year peak" dates={rk.drawdown_series.dates} values={rk.drawdown_series.dd} baseline={0} area color="var(--color-down)" pct height={130} />
              <SeriesChart title="Rolling 20-day realised volatility (annualised)" dates={rk.vol_series.dates} values={rk.vol_series.vol} area color="var(--color-data-4)" pct height={130} />
            </div>
          </div>
          <div className="mt-3 grid gap-6 md:grid-cols-2 print:grid-cols-2">
            <Histogram title="Distribution of daily returns (1 year)" edges={rk.distribution.edges} counts={rk.distribution.counts} varLine={rk.var95_1d} />
            {rg && <div><RegimeStrip title={`Volatility regime (3-state hidden Markov model) · today ${rg.current}`} dates={rg.strip.dates} state={rg.strip.state} />
              <Table head={["Regime", "Typical vol", "Share of days", "Today's probability"]} right={[1, 2, 3]} rows={(rg.states as any[]).map(s => [s.name, p0(s.annual_vol, 0), p0(s.share, 0), p0(rg.probabilities[s.name], 0)])} />
              <p className="mt-1 text-[10px] text-muted">Historical chance of staying in today&apos;s regime tomorrow: {p0(rg.stay_probability, 0)}.</p></div>}
          </div>
          <div className="mt-3"><Prose src={src}>{a?.volatility_risk}</Prose></div>

          </section>
          {/* ── 6 ranges & scenarios ── */}
          <section className="rsec"><H2 n={6} title={SECTIONS[5][0]} sub={SECTIONS[5][1]} />
          {(() => { const m1 = (Q.ranges.rows as any[]).find(r => r.horizon === "1 month"); return m1 ? <div className="mt-3"><RangeBar title="One-month volatility range (±1σ and ±2σ from 20-day realised vol)" low={m1.minus_2sd * 0.99} high={m1.plus_2sd * 1.01}
            marks={[{ label: "−2σ", value: m1.minus_2sd }, { label: "−1σ", value: m1.minus_1sd }, { label: "Last", value: q.price ?? tr.price, strong: true }, { label: "+1σ", value: m1.plus_1sd }, { label: "+2σ", value: m1.plus_2sd }]} /></div> : null; })()}
          <div className="mt-2"><Table head={["Horizon", "−2σ", "−1σ", "+1σ", "+2σ", "1σ move"]} right={[1, 2, 3, 4, 5]} rows={(Q.ranges.rows as any[]).map(r => [r.horizon, num(r.minus_2sd), num(r.minus_1sd), num(r.plus_1sd), num(r.plus_2sd), `±${p0(r.one_sd_pct, 1)}`])} />
            <p className="mt-1 text-[10px] text-muted">{Q.ranges.basis}. These are statistical ranges, not price targets or forecasts.</p></div>
          {a?.scenarios && a.scenarios.length > 0 && <div className="mt-3 grid gap-3 md:grid-cols-3 print:grid-cols-3">{a.scenarios.map(sc => (
            <div key={sc.name} className="print-avoid-break rounded-md border border-line p-3 text-xs"><div className={`text-sm font-semibold ${sc.name === "Upside" ? "text-up" : sc.name === "Downside" ? "text-down" : ""}`}>{sc.name}</div>
              <p className="mt-1 leading-relaxed">{sc.conditions}<Cites ids={sc.sources} sources={src} /></p></div>))}</div>}

          </section>
          {/* ── 7 valuation ── */}
          <section className="rsec"><H2 n={7} title={SECTIONS[6][0]} sub={SECTIONS[6][1]} />
          <div className="mt-3 grid gap-6 md:grid-cols-3 print:grid-cols-3">
            <div><div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted">Valuation</div><KV cols={1} rows={[["Trailing P/E", num(fund.trailing_pe, 1)], ["Forward P/E", num(fund.forward_pe, 1)], ["PEG", num(fund.peg_ratio, 2)], ["EV/EBITDA", num(fund.ev_ebitda, 1)], ["Price/sales", num(fund.price_to_sales, 1)], ["Price/book", num(fund.price_to_book, 1)]]} /></div>
            <div><div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted">Profitability & growth</div><KV cols={1} rows={[["Gross margin", p0(fund.gross_margin)], ["Operating margin", p0(fund.operating_margin)], ["Net margin", p0(fund.profit_margin)], ["ROE", p0(fund.roe)], ["Revenue growth (y/y)", ps(fund.revenue_growth)], ["Earnings growth (y/y)", ps(fund.earnings_growth)]]} /></div>
            <div><div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted">Balance sheet & cash</div><KV cols={1} rows={[["Debt/equity", fund.debt_to_equity != null ? `${num(fund.debt_to_equity, 0)}%` : "—"], ["Free cash flow", `$${compact(fund.free_cash_flow)}`], ["Revenue (TTM)", `$${compact(fund.revenue)}`], ["FCF yield", fund.free_cash_flow && info.market_cap ? p0(fund.free_cash_flow / info.market_cap) : "—"]]} /></div>
          </div>
          {ready?.peers?.rows && ready.peers.rows.length > 0 && <div className="mt-4"><div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted">Peer comparison</div>
            <Table head={["Company", "Fwd P/E", "EV/EBITDA", "Op. margin", "Rev. growth", "ROE"]} right={[1, 2, 3, 4, 5]} rows={[...ready.peers.rows.map((r: any) => [r.symbol === symbol ? <b key="s">{r.symbol}</b> : r.symbol, num(r.forward_pe, 1), num(r.ev_ebitda, 1), p0(r.operating_margin), ps(r.revenue_growth), p0(r.roe)]),
              ...(ready.peers.median ? [[<i key="m">Peer median</i>, num(ready.peers.median.forward_pe, 1), num(ready.peers.median.ev_ebitda, 1), p0(ready.peers.median.operating_margin), ps(ready.peers.median.revenue_growth), p0(ready.peers.median.roe)]] : [])]} />
            {ready.peers.median?.forward_pe && fund.forward_pe ? <p className="mt-1 text-[11px] text-muted">Forward P/E is {ps(fund.forward_pe / (ready.peers.median.forward_pe as number) - 1, 0)} versus the peer median.</p> : null}</div>}
          {rt?.factors && <div className="mt-4 print-avoid-break"><div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted">Irradiance quant ratings · overall {rt.overall_grade} ({rt.overall_label})</div>
            <div className="grid grid-cols-5 gap-2 text-center text-sm">{Object.entries(rt.factors).map(([k, f]) => <div key={k} className="rounded border border-line p-2"><div className="text-[11px] capitalize text-muted">{k}</div><div className="stat text-lg">{f.grade ?? "—"}</div></div>)}</div></div>}
          <div className="mt-3"><Prose src={src}>{a?.valuation}</Prose></div>

          </section>
          {/* ── 8 earnings ── */}
          <section className="rsec"><H2 n={8} title={SECTIONS[7][0]} sub={SECTIONS[7][1]} />
          {ready?.earnings?.last_4 && ready.earnings.last_4.length > 0 ? <div className="mt-3 grid gap-6 md:grid-cols-2 print:grid-cols-2">
            <SignedBars title="EPS surprise vs consensus" unit="raw" labels={[...ready.earnings.last_4].reverse().map(e => e.date.slice(0, 7))} values={[...ready.earnings.last_4].reverse().map(e => e.surprise_pct)} />
            <Table head={["Report date", "EPS est.", "EPS actual", "Surprise"]} right={[1, 2, 3]} rows={ready.earnings.last_4.map(e => [e.date, num(e.eps_estimate), num(e.eps_actual), <span key="s" className={tone(e.surprise_pct)}>{e.surprise_pct == null ? "—" : `${e.surprise_pct > 0 ? "+" : ""}${e.surprise_pct.toFixed(1)}%`}</span>])} />
          </div> : <p className="mt-3 text-xs text-muted">No reported quarters available{ready ? "" : " until an analysis has run"}.</p>}
          <div className="mt-3 grid gap-6 md:grid-cols-2 print:grid-cols-2">
            <KV cols={1} rows={[["Next report", ready?.earnings?.next?.date ?? snap?.next_earnings?.date ?? "—"], ["EPS estimate (next)", num(ready?.earnings?.next?.eps_estimate ?? snap?.next_earnings?.eps_estimate)],
              ["Options-implied move (front expiry)", op?.expected_move_pct ? `±${p0(op.expected_move_pct, 1)}` : "—"]]} />
            {ready?.dividends ? <KV cols={1} rows={[["Dividend (TTM per share)", num(ready.dividends.ttm_per_share as number, 2)], ["Yield (TTM)", p0(ready.dividends.yield_ttm as number, 2)], ["Payout ratio", p0(ready.dividends.payout_ratio as number, 0)],
              ["5-year dividend growth", ps(ready.dividends.five_year_growth as number)], ["Consecutive increases", ready.dividends.consecutive_increases ?? "—"], ["Ex-dividend date", ready.dividends.ex_dividend_date ?? "—"]]} /> : <p className="text-xs text-muted">No regular dividend on record.</p>}
          </div>
          <div className="mt-3"><Prose src={src}>{a?.earnings_quality}</Prose></div>

          </section>
          {/* ── 9 options, positioning, seasonality ── */}
          <section className="rsec"><H2 n={9} title={SECTIONS[8][0]} sub={SECTIONS[8][1]} />
          <div className="mt-3 grid gap-6 md:grid-cols-2 print:grid-cols-2">
            <div><div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted">Options {op?.expiry ? `· front expiry ${op.expiry} (${op.days} days)` : ""}</div>
              {op ? <KV cols={1} rows={[["ATM implied vol", p0(op.atm_iv, 0)], ["Implied ÷ 20-day realised", op.iv_vs_realised ? `${num(op.iv_vs_realised, 2)}x` : "—"], ["Straddle-implied move", op.expected_move_pct ? `±${p0(op.expected_move_pct, 1)} (±${num(op.expected_move, 2)})` : "—"],
                ["Put/call volume · open interest", `${num(op.put_call_volume, 2)} · ${num(op.put_call_oi, 2)}`], ["Max pain", num(op.max_pain, 2)]]} /> : <p className="text-xs text-muted">Listed options data was not available for this report.</p>}
              {op?.unusual?.length > 0 && <div className="mt-2"><Table head={["Unusual", "Strike", "Volume", "Open int.", "IV"]} right={[1, 2, 3, 4]} rows={op.unusual.map((u: any) => [u.type, num(u.strike), compact(u.volume), compact(u.open_interest), p0(u.iv, 0)])} /></div>}</div>
            <div><div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted">Positioning</div>
              <KV cols={1} rows={[["Short interest (% of float)", p0(pos?.short_percent_float ?? info.short_percent_float)], ["Institutional ownership", p0(pos?.held_by_institutions ?? info.held_by_institutions, 0)], ["Insider ownership", p0(pos?.held_by_insiders, 1)], ["Float", compact(pos?.float_shares)]]} /></div>
          </div>
          <div className="mt-3"><Prose src={src}>{a?.options_positioning}</Prose></div>
          {Q.seasonality?.by_month?.length > 0 && <div className="mt-4"><SignedBars title={`Average return by calendar month (${Q.from?.slice(0, 4)}–${Q.as_of?.slice(0, 4)}), with share of years positive`}
            labels={(Q.seasonality.by_month as any[]).map(m => MONTHS[m.month - 1])} values={(Q.seasonality.by_month as any[]).map(m => m.avg)} sub={(Q.seasonality.by_month as any[]).map(m => `${Math.round(m.hit_rate * 100)}% up`)} />
            <p className="mt-1 text-[10px] text-muted">Seasonality is descriptive and based on few observations per month; treat it as context, not an edge.</p></div>}

          </section>
          {/* ── 10 sentiment ── */}
          <section className="rsec"><H2 n={10} title={SECTIONS[9][0]} sub={SECTIONS[9][1]} />
          {cons.target_mean && cons.target_low && cons.target_high ? <div className="mt-3"><RangeBar title={`Street price-target range (${cons.analyst_count ?? "n/a"} analysts) vs last price`} low={Math.min(cons.target_low, q.price ?? cons.target_low) * 0.97} high={Math.max(cons.target_high, q.price ?? cons.target_high) * 1.03}
            marks={[{ label: "Low", value: cons.target_low }, { label: "Mean", value: cons.target_mean }, { label: "High", value: cons.target_high }, { label: "Last", value: q.price ?? 0, strong: true }]} /></div> : null}
          <div className="mt-3 grid gap-6 md:grid-cols-[1fr_1.4fr] print:grid-cols-[1fr_1.4fr]">
            <KV cols={1} rows={[["Street sentiment", cons.sentiment ?? "—"], ["Mean target vs price", ps(cons.implied_move)], ["Buzz (attention)", snap?.buzz?.level ? `${snap.buzz.level} (${Math.round(snap.buzz.score ?? 0)})` : "—"], ["News tone", snap?.buzz?.tone_label ?? "—"]]} />
            {ready?.headlines && ready.headlines.length > 0 && <Table head={["Recent headlines", "Outlet"]} rows={ready.headlines.slice(0, 7).map(h => [<span key="t">{h.title}<Cites ids={[h.source_id]} sources={src} /></span>, <span key="o" className="text-muted">{h.outlet ?? ""}</span>])} />}
          </div>
          {ready?.filings && ready.filings.length > 0 && <div className="mt-3"><Table head={["SEC filing", "Form", "Date"]} rows={ready.filings.slice(0, 6).map(f => [<span key="l">{f.label}<Cites ids={[f.source_id]} sources={src} /></span>, f.form, <span key="d" className="num">{f.date}</span>])} /></div>}
          <div className="mt-3"><Prose src={src}>{a?.sentiment}</Prose></div>

          </section>
          {/* ── 11 pattern lab ── */}
          {Q.patterns && <section className="rsec">
            <H2 n={11} title={SECTIONS[10][0]} sub={`${SECTIONS[10][1]} Asset class: ${Q.patterns.asset_class_label}, daily bars.`} />
            <div className="mt-3"><Table head={["Pattern", "Today", "Last seen", "Latest test", "Checks", "Avg outcome"]} right={[4, 5]} rows={(Q.patterns.rows as any[]).map(r => [r.pattern,
              r.active ? <b key="a" style={{ color: "#E0605A" }}>Present</b> : "—", <span key="l" className="num">{r.last_seen ?? "—"}</span>, r.verdict ?? "not yet tested", r.checks ?? "—", r.mean_r != null ? `${r.mean_r >= 0 ? "+" : ""}${r.mean_r.toFixed(2)} R` : "—"])} />
              <p className="mt-1 text-[10px] text-muted">A pattern is &quot;Robust&quot; only if it passed every stress test in the Pattern Lab (holdout, walk-forward, permutation, false-discovery control, deflated hurdle, regimes, sensitivity) after costs. R = one expected move. See irradiance.ai/patterns.</p></div>
          </section>}
        </>}

        {/* ── 12 bull / bear ── */}
        {a && <section className="rsec">
          <H2 n={12} title={SECTIONS[11][0]} sub={SECTIONS[11][1]} />
          {a.whats_new?.length > 0 && <div className="mt-3"><div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted">What&apos;s new</div><ul className="list-disc space-y-1 pl-5 text-sm">{a.whats_new.map((w, i) => <li key={i}>{w.point}<Cites ids={w.sources} sources={src} /></li>)}</ul></div>}
          <div className="mt-4 grid gap-4 md:grid-cols-2 print:grid-cols-2">
            {([["Bull case", a.bull_case, "text-up"], ["Bear case", a.bear_case, "text-down"]] as const).map(([t, items, cls]) => <div key={t} className="print-avoid-break rounded-md border border-line p-3"><div className={`text-sm font-semibold ${cls}`}>{t}</div>
              <ul className="mt-1.5 list-disc space-y-1 pl-5 text-sm">{items.map((x, i) => <li key={i}>{x.point}<Cites ids={x.sources} sources={src} /></li>)}</ul></div>)}
          </div>
          {a.catalysts?.length > 0 && <div className="mt-4"><Table head={["Date", "Catalyst"]} rows={a.catalysts.map(c => [<span key="d" className="num">{c.date ?? "—"}</span>, <span key="e">{c.event}<Cites ids={c.sources} sources={src} /></span>])} /></div>}
          <div className="mt-4 grid gap-4 text-sm md:grid-cols-2 print:grid-cols-2">
            {a.risks?.length > 0 && <div><div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted">Key risks</div><ul className="list-disc space-y-1 pl-5">{a.risks.map((x, i) => <li key={i}>{x}</li>)}</ul></div>}
            {a.questions?.length > 0 && <div><div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted">Questions for further research</div><ul className="list-disc space-y-1 pl-5">{a.questions.map((x, i) => <li key={i}>{x}</li>)}</ul></div>}
          </div>
          {a.data_gaps?.length > 0 && <p className="mt-3 rounded border border-line bg-accent/50 p-2 text-xs text-muted"><b>Data notes:</b> {a.data_gaps.join(" · ")}</p>}
        </section>}

        {/* ── closing page: methodology, about, sources, disclosure ── */}
        <section className="report-last mt-10 flex flex-col border-t-2 pt-4 print:break-before-page print:mt-0" style={{ borderColor: "#E0605A" }}>
          <div className="grid gap-6 md:grid-cols-2 print:grid-cols-2">
            <div>
              <h2 className="text-lg">About Irradiance</h2>
              <p className="mt-2 text-xs leading-relaxed">Irradiance.AI is an independent research platform for self-directed investors. <i>Illuminating markets.</i> We combine an AI analyst, the ValueBot DCF engine,
                a Pattern Lab that stress-tests market patterns across asset classes and timeframes, daily Premium Signals and the IRAI AlgoTrader paper-trading engine in one workspace.
                Our standard is simple: every number shows its source and every model shows its working, so you can check the analysis rather than take it on trust.</p>
              <h3 className="mt-4 text-sm">How this report is built</h3>
              <ul className="mt-1 list-disc space-y-0.5 pl-4 text-[11px] leading-relaxed text-muted">
                <li>Charts and tables are computed deterministically from daily OHLCV, company statistics, SEC EDGAR, options chains and news feeds.</li>
                <li>The narrative is written by {report?.engine === "rules" ? "the Irradiance rules engine" : report?.engine ?? "the Analyst Bot"} from that data pack only; each claim cites a numbered source.</li>
                <li>Volatility uses close-to-close log returns, annualised with √252; VaR/CVaR are historical; the regime model is a 3-state Gaussian HMM.</li>
                <li>Statistical ranges assume lognormal returns at the current 20-day realised volatility; they are not forecasts.</li>
              </ul>
            </div>
            <div>
              <h2 className="text-lg">Sources</h2>
              {src.length > 0 ? <ol className="mt-2 space-y-0.5 text-[10px] leading-snug">{src.map(x => <li key={x.id}><span className="num mr-1 text-muted">{x.id}</span>{x.label}</li>)}</ol>
                : <p className="mt-2 text-[11px] text-muted">Market data: Yahoo Finance (quotes, history, statistics, options). Filings: SEC EDGAR. News: Yahoo Finance RSS and the GDELT Project. Ratings, profile metrics and patterns: computed by Irradiance.</p>}
            </div>
          </div>
          <footer className="mt-auto pt-6 text-[8.5px] leading-snug text-muted">
            <div className="border-t border-line pt-2">
              <p><b>Important disclosures.</b> This report is published by Irradiance.ai for general information, research and educational purposes only. It is not investment, legal, tax or accounting advice, and it is not an offer, solicitation or recommendation to buy, sell or hold any security or to adopt any strategy. It does not take into account your objectives, financial situation or needs. Irradiance is not a registered investment adviser or broker-dealer and does not act as your fiduciary. Portions of this report are generated by automated systems, including artificial intelligence, from third-party data that may be delayed, incomplete or inaccurate; Irradiance makes no representation or warranty as to accuracy, completeness or timeliness and provides this report &quot;as is&quot;. Statistical ranges, patterns, scenarios and historical results are illustrative only, are not forecasts or price targets, and do not guarantee future performance. Investing involves risk, including the possible loss of principal. You are solely responsible for your investment decisions and should consult a qualified professional before acting. To the fullest extent permitted by law, Irradiance and its affiliates, officers and employees accept no liability for any loss or damage arising from the use of, or reliance on, this report. Market data © its respective providers. Broker and company names are trademarks of their owners. © {new Date().getFullYear()} Irradiance.ai. Full terms: irradiance.ai/legal/disclaimer.</p>
            </div>
          </footer>
        </section>
      </article>
    </div>
  );
}
