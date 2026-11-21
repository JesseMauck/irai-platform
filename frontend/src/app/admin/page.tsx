"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { ago, num } from "@/lib/format";
import { useAuth } from "@/components/AuthProvider";
import { Button, Card, ErrorNote, PageHeader, Skeleton } from "@/components/ui";
import Link from "next/link";

interface Stats {
  users: { total: number; by_plan: Record<string, number>; new_30d: number }; mrr_active: number; valuebot_runs_30d: number;
  backtests_30d: number; threads: number; trades: number; outbox: Record<string, number>; market: { mode: string; source: string };
  subscriptions: { plan: string; interval: string; status: string; count: number }[];
}
interface AdminUser { id: number; email: string; handle: string; display_name: string; plan: string; is_admin: boolean; disabled: boolean; verified_trader: boolean; created_at: string }
interface AdminArticle { id?: number; slug: string; title: string; category: string; tickers: string[]; summary: string; body_md: string; author: string; read_minutes: number; premium: boolean; published_at?: string | null }
interface Coverage { adr_pairs: Record<string, string | number | boolean>[]; etf_funds: { symbol: string; name: string; category: string; active: boolean }[];
  peer_groups: { id: number; name: string; sector: string; members: { id: number; symbol: string; name: string }[] }[] }

const TABS = ["Overview", "Users", "Articles", "Coverage", "Moderation", "Billing", "ValueBot QA", "Data cycle"] as const;

export default function Admin() {
  const { user, ready } = useAuth();
  const router = useRouter();
  const [tab, setTab] = useState<(typeof TABS)[number]>("Overview");
  useEffect(() => { if (ready && (!user || !user.is_admin)) router.push("/"); }, [ready, user, router]);
  if (!user?.is_admin) return null;
  return (
    <div className="mx-auto max-w-7xl px-4 py-12">
      <PageHeader title="Admin" intro="Business metrics, members, research, coverage and moderation." />
      <div className="mb-6 flex gap-1 border-b border-line">{TABS.map(t => <button key={t} onClick={() => setTab(t)} className={`px-4 py-2 text-sm ${t === tab ? "border-b-2 border-primary text-fg" : "text-muted"}`}>{t}</button>)}</div>
      {tab === "Overview" && <Overview />}{tab === "Users" && <Users />}{tab === "Articles" && <Articles />}
      {tab === "Coverage" && <CoverageTab />}{tab === "Moderation" && <Moderation />}{tab === "Billing" && <Billing />}{tab === "ValueBot QA" && <Calibration />}{tab === "Data cycle" && <DataCycle />}
    </div>
  );
}

function Overview() {
  const { data: s } = useApi<Stats>("/api/admin/stats");
  if (!s) return null;
  const tiles: [string, string][] = [["Members", String(s.users.total)], ["New (30d)", String(s.users.new_30d)], ["MRR (active)", `$${num(s.mrr_active, 0)}`],
    ["ValueBot runs (30d)", String(s.valuebot_runs_30d)], ["Backtests (30d)", String(s.backtests_30d)], ["Threads / trades", `${s.threads} / ${s.trades}`]];
  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-3 lg:grid-cols-6">{tiles.map(([k, v]) => <Card key={k} className="p-4"><div className="text-xs text-muted">{k}</div><div className="stat text-2xl">{v}</div></Card>)}</div>
      <div className="grid gap-4 md:grid-cols-3">
        <Card className="p-5"><h3 className="font-semibold">Members by plan</h3><ul className="mt-2 text-sm">{Object.entries(s.users.by_plan).map(([k, v]) => <li key={k} className="flex justify-between capitalize"><span>{k}</span><span className="num">{v}</span></li>)}</ul></Card>
        <Card className="p-5"><h3 className="font-semibold">Subscriptions</h3><ul className="mt-2 text-sm">{s.subscriptions.map((x, i) => <li key={i} className="flex justify-between capitalize"><span>{x.plan} · {x.interval} · {x.status}</span><span className="num">{x.count}</span></li>)}{!s.subscriptions.length && <li className="text-muted">None yet</li>}</ul></Card>
        <Card className="p-5"><h3 className="font-semibold">Systems</h3><ul className="mt-2 text-sm"><li>Market data: {s.market.source} ({s.market.mode})</li>{Object.entries(s.outbox).map(([k, v]) => <li key={k}>Email {k}: {v}</li>)}</ul></Card>
      </div>
    </div>
  );
}

