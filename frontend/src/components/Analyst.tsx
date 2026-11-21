"use client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { ago, num, pct, tone } from "@/lib/format";
import { useAuth } from "@/components/AuthProvider";
import { Button, Card, ErrorNote, SourceBadge } from "@/components/ui";

export interface Cited { point: string; sources: string[] }
export interface AnalystNote {
  headline: string; summary: string; whats_new: Cited[]; bull_case: Cited[]; bear_case: Cited[];
  valuation: string; technical: string; sentiment: string;
  catalysts: { event: string; date?: string | null; sources: string[] }[];
  risks: string[]; questions: string[]; data_gaps: string[];
}
export interface AnalystSource { id: string; label: string; url: string | null; kind: string }
export interface AnalystReport {
  id: string; symbol: string; status: "queued" | "running" | "done" | "error"; progress: number; engine: string | null; error: string | null;
  created_at: string | null; finished_at: string | null; reused?: boolean;
  stages: { key: string; label: string; status: "pending" | "running" | "done" | "error"; detail: string | null }[];
  result: null | {
    symbol: string; name: string | null; generated_at: string; analysis: AnalystNote; sources: AnalystSource[];
    snapshot: {
      price: number | null; change_pct: number | null; currency: string | null; data_label: string;
      returns: Record<string, number | null>; quant: { overall: string; label: string; factors: Record<string, string> } | null;
      consensus: { analyst_count?: number; sentiment?: string; target_mean?: number; implied_move?: number };
      buzz: { score?: number; level?: string; tone_label?: string } | null;
      technicals: { trend?: string; rsi14?: number }; next_earnings: { date?: string; eps_estimate?: number } | null;
      dividend_yield: number | null; fundamentals: Record<string, number | null>;
    };
  };
}

export function Cites({ ids, sources }: { ids: string[]; sources: AnalystSource[] }) {
  if (!ids?.length) return null;
  return <span className="ml-1 whitespace-nowrap text-[10px] text-muted">{ids.map(id => {
    const s = sources.find(x => x.id === id);
    return s?.url ? <a key={id} href={s.url} target="_blank" rel="noopener noreferrer" title={s.label} className="mr-0.5 rounded bg-accent px-1 hover:text-primary">{id}</a>
      : <span key={id} title={s?.label} className="mr-0.5 rounded bg-accent px-1">{id}</span>;
  })}</span>;
}

export function ProgressSteps({ r }: { r: AnalystReport }) {
  return (
    <div>
      <div className="flex items-center justify-between text-xs text-muted"><span>{r.status === "done" ? "Complete" : r.status === "error" ? "Stopped" : "Analyzing…"}</span><span className="num">{Math.round(r.progress * 100)}%</span></div>
      <div className="mt-1 h-2 overflow-hidden rounded bg-accent"><div className="h-2 rounded bg-primary transition-all duration-500" style={{ width: `${Math.max(4, r.progress * 100)}%` }} /></div>
      <ol className="mt-3 grid gap-1 text-sm sm:grid-cols-3">{r.stages.map(s => (
        <li key={s.key} className="flex items-start gap-2">
          <span className={`mt-1 inline-block h-2.5 w-2.5 shrink-0 rounded-full ${s.status === "done" ? "bg-up" : s.status === "running" ? "animate-pulse bg-primary" : s.status === "error" ? "bg-down" : "bg-line"}`} />
          <span><span className={s.status === "pending" ? "text-muted" : ""}>{s.label}</span>{s.detail && <span className="block text-[11px] text-muted">{s.detail}</span>}</span>
        </li>))}</ol>
    </div>
  );
}

function List({ title, items, sources, cls = "" }: { title: string; items: Cited[]; sources: AnalystSource[]; cls?: string }) {
  if (!items?.length) return null;
  return <div><h3 className={`text-sm font-semibold ${cls}`}>{title}</h3><ul className="mt-1.5 list-disc space-y-1 pl-5 text-sm">{items.map((i, k) => <li key={k}>{i.point}<Cites ids={i.sources} sources={sources} /></li>)}</ul></div>;
}

