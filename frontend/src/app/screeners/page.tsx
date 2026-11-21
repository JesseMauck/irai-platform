"use client";
import Link from "next/link";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { compact, num, pct, tone } from "@/lib/format";
import { useAuth } from "@/components/AuthProvider";
import { Sparkline } from "@/components/Chart";
import { MonitorScreens } from "@/components/MonitorScreens";
import { Button, Card, ErrorNote, Skeleton, SourceBadge } from "@/components/ui";

type Filter = [string, string, number | string | string[] | null];
interface PresetCard { id: string; title: string; description: string; kind: string | null; sort: string; desc: boolean; filters: Filter[]; matches: number; total_matches: number; avg_change: number | null; top: string[] }
interface Field { key: string; label: string; group: string; unit: string }
interface Catalog { building?: boolean; spotlight: PresetCard[]; groups: { id: string; label: string; presets: PresetCard[] }[]; as_of: string | null; source: string | null; universe: number;
  breadth: { advancers: number; decliners: number; median_change: number | null }; fields: Field[]; note: string }
type Row = Record<string, string | number | boolean | null | number[]>;
interface Result { matches: number; rows: Row[]; columns: string[]; avg_change: number | null; advancers: number; decliners: number; locked?: boolean; hidden?: number; source: string | null; as_of: string | null;
  preset?: { id: string; title: string; description: string } }
interface Saved { id: number; name: string; universe: string; filters: { filters: Filter[]; sort: string; desc: boolean; kind: string | null } }

const SIGNED = new Set(["change_pct", "ret_1w", "ret_1m", "ret_3m", "ret_6m", "ret_ytd", "ret_1y", "rs_3m", "gap_pct", "vs_sma20", "vs_sma50", "vs_sma200", "from_high_52w", "from_low_52w", "max_dd_1y", "revenue_growth", "earnings_growth"]);

function fmt(unit: string | undefined, v: unknown, key = "") {
  if (v == null || v === "") return "—";
  if (key === "leverage" && typeof v === "number") return `${v > 0 ? "+" : "−"}${Math.abs(v)}x`;
  if (typeof v === "boolean") return v ? "✓" : "—";
  if (typeof v !== "number") return String(v);
  switch (unit) {
    case "pct": return pct(v, Math.abs(v) < 0.1 ? 2 : 1, SIGNED.has(key));
    case "x": return `${num(v, v < 10 ? 2 : 1)}x`;
    case "usd": return `$${compact(v)}`;
    case "int": return compact(v);
    default: return num(v, Math.abs(v) >= 100 ? 0 : 2);
  }
}

export default function ScreenerPage() {
  return <Suspense fallback={<div className="mx-auto max-w-7xl px-4 py-10"><Skeleton rows={10} /></div>}><Screener /></Suspense>;
}