function Users() {
  const [q, setQ] = useState("");
  const { data, reload } = useApi<AdminUser[]>(`/api/admin/users?q=${encodeURIComponent(q)}`, undefined, [q]);
  const [err, setErr] = useState<Error | null>(null);
  const patch = async (id: number, body: Partial<AdminUser>) => { setErr(null); try { await api(`/api/admin/users/${id}`, { method: "PATCH", json: body }); reload(); } catch (e) { setErr(e as Error); } };
  return (
    <Card>
      <div className="border-b border-line p-4"><input value={q} onChange={e => setQ(e.target.value)} placeholder="Search email or handle" className="w-72 rounded border border-line bg-bg px-3 py-1.5 text-sm" /><ErrorNote error={err} /></div>
      <table className="w-full text-sm"><thead className="text-left text-xs uppercase text-muted"><tr>{["Member", "Plan", "Verified trader", "Admin", "Status", "Joined"].map(h => <th key={h} className="px-3 py-2">{h}</th>)}</tr></thead>
        <tbody className="divide-y divide-line">{data?.map(u => (
          <tr key={u.id}><td className="px-3 py-2">{u.display_name} <span className="text-muted">@{u.handle}</span><div className="text-xs text-muted">{u.email}</div></td>
            <td className="px-3 py-2"><select value={u.plan} onChange={e => patch(u.id, { plan: e.target.value })} className="rounded border border-line bg-bg px-2 py-1">{["free", "essential", "pro"].map(p => <option key={p}>{p}</option>)}</select></td>
            <td className="px-3 py-2"><input type="checkbox" checked={u.verified_trader} onChange={e => patch(u.id, { verified_trader: e.target.checked })} /></td>
            <td className="px-3 py-2"><input type="checkbox" checked={u.is_admin} onChange={e => patch(u.id, { is_admin: e.target.checked })} /></td>
            <td className="px-3 py-2"><button onClick={() => patch(u.id, { disabled: !u.disabled })} className={u.disabled ? "text-down" : "text-muted hover:text-down"}>{u.disabled ? "Disabled · enable" : "Disable"}</button></td>
            <td className="px-3 py-2 text-muted">{ago(u.created_at)}</td></tr>))}</tbody></table>
    </Card>
  );
}

const BLANK: AdminArticle = { slug: "", title: "", category: "ADR", tickers: [], summary: "", body_md: "", author: "IRAI Research", read_minutes: 5, premium: false };

