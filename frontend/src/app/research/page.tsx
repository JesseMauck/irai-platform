"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import type { ArticleCard } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useAuth } from "@/components/AuthProvider";
import { PinButton, ThemeEditor, UnifiedSearch, type Theme } from "@/components/Workspace";
import { Button, Card, PageHeader, Pill, Skeleton } from "@/components/ui";

interface PinRow { kind: string; ref: string; label: string }

const TABS = ["All", "ADR", "ETF", "Fundamental", "Methodology"];

export default function Research() {
  const [tab, setTab] = useState("All");
  const { data } = useApi<ArticleCard[]>(`/api/research/articles?category=${tab}`, undefined, [tab]);
  const { user } = useAuth();
  const router = useRouter();
  const { data: themes, reload: reloadThemes } = useApi<Theme[]>("/api/workspace/themes");
  const { data: pins, reload: reloadPins } = useApi<PinRow[]>(user ? "/api/workspace/pins" : null);
  const [creating, setCreating] = useState(false);
  const refresh = () => { reloadThemes(); reloadPins(); };
  return (
    <div className="mx-auto max-w-6xl px-4 py-12">
      <PageHeader title="Research workspace" intro="Search anything, pin what you follow, and work through themes with their key drivers, a PESTEL news radar and market sentiment. Every number links to its source." />
      <div className="mt-6"><UnifiedSearch /></div>

      {user && (
        <section className="mt-8">
          <h2 className="text-lg">Pinned</h2>
          {!pins?.length ? <p className="mt-2 text-sm text-muted">Use ☆ on themes, and on tickers in the terminal, to pin them here.</p> : (
            <div className="mt-3 flex flex-wrap gap-2">{pins.map(p => (
              <Link key={p.kind + p.ref} href={p.kind === "theme" ? `/research/themes/${p.ref}` : p.kind === "ticker" ? `/ticker/${p.ref}` : p.kind === "report" ? `/valuebot/${p.ref}` : "/account"}
                className="rounded-full border border-line bg-card px-3 py-1 text-sm hover:border-primary/50"><span className="mr-1 text-[10px] uppercase text-muted">{p.kind}</span>{p.label}</Link>))}</div>)}
        </section>
      )}

      <section className="mt-10">
        <div className="flex items-center justify-between"><h2 className="text-lg">Themes</h2>
          {user ? <Button variant="outline" onClick={() => setCreating(true)}>+ Custom theme</Button> : <Link href="/login?next=/research" className="text-sm text-primary">Sign in to build your own themes</Link>}</div>
        {creating && <div className="mt-4"><ThemeEditor onSaved={t => { setCreating(false); refresh(); router.push(`/research/themes/${t.slug}`); }} onCancel={() => setCreating(false)} /></div>}
        {!themes ? <Skeleton rows={3} /> : (
          <div className="mt-4 grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            {themes.map(t => (
              <Link key={t.slug} href={`/research/themes/${t.slug}`} className="rounded-xl border border-line bg-card p-4 transition hover:border-primary/50">
                <div className="flex items-start justify-between gap-2"><h3 className="text-base">{t.name}</h3><PinButton kind="theme" refId={t.slug} pinned={t.pinned} onChange={reloadPins} /></div>
                <p className="mt-1 line-clamp-2 text-sm text-muted">{t.description}</p>
                <div className="mt-2 flex flex-wrap gap-1 text-[11px] text-muted">{t.tickers.slice(0, 8).map(x => <span key={x} className="rounded bg-accent px-1.5 py-0.5">{x}</span>)}</div>
                <div className="mt-2 text-[11px] text-muted">{t.drivers.length} key drivers{t.mine ? " · yours" : t.custom ? " · member theme" : ""}</div>
              </Link>))}
          </div>)}
      </section>

      <h2 className="mt-12 text-lg">Research notes</h2>
      <div className="mb-6 mt-3 flex flex-wrap gap-2">
        {TABS.map(t => <button key={t} onClick={() => setTab(t)} className={`rounded-full px-3 py-1 text-sm ${t === tab ? "bg-primary/15 text-primary" : "bg-card text-muted hover:text-fg"}`}>{t}</button>)}
      </div>
      {!data ? <Skeleton rows={6} /> : (
        <div className="grid gap-4">
          {data.map(a => (
            <Card key={a.slug} className="p-6 transition hover:border-primary/40">
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <Pill tone="primary">{a.category}</Pill>
                {a.tickers.map(t => <Link key={t} href={`/ticker/${t}`} className="text-muted hover:text-primary">${t}</Link>)}
                {a.premium && <Pill>Members</Pill>}
              </div>
              <h2 className="mt-3 text-xl font-semibold"><Link href={`/research/${a.slug}`} className="hover:text-primary">{a.title}</Link></h2>
              <p className="mt-2 text-muted">{a.summary}</p>
              <div className="mt-4 flex items-center justify-between text-sm text-muted">
                <span>{a.author} · {new Date(a.published_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })} · {a.read_minutes} min</span>
                <Link href={`/research/${a.slug}`} className="text-fg hover:text-primary">Read →</Link>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