function Screener() {
  const { user } = useAuth();
  const sp = useSearchParams();
  const router = useRouter();
  const { data: cat, error } = useApi<Catalog>("/api/screener", 60_000);
  const [tab, setTab] = useState(sp.get("tab") ?? "market_mover");
  const [pid, setPid] = useState<string | null>(sp.get("preset") ?? "top_gainers");
  const [custom, setCustom] = useState<{ filters: Filter[]; sort: string; desc: boolean; kind: string | null } | null>(null);
  const [res, setRes] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [sel, setSel] = useState<string[]>([]);
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDesc, setSortDesc] = useState(true);
  const member = !!user && user.plan !== "free";
  const fields = useMemo(() => Object.fromEntries((cat?.fields ?? []).map(f => [f.key, f])), [cat]);
  const { data: saved, reload: reloadSaved } = useApi<Saved[]>(user ? "/api/me/screens" : null);
  const mySaved = (saved ?? []).filter(s => s.universe === "market");

  useEffect(() => {
    if (custom) return;
    if (!pid) return;
    setBusy(true); setErr(null); setSel([]); setSortKey(null);
    api<Result>(`/api/screener/presets/${pid}`).then(setRes).catch(e => setErr((e as Error).message)).finally(() => setBusy(false));
  }, [pid, custom, user?.id]);

  const runCustom = async (c = custom) => {
    if (!c) return;
    setBusy(true); setErr(null); setSel([]); setSortKey(null);
    try { setRes(await api<Result>("/api/screener/run", { method: "POST", json: { ...c, limit: 200 } })); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  const pick = (p: PresetCard) => { setCustom(null); setPid(p.id); router.replace(`/screeners?tab=${tab}&preset=${p.id}`, { scroll: false }); document.getElementById("results")?.scrollIntoView({ behavior: "smooth" }); };
  const rows = useMemo(() => {
    if (!res) return [];
    if (!sortKey) return res.rows;
    return [...res.rows].sort((a, b) => { const x = a[sortKey] as number | null, y = b[sortKey] as number | null; if (x == null) return 1; if (y == null) return -1; return sortDesc ? y - x : x - y; });
  }, [res, sortKey, sortDesc]);
  const title = custom ? "Custom screen" : res?.preset?.title;

  return (
    <div className="mx-auto max-w-7xl px-4 py-10">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><div className="text-xs uppercase tracking-wide text-primary">Research</div><h1 className="text-3xl">Screener</h1>
          <p className="mt-1 max-w-3xl text-sm text-muted">{cat?.universe ?? "400+"} liquid US stocks and ETFs, scored on the metrics traders filter on: momentum, relative strength, trend, RSI, ATR, volatility, relative volume, liquidity, valuation, yield and cost. Start from a preset or build your own.</p></div>
        {cat && <div className="text-right text-xs text-muted">
          <div><span className="text-up">{cat.breadth.advancers} up</span> · <span className="text-down">{cat.breadth.decliners} down</span> · median <span className={tone(cat.breadth.median_change)}>{pct(cat.breadth.median_change, 2)}</span></div>
          <div className="mt-0.5">{cat.as_of ? `Updated ${new Date(cat.as_of).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}` : ""} <SourceBadge source={cat.source ?? undefined} /></div></div>}
      </div>
      <ErrorNote error={error} />
      {cat?.building && <Card className="mt-4 p-4 text-sm text-muted">The screener is loading today&apos;s data for 400+ stocks and ETFs. This takes a few minutes the first time; the page refreshes on its own.</Card>}

      <h2 className="mt-7 text-sm font-semibold uppercase tracking-wide text-muted">Daily Spotlight</h2>
      {!cat ? <div className="mt-2"><Skeleton rows={3} /></div> : (
        <div className="mt-2 flex snap-x gap-3 overflow-x-auto pb-2">{cat.spotlight.map(p => (
          <button key={p.id} onClick={() => pick(p)} className={`w-60 shrink-0 snap-start rounded-xl border bg-card p-4 text-left transition hover:border-primary ${!custom && pid === p.id ? "border-primary" : "border-line"}`}>
            <div className="font-semibold">{p.title}</div><p className="mt-1 line-clamp-2 h-8 text-[11px] leading-4 text-muted">{p.description}</p>
            <div className="mt-3 flex items-end justify-between"><div><div className="text-[10px] text-muted">Matches</div><div className="stat text-lg">{p.matches}</div></div>
              <div className="text-right"><div className="text-[10px] text-muted">Avg today</div><div className={`stat text-lg ${tone(p.avg_change)}`}>{pct(p.avg_change, 2)}</div></div></div>
            <div className="mt-2 truncate text-[11px] text-muted">{p.top.join(" · ")}</div></button>))}</div>)}

      <div className="mt-6 flex flex-wrap gap-1 border-b border-line">
        {[["saved", "My saved"], ...(cat?.groups ?? []).map(g => [g.id, g.label]), ["monitors", "Monitors"]].map(([id, l]) => (
          <button key={id} onClick={() => setTab(id)} className={`px-3 py-2 text-sm ${tab === id ? "border-b-2 border-primary text-fg" : "text-muted hover:text-fg"}`}>{l}</button>))}
      </div>
      {tab === "monitors" ? <MonitorScreens /> : tab === "saved" ? (
        <div className="mt-4">{!user ? <Card className="p-5 text-sm">Sign in to save screens and get alerts when new names match. <Button className="ml-2" href="/login?next=/screeners">Sign in</Button></Card>
          : !mySaved.length ? <Card className="p-5 text-sm text-muted">No saved market screens yet. Open any preset, choose “Customize”, adjust the filters and save it.</Card>
            : <div className="grid gap-3 md:grid-cols-3">{mySaved.map(s => <div key={s.id} className="rounded-xl border border-line bg-card p-4">
              <div className="font-semibold">{s.name}</div><div className="mt-1 text-[11px] text-muted">{s.filters.filters.length} filters · sorted by {fields[s.filters.sort]?.label ?? s.filters.sort}</div>
              <div className="mt-3 flex gap-2"><Button onClick={() => { setCustom(s.filters); runCustom(s.filters); document.getElementById("results")?.scrollIntoView({ behavior: "smooth" }); }}>Run</Button>
                <Button variant="ghost" onClick={async () => { await api(`/api/me/screens/${s.id}`, { method: "DELETE" }); reloadSaved(); }}>Delete</Button></div></div>)}</div>}</div>
      ) : (
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{(cat?.groups.find(g => g.id === tab)?.presets ?? []).map(p => (
          <button key={p.id} onClick={() => pick(p)} className={`rounded-xl border bg-card p-4 text-left transition hover:border-primary ${!custom && pid === p.id ? "border-primary" : "border-line"}`}>
            <div className="flex items-start justify-between gap-2"><div className="font-semibold">{p.title}</div><span className={`text-xs num ${tone(p.avg_change)}`}>{pct(p.avg_change, 2)}</span></div>
            <p className="mt-1 text-[11px] leading-4 text-muted">{p.description}</p>
            <div className="mt-2 text-[11px] text-muted">{p.matches} matches{p.top.length ? ` · ${p.top.join(", ")}` : ""}</div></button>))}</div>)}

      {tab !== "monitors" && <div id="results" className="scroll-mt-20">
        <Builder fields={cat?.fields ?? []} member={member} pro={user?.plan === "pro" || !!user?.is_admin} start={custom ?? (pid ? (() => { const p = cat?.groups.flatMap(g => g.presets).find(x => x.id === pid); return p ? { filters: p.filters, sort: p.sort, desc: p.desc, kind: p.kind } : null; })() : null)}
          onRun={c => { setCustom(c); runCustom(c); }} onSaved={reloadSaved} />
        <Card className="mt-3 overflow-hidden p-0">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-3">
            <div><div className="font-semibold">{title ?? "Results"}</div>{res && <div className="text-xs text-muted">{res.matches} matches · <span className="text-up">{res.advancers} up</span> · <span className="text-down">{res.decliners} down</span> · avg <span className={tone(res.avg_change)}>{pct(res.avg_change, 2)}</span> today</div>}</div>
            <div className="flex gap-2">{sel.length >= 2 && <Button href={`/compare?symbols=${sel.slice(0, 8).join(",")}`}>Compare {Math.min(sel.length, 8)}</Button>}
              {sel.length === 1 && <Button href={`/ticker/${sel[0]}#analyst`}>Analyze {sel[0]}</Button>}</div>
          </div>
          {err ? <div className="p-5"><p className="text-sm text-down">{err}</p>{/Essential|Pro/.test(err) && <Button className="mt-2" href={user ? "/pricing" : "/signup?next=/screeners"}>See plans</Button>}</div>
            : busy && !res ? <Skeleton rows={8} /> : res && (
            <div className="overflow-x-auto"><table className="w-full min-w-[900px] text-sm">
              <thead className="text-xs text-muted"><tr><th className="w-8 px-3" />
                <th className="px-3 py-2 text-left font-normal">Name</th>
                {res.columns.map(c => <th key={c} className="px-3 py-2 text-right font-normal"><button onClick={() => { if (sortKey === c) setSortDesc(d => !d); else { setSortKey(c); setSortDesc(true); } }} className="hover:text-fg">{fields[c]?.label ?? c}{sortKey === c ? (sortDesc ? " ↓" : " ↑") : ""}</button></th>)}
                <th className="px-3 py-2 text-right font-normal">3 months</th><th /></tr></thead>
              <tbody className="divide-y divide-line">{rows.map(r => { const s = String(r.symbol); return (
                <tr key={s} className={sel.includes(s) ? "bg-primary/5" : ""}>
                  <td className="px-3"><input type="checkbox" checked={sel.includes(s)} onChange={() => setSel(x => x.includes(s) ? x.filter(y => y !== s) : [...x, s])} aria-label={`Select ${s}`} /></td>
                  <td className="px-3 py-2"><Link href={`/ticker/${s}`} className="font-semibold hover:text-primary">{s}</Link> <span className="rounded bg-accent px-1 text-[10px] uppercase text-muted">{String(r.kind)}</span>
                    {r.leverage != null && <span className="ml-1 rounded bg-down/15 px-1 text-[10px] text-down">{Number(r.leverage) > 0 ? "+" : ""}{String(r.leverage)}x</span>}
                    <div className="max-w-[260px] truncate text-[11px] text-muted">{String(r.name ?? "")}{r.category && r.kind === "etf" ? ` · ${r.category}` : r.sector ? ` · ${r.sector}` : ""}</div></td>
                  {res.columns.map(c => <td key={c} className={`px-3 text-right num ${fields[c]?.unit === "pct" && ["change_pct", "ret_1w", "ret_1m", "ret_3m", "ret_6m", "ret_ytd", "ret_1y", "rs_3m", "gap_pct", "vs_sma20", "vs_sma50", "vs_sma200"].includes(c) ? tone(r[c] as number) : ""}`}>{fmt(fields[c]?.unit, r[c], c)}</td>)}
                  <td className="px-3 text-right">{Array.isArray(r.spark) && <span className="inline-block"><Sparkline values={r.spark as number[]} width={80} height={22} /></span>}</td>
                  <td className="px-3 text-right text-xs"><Link href={`/ticker/${s}#analyst`} className="text-primary">Analyze</Link></td></tr>); })}</tbody></table>
              {!rows.length && <p className="p-6 text-center text-sm text-muted">Nothing matches right now.</p>}
              {res.locked && <div className="border-t border-line p-4 text-center text-sm"><b>{res.hidden} more matches.</b> Essential shows every match and lets you build and save your own screens. <Button className="ml-2" href={user ? "/pricing" : "/signup?next=/screeners"}>See plans</Button></div>}
            </div>)}
        </Card>
        <p className="mt-3 text-[11px] text-muted">{cat?.note} Universe: a curated list of liquid US-listed stocks and ETFs, including inverse and leveraged funds. Leveraged and inverse funds reset daily and can lose value over time even when the index moves the way they target.</p>
      </div>}
    </div>
  );
}

function Builder({ fields, member, pro, start, onRun, onSaved }: { fields: Field[]; member: boolean; pro: boolean; start: { filters: Filter[]; sort: string; desc: boolean; kind: string | null } | null;
  onRun: (c: { filters: Filter[]; sort: string; desc: boolean; kind: string | null }) => void; onSaved: () => void }) {
  const [open, setOpen] = useState(false);
  const [filters, setFilters] = useState<Filter[]>([]);
  const [sort, setSort] = useState("dollar_volume");
  const [desc, setDesc] = useState(true);
  const [kind, setKind] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const numeric = fields.filter(f => f.unit !== "bool");
  const load = () => { if (start) { setFilters(start.filters.filter(f => f[1] === ">=" || f[1] === "<=" || f[1] === "true" || f[1] === "==" || f[1] === "in")); setSort(start.sort); setDesc(start.desc); setKind(start.kind); } setOpen(true); };
  const scale = (f: string) => (fields.find(x => x.key === f)?.unit === "pct" ? 100 : 1);
  const spec = { filters, sort, desc, kind };
  const exportCsv = async () => {
    const r = await fetch("/api/screener/export", { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${localStorage.getItem("irai_token") ?? ""}` }, body: JSON.stringify(spec) });
    if (!r.ok) { setMsg("CSV export is part of Pro"); return; }
    const url = URL.createObjectURL(await r.blob()); const a = document.createElement("a"); a.href = url; a.download = "irai-screen.csv"; a.click();
  };
  if (!open) return <div className="mt-6 flex flex-wrap items-center gap-2"><Button variant="outline" onClick={load}>Customize this screen</Button><Button variant="ghost" onClick={() => { setFilters([]); setSort("dollar_volume"); setKind(null); setOpen(true); }}>Build a new screen</Button>
    {!member && <span className="text-xs text-muted">Custom and saved screens are part of Essential and Pro.</span>}</div>;
  return (
    <Card className="mt-6 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2"><div className="font-semibold">Screen builder</div>
        <div className="flex gap-1 text-xs">{[[null, "Stocks & ETFs"], ["stock", "Stocks"], ["etf", "ETFs"]].map(([k, l]) => <button key={l} onClick={() => setKind(k)} className={`rounded-full border px-3 py-1 ${kind === k ? "border-primary bg-primary/10" : "border-line text-muted"}`}>{l}</button>)}</div></div>
      <div className="mt-3 space-y-2">{filters.map((f, i) => { const isNum = f[1] === ">=" || f[1] === "<="; const u = fields.find(x => x.key === f[0])?.unit; return (
        <div key={i} className="flex flex-wrap items-center gap-2 text-sm">
          <select value={f[0]} onChange={e => setFilters(x => x.map((y, j) => j === i ? [e.target.value, y[1], y[2]] : y))} className="rounded border border-line bg-bg px-2 py-1">
            {Object.entries(Object.groupBy ? Object.groupBy(fields, x => x.group) : { All: fields }).map(([g, fs]) => <optgroup key={g} label={g}>{(fs ?? []).map(x => <option key={x.key} value={x.key}>{x.label}</option>)}</optgroup>)}
            {!fields.some(x => x.key === f[0]) && <option value={f[0]}>{f[0]}</option>}</select>
          {isNum ? <><select value={f[1]} onChange={e => setFilters(x => x.map((y, j) => j === i ? [y[0], e.target.value, y[2]] : y))} className="rounded border border-line bg-bg px-2 py-1"><option value=">=">at least</option><option value="<=">at most</option></select>
            <input type="number" step="any" value={typeof f[2] === "number" ? +(f[2] * scale(f[0])).toFixed(6) : ""} onChange={e => setFilters(x => x.map((y, j) => j === i ? [y[0], y[1], e.target.value === "" ? null : Number(e.target.value) / scale(y[0])] : y))} className="w-28 rounded border border-line bg-bg px-2 py-1" />
            <span className="text-xs text-muted">{u === "pct" ? "%" : u === "x" ? "x" : u === "usd" ? "$" : ""}</span></>
            : <span className="text-xs text-muted">{f[1] === "true" ? "is true" : `${f[1]} ${Array.isArray(f[2]) ? f[2].join(", ") : String(f[2])}`}</span>}
          <button onClick={() => setFilters(x => x.filter((_, j) => j !== i))} className="text-xs text-muted hover:text-down">Remove</button></div>); })}
        <button onClick={() => setFilters(x => [...x, [numeric[0]?.key ?? "change_pct", ">=", 0]])} className="text-sm text-primary">+ Add filter</button></div>
      <div className="mt-3 flex flex-wrap items-center gap-2 text-sm"><span className="text-muted">Sort by</span>
        <select value={sort} onChange={e => setSort(e.target.value)} className="rounded border border-line bg-bg px-2 py-1">{numeric.map(x => <option key={x.key} value={x.key}>{x.label}</option>)}</select>
        <button onClick={() => setDesc(d => !d)} className="rounded border border-line px-2 py-1 text-xs">{desc ? "Highest first" : "Lowest first"}</button>
        <Button onClick={() => (member ? onRun({ filters: filters.filter(f => f[2] !== null || f[1] === "true"), sort, desc, kind }) : setMsg("Custom screens are part of Essential and Pro"))}>Run screen</Button>
        <input value={name} onChange={e => setName(e.target.value)} placeholder="Name to save as" maxLength={80} className="w-44 rounded border border-line bg-bg px-2 py-1" />
        <Button variant="outline" disabled={!name.trim()} onClick={async () => { setMsg(null); try { await api("/api/me/screens", { method: "POST", json: { name: name.trim(), universe: "market", filters: spec, alert_on_new: true } }); setMsg("Saved. We'll alert you when new names match."); setName(""); onSaved(); } catch (e) { setMsg((e as Error).message); } }}>Save</Button>
        <Button variant="ghost" onClick={exportCsv}>CSV{pro ? "" : " (Pro)"}</Button>
        <button onClick={() => setOpen(false)} className="ml-auto text-xs text-muted">Close</button></div>
      {msg && <p className="mt-2 text-xs text-muted">{msg}</p>}
    </Card>
  );
}
