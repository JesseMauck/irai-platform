"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, download, type Quote } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { ago, num, pct, tone } from "@/lib/format";
import { useAuth } from "@/components/AuthProvider";
import { Button, Card, ErrorNote, PageHeader, SourceBadge } from "@/components/ui";

interface WL { id: number; name: string; symbols: string[]; quotes: Record<string, Quote> }
interface AlertRow { id: number; symbol: string; kind: string; threshold: number; channel: string; last_triggered_at: string | null }
interface Sub { plan: string; payments: string; trial_available: boolean; subscription: { plan: string; interval: string; status: string; provider: string; trial_ends_at: string | null; current_period_end: string | null; cancel_at_period_end: boolean } | null }

export default function Account() {
  const { user, ready, refresh } = useAuth();
  const router = useRouter();
  useEffect(() => { if (ready && !user) router.push("/login?next=/account"); }, [ready, user, router]);
  const { data: wls, reload: reloadWl } = useApi<WL[]>(user ? "/api/me/watchlists" : null, 30_000);
  const { data: alerts, reload: reloadAlerts } = useApi<AlertRow[]>(user ? "/api/me/alerts" : null);
  const { data: sub, reload: reloadSub } = useApi<Sub>(user ? "/api/billing/subscription" : null);
  const [sym, setSym] = useState(""); const [al, setAl] = useState({ symbol: "", kind: "price_above", threshold: "" });
  const [err, setErr] = useState<Error | null>(null);
  if (!user) return null;
  const add = async () => { setErr(null); try { await api(`/api/me/watchlists/${wls![0].id}/items`, { method: "POST", json: { symbol: sym } }); setSym(""); reloadWl(); } catch (e) { setErr(e as Error); } };
  const remove = async (s: string) => { await api(`/api/me/watchlists/${wls![0].id}/items/${s}`, { method: "DELETE" }); reloadWl(); };
  const addAlert = async () => { setErr(null); try { await api("/api/me/alerts", { method: "POST", json: { ...al, threshold: parseFloat(al.threshold) } }); reloadAlerts(); } catch (e) { setErr(e as Error); } };
  const cancel = async () => {
    if (!confirm("Cancel your membership? You keep access until the end of the period you've paid for.")) return;
    await api("/api/billing/cancel", { method: "POST" }); await refresh(); reloadSub();
  };
  const wl = wls?.[0];
  return (
    <div className="mx-auto max-w-6xl px-4 py-12">
      <PageHeader title={`Hi, ${user.display_name}`} intro={`@${user.handle} · ${user.email}`}>
        <div className="flex items-center gap-3"><span className="rounded-full bg-primary/15 px-3 py-1 text-sm capitalize text-primary">{user.plan}</span>
          {user.plan !== "pro" && <Button href="/pricing">Upgrade</Button>}</div>
      </PageHeader>
      <ErrorNote error={err} />
      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <div className="flex items-center justify-between border-b border-line p-4"><h2 className="font-semibold">{wl?.name ?? "Watchlist"}</h2>
            <div className="flex gap-2"><input value={sym} onChange={e => setSym(e.target.value.toUpperCase())} placeholder="Add ticker" className="w-32 rounded-lg border border-line bg-bg px-3 py-1.5 text-sm" onKeyDown={e => e.key === "Enter" && add()} /><Button onClick={add} disabled={!sym}>Add</Button></div></div>
          <table className="w-full text-sm"><tbody className="divide-y divide-line num">
            {wl?.symbols.map(s => { const q = wl.quotes[s]; return (
              <tr key={s}><td className="p-3"><Link href={`/ticker/${s}`} className="font-semibold hover:text-primary">{s}</Link><div className="text-xs text-muted">{q?.name}</div></td>
                <td className="p-3 text-right">{num(q?.price)}</td><td className={`p-3 text-right ${tone(q?.change_pct)}`}>{pct(q?.change_pct)}</td>
                <td className="p-3"><SourceBadge source={q?.source} /></td><td className="p-3 text-right"><button onClick={() => remove(s)} className="text-xs text-muted hover:text-down">Remove</button></td></tr>); })}
            {wl?.symbols.length === 0 && <tr><td className="p-6 text-center text-muted">Add any ticker to track it live.</td></tr>}
          </tbody></table>
        </Card>
        <div className="space-y-6">
          <Card className="p-5">
            <h2 className="font-semibold">Subscription</h2>
            {sub?.subscription ? <div className="mt-2 space-y-1 text-sm text-muted"><div className="capitalize text-fg">{sub.subscription.plan} · {sub.subscription.status === "trialing" ? "free trial" : sub.subscription.interval}</div>
              {sub.subscription.status === "trialing" && sub.subscription.trial_ends_at && <div>Trial ends {new Date(sub.subscription.trial_ends_at).toLocaleDateString()}. <Link href="/pricing" className="text-primary">Subscribe to keep access</Link></div>}
              {sub.subscription.provider === "square" && sub.subscription.current_period_end && <div>{sub.subscription.cancel_at_period_end ? "Access until" : "Renews"} {new Date(sub.subscription.current_period_end).toLocaleDateString()} · billed by Square</div>}
              {!sub.subscription.cancel_at_period_end && <button onClick={cancel} className="mt-2 text-down">{sub.subscription.status === "trialing" ? "End trial" : "Cancel membership"}</button>}</div>
              : <p className="mt-2 text-sm text-muted">Free plan. <Link href="/pricing" className="text-primary">{sub?.trial_available ? "Start a 7-day free trial" : "See plans"}</Link></p>}
          </Card>
          <Card className="p-5">
            <h2 className="font-semibold">Alerts</h2>
            <ul className="mt-2 space-y-1 text-sm">{alerts?.map(a => <li key={a.id} className="flex justify-between"><span>{a.symbol} {a.kind.replace(/_/g, " ")} {a.threshold}</span><span className="text-xs text-muted">{a.last_triggered_at ? ago(a.last_triggered_at) : a.channel}</span></li>)}</ul>
            <div className="mt-3 grid grid-cols-3 gap-2">
              <input placeholder="Ticker" value={al.symbol} onChange={e => setAl({ ...al, symbol: e.target.value.toUpperCase() })} className="rounded border border-line bg-bg px-2 py-1 text-sm" />
              <select value={al.kind} onChange={e => setAl({ ...al, kind: e.target.value })} className="rounded border border-line bg-bg px-1 py-1 text-xs">
                <option value="price_above">Price ≥</option><option value="price_below">Price ≤</option><option value="change_pct_abs">|Day %| ≥</option><option value="adr_z_abs">ADR |z| ≥</option></select>
              <input placeholder="Value" value={al.threshold} onChange={e => setAl({ ...al, threshold: e.target.value })} className="rounded border border-line bg-bg px-2 py-1 text-sm" />
            </div>
            <Button variant="outline" className="mt-2 w-full" onClick={addAlert} disabled={!al.symbol || !al.threshold}>Add alert</Button>
          </Card>
          <ApiKeys plan={user.plan} />
          <Card className="p-5"><h2 className="font-semibold">ValueBot</h2><p className="mt-1 text-sm text-muted">Your valuations, notes and models.</p><Button href="/valuebot/reports" variant="outline" className="mt-3 w-full">My reports</Button></Card>
          <YourData />
        </div>
      </div>
    </div>
  );
}


