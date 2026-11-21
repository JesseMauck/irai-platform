"use client";
import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import { api, download } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { num, pct } from "@/lib/format";
import { Button, Card, ErrorNote } from "@/components/ui";

export interface Scenario { name: string; assumptions: Record<string, number>; value_per_share: number; upside: number | null; saved_at: string; warnings: string[] }
export interface ReportMeta {
  id: string; ticker: string; title: string; pinned: boolean; archived: boolean; notes_md: string;
  scenarios: Scenario[]; notes_updated_at: string | null; status: string;
}

/** Owner-only controls for a ValueBot report: title, pin, notes editor, exports. */
export function ReportHeaderTools({ jobId, onMeta }: { jobId: string; onMeta?: (m: ReportMeta | null) => void }) {
  const { data: meta, setData } = useApi<ReportMeta>(`/api/valuebot/jobs/${jobId}/meta`);
  const [title, setTitle] = useState("");
  const [err, setErr] = useState<Error | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  useEffect(() => { if (meta) setTitle(meta.title); onMeta?.(meta); }, [meta, onMeta]);
  if (!meta) return null;
  const patch = async (body: Partial<ReportMeta>) => {
    setErr(null);
    try { setData(await api<ReportMeta>(`/api/valuebot/jobs/${jobId}/meta`, { method: "PATCH", json: body })); } catch (e) { setErr(e as Error); }
  };
  const exp = async (kind: "pdf" | "xlsx") => {
    setBusy(kind); setErr(null);
    try { await download(`/api/valuebot/jobs/${jobId}/export.${kind}`, `${meta.ticker}_valuebot.${kind}`); } catch (e) { setErr(e as Error); } finally { setBusy(null); }
  };
  return (
    <div className="mt-4 flex flex-wrap items-center gap-2">
      <input value={title} onChange={e => setTitle(e.target.value)} onBlur={() => title !== meta.title && patch({ title })}
        aria-label="Report title" className="min-w-64 flex-1 rounded-lg border border-line bg-card px-3 py-2 text-sm" />
      <Button variant="outline" onClick={() => patch({ pinned: !meta.pinned })}>{meta.pinned ? "★ Pinned" : "☆ Pin"}</Button>
      <Button variant="outline" onClick={() => exp("pdf")} disabled={busy === "pdf"}>{busy === "pdf" ? "Preparing…" : "Download PDF"}</Button>
      <Button variant="outline" onClick={() => exp("xlsx")} disabled={busy === "xlsx"}>{busy === "xlsx" ? "Preparing…" : "Download Excel"}</Button>
      <Button variant="ghost" onClick={() => patch({ archived: !meta.archived })}>{meta.archived ? "Restore" : "Archive"}</Button>
      <ErrorNote error={err} />
    </div>
  );
}

/** Markdown notes editor with preview; saves to the report. */
export function NotesEditor({ jobId, initial, updatedAt }: { jobId: string; initial: string; updatedAt: string | null }) {
  const [text, setText] = useState(initial);
  const [tab, setTab] = useState<"write" | "preview">(initial ? "preview" : "write");
  const [saved, setSaved] = useState(updatedAt);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<Error | null>(null);
  const dirty = text !== initial && saved === updatedAt;
  const save = async () => {
    setBusy(true); setErr(null);
    try { const m = await api<ReportMeta>(`/api/valuebot/jobs/${jobId}/meta`, { method: "PATCH", json: { notes_md: text } }); setSaved(m.notes_updated_at); setTab("preview"); }
    catch (e) { setErr(e as Error); } finally { setBusy(false); }
  };
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between">
        <h2 className="text-xl">Your notes</h2>
        <div className="flex rounded-lg border border-line p-0.5 text-xs">
          {(["write", "preview"] as const).map(t => <button key={t} onClick={() => setTab(t)} className={`rounded-md px-3 py-1 capitalize ${tab === t ? "bg-accent text-fg" : "text-muted"}`}>{t}</button>)}
        </div>
      </div>
      <p className="mt-1 text-xs text-muted">Private to you. Included in your PDF and Excel downloads. Markdown supported (## headings, **bold**, - lists, tables).</p>
      {tab === "write" ? (
        <textarea value={text} onChange={e => setText(e.target.value)} rows={14} placeholder={"## My thesis\n\n- What has to go right\n- What would change my mind\n\n## Catalysts\n"}
          className="mt-3 w-full rounded-lg border border-line bg-bg p-3 font-mono text-sm leading-6" />
      ) : (
        <div className="prose-irai mt-2 min-h-24">{text ? <ReactMarkdown>{text}</ReactMarkdown> : <p className="text-muted">No notes yet. Switch to Write.</p>}</div>
      )}
      <div className="mt-3 flex items-center gap-3">
        <Button onClick={save} disabled={busy}>{busy ? "Saving…" : "Save notes"}</Button>
        {saved && <span className="text-xs text-muted">Saved {new Date(saved).toLocaleString()}</span>}
        {dirty && <span className="text-xs text-primary">Unsaved changes</span>}
      </div>
      <ErrorNote error={err} />
    </Card>
  );
}

/** Save the current what-if as a named scenario, and list saved ones. */
export function Scenarios({ jobId, whatIf, labels, initial }: {
  jobId: string; whatIf: Record<string, number>; labels: Record<string, { label: string; unit: string }>; initial: Scenario[];
}) {
  const [items, setItems] = useState(initial);
  const [name, setName] = useState("");
  const [err, setErr] = useState<Error | null>(null);
  const save = async () => {
    setErr(null);
    try { const m = await api<ReportMeta>(`/api/valuebot/jobs/${jobId}/scenarios`, { method: "POST", json: { name: name || `Scenario ${items.length + 1}`, assumptions: whatIf } }); setItems(m.scenarios); setName(""); }
    catch (e) { setErr(e as Error); }
  };
  const remove = async (i: number) => {
    try { const m = await api<ReportMeta>(`/api/valuebot/jobs/${jobId}/scenarios/${i}`, { method: "DELETE" }); setItems(m.scenarios); } catch (e) { setErr(e as Error); }
  };
  return (
    <div className="mt-4 border-t border-line pt-3">
      <div className="flex gap-2">
        <input value={name} onChange={e => setName(e.target.value)} placeholder="Scenario name" className="min-w-0 flex-1 rounded border border-line bg-bg px-2 py-1 text-xs" />
        <Button variant="outline" onClick={save} disabled={!Object.keys(whatIf).length} className="px-3 py-1 text-xs">Save scenario</Button>
      </div>
      {!Object.keys(whatIf).length && <p className="mt-1 text-[11px] text-muted">Change a driver above, then save it as a scenario.</p>}
      <ErrorNote error={err} />
      {items.length > 0 && (
        <ul className="mt-3 space-y-2 text-xs">
          {items.map((s, i) => (
            <li key={s.saved_at + i} className="rounded border border-line p-2">
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium">{s.name}</span>
                <span className="num">{num(s.value_per_share)} {s.upside != null && <span className={s.upside >= 0 ? "text-up" : "text-down"}>({pct(s.upside, 1)})</span>}</span>
              </div>
              <div className="mt-1 text-muted">{Object.entries(s.assumptions).map(([k, v]) => `${labels[k]?.label ?? k}: ${labels[k]?.unit === "pct" ? (v * 100).toFixed(1) + "%" : +v.toFixed(3)}`).join(" · ")}</div>
              <button onClick={() => remove(i)} className="mt-1 text-muted hover:text-down">Remove</button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
