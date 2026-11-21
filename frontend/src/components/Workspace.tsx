"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useAuth } from "@/components/AuthProvider";
import { Button, Card, ErrorNote } from "@/components/ui";

export interface Theme { slug: string; name: string; description: string; tickers: string[]; keywords: string[]; drivers: { name: string; why: string; symbol?: string }[];
  custom: boolean; mine: boolean; pinned: boolean; notes_md: string | null; public: boolean }
interface SearchRes { tickers: { symbol: string; name: string; exchange: string; type: string }[]; articles: { slug: string; title: string; category: string }[];
  themes: { slug: string; name: string; custom: boolean }[]; analysis: { id: number; title: string; kind: string; ticker: string | null }[] }

export function UnifiedSearch({ autoFocus = false }: { autoFocus?: boolean }) {
  const [q, setQ] = useState(""); const [deb, setDeb] = useState("");
  useEffect(() => { const t = setTimeout(() => setDeb(q.trim()), 250); return () => clearTimeout(t); }, [q]);
  const { data } = useApi<SearchRes>(deb ? `/api/workspace/search?q=${encodeURIComponent(deb)}` : null, undefined, [deb]);
  const has = data && (data.tickers.length + data.articles.length + data.themes.length + data.analysis.length) > 0;
  return (
    <div className="relative">
      <input value={q} onChange={e => setQ(e.target.value)} autoFocus={autoFocus} aria-label="Search research"
        placeholder="Search tickers, companies, themes, research and member analysis…"
        className="w-full rounded-xl border border-line bg-card px-4 py-3 text-base outline-none focus:border-primary" />
      {deb && data && (
        <div className="absolute z-30 mt-2 w-full rounded-xl border border-line bg-card p-3 shadow-xl">
          {!has && <p className="text-sm text-muted">No matches for “{deb}”.</p>}
          {data.tickers.length > 0 && <Group title="Securities">{data.tickers.map(t => <Link key={t.symbol} href={`/ticker/${encodeURIComponent(t.symbol)}`} className="flex justify-between rounded px-2 py-1 hover:bg-accent"><span><b>{t.symbol}</b> <span className="text-muted">{t.name}</span></span><span className="text-xs text-muted">{t.type} · {t.exchange}</span></Link>)}</Group>}
          {data.themes.length > 0 && <Group title="Themes">{data.themes.map(t => <Link key={t.slug} href={`/research/themes/${t.slug}`} className="block rounded px-2 py-1 hover:bg-accent">{t.name}{t.custom && <span className="ml-2 text-xs text-muted">custom</span>}</Link>)}</Group>}
          {data.articles.length > 0 && <Group title="Research">{data.articles.map(a => <Link key={a.slug} href={`/research/${a.slug}`} className="block rounded px-2 py-1 hover:bg-accent">{a.title} <span className="text-xs text-muted">{a.category}</span></Link>)}</Group>}
          {data.analysis.length > 0 && <Group title="Member analysis">{data.analysis.map(a => <Link key={a.id} href={`/community/threads/${a.id}`} className="block rounded px-2 py-1 hover:bg-accent">{a.title} {a.ticker && <span className="text-xs text-muted">${a.ticker}</span>}</Link>)}</Group>}
          <Link href={`/compare?symbols=${encodeURIComponent(deb)}`} className="mt-2 block text-xs text-primary">Compare “{deb}” with others →</Link>
        </div>
      )}
    </div>
  );
}
const Group = ({ title, children }: { title: string; children: React.ReactNode }) => <div className="mb-2"><div className="mb-1 text-[11px] uppercase tracking-wide text-muted">{title}</div>{children}</div>;

