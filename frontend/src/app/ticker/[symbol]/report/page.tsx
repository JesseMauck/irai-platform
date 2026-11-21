"use client";
import Link from "next/link";
import { use } from "react";
import { type TickerPage } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { compact, num, pct, tone } from "@/lib/format";
import { LineChart } from "@/components/Chart";
import { LogoMark } from "@/components/Header";
import { AnalystNoteView, ProgressSteps, useAnalystRun } from "@/components/Analyst";
import { useAuth } from "@/components/AuthProvider";
import { Button, Skeleton } from "@/components/ui";

interface Ratings { overall_grade: string; overall_label: string; factors: Record<string, { grade: string | null; score: number | null }> }

export default function TickerReport({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol: raw } = use(params);
  const symbol = decodeURIComponent(raw).toUpperCase();
  const { user } = useAuth();
  const { data } = useApi<TickerPage>(`/api/market/ticker/${encodeURIComponent(symbol)}`);
  const { data: rt } = useApi<Ratings>(`/api/insight/${encodeURIComponent(symbol)}/ratings`);
  const { report, running, start, err } = useAnalystRun(symbol);
  const today = new Date().toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" });
  if (!data) return <div className="mx-auto max-w-4xl px-4 py-12"><Skeleton rows={10} /></div>;
  const q = data.quote, info = data.info ?? {};
  const closes = data.history.map(h => h.close);
  const ready = report?.status === "done" && report.result;
  const stats: [string, string][] = [
    ["Market cap", compact(info.market_cap)], ["Forward P/E", num(info.forward_pe, 1)], ["EV/EBITDA", num(info.ev_ebitda, 1)],
    ["Operating margin", pct(info.operating_margin, 1, false)], ["Revenue growth", pct(info.revenue_growth, 1)], ["ROE", pct(info.roe, 1, false)],
    ["Dividend yield", pct(info.dividend_yield, 2, false)], ["Beta", num(info.beta, 2)],
    ["52-week range", q.fifty_two_week_low ? `${num(q.fifty_two_week_low)} – ${num(q.fifty_two_week_high)}` : "—"], ["Grade", data.grade?.grade ?? "—"],
  ];
  return (
    <div className="mx-auto max-w-4xl px-4 py-6 print:max-w-none print:px-0 print:py-0">
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
        <header className="flex items-start justify-between border-b-2 pb-4" style={{ borderColor: "#E0605A" }}>
          <div className="flex items-center gap-3">
            <LogoMark className="h-10 w-auto" />
            <div><div className="text-xl font-bold tracking-wide" style={{ fontFamily: "var(--font-display, inherit)" }}>IRRADIANCE<span className="logo-ai">.AI</span></div>
              <div className="text-[11px] uppercase tracking-[0.2em] text-muted">Equity research report</div></div>
          </div>
          <div className="text-right text-xs text-muted"><div>{today}</div><div>irradiance.ai/ticker/{symbol}</div></div>
        </header>

        <section className="mt-5 flex flex-wrap items-end justify-between gap-3">
          <div><h1 className="text-3xl">{q.name ?? symbol} <span className="text-muted">({symbol})</span></h1>
            <p className="text-sm text-muted">{[info.sector, info.industry, q.exchange].filter(Boolean).join(" · ")}</p></div>
          <div className="text-right"><div className="stat text-3xl num">{num(q.price)} <span className="text-base text-muted">{q.currency}</span></div>
            <div className={`text-sm num ${tone(q.change_pct)}`}>{pct(q.change_pct)} today · data {q.source}</div></div>
        </section>

        <section className="print-avoid-break mt-5 grid gap-5 md:grid-cols-3 print:grid-cols-3">
          <div className="md:col-span-2 print:col-span-2">
            <div className="text-xs font-semibold uppercase tracking-wide text-muted">One-year price</div>
            <LineChart height={170} dates={data.history.map(h => h.date)} series={[{ values: closes, color: "#E0605A", label: symbol }]} format={v => num(v)} />
          </div>
          <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-xs">{stats.map(([k, v]) => <div key={k}><dt className="text-muted">{k}</dt><dd className="num font-medium">{v}</dd></div>)}</dl>
        </section>

        {rt?.factors && <section className="print-avoid-break mt-5">
          <div className="text-xs font-semibold uppercase tracking-wide text-muted">Quant ratings · overall {rt.overall_grade} ({rt.overall_label})</div>
          <div className="mt-2 grid grid-cols-5 gap-2 text-center text-sm">{Object.entries(rt.factors).map(([k, f]) => (
            <div key={k} className="rounded border border-line p-2"><div className="text-[11px] capitalize text-muted">{k}</div><div className="stat text-lg">{f.grade ?? "—"}</div></div>))}</div>
        </section>}

        <section className="mt-6 border-t border-line pt-5">
          <div className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted">IRAI Analyst Bot · same-day analysis</div>
          {ready ? <AnalystNoteView r={report} /> : <p className="text-sm text-muted">No AI analysis yet for today. {user ? "Use “Run AI analysis” above, then print." : "Sign in to run one."} The data sections above print on their own.</p>}
        </section>

        <footer className="mt-8 border-t border-line pt-3 text-[10px] leading-snug text-muted">
          <p><b>Important:</b> This report is general research and education by Irradiance.ai. It is not investment advice or a recommendation to buy, sell or hold any security, and does not consider your objectives or circumstances. AI-written sections are generated from the cited data and may contain errors; verify the sources. Market data may be delayed. Past performance does not guarantee future results.</p>
          <p className="mt-1">Sources: market data from Yahoo Finance; filings from SEC EDGAR; news from Yahoo Finance RSS and the GDELT Project; ratings computed by Irradiance. © {new Date().getFullYear()} Irradiance.ai · See irradiance.ai/legal/disclaimer.</p>
        </footer>
      </article>
    </div>
  );
}
