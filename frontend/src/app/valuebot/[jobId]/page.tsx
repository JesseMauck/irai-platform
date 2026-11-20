"use client";
import Link from "next/link";
import { use, useState } from "react";
import ReactMarkdown from "react-markdown";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { num, pct } from "@/lib/format";
import { Button, Card, ErrorNote, Skeleton } from "@/components/ui";

interface Stage { key: string; label: string; status: string; detail: string | null }
interface Job { id: string; ticker: string; status: string; stages: Stage[]; error: string | null; share_token: string; plan: { method_title: string } | null }
interface Assumption { label: string; unit: string; value: number; rationale: string }
interface Result {
  company: { name: string; ticker: string; currency: string; price: number; demo?: boolean };
  method_title: string; date: string; thesis: string;
  result: { value_per_share: number; price: number; upside: number; warnings: string[] };
  sensitivity: { scenarios: Record<"bear" | "bull", { value_per_share: number }>; drivers: { key: string; label: string; low: number; high: number }[] };
  probabilistic: { simulation: { percentiles: Record<string, number>; prob_undervalued?: number }; reverse_dcf: { rows: { key: string; label: string; base: number; market: number | null }[] } };
  assumptions: Record<string, Assumption>; sections: Record<string, string>; section_titles: [string, string][];
  narrative_tests: { test: string; pass: boolean; detail: string }[];
  files: Record<string, string | null>;
}


export default function Run({ params }: { params: Promise<{ jobId: string }> }) {
  const { jobId } = use(params);
  const { data: job, error } = useApi<Job>(`/api/valuebot/jobs/${jobId}`, 1500);
  const done = job?.status === "done";
  const { data: r } = useApi<Result>(done ? `/api/valuebot/jobs/${jobId}/result` : null);
  const [whatIf, setWhatIf] = useState<Record<string, number>>({});
  const [rv, setRv] = useState<{ value_per_share: number; upside: number } | null>(null);

  const revalue = async (k: string, v: number) => {
    const next = { ...whatIf, [k]: v }; setWhatIf(next);
    try { setRv(await api(`/api/valuebot/jobs/${jobId}/revalue`, { method: "POST", json: { assumptions: next } })); } catch {}
  };
  const file = (n: string) => `/api/valuebot/jobs/${jobId}/files/${n}`;

  return (
    <div className="mx-auto max-w-6xl px-4 py-10">
      <Link href="/valuebot" className="text-sm text-muted hover:text-fg">← ValueBot</Link>
      <ErrorNote error={error} />
      {!job ? <Skeleton /> : !done ? (
        <Card className="mt-4 p-6">
          <h1 className="text-2xl font-semibold">Valuing {job.ticker}…</h1>
          {job.status === "error" && <p className="mt-2 text-down">{job.error}</p>}
          <ol className="mt-5 space-y-2">
            {job.stages.map(s => (
              <li key={s.key} className="flex gap-3 text-sm">
                <span className={s.status === "done" ? "text-up" : s.status === "running" ? "animate-pulse text-primary" : s.status === "error" ? "text-down" : "text-muted"}>
                  {s.status === "done" ? "✓" : s.status === "running" ? "●" : s.status === "error" ? "✕" : "○"}</span>
                <span className={s.status === "pending" ? "text-muted" : ""}>{s.label}</span>
                {s.detail && <span className="truncate text-muted">— {s.detail}</span>}
              </li>
            ))}
          </ol>
        </Card>
      ) : !r ? <Skeleton /> : (
        <>
          <div className="mt-4 flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
            <div>
              <p className="text-sm text-muted">{r.method_title} · {r.date}{r.company.demo && " · fictional demo company"}</p>
              <h1 className="text-3xl font-semibold">{r.sections.title || `${r.company.name} (${r.company.ticker})`}</h1>
              {r.sections.subtitle && <p className="text-muted">{r.sections.subtitle}</p>}
            </div>
            <div className="flex flex-wrap gap-2">
              {r.files.xlsx && <Button href={file(r.files.xlsx)} variant="outline">Excel model</Button>}
              {r.files.pdf && <Button href={file(r.files.pdf)} variant="outline">PDF</Button>}
              <Button variant="ghost" onClick={() => navigator.clipboard?.writeText(`${location.origin}/valuebot/share/${job.share_token}`)}>Copy share link</Button>
            </div>
          </div>
          <div className="mt-6 grid gap-3 md:grid-cols-5">
            {[["Value / share", num(r.result.value_per_share)], ["Price", num(r.result.price)], ["Upside", pct(r.result.upside, 1)],
              ["P(undervalued)", pct(r.probabilistic.simulation.prob_undervalued ?? null, 0, false)],
              ["Bear – Bull", `${num(r.sensitivity.scenarios.bear.value_per_share, 0)} – ${num(r.sensitivity.scenarios.bull.value_per_share, 0)}`]].map(([k, v]) => (
              <Card key={k} className="p-4"><div className="text-xs text-muted">{k}</div><div className={`mt-1 text-2xl font-semibold num ${k === "Upside" ? (r.result.upside >= 0 ? "text-up" : "text-down") : ""}`}>{v}</div></Card>
            ))}
          </div>
          <div className="mt-6 grid gap-6 lg:grid-cols-3">
            <div className="space-y-6 lg:col-span-2">
              {r.section_titles.filter(([k]) => r.sections[k]).map(([k, title]) => (
                <section key={k}><h2 className="text-xl font-semibold">{title}</h2><div className="prose-irai"><ReactMarkdown>{r.sections[k]}</ReactMarkdown></div></section>
              ))}
            </div>
            <div className="space-y-4">
              <Card className="p-5">
                <h3 className="font-semibold">What if?</h3>
                <p className="text-xs text-muted">Edit a driver to reprice instantly (nothing is saved).</p>
                {rv && <p className="mt-2 text-lg font-semibold num">{num(rv.value_per_share)} <span className={rv.upside >= 0 ? "text-up" : "text-down"}>({pct(rv.upside, 1)})</span></p>}
                <div className="mt-3 space-y-2">
                  {Object.entries(r.assumptions).slice(0, 12).map(([k, a]) => (
                    <label key={k} className="flex items-center justify-between gap-2 text-xs">
                      <span className="text-muted" title={a.rationale}>{a.label}</span>
                      <input type="number" step={a.unit === "pct" ? 0.5 : 0.1} defaultValue={a.unit === "pct" ? +(a.value * 100).toFixed(2) : +a.value.toFixed(2)}
                        onChange={e => { const v = parseFloat(e.target.value); if (isFinite(v)) revalue(k, a.unit === "pct" ? v / 100 : v); }}
                        className="w-20 rounded border border-line bg-bg px-2 py-1 text-right num" />
                    </label>
                  ))}
                </div>
              </Card>
              <Card className="p-5">
                <h3 className="font-semibold">Story tests</h3>
                <ul className="mt-2 space-y-2 text-sm">{r.narrative_tests.map(t => <li key={t.test}><span className={t.pass ? "text-up" : "text-down"}>{t.pass ? "✓" : "!"}</span> {t.test}<div className="text-xs text-muted">{t.detail}</div></li>)}</ul>
              </Card>
              <Card className="p-5">
                <h3 className="font-semibold">Downloads</h3>
                <ul className="mt-2 space-y-1 text-sm">
                  {Object.entries(r.files).filter(([, v]) => v).map(([k, v]) => <li key={k}><a href={file(v!)} className="hover:text-primary">{v}</a></li>)}
                </ul>
              </Card>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