export function PinButton({ kind, refId, pinned, onChange }: { kind: string; refId: string; pinned: boolean; onChange?: () => void }) {
  const { user } = useAuth();
  const [on, setOn] = useState(pinned);
  useEffect(() => setOn(pinned), [pinned]);
  if (!user) return null;
  const toggle = async (e: React.MouseEvent) => {
    e.preventDefault(); e.stopPropagation();
    try {
      if (on) await api(`/api/workspace/pins/${kind}/${encodeURIComponent(refId)}`, { method: "DELETE" });
      else await api("/api/workspace/pins", { method: "POST", json: { kind, ref: refId } });
      setOn(!on); onChange?.();
    } catch { /* ignore */ }
  };
  return <button onClick={toggle} aria-label={on ? "Unpin" : "Pin"} title={on ? "Unpin" : "Pin to your workspace"} className={on ? "text-primary" : "text-muted hover:text-fg"}>{on ? "★" : "☆"}</button>;
}

export function ThemeEditor({ initial, onSaved, onCancel }: { initial?: Theme; onSaved: (t: Theme) => void; onCancel: () => void }) {
  const [f, setF] = useState({ name: initial?.name ?? "", description: initial?.description ?? "", tickers: initial?.tickers.join(", ") ?? "",
    keywords: initial?.keywords.join(", ") ?? "", drivers: (initial?.drivers ?? []).map(d => `${d.name} | ${d.why}${d.symbol ? ` | ${d.symbol}` : ""}`).join("\n"),
    notes_md: initial?.notes_md ?? "", public: initial?.public ?? false });
  const [err, setErr] = useState<Error | null>(null);
  const save = async () => {
    setErr(null);
    const body = { name: f.name, description: f.description, tickers: f.tickers.split(/[\s,]+/).filter(Boolean), keywords: f.keywords.split(",").map(s => s.trim()).filter(Boolean),
      drivers: f.drivers.split("\n").map(l => l.split("|").map(s => s.trim())).filter(p => p[0]).map(([name, why = "", symbol]) => ({ name, why, ...(symbol ? { symbol } : {}) })),
      notes_md: f.notes_md, public: f.public };
    try { onSaved(await api<Theme>(initial ? `/api/workspace/themes/${initial.slug}` : "/api/workspace/themes", { method: initial ? "PUT" : "POST", json: body })); } catch (e) { setErr(e as Error); }
  };
  const field = "w-full rounded border border-line bg-bg px-2 py-1.5 text-sm";
  return (
    <Card className="space-y-3 p-5">
      <h3 className="font-semibold">{initial ? "Edit theme" : "New custom research theme"}</h3>
      <input value={f.name} onChange={e => setF({ ...f, name: e.target.value })} placeholder="Theme name, e.g. Humanoid robotics" className={field} />
      <textarea value={f.description} onChange={e => setF({ ...f, description: e.target.value })} rows={2} placeholder="What the theme is about" className={field} />
      <input value={f.tickers} onChange={e => setF({ ...f, tickers: e.target.value })} placeholder="Tickers: TSLA, NVDA, ISRG" className={`${field} uppercase`} />
      <input value={f.keywords} onChange={e => setF({ ...f, keywords: e.target.value })} placeholder="News keywords for the PESTEL radar: humanoid robot, robotics" className={field} />
      <label className="block text-xs text-muted">Key drivers, one per line: <span className="font-mono">name | why it matters | optional ticker to track</span>
        <textarea value={f.drivers} onChange={e => setF({ ...f, drivers: e.target.value })} rows={4} placeholder={"Labor costs | Higher wages make automation pay back faster\nAI model progress | Better models widen what robots can do | NVDA"} className={`${field} mt-1 font-mono`} /></label>
      <textarea value={f.notes_md} onChange={e => setF({ ...f, notes_md: e.target.value })} rows={6} placeholder="Your research notes (Markdown). Private unless you share the theme." className={`${field} font-mono`} />
      <label className="flex items-center gap-2 text-sm text-muted"><input type="checkbox" checked={f.public} onChange={e => setF({ ...f, public: e.target.checked })} /> Visible to other members (notes stay private)</label>
      <ErrorNote error={err} />
      <div className="flex gap-2"><Button onClick={save} disabled={f.name.length < 2}>Save theme</Button><Button variant="ghost" onClick={onCancel}>Cancel</Button></div>
    </Card>
  );
}
