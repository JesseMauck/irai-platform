"use client";
import { use } from "react";
import ReactMarkdown from "react-markdown";
import { useApi } from "@/lib/hooks";
import { num, pct } from "@/lib/format";
import { Card, ErrorNote, Skeleton } from "@/components/ui";

interface Shared { company: { name: string; ticker: string }; method_title: string; date: string; result: { value_per_share: number; price: number; upside: number };
  sections: Record<string, string>; section_titles: [string, string][]; files: Record<string, string | null> }

export default function SharedRun({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params);
  const { data: r, error } = useApi<Shared>(`/api/valuebot/share/${token}`);
  return (
    <div className="mx-auto max-w-3xl px-4 py-12">
      <ErrorNote error={error} />
      {!r ? !error && <Skeleton /> : <>
        <p className="text-sm text-muted">Shared ValueBot report · {r.method_title} · {r.date}</p>
        <h1 className="mt-1 text-3xl font-semibold">{r.sections.title || `${r.company.name} (${r.company.ticker})`}</h1>
        <div className="mt-6 grid grid-cols-3 gap-3">{[["Value / share", num(r.result.value_per_share)], ["Price", num(r.result.price)], ["Upside", pct(r.result.upside, 1)]].map(([k, v]) =>
          <Card key={k} className="p-4"><div className="text-xs text-muted">{k}</div><div className="stat text-2xl">{v}</div></Card>)}</div>
        {r.section_titles.filter(([k]) => r.sections[k]).map(([k, t]) => <section key={k} className="mt-8"><h2 className="text-xl font-semibold">{t}</h2><div className="prose-irai"><ReactMarkdown>{r.sections[k]}</ReactMarkdown></div></section>)}
        {r.files.xlsx && <a href={`/api/valuebot/share/${token}/files/${r.files.xlsx}`} className="mt-8 inline-block text-primary">Download the Excel model →</a>}
        <p className="mt-10 text-xs text-muted">AI-assisted valuation for research and education, not investment advice.</p>
      </>}
    </div>
  );
}