export function AnalystNoteView({ r }: { r: AnalystReport }) {
  const res = r.result!;
  const a = res.analysis, s = res.snapshot, src = res.sources;
  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-xl">{a.headline}</h3>
        <p className="mt-2 text-sm leading-relaxed">{a.summary}</p>
      </div>
      <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
        <Stat k="Price" v={<>{num(s.price)} <span className={tone(s.change_pct)}>{pct(s.change_pct)}</span> <SourceBadge source={s.data_label} /></>} />
        <Stat k="Quant rating" v={s.quant ? `${s.quant.overall} · ${s.quant.label}` : "—"} />
        <Stat k="Street" v={s.consensus?.analyst_count ? `${s.consensus.sentiment ?? "—"} · ${s.consensus.analyst_count} analysts` : "—"} />
        <Stat k="Buzz" v={s.buzz?.level ? `${s.buzz.level} (${Math.round(s.buzz.score ?? 0)})` : "—"} />
        <Stat k="12-month return" v={<span className={tone(s.returns["12m"])}>{pct(s.returns["12m"], 1)}</span>} />
        <Stat k="Trend · RSI" v={`${s.technicals.trend ?? "—"} · ${s.technicals.rsi14 ? Math.round(s.technicals.rsi14) : "—"}`} />
        <Stat k="Forward P/E" v={num(s.fundamentals.forward_pe, 1)} />
        <Stat k="Next earnings" v={s.next_earnings?.date ?? "—"} />
      </div>
      <List title="What's new" items={a.whats_new} sources={src} />
      <div className="grid gap-5 md:grid-cols-2">
        <List title="Bull case" items={a.bull_case} sources={src} cls="text-up" />
        <List title="Bear case" items={a.bear_case} sources={src} cls="text-down" />
      </div>
      <div className="grid gap-5 md:grid-cols-3 text-sm">
        <div><h3 className="font-semibold">Valuation</h3><p className="mt-1">{a.valuation}</p></div>
        <div><h3 className="font-semibold">Technicals</h3><p className="mt-1">{a.technical}</p></div>
        <div><h3 className="font-semibold">Sentiment</h3><p className="mt-1">{a.sentiment}</p></div>
      </div>
      {a.catalysts?.length > 0 && <div><h3 className="text-sm font-semibold">Catalysts to watch</h3><ul className="mt-1.5 space-y-1 text-sm">{a.catalysts.map((c, i) => <li key={i}>{c.date && <span className="num mr-2 text-muted">{c.date}</span>}{c.event}<Cites ids={c.sources} sources={src} /></li>)}</ul></div>}
      <div className="grid gap-5 md:grid-cols-2 text-sm">
        {a.risks?.length > 0 && <div><h3 className="font-semibold">Risks</h3><ul className="mt-1 list-disc space-y-1 pl-5">{a.risks.map((x, i) => <li key={i}>{x}</li>)}</ul></div>}
        {a.questions?.length > 0 && <div><h3 className="font-semibold">Questions to research next</h3><ul className="mt-1 list-disc space-y-1 pl-5">{a.questions.map((x, i) => <li key={i}>{x}</li>)}</ul></div>}
      </div>
      {a.data_gaps?.length > 0 && <p className="rounded border border-line bg-accent/50 p-2 text-xs text-muted"><b>Data gaps:</b> {a.data_gaps.join(" · ")}</p>}
      <details className="text-xs"><summary className="cursor-pointer text-muted">Sources ({src.length})</summary>
        <ol className="mt-2 space-y-0.5">{src.map(x => <li key={x.id}><span className="num mr-1 text-muted">{x.id}</span>{x.url ? <a href={x.url} target="_blank" rel="noopener noreferrer" className="hover:text-primary">{x.label}</a> : x.label}</li>)}</ol></details>
    </div>
  );
}

function Stat({ k, v }: { k: string; v: React.ReactNode }) {
  return <div className="rounded border border-line p-2"><div className="text-[11px] text-muted">{k}</div><div className="mt-0.5 num">{v}</div></div>;
}

export function useAnalystRun(symbol: string) {
  const { data: latest, reload } = useApi<AnalystReport | null>(`/api/analyst/${encodeURIComponent(symbol)}/latest`);
  const [run, setRun] = useState<AnalystReport | null>(null);
  const [err, setErr] = useState<Error | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const poll = useCallback((id: string) => {
    timer.current = setTimeout(async () => {
      try {
        const r = await api<AnalystReport>(`/api/analyst/reports/${id}`);
        setRun(r);
        if (r.status === "queued" || r.status === "running") poll(id); else reload();
      } catch (e) { setErr(e as Error); }
    }, 1200);
  }, [reload]);
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);
  const start = async (fresh = false) => {
    setErr(null);
    try {
      const r = await api<AnalystReport>(`/api/analyst/${encodeURIComponent(symbol)}${fresh ? "?fresh=true" : ""}`, { method: "POST" });
      setRun(r);
      if (r.status === "queued" || r.status === "running") poll(r.id);
    } catch (e) { setErr(e as Error); }
  };
  return { report: run ?? latest ?? null, running: !!run && (run.status === "queued" || run.status === "running"), start, err };
}

export function AnalystPanel({ symbol }: { symbol: string }) {
  const { user } = useAuth();
  const { report, running, start, err } = useAnalystRun(symbol);
  const done = report?.status === "done" && report.result;
  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-semibold">IRAI Analyst Bot</h2>
          <p className="max-w-2xl text-sm text-muted">Reads today&apos;s news and RSS feeds, SEC filings, fundamentals, earnings, technicals and Street views, then writes a sourced same-day analysis. Every point links to its source.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {done && <Button variant="outline" href={`/ticker/${encodeURIComponent(symbol)}/report`}>Print report</Button>}
          {user ? <Button onClick={() => start(!!done)} disabled={running}>{running ? "Analyzing…" : done ? "Refresh analysis" : "Run analysis"}</Button>
            : <Button href={`/login?next=/ticker/${encodeURIComponent(symbol)}%23analyst`}>Sign in to run</Button>}
        </div>
      </div>
      <ErrorNote error={err} />
      {report && (report.status !== "done" || running) && <div className="mt-4"><ProgressSteps r={report} /></div>}
      {report?.status === "error" && <p className="mt-3 text-sm text-down">The run stopped: {report.error}. Try again in a minute.</p>}
      {done && !running && <>
        <p className="mt-3 text-[11px] text-muted">Generated {ago(report.finished_at ?? report.created_at ?? "")} · engine: {report.engine}{report.reused ? " · shared recent report" : ""}</p>
        <div className="mt-3"><AnalystNoteView r={report} /></div>
      </>}
      {!report && !running && <p className="mt-4 text-sm text-muted">No analysis yet for {symbol} today. {user ? "Run one to see the progress here." : <Link href="/login" className="text-primary">Sign in</Link>}</p>}
      <p className="mt-4 text-[11px] text-muted">AI-written research from the cited data. It can be wrong; check the sources. Research and education only, not investment advice.</p>
    </Card>
  );
}
