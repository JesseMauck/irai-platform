"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { ago } from "@/lib/format";
import { Button, Card, ErrorNote, Skeleton } from "@/components/ui";

interface QaStatus {
  last_run: { id: number; status: string; started_at: string; heartbeat_age_s: number; requests: number; checks: number; issues_new: number; issues_seen: number } | null;
  recent: { id: number; status: string; tickers: number; new: number; seen: number }[];
  issues_by_status: Record<string, number>;
  open: { category: string; severity: string; count: number }[];
}
interface QaIssue {
  id: number; fingerprint: string; title: string; issue_type: string; category: string; severity: string; status: string; flow: string;
  step: string | null; strategy: string | null; endpoint: string; tickers: string[]; occurrences: number; first_seen: string; last_seen: string;
  verdict: string | null; fix_ref: string | null;
}
interface QaIssueFull extends QaIssue {
  expected: string; actual: string; trace: Record<string, unknown> | null; context: Record<string, unknown> | null;
  triage: { verdict?: string; rationale?: string; by?: string; likely_location?: string; fix_hint?: string; regression_test?: string; admin_note?: string } | null;
}

const OPEN = ["new", "valid", "regressed", "needs_more_data"];
const FILTERS = ["open", "valid", "new", "needs_more_data", "regressed", "fixed", "false_positive", "wontfix", "all"] as const;
const SEV: Record<string, string> = { high: "bg-down/20 text-down", medium: "bg-primary/15 text-primary", low: "bg-accent text-muted" };
const STALE_HEARTBEAT_S = 45 * 60; // loop runs every 15 min by default; three missed cycles means it's down
const label = (s: string) => s.replace(/_/g, " ");

export default function QaTab() {
  const { data: st, error } = useApi<QaStatus>("/api/admin/qa/status", 30_000);
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("open");
  const path = ["open", "all"].includes(filter) ? "/api/admin/qa/issues" : `/api/admin/qa/issues?status=${filter}`;
  const { data: issues, reload } = useApi<QaIssue[]>(path, 30_000, [filter]);
  const [openId, setOpenId] = useState<number | null>(null);
  if (error) return <p className="text-down">{error.message}</p>;
  if (!st) return <Skeleton rows={6} />;
  const lr = st.last_run;
  const stale = !lr || lr.heartbeat_age_s > STALE_HEARTBEAT_S;
  const rows = (issues ?? []).filter(i => filter !== "open" || OPEN.includes(i.status));
  return (
    <div className="space-y-4">
      <Card className="p-5">
        <h2 className="font-semibold">Synthetic-trader QA</h2>
        <p className="max-w-3xl text-sm text-muted">A background agent paper-trades random tickers with throwaway test accounts, files deduplicated findings and has Claude check each one. Only issues marked valid reach the weekly fixer, which opens pull requests for review.</p>
        <div className="mt-4 grid gap-3 sm:grid-cols-4">
          <Stat k="Last run" v={lr ? `#${lr.id} · ${lr.status}` : "never"} sub={lr ? ago(lr.started_at) : "start the qa service"} bad={!lr || ["crashed", "aborted"].includes(lr.status)} />
          <Stat k="Heartbeat" v={lr ? fmtAge(lr.heartbeat_age_s) : "—"} sub={stale ? "agent looks down" : "healthy"} bad={stale} />
          <Stat k="Last run checks" v={lr ? `${lr.checks}` : "—"} sub={lr ? `${lr.requests} requests · ${lr.issues_new} new · ${lr.issues_seen} repeat` : ""} />
          <Stat k="Awaiting fix" v={`${st.issues_by_status.valid ?? 0}`} sub={`${st.issues_by_status.regressed ?? 0} regressed · ${st.issues_by_status.fixed ?? 0} fixed`} bad={(st.issues_by_status.regressed ?? 0) > 0} />
        </div>
        {st.open.length > 0 && <div className="mt-3 flex flex-wrap gap-2 text-xs">{st.open.map(o => <span key={o.category + o.severity} className={`rounded px-2 py-1 ${SEV[o.severity] ?? ""}`}>{o.count} {o.severity} · {label(o.category)}</span>)}</div>}
        {st.recent.length > 1 && <p className="mt-3 text-xs text-muted">Recent runs: {st.recent.map(r => `#${r.id} ${r.status} (${r.tickers} tickers, ${r.new} new)`).join(" · ")}</p>}
      </Card>
      <Card className="p-0">
        <div className="flex flex-wrap gap-1 border-b border-line p-3">{FILTERS.map(f => <button key={f} onClick={() => setFilter(f)} className={`rounded px-2.5 py-1 text-xs ${f === filter ? "bg-primary/15 text-primary" : "text-muted hover:text-fg"}`}>{label(f)}</button>)}</div>
        {!issues ? <div className="p-4"><Skeleton rows={4} /></div> : rows.length === 0 ? <p className="p-6 text-center text-sm text-muted">No issues here.</p> : (
          <div className="overflow-x-auto"><table className="w-full min-w-[760px] text-sm">
            <thead className="text-left text-xs text-muted"><tr>{["Severity", "Issue", "Flow / step", "Tickers", "Seen", "Status"].map(h => <th key={h} className="px-3 py-2 font-normal">{h}</th>)}</tr></thead>
            <tbody className="divide-y divide-line">{rows.map(i => [
              <tr key={i.id} onClick={() => setOpenId(openId === i.id ? null : i.id)} className="cursor-pointer hover:bg-card">
                <td className="px-3 py-2"><span className={`rounded px-1.5 py-0.5 text-xs ${SEV[i.severity] ?? ""}`}>{i.severity}</span></td>
                <td className="px-3 py-2"><div>{i.title}</div><div className="text-xs text-muted">{label(i.category)} · {i.issue_type}</div></td>
                <td className="px-3 py-2 text-xs">{label(i.flow)}{i.step ? ` / ${i.step}` : ""}</td>
                <td className="px-3 py-2 text-xs">{i.tickers.slice(-4).join(", ")}</td>
                <td className="px-3 py-2 text-xs num">{i.occurrences}× · {ago(i.last_seen)}</td>
                <td className="px-3 py-2 text-xs">{label(i.status)}</td>
              </tr>,
              openId === i.id && <tr key={`${i.id}-d`}><td colSpan={6} className="bg-card/50 px-3 py-3"><IssueDetail id={i.id} onChange={reload} /></td></tr>,
            ])}</tbody></table></div>)}
      </Card>
    </div>
  );
}