function Articles() {
  const { data, reload } = useApi<AdminArticle[]>("/api/admin/articles");
  const [edit, setEdit] = useState<AdminArticle | null>(null);
  const [err, setErr] = useState<Error | null>(null);
  const save = async () => {
    if (!edit) return; setErr(null);
    try { await api(edit.id ? `/api/admin/articles/${edit.id}` : "/api/admin/articles", { method: edit.id ? "PUT" : "POST", json: edit }); setEdit(null); reload(); }
    catch (e) { setErr(e as Error); }
  };
  const del = async (id: number) => { if (confirm("Delete this article?")) { await api(`/api/admin/articles/${id}`, { method: "DELETE" }); reload(); } };
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <div className="flex items-center justify-between border-b border-line p-4"><h3 className="font-semibold">Articles</h3><Button onClick={() => setEdit({ ...BLANK })}>New article</Button></div>
        <ul className="divide-y divide-line text-sm">{data?.map(a => <li key={a.id} className="flex items-center justify-between p-3"><button onClick={() => setEdit(a)} className="text-left hover:text-primary">{a.title}<div className="text-xs text-muted">{a.category} · {a.published_at}{a.premium ? " · members" : ""}</div></button>
          <button onClick={() => del(a.id!)} className="text-xs text-muted hover:text-down">Delete</button></li>)}</ul>
      </Card>
      {edit && (
        <Card className="space-y-3 p-5">
          <h3 className="font-semibold">{edit.id ? "Edit article" : "New article"}</h3>
          {(["title", "slug", "author"] as const).map(k => <input key={k} placeholder={k} value={edit[k]} onChange={e => setEdit({ ...edit, [k]: e.target.value })} className="w-full rounded border border-line bg-bg px-3 py-2 text-sm" />)}
          <div className="flex gap-2">
            <select value={edit.category} onChange={e => setEdit({ ...edit, category: e.target.value })} className="rounded border border-line bg-bg px-2 py-2 text-sm">{["ADR", "ETF", "Fundamental", "Methodology"].map(c => <option key={c}>{c}</option>)}</select>
            <input placeholder="Tickers (comma-separated)" value={edit.tickers.join(", ")} onChange={e => setEdit({ ...edit, tickers: e.target.value.split(/[,\s]+/).filter(Boolean) })} className="flex-1 rounded border border-line bg-bg px-3 py-2 text-sm" />
            <input type="number" value={edit.read_minutes} onChange={e => setEdit({ ...edit, read_minutes: parseInt(e.target.value) || 5 })} className="w-20 rounded border border-line bg-bg px-2 py-2 text-sm" title="Read minutes" />
          </div>
          <textarea placeholder="Summary" rows={2} value={edit.summary} onChange={e => setEdit({ ...edit, summary: e.target.value })} className="w-full rounded border border-line bg-bg px-3 py-2 text-sm" />
          <textarea placeholder="Body (Markdown)" rows={12} value={edit.body_md} onChange={e => setEdit({ ...edit, body_md: e.target.value })} className="w-full rounded border border-line bg-bg px-3 py-2 font-mono text-xs" />
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={edit.premium} onChange={e => setEdit({ ...edit, premium: e.target.checked })} />Members only</label>
          <ErrorNote error={err} /><div className="flex gap-2"><Button onClick={save}>Save</Button><Button variant="ghost" onClick={() => setEdit(null)}>Cancel</Button></div>
        </Card>
      )}
    </div>
  );
}

function CoverageTab() {
  const { data, reload } = useApi<Coverage>("/api/admin/coverage");
  const [adr, setAdr] = useState({ adr_symbol: "", local_symbol: "", name: "", country: "", local_currency: "", ratio: "1" });
  const [peer, setPeer] = useState({ group: "", symbol: "", name: "" });
  const [err, setErr] = useState<Error | null>(null);
  const run = async (fn: () => Promise<unknown>) => { setErr(null); try { await fn(); reload(); } catch (e) { setErr(e as Error); } };
  return (
    <div className="space-y-4">
      <ErrorNote error={err} />
      <Card className="p-5">
        <h3 className="font-semibold">ADR pairs</h3>
        <p className="text-xs text-muted">Ratio = local ordinary shares per ONE ADR. Check it with the depositary bank, because ratios change after splits.</p>
        <table className="mt-3 w-full text-sm"><tbody className="divide-y divide-line num">{data?.adr_pairs.map(p => (
          <tr key={String(p.adr_symbol)}><td className="py-1.5 font-semibold">{String(p.adr_symbol)}</td><td>{String(p.local_symbol)}</td><td className="text-muted">{String(p.name)}</td><td>{String(p.local_currency)}</td><td>1 : {String(p.ratio)}</td>
            <td><button onClick={() => run(() => api("/api/admin/coverage/adr", { method: "PUT", json: { ...p, active: !p.active } }))} className={p.active ? "text-up" : "text-muted"}>{p.active ? "Active" : "Inactive"}</button></td></tr>))}</tbody></table>
        <div className="mt-3 grid grid-cols-2 gap-2 md:grid-cols-7">
          {(Object.keys(adr) as (keyof typeof adr)[]).map(k => <input key={k} placeholder={k} value={adr[k]} onChange={e => setAdr({ ...adr, [k]: e.target.value })} className="rounded border border-line bg-bg px-2 py-1.5 text-sm" />)}
          <Button variant="outline" onClick={() => run(() => api("/api/admin/coverage/adr", { method: "PUT", json: { ...adr, ratio: parseFloat(adr.ratio) } }))}>Add / update</Button>
        </div>
      </Card>
      <Card className="p-5">
        <h3 className="font-semibold">Peer groups</h3>
        <div className="mt-3 grid gap-3 md:grid-cols-3">{data?.peer_groups.map(g => (
          <div key={g.id} className="rounded-lg bg-accent/40 p-3"><div className="font-medium">{g.name}</div><div className="mt-1 flex flex-wrap gap-1">{g.members.map(m => (
            <span key={m.id} className="inline-flex items-center gap-1 rounded bg-card px-2 py-0.5 text-xs">{m.symbol}<button onClick={() => run(() => api(`/api/admin/coverage/peers/${m.id}`, { method: "DELETE" }))} className="text-muted hover:text-down">×</button></span>))}</div></div>))}</div>
        <div className="mt-3 flex gap-2">{(Object.keys(peer) as (keyof typeof peer)[]).map(k => <input key={k} placeholder={k} value={peer[k]} onChange={e => setPeer({ ...peer, [k]: e.target.value })} className="rounded border border-line bg-bg px-2 py-1.5 text-sm" />)}
          <Button variant="outline" onClick={() => run(() => api("/api/admin/coverage/peers", { method: "POST", json: peer }))}>Add member</Button></div>
      </Card>
      <Card className="p-5"><h3 className="font-semibold">ETF funds</h3>
        <div className="mt-2 flex flex-wrap gap-2 text-sm">{data?.etf_funds.map(f => <button key={f.symbol} onClick={() => run(() => api("/api/admin/coverage/etf", { method: "PUT", json: { ...f, active: !f.active } }))} className={`rounded px-2 py-1 ${f.active ? "bg-up/15 text-up" : "bg-accent text-muted"}`}>{f.symbol}</button>)}</div></Card>
    </div>
  );
}

