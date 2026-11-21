"use client";
import Link from "next/link";
import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import ReactMarkdown from "react-markdown";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useAuth } from "@/components/AuthProvider";
import { Button, Card, ErrorNote, PageHeader } from "@/components/ui";

const TEMPLATE = `## Summary
One paragraph: what the market is missing and why it matters.

## Thesis
- Driver 1 (with the numbers that support it)
- Driver 2

## Valuation
What the current price implies, and your range of fair value (link a ValueBot report if you ran one).

## Risks and what would change my mind
- Risk 1
- Risk 2

## Catalysts and timeline

## Disclosure
I/we have no position in the securities mentioned. (Edit if you do.)
`;

function Write() {
  const sp = useSearchParams();
  const router = useRouter();
  const { user } = useAuth();
  const { data: comms } = useApi<{ slug: string; name: string; pro_only: boolean }[]>("/api/community/communities");
  const { data: runs } = useApi<{ id: string; ticker: string; title: string; status: string }[]>(user ? "/api/valuebot/library" : null);
  const kind = (sp.get("kind") as "analysis" | "strategy" | "discussion") ?? "analysis";
  const [f, setF] = useState({ community: "", title: "", tickers: sp.get("ticker") ?? "", outlook: "neutral", body: TEMPLATE,
    valuation_job_id: sp.get("report") ?? "", backtest_run_id: sp.get("backtest") ?? "" });
  const [tab, setTab] = useState<"write" | "preview">("write");
  const [err, setErr] = useState<Error | null>(null);
  useEffect(() => { if (comms && !f.community) setF(x => ({ ...x, community: comms.find(c => !c.pro_only)?.slug ?? comms[0]?.slug ?? "" })); }, [comms, f.community]);
  const submit = async () => {
    setErr(null);
    try {
      const t = await api<{ id: number }>("/api/community/threads", { method: "POST", json: {
        community: f.community, title: f.title, body: f.body, kind, tickers: f.tickers.split(/[\s,]+/).filter(Boolean),
        outlook: kind === "analysis" ? f.outlook : null, valuation_job_id: f.valuation_job_id || null,
        backtest_run_id: f.backtest_run_id ? parseInt(f.backtest_run_id) : null } });
      router.push(`/community/threads/${t.id}`);
    } catch (e) { setErr(e as Error); }
  };
  if (!user) return <div className="mx-auto max-w-3xl px-4 py-16 text-center"><h1 className="text-3xl">Publish your analysis</h1><p className="mt-2 text-muted">Sign in (Essential or Pro) to publish.</p><div className="mt-6"><Button href="/login?next=/community/write">Sign in</Button></div></div>;
  return (
    <div className="mx-auto max-w-4xl px-4 py-10">
      <PageHeader title={kind === "strategy" ? "Share a strategy" : "Write an analysis"} intro="Long-form research tagged to tickers. Show your numbers, state your risks and disclose any position." />
      <Card className="mt-6 space-y-4 p-5">
        <input value={f.title} onChange={e => setF({ ...f, title: e.target.value })} placeholder="Title — the thesis in one line" className="w-full rounded-lg border border-line bg-bg px-3 py-2 text-lg" />
        <div className="grid gap-3 md:grid-cols-4">
          <label className="text-xs text-muted md:col-span-2">Tickers (first is primary)<input value={f.tickers} onChange={e => setF({ ...f, tickers: e.target.value })} placeholder="AAPL, MSFT" className="mt-1 w-full rounded border border-line bg-bg px-2 py-1.5 text-sm uppercase" /></label>
          {kind === "analysis" && <label className="text-xs text-muted">Outlook<select value={f.outlook} onChange={e => setF({ ...f, outlook: e.target.value })} className="mt-1 w-full rounded border border-line bg-bg px-2 py-1.5 text-sm"><option value="bullish">Bullish</option><option value="neutral">Neutral</option><option value="bearish">Bearish</option></select></label>}
          <label className="text-xs text-muted">Community<select value={f.community} onChange={e => setF({ ...f, community: e.target.value })} className="mt-1 w-full rounded border border-line bg-bg px-2 py-1.5 text-sm">{comms?.map(c => <option key={c.slug} value={c.slug}>{c.name}{c.pro_only ? " (Pro)" : ""}</option>)}</select></label>
        </div>
        <label className="block text-xs text-muted">Attach a ValueBot report (optional)
          <select value={f.valuation_job_id} onChange={e => setF({ ...f, valuation_job_id: e.target.value })} className="mt-1 w-full rounded border border-line bg-bg px-2 py-1.5 text-sm">
            <option value="">None</option>{runs?.filter(r => r.status === "done").map(r => <option key={r.id} value={r.id}>{r.title}</option>)}</select></label>
        <div className="flex rounded-lg border border-line p-0.5 text-xs w-fit">{(["write", "preview"] as const).map(t => <button key={t} onClick={() => setTab(t)} className={`rounded-md px-3 py-1 capitalize ${tab === t ? "bg-accent text-fg" : "text-muted"}`}>{t}</button>)}</div>
        {tab === "write" ? <textarea value={f.body} onChange={e => setF({ ...f, body: e.target.value })} rows={22} className="w-full rounded-lg border border-line bg-bg p-3 font-mono text-sm leading-6" />
          : <div className="prose-irai min-h-64"><ReactMarkdown>{f.body}</ReactMarkdown></div>}
        <p className="text-xs text-muted">{f.body.length.toLocaleString()} characters · analysis posts need 300+ characters and at least one ticker. Posts follow the <Link href="/legal/community-guidelines" className="underline">Community Guidelines</Link>.</p>
        <ErrorNote error={err} />
        <div className="flex gap-2"><Button onClick={submit} disabled={!f.title || !f.community}>Publish</Button><Button variant="ghost" onClick={() => router.back()}>Cancel</Button></div>
      </Card>
    </div>
  );
}

export default function Page() { return <Suspense><Write /></Suspense>; }
