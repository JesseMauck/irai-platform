"use client";
import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { num, pct } from "@/lib/format";
import { useAuth } from "@/components/AuthProvider";
import { Button, Card, ErrorNote, PageHeader, Skeleton } from "@/components/ui";

interface Run {
  id: string; ticker: string; title: string; stance: string; status: string; method: string | null;
  value_per_share: number | null; price: number | null; upside: number | null; pinned: boolean; archived: boolean;
  has_notes: boolean; scenario_count: number; created_at: string | null;
}

export default function Reports() {
  const { user } = useAuth();
  const [archived, setArchived] = useState(false);
  const [q, setQ] = useState("");
  const path = user ? `/api/valuebot/library?archived=${archived}${q ? `&q=${encodeURIComponent(q)}` : ""}` : null;
  const { data, error, reload } = useApi<Run[]>(path);
  const [err, setErr] = useState<Error | null>(null);
  const patch = async (id: string, body: Partial<Run>) => {
    try { await api(`/api/valuebot/jobs/${id}/meta`, { method: "PATCH", json: body }); reload(); } catch (e) { setErr(e as Error); }
  };
  if (!user) return (
    <div className="mx-auto max-w-3xl px-4 py-16 text-center">
      <h1 className="text-3xl">Your ValueBot reports</h1>
      <p className="mt-2 text-muted">Sign in to see, edit and download the valuations you&rsquo;ve run.</p>
      <div className="mt-6 flex justify-center gap-3"><Button href="/login?next=/valuebot/reports">Sign in</Button><Button href="/valuebot" variant="outline">Try ValueBot</Button></div>
    </div>
  );
  return (
    <div className="mx-auto max-w-6xl px-4 py-10">
      <PageHeader title="My reports" intro="Every valuation you've run, with your notes and saved scenarios. Open one to edit it, re-price it, or download it as PDF or Excel." />
      <div className="mt-6 flex flex-wrap items-center gap-3">
        <input value={q} onChange={e => setQ(e.target.value)} placeholder="Filter by ticker or title" className="w-64 rounded-lg border border-line bg-card px-3 py-2 text-sm" />
        <div className="flex rounded-lg border border-line p-0.5 text-sm">
          {[false, true].map(a => <button key={String(a)} onClick={() => setArchived(a)} className={`rounded-md px-3 py-1 ${archived === a ? "bg-accent text-fg" : "text-muted"}`}>{a ? "Archived" : "Active"}</button>)}
        </div>
        <div className="ml-auto"><Button href="/valuebot">New valuation →</Button></div>
      </div>
      <ErrorNote error={error ?? err} />
      {!data ? <Skeleton /> : data.length === 0 ? (
        <Card className="mt-6 p-8 text-center text-muted">{archived ? "Nothing archived." : q ? "No reports match." : "No reports yet — run your first valuation."}</Card>
      ) : (
        <div className="mt-6 overflow-x-auto rounded-xl border border-line">
          <table className="w-full min-w-[760px] text-sm">
            <thead className="bg-card text-left text-xs text-muted"><tr>
              <th className="p-3"></th><th className="p-3">Report</th><th className="p-3">Method</th><th className="p-3 text-right">Value / share</th>
              <th className="p-3 text-right">Price then</th><th className="p-3 text-right">vs price</th><th className="p-3">Your work</th><th className="p-3">Run</th><th className="p-3"></th>
            </tr></thead>
            <tbody className="divide-y divide-line">
              {data.map(r => (
                <tr key={r.id} className="hover:bg-accent/40">
                  <td className="p-3"><button aria-label={r.pinned ? "Unpin" : "Pin"} onClick={() => patch(r.id, { pinned: !r.pinned })} className={r.pinned ? "text-primary" : "text-muted hover:text-fg"}>{r.pinned ? "★" : "☆"}</button></td>
                  <td className="p-3"><Link href={`/valuebot/${r.id}`} className="font-medium hover:text-primary">{r.title}</Link><div className="text-xs text-muted">{r.ticker} · {r.stance}</div></td>
                  <td className="p-3 text-muted">{r.status === "done" ? r.method?.toUpperCase() : r.status}</td>
                  <td className="p-3 text-right num">{num(r.value_per_share)}</td>
                  <td className="p-3 text-right num">{num(r.price)}</td>
                  <td className={`p-3 text-right num ${r.upside == null ? "" : r.upside >= 0 ? "text-up" : "text-down"}`}>{pct(r.upside, 1)}</td>
                  <td className="p-3 text-xs text-muted">{[r.has_notes && "notes", r.scenario_count && `${r.scenario_count} scenario${r.scenario_count > 1 ? "s" : ""}`].filter(Boolean).join(" · ") || "—"}</td>
                  <td className="p-3 text-xs text-muted">{r.created_at ? new Date(r.created_at).toLocaleDateString() : ""}</td>
                  <td className="p-3 text-right"><button onClick={() => patch(r.id, { archived: !r.archived })} className="text-xs text-muted hover:text-fg">{r.archived ? "Restore" : "Archive"}</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="mt-4 text-xs text-muted">&ldquo;Price then&rdquo; is the market price when the valuation ran. Research and education only — not investment advice.</p>
    </div>
  );
}