function Moderation() {
  const { data } = useApi<{ id: number; target_type: string; target_id: number; action: string; reason: string; created_at: string }[]>("/api/admin/moderation-log");
  return (
    <Card>
      <div className="border-b border-line p-4 text-sm text-muted">Hide threads, replies or trade posts from their pages (admins see a Hide control). Every action is logged here and can be appealed.</div>
      <table className="w-full text-sm"><tbody className="divide-y divide-line">{data?.map(m => <tr key={m.id}><td className="px-3 py-2 capitalize">{m.action}</td><td className="px-3 py-2">{m.target_type} #{m.target_id}</td><td className="px-3 py-2 text-muted">{m.reason}</td><td className="px-3 py-2 text-muted">{ago(m.created_at)}</td></tr>)}
        {data?.length === 0 && <tr><td className="p-6 text-center text-muted">No moderation actions yet.</td></tr>}</tbody></table>
    </Card>
  );
}

interface SquareStatus { token_set: boolean; environment: string; location_id: string | null; plans: Record<string, boolean>;
  webhook_signature_key_set: boolean; webhook_url: string | null; expected_webhook_url: string; webhook_events: string[]; ready: boolean }

interface SquareVariation { id: string; name: string; plan: string; cadence: string; amount_cents: number | null; suggested: string | null }

function Billing() {
  const { data: st, reload } = useApi<SquareStatus>("/api/admin/billing/square");
  const [locs, setLocs] = useState<{ id: string; name: string; status: string }[] | null>(null);
  const [vars, setVars] = useState<Record<string, string> | null>(null);
  const [found, setFound] = useState<SquareVariation[] | null>(null);
  const [err, setErr] = useState<Error | null>(null);
  const run = async <T,>(fn: () => Promise<T>, then: (v: T) => void) => { setErr(null); try { then(await fn()); reload(); } catch (e) { setErr(e as Error); } };
  if (!st) return null;
  const Row = ({ ok, label, hint }: { ok: boolean; label: string; hint?: string }) => (
    <li className="flex gap-3 py-2"><span className={ok ? "text-up" : "text-down"}>{ok ? "✓" : "○"}</span><div><div>{label}</div>{hint && <div className="text-xs text-muted">{hint}</div>}</div></li>);
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card className="p-5">
        <h3 className="font-semibold">Square payments {st.ready ? <span className="ml-2 text-sm text-up">ready</span> : <span className="ml-2 text-sm text-muted">setup</span>}</h3>
        <ul className="mt-3 divide-y divide-line text-sm">
          <Row ok={st.token_set} label={`Access token (${st.environment})`} hint="Railway → api → Variables: SQUARE_ACCESS_TOKEN, SQUARE_ENVIRONMENT" />
          <Row ok={!!st.location_id} label={st.location_id ? `Location ${st.location_id}` : "Location"} hint="Find it below, then set SQUARE_LOCATION_ID" />
          <Row ok={Object.values(st.plans).every(Boolean)} label="Subscription plans" hint="Create them below, then set the four SQUARE_PLAN_* variables" />
          <Row ok={st.webhook_signature_key_set && !!st.webhook_url} label="Webhook" hint={`Square Developer Dashboard → Webhooks → add ${st.expected_webhook_url} for ${st.webhook_events.join(", ")}; set SQUARE_WEBHOOK_SIGNATURE_KEY and SQUARE_WEBHOOK_URL`} />
        </ul>
        <ErrorNote error={err} />
        <div className="mt-3 flex flex-wrap gap-2">
          <Button variant="outline" disabled={!st.token_set} onClick={() => run(() => api<{ id: string; name: string; status: string }[]>("/api/admin/billing/square/locations"), setLocs)}>Find locations</Button>
          <Button variant="outline" disabled={!st.token_set} onClick={() => run(() => api<{ variations: SquareVariation[]; variables: Record<string, string> }>("/api/admin/billing/square/plans"), r => { setFound(r.variations); setVars(r.variables); })}>Find existing plans</Button>
          <Button disabled={!st.token_set || !st.location_id || Object.values(st.plans).every(Boolean)} onClick={() => run(() => api<{ variables: Record<string, string> }>("/api/admin/billing/square/setup", { method: "POST" }), r => setVars(r.variables))}>Create subscription plans</Button>
        </div>
      </Card>
      <Card className="p-5 font-mono text-xs">
        <h3 className="mb-2 font-sans font-semibold">Values to set on Railway (not secret)</h3>
        {locs?.map(l => <div key={l.id}>SQUARE_LOCATION_ID={l.id} <span className="text-muted"># {l.name} ({l.status})</span></div>)}
        {vars && Object.entries(vars).map(([k, v]) => <div key={k}>{k}={v}</div>)}
        {found && <div className="mt-3 font-sans">
          <div className="mb-1 text-muted">Plans found in Square ({found.length})</div>
          {found.length === 0 && <p className="text-muted">None yet. Use “Create subscription plans”.</p>}
          {found.map(v => <div key={v.id} className="flex flex-wrap gap-x-3 border-t border-line py-1">
            <span>{v.plan}: {v.name}</span><span className="text-muted">{v.cadence}{v.amount_cents != null ? ` · $${(v.amount_cents / 100).toFixed(2)}` : ""}</span>
            <span className="font-mono">{v.id}</span><span className={v.suggested ? "text-up" : "text-muted"}>{v.suggested ?? "not matched"}</span></div>)}
        </div>}
        {!locs && !vars && !found && <p className="font-sans text-muted">Results appear here.</p>}
      </Card>
    </div>
  );
}


interface CalRow { ticker: string; ok: boolean; value_per_share?: number | null; price?: number | null; ratio?: number | null; method?: string | null;
  prev_value?: number | null; flags: string[]; error?: string | null; failed_stage?: string | null; seconds?: number }
interface CalRun { id: number; started_at: string; finished_at: string | null; status: string; trigger: string; progress: number;
  summary: { tickers: number; ok: number; errors: number; flagged: number; median_ratio: number | null; in_band: number } | null; results: CalRow[] | null }

function Calibration() {
  const { data, reload, error } = useApi<{ config: { tickers: string[]; band: { low: number; high: number } }; runs: CalRun[] }>("/api/admin/calibration", 15_000);
  const [err, setErr] = useState<Error | null>(null);
  const start = async () => { setErr(null); try { await api("/api/admin/calibration/run", { method: "POST" }); setTimeout(reload, 1500); } catch (e) { setErr(e as Error); } };
  if (error) return <p className="text-down">{error.message}</p>;
  if (!data) return <Skeleton rows={6} />;
  const latest = data.runs[0];
  return (
    <div className="space-y-4">
      <Card className="p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div><h2 className="font-semibold">ValueBot calibration</h2>
            <p className="max-w-2xl text-sm text-muted">Every night after 07:00 UTC the worker values {data.config.tickers.length} benchmark companies with the deterministic pipeline (no AI cost) and compares value per share with price. Values outside {data.config.band.low}x to {data.config.band.high}x of price, errors, and big swings from the previous run are flagged for review.</p></div>
          <Button onClick={start} disabled={latest?.status === "running"}>{latest?.status === "running" ? `Running (${latest.progress}/${data.config.tickers.length})` : "Run now"}</Button>
        </div>
        <ErrorNote error={err} />
      </Card>
      {latest?.results && (
        <Card className="p-5">
          <div className="flex flex-wrap items-baseline justify-between gap-2"><h3 className="font-semibold">Run #{latest.id} · {new Date(latest.started_at).toLocaleString()} · {latest.trigger}</h3>
            {latest.summary && <span className="text-sm text-muted">{latest.summary.ok}/{latest.summary.tickers} ok · {latest.summary.in_band} in band · {latest.summary.flagged} flagged · median value/price {latest.summary.median_ratio?.toFixed(2) ?? "—"}</span>}</div>
          <div className="mt-3 overflow-x-auto"><table className="w-full min-w-[760px] text-sm">
            <thead className="text-xs text-muted"><tr>{["Ticker", "Method", "Value/share", "Price", "Value/price", "Previous", "Flags", "Time"].map((h, i) => <th key={h} className={`py-1 font-normal ${i ? "text-right" : "text-left"}`}>{h}</th>)}</tr></thead>
            <tbody className="divide-y divide-line">{latest.results.map(r => (
              <tr key={r.ticker} className={r.flags.length ? "bg-down/5" : ""}>
                <td className="py-1.5 font-medium"><Link href={`/ticker/${r.ticker}`} className="hover:text-primary">{r.ticker}</Link></td>
                <td className="text-right text-xs text-muted">{r.method ?? "—"}</td>
                <td className="text-right num">{r.value_per_share?.toFixed(2) ?? "—"}</td>
                <td className="text-right num">{r.price?.toFixed(2) ?? "—"}</td>
                <td className={`text-right num ${r.ratio && (r.ratio < data.config.band.low || r.ratio > data.config.band.high) ? "text-down" : ""}`}>{r.ratio?.toFixed(2) ?? "—"}</td>
                <td className="text-right num text-muted">{r.prev_value?.toFixed(2) ?? "—"}</td>
                <td className="text-right text-xs">{r.ok ? (r.flags.join(", ") || <span className="text-up">ok</span>) : <span className="text-down" title={r.error ?? ""}>error{r.failed_stage ? ` at ${r.failed_stage}` : ""}</span>}</td>
                <td className="text-right text-xs text-muted num">{r.seconds ? `${r.seconds}s` : ""}</td>
              </tr>))}</tbody></table></div>
        </Card>)}
      {data.runs.length > 1 && <Card className="p-5"><h3 className="font-semibold">History</h3>
        <ul className="mt-2 space-y-1 text-sm">{data.runs.slice(1).map(r => <li key={r.id} className="flex justify-between"><span>#{r.id} · {new Date(r.started_at).toLocaleDateString()} · {r.trigger}</span>
          <span className="text-muted num">{r.summary ? `${r.summary.ok}/${r.summary.tickers} ok · ${r.summary.flagged} flagged · median ${r.summary.median_ratio?.toFixed(2) ?? "—"}` : r.status}</span></li>)}</ul></Card>}
    </div>
  );
}

interface DV { id: number; version: string; trigger: string; created_at: string; rows: number; seconds: number | null; included: number; quality: number | null; alerts: string[] | null;
  drift: Record<string, { psi: number; level: string }> | null; splits: Record<string, { start: string; end: string }> | null;
  profiles: { symbol: string; rows: number; quality: number; issues: string[] }[] | null }

function DataCycle() {
  const { data, reload, error } = useApi<{ running: boolean; universe: string[]; features: string[]; versions: DV[] }>("/api/admin/datapipe", 20_000);
  const [msg, setMsg] = useState<string | null>(null);
  const run = async (path: string) => { setMsg(null); try { await api(path, { method: "POST" }); setMsg("Started."); setTimeout(reload, 2000); } catch (e) { setMsg((e as Error).message); } };
  const v = data?.versions[0];
  return (<div className="space-y-4">
    <ErrorNote error={error} />
    <Card className="p-5"><div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="font-semibold">Data cycle</h2>
      <p className="text-sm text-muted">Nightly after 22:30 UTC: ingestion, profiling, cleaning, features, time splits and drift monitoring on {data?.universe.length ?? "…"} series. The pattern study runs after 23:15 UTC on top of it.</p></div>
      <div className="flex gap-2"><Button onClick={() => run("/api/admin/datapipe/run")} disabled={data?.running}>{data?.running ? "Running…" : "Run data cycle"}</Button><Button variant="outline" onClick={() => run("/api/admin/patterns/run")}>Run pattern study</Button></div></div>
      {msg && <p className="mt-2 text-sm text-muted">{msg}</p>}</Card>
    {!data ? <Skeleton rows={6} /> : !v ? <Card className="p-5 text-sm text-muted">No dataset versions yet.</Card> : (<>
      <div className="grid gap-3 md:grid-cols-4">{[["Version", v.version], ["Series included", String(v.included)], ["Mean quality", num(v.quality, 3)], ["Rows / seconds", `${v.rows.toLocaleString()} / ${num(v.seconds, 0)}`]].map(([l, x]) => <Card key={l} className="p-4"><div className="text-xs text-muted">{l}</div><div className="mt-1 font-semibold num">{x}</div></Card>)}</div>
      {v.alerts && v.alerts.length > 0 && <Card className="p-4"><div className="text-sm font-medium">Alerts</div><ul className="mt-1 list-disc pl-5 text-sm">{v.alerts.map(a => <li key={a}>{a}</li>)}</ul></Card>}
      <Card className="p-4"><div className="text-sm font-medium">Drift vs previous version (PSI)</div><div className="mt-2 flex flex-wrap gap-2 text-xs">{Object.entries(v.drift ?? {}).map(([k, d]) => <span key={k} className={`rounded px-2 py-1 ${d.level === "major" ? "bg-down/20 text-down" : d.level === "notable" ? "bg-primary/15 text-primary" : "bg-accent"}`}>{k} {d.psi}</span>)}{!Object.keys(v.drift ?? {}).length && <span className="text-muted">First version: nothing to compare.</span>}</div>
        {v.splits && <p className="mt-2 text-xs text-muted">Splits: train {v.splits.train?.start} to {v.splits.train?.end} · validation to {v.splits.validation?.end} · test to {v.splits.test?.end}</p>}</Card>
      <Card className="overflow-x-auto p-0"><table className="w-full text-sm"><thead className="text-xs text-muted"><tr>{["Series", "Rows", "Quality", "Issues"].map(h => <th key={h} className="px-4 py-2 text-left font-normal">{h}</th>)}</tr></thead>
        <tbody className="divide-y divide-line">{(v.profiles ?? []).slice().sort((a, b) => a.quality - b.quality).map(p => <tr key={p.symbol}><td className="px-4 py-1.5">{p.symbol}</td><td className="px-4 num">{p.rows}</td><td className={`px-4 num ${p.quality < 0.8 ? "text-down" : ""}`}>{num(p.quality, 3)}</td><td className="px-4 text-xs text-muted">{p.issues.join("; ")}</td></tr>)}</tbody></table></Card>
      <Card className="p-4 text-xs text-muted">History: {data.versions.map(x => `${x.created_at.slice(0, 10)} ${x.version.slice(-10)} (${x.trigger}, q ${num(x.quality, 2)}) ${ago(x.created_at)}`).join(" · ")}</Card>
    </>)}
  </div>);
}
