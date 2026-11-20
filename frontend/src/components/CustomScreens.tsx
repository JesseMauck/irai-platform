"use client";
import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { pct } from "@/lib/format";
import { useAuth } from "./AuthProvider";
import { Button, Card, ErrorNote, SourceBadge } from "./ui";

type Universe = "fundamental" | "adr" | "etf";
interface Row { symbol: string; name: string; detail: string; value: number | null; source: string }
interface Saved { id: number; name: string; universe: Universe; filters: Record<string, number | string | boolean>; alert_on_new: boolean }

const FIELDS: Record<Universe, { key: string; label: string; kind: "num" | "pct" | "bool" | "text" }[]> = {
  fundamental: [{ key: "rv_min", label: "RV percentile ≥", kind: "num" }, { key: "quality_min", label: "Quality percentile ≥", kind: "num" },
    { key: "multiple_max", label: "Multiple ≤", kind: "num" }, { key: "roe_min", label: "ROE ≥ (%)", kind: "pct" }, { key: "peer_group", label: "Peer group", kind: "text" }],
  adr: [{ key: "z_abs_min", label: "|z| ≥", kind: "num" }, { key: "premium_min", label: "Premium ≥ (%)", kind: "pct" }, { key: "premium_max", label: "Premium ≤ (%)", kind: "pct" },
    { key: "tradable_only", label: "Tradable only", kind: "bool" }, { key: "country", label: "Country", kind: "text" }],
  etf: [{ key: "premium_abs_min", label: "|Premium| ≥ (%)", kind: "pct" }, { key: "category", label: "Category", kind: "text" }],
};

export function CustomScreens() {
  const { user } = useAuth();
  const [universe, setUniverse] = useState<Universe>("fundamental");
  const [vals, setVals] = useState<Record<string, string | boolean>>({});
  const [name, setName] = useState("");
  const [alertNew, setAlertNew] = useState(false);
  const [rows, setRows] = useState<Row[] | null>(null);
  const [err, setErr] = useState<Error | null>(null);
  const { data: saved, reload } = useApi<Saved[]>(user && user.plan !== "free" ? "/api/me/screens" : null);

  const filters = () => Object.fromEntries(FIELDS[universe].flatMap((f): [string, string | number | boolean][] => {
    const v = vals[f.key];
    if (v === undefined || v === "" || v === false) return [];
    if (f.kind === "bool") return [[f.key, true]];
    if (f.kind === "text") return [[f.key, String(v)]];
    const n = parseFloat(String(v)); return isFinite(n) ? [[f.key, f.kind === "pct" ? n / 100 : n]] : [];
  }));
  const preview = async () => { setErr(null); try { setRows((await api<{ rows: Row[] }>("/api/me/screens/preview", { method: "POST", json: { name: name || "preview", universe, filters: filters() } })).rows); } catch (e) { setErr(e as Error); } };
  const save = async () => { setErr(null); try { await api("/api/me/screens", { method: "POST", json: { name, universe, filters: filters(), alert_on_new: alertNew } }); setName(""); reload(); } catch (e) { setErr(e as Error); } };
  const runSaved = async (s: Saved) => { setUniverse(s.universe); setRows((await api<{ rows: Row[] }>(`/api/me/screens/${s.id}/run`)).rows); };
  const del = async (s: Saved) => { await api(`/api/me/screens/${s.id}`, { method: "DELETE" }); reload(); };

  if (!user || user.plan === "free") return (
    <Card className="mt-10 p-6 text-center"><h2 className="font-semibold">Build your own screen</h2>
      <p className="mt-1 text-sm text-muted">Custom filters across the ADR, ETF and Fundamental universes, saved screens, and email alerts when new names match. Essential and Pro.</p>
      <div className="mt-3"><Button href={user ? "/pricing" : "/login?next=/screeners"}>{user ? "See plans" : "Sign in"}</Button></div></Card>
  );
  return (
    <section className="mt-10 grid gap-6 lg:grid-cols-3">
      <Card className="p-5 lg:col-span-2">
        <h2 className="font-semibold">Build a screen</h2>
        <div className="mt-3 flex gap-1">{(["fundamental", "adr", "etf"] as Universe[]).map(u => <button key={u} onClick={() => { setUniverse(u); setVals({}); setRows(null); }} className={`rounded-full px-3 py-1 text-sm capitalize ${u === universe ? "bg-primary/15 text-primary" : "bg-accent text-muted"}`}>{u === "adr" ? "ADR" : u === "etf" ? "ETF" : "Fundamental"}</button>)}</div>
        <div className="mt-4 grid gap-3 md:grid-cols-3">
          {FIELDS[universe].map(f => f.kind === "bool"
            ? <label key={f.key} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={!!vals[f.key]} onChange={e => setVals({ ...vals, [f.key]: e.target.checked })} />{f.label}</label>
            : <label key={f.key} className="text-xs text-muted">{f.label}<input value={String(vals[f.key] ?? "")} onChange={e => setVals({ ...vals, [f.key]: e.target.value })} className="mt-1 w-full rounded border border-line bg-bg px-2 py-1.5 text-sm text-fg" /></label>)}
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Button variant="outline" onClick={preview}>Preview</Button>
          <input placeholder="Screen name" value={name} onChange={e => setName(e.target.value)} className="rounded border border-line bg-bg px-3 py-2 text-sm" />
          <label className="flex items-center gap-2 text-sm text-muted"><input type="checkbox" checked={alertNew} onChange={e => setAlertNew(e.target.checked)} />Email me new matches</label>
          <Button onClick={save} disabled={!name}>Save screen</Button>
        </div>
        <ErrorNote error={err} />
        {rows && (
          <table className="mt-4 w-full text-sm"><tbody className="divide-y divide-line num">
            {rows.map(r => <tr key={r.symbol + r.name}><td className="py-2"><Link href={universe === "adr" ? `/monitor/adr/${r.symbol}` : `/ticker/${r.symbol}`} className="font-semibold hover:text-primary">{r.name}</Link></td>
              <td className="py-2 text-muted">{r.detail}</td><td className="py-2 text-right">{universe === "fundamental" ? r.value?.toFixed(0) : pct(r.value)}</td><td className="py-2 pl-3"><SourceBadge source={r.source} /></td></tr>)}
            {rows.length === 0 && <tr><td className="py-4 text-center text-muted">No names match.</td></tr>}
          </tbody></table>
        )}
      </Card>
      <Card className="h-fit p-5">
        <h2 className="font-semibold">Saved screens</h2>
        <p className="text-xs text-muted">{user.plan === "pro" ? "Unlimited" : "Up to 5"} · re-run any time</p>
        <ul className="mt-3 divide-y divide-line text-sm">
          {(saved ?? []).map(s => <li key={s.id} className="flex items-center justify-between py-2"><button onClick={() => runSaved(s)} className="text-left hover:text-primary">{s.name}<div className="text-xs capitalize text-muted">{s.universe}{s.alert_on_new ? " · alerts on" : ""}</div></button>
            <button onClick={() => del(s)} className="text-xs text-muted hover:text-down">Delete</button></li>)}
          {saved?.length === 0 && <li className="py-2 text-muted">None yet.</li>}
        </ul>
      </Card>
    </section>
  );
}