function IssueDetail({ id, onChange }: { id: number; onChange: () => void }) {
  const { data: d, reload } = useApi<QaIssueFull>(`/api/admin/qa/issues/${id}`);
  const [ref, setRef] = useState("");
  const [err, setErr] = useState<Error | null>(null);
  if (!d) return <Skeleton rows={3} />;
  const set = async (status: string) => {
    setErr(null);
    try { await api(`/api/admin/qa/issues/${id}`, { method: "PATCH", json: { status, ...(ref.trim() ? { fix_ref: ref.trim() } : {}) } }); reload(); onChange(); }
    catch (e) { setErr(e as Error); }
  };
  const t = d.triage ?? {};
  return (
    <div className="space-y-3 text-sm">
      <div className="grid gap-3 md:grid-cols-2">
        <div><div className="text-xs text-muted">Expected</div><div>{d.expected}</div></div>
        <div><div className="text-xs text-muted">Actual</div><div>{d.actual}</div></div>
      </div>
      {t.verdict && <div><div className="text-xs text-muted">Check ({t.by}): <span className="text-fg">{label(t.verdict)}</span></div><div>{t.rationale}</div>
        {t.likely_location && <div className="mt-1 text-xs"><span className="text-muted">Likely location:</span> <code>{t.likely_location}</code></div>}
        {t.fix_hint && <div className="mt-1 text-xs"><span className="text-muted">Fix hint:</span> {t.fix_hint}</div>}</div>}
      <div className="text-xs text-muted">Fingerprint <code>{d.fingerprint}</code> · endpoint <code>{d.endpoint}</code>{d.strategy ? ` · strategy ${d.strategy}` : ""} · first seen {ago(d.first_seen)}{d.fix_ref ? <> · fix <a href={d.fix_ref} target="_blank" rel="noreferrer" className="text-primary hover:underline">{d.fix_ref}</a></> : null}</div>
      {d.trace && <details><summary className="cursor-pointer text-xs text-muted">Request / response trace</summary><pre className="mt-2 max-h-72 overflow-auto rounded bg-card p-3 text-xs">{JSON.stringify(d.trace, null, 1)}</pre></details>}
      <div className="flex flex-wrap items-center gap-2">
        <input value={ref} onChange={e => setRef(e.target.value)} placeholder="PR link (optional)" className="w-64 rounded border border-line bg-bg px-2 py-1 text-xs" />
        <Button variant="outline" onClick={() => set("fixed")}>Mark fixed</Button>
        <Button variant="outline" onClick={() => set("valid")}>Confirm valid</Button>
        <Button variant="outline" onClick={() => set("false_positive")}>False positive</Button>
        <Button variant="outline" onClick={() => set("wontfix")}>Won&apos;t fix</Button>
      </div>
      <ErrorNote error={err} />
    </div>
  );
}

function Stat({ k, v, sub, bad }: { k: string; v: string; sub?: string; bad?: boolean }) {
  return <div className="rounded border border-line p-3"><div className="text-xs text-muted">{k}</div><div className={`mt-1 font-semibold num ${bad ? "text-down" : ""}`}>{v}</div>{sub && <div className="text-xs text-muted">{sub}</div>}</div>;
}

function fmtAge(s: number) {
  if (s < 90) return `${s}s ago`;
  if (s < 5400) return `${Math.round(s / 60)} min ago`;
  return `${Math.round(s / 3600)} h ago`;
}