interface Key { id: number; name: string; prefix: string; created_at: string; last_used_at: string | null }

function ApiKeys({ plan }: { plan: string }) {
  const { data, reload } = useApi<Key[]>(plan === "pro" ? "/api/me/api-keys" : null);
  const [name, setName] = useState("");
  const [fresh, setFresh] = useState<string | null>(null);
  const [err, setErr] = useState<Error | null>(null);
  if (plan !== "pro") return <Card className="p-5"><h2 className="font-semibold">API access</h2><p className="mt-1 text-sm text-muted">A read-only API key for the monitors, grades and market data comes with Pro.</p></Card>;
  const create = async () => { setErr(null); try { const r = await api<{ key: string }>("/api/me/api-keys", { method: "POST", json: { name } }); setFresh(r.key); setName(""); reload(); } catch (e) { setErr(e as Error); } };
  const revoke = async (id: number) => { await api(`/api/me/api-keys/${id}`, { method: "DELETE" }); reload(); };
  return (
    <Card className="p-5">
      <h2 className="font-semibold">API keys</h2>
      <p className="text-xs text-muted">Read-only. Send as the <code>X-API-Key</code> header to any GET endpoint under /api.</p>
      {fresh && <div className="mt-2 break-all rounded bg-accent p-2 font-mono text-xs">{fresh}<div className="mt-1 font-sans text-primary">Copy it now. It won&apos;t be shown again.</div></div>}
      <ul className="mt-2 space-y-1 text-sm">{data?.map(k => <li key={k.id} className="flex justify-between"><span>{k.name} <span className="font-mono text-xs text-muted">{k.prefix}…</span></span>
        <button onClick={() => revoke(k.id)} className="text-xs text-muted hover:text-down">Revoke</button></li>)}</ul>
      <div className="mt-2 flex gap-2"><input value={name} onChange={e => setName(e.target.value)} placeholder="Key name" className="flex-1 rounded border border-line bg-bg px-2 py-1 text-sm" /><Button variant="outline" onClick={create} disabled={!name}>Create</Button></div>
      <ErrorNote error={err} />
    </Card>
  );
}


function YourData() {
  const { logout } = useAuth();
  const [open, setOpen] = useState(false);
  const [pw, setPw] = useState(""); const [confirmText, setConfirmText] = useState("");
  const [err, setErr] = useState<Error | null>(null);
  const exportData = async () => { setErr(null); try { await download("/api/me/export", "irradiance-my-data.json"); } catch (e) { setErr(e as Error); } };
  const del = async () => {
    setErr(null);
    try { await api("/api/me/delete", { method: "POST", json: { password: pw, confirm: confirmText } }); await logout(); location.href = "/"; }
    catch (e) { setErr(e as Error); }
  };
  return (
    <Card className="p-5">
      <h2 className="font-semibold">Your data</h2>
      <p className="mt-1 text-sm text-muted">Download everything linked to your account, or delete it. See the <Link href="/legal/privacy" className="text-primary">Privacy Policy</Link>.</p>
      <Button variant="outline" className="mt-3 w-full" onClick={exportData}>Export my data</Button>
      {!open ? <button onClick={() => setOpen(true)} className="mt-3 text-sm text-down">Delete account…</button> : (
        <div className="mt-3 space-y-2 rounded-lg border border-down/40 p-3 text-sm">
          <p className="text-fg-2">This permanently deletes your account, watchlists, alerts, reports, notes and posts, and cancels any paid membership. It can&rsquo;t be undone.</p>
          <input type="password" value={pw} onChange={e => setPw(e.target.value)} placeholder="Your password" autoComplete="current-password" className="w-full rounded border border-line bg-bg px-2 py-1" />
          <input value={confirmText} onChange={e => setConfirmText(e.target.value)} placeholder='Type DELETE to confirm' className="w-full rounded border border-line bg-bg px-2 py-1" />
          <div className="flex gap-2"><Button onClick={del} disabled={!pw || confirmText !== "DELETE"} className="bg-none bg-down text-white">Delete permanently</Button><Button variant="ghost" onClick={() => setOpen(false)}>Cancel</Button></div>
        </div>
      )}
      <ErrorNote error={err} />
    </Card>
  );
}
