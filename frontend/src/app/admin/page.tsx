"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { ago, num } from "@/lib/format";
import { useAuth } from "@/components/AuthProvider";
import { Button, Card, ErrorNote, PageHeader } from "@/components/ui";

interface Stats {
  users: { total: number; by_plan: Record<string, number>; new_30d: number }; mrr_active: number; valuebot_runs_30d: number;
  backtests_30d: number; threads: number; trades: number; outbox: Record<string, number>; market: { mode: string; source: string };
  subscriptions: { plan: string; interval: string; status: string; count: number }[];
}
interface AdminUser { id: number; email: string; handle: string; display_name: string; plan: string; is_admin: boolean; disabled: boolean; verified_trader: boolean; created_at: string }
interface AdminArticle { id?: number; slug: string; title: string; category: string; tickers: string[]; summary: string; body_md: string; author: string; read_minutes: number; premium: boolean; published_at?: string | null }
interface Coverage { adr_pairs: Record<string, string | number | boolean>[]; etf_funds: { symbol: string; name: string; category: string; active: boolean }[];
  peer_groups: { id: number; name: string; sector: string; members: { id: number; symbol: string; name: string }[] }[] }

const TABS = ["Overview", "Users", "Articles", "Coverage", "Moderation"] as const;

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
      {tab === "Coverage" && <CoverageTab />}{tab === "Moderation" && <Moderation />}
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
      <div className="grid gap-3 md:grid-cols-3 lg:grid-cols-6">{tiles.map(([k, v]) => <Card key={k} className="p-4"><div className="text-xs text-muted">{k}</div><div className="text-2xl font-semibold num">{v}</div></Card>)}</div>
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
