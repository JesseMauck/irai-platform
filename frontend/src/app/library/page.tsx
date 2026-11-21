"use client";
import Link from "next/link";
import { useApi } from "@/lib/hooks";
import { ago, num, pct, tone } from "@/lib/format";
import { openIrai } from "@/lib/assistant";
import { useAuth } from "@/components/AuthProvider";
import { Button, Card, Skeleton } from "@/components/ui";

interface Lib {
  valuations: { id: string; ticker: string; title: string; value_per_share: number | null; price: number | null; pinned: boolean; created_at: string | null }[];
  analyst_reports: { id: string; symbol: string; headline: string | null; created_at: string | null }[];
  pins: { kind: string; ref: string }[]; screens: { id: number; name: string }[];
  backtests: { id: number; symbol: string; strategy: string; kind: string; return: number | null; created_at: string | null }[];
  chats: { id: number; title: string; updated_at: string }[]; listings: { id: number; title: string; copies: number }[];
}

function Section({ title, href, children, empty }: { title: string; href?: string; children: React.ReactNode; empty: boolean }) {
  return <Card className="p-5"><div className="flex items-center justify-between"><h2 className="font-semibold">{title}</h2>{href && <Link href={href} className="text-xs text-primary">Open →</Link>}</div>
    {empty ? <p className="mt-2 text-sm text-muted">Nothing saved yet.</p> : <div className="mt-2">{children}</div>}</Card>;
}

export default function Library() {
  const { user, ready } = useAuth();
  const { data } = useApi<Lib>(user ? "/api/me/library" : null);
  if (!ready) return null;
  if (!user) return <div className="mx-auto max-w-md px-4 py-20 text-center"><p>Sign in to see your library.</p><Button href="/login?next=/library" className="mt-4">Sign in</Button></div>;
  const pinHref = (p: { kind: string; ref: string }) => p.kind === "theme" ? `/research/themes/${p.ref}` : p.kind === "ticker" ? `/ticker/${p.ref}` : "#";
  return (
    <div className="mx-auto max-w-7xl px-4 py-10">
      <h1 className="text-3xl">Library</h1>
      <p className="mt-1 text-sm text-muted">Everything you&apos;ve saved: valuations, Analyst Bot notes, pins, screens, backtests, IRAI chats and published strategies.</p>
      {!data ? <div className="mt-6"><Skeleton rows={10} /></div> : (
        <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          <Section title="ValueBot reports" href="/valuebot/reports" empty={!data.valuations.length}>
            <ul className="divide-y divide-line text-sm">{data.valuations.slice(0, 10).map(v => <li key={v.id} className="flex justify-between py-1.5"><Link href={`/valuebot/${v.id}`} className="truncate hover:text-primary">{v.pinned && "📌 "}{v.title}</Link>
              <span className="num text-xs">{num(v.value_per_share)} <span className={tone(v.value_per_share && v.price ? v.value_per_share / v.price - 1 : null)}>{v.value_per_share && v.price ? pct(v.value_per_share / v.price - 1, 0) : ""}</span></span></li>)}</ul></Section>
          <Section title="Analyst Bot notes" empty={!data.analyst_reports.length}>
            <ul className="divide-y divide-line text-sm">{data.analyst_reports.slice(0, 10).map(r => <li key={r.id} className="py-1.5"><Link href={`/ticker/${r.symbol}#analyst`} className="hover:text-primary"><b>{r.symbol}</b> <span className="text-muted">{r.headline}</span></Link></li>)}</ul></Section>
          <Section title="IRAI chats" empty={!data.chats.length}>
            <ul className="divide-y divide-line text-sm">{data.chats.slice(0, 10).map(c => <li key={c.id} className="flex justify-between gap-2 py-1.5"><button onClick={() => openIrai({ chatId: c.id })} className="truncate text-left hover:text-primary">{c.title}</button><span className="shrink-0 text-[11px] text-muted">{ago(c.updated_at)}</span></li>)}</ul></Section>
          <Section title="Pins" href="/research" empty={!data.pins.length}>
            <div className="flex flex-wrap gap-1.5">{data.pins.map(p => <Link key={p.kind + p.ref} href={pinHref(p)} className="rounded-full border border-line px-2.5 py-0.5 text-sm hover:border-primary">{p.ref}</Link>)}</div></Section>
          <Section title="Saved screens" href="/screeners" empty={!data.screens.length}>
            <ul className="text-sm">{data.screens.map(s => <li key={s.id} className="py-1"><Link href={`/screeners?saved=${s.id}`} className="hover:text-primary">{s.name}</Link></li>)}</ul></Section>
          <Section title="Backtests and simulations" href="/lab" empty={!data.backtests.length}>
            <ul className="divide-y divide-line text-sm">{data.backtests.slice(0, 10).map(b => <li key={b.id} className="flex justify-between py-1.5"><span>{b.kind === "montecarlo" ? "Monte Carlo" : b.strategy} · {b.symbol}</span><span className={`num text-xs ${tone(b.return)}`}>{pct(b.return, 1)}</span></li>)}</ul></Section>
          <Section title="My published strategies" href="/strategies" empty={!data.listings.length}>
            <ul className="text-sm">{data.listings.map(x => <li key={x.id} className="flex justify-between py-1"><Link href={`/strategies/${x.id}`} className="hover:text-primary">{x.title}</Link><span className="text-xs text-muted">{x.copies} copies</span></li>)}</ul></Section>
        </div>)}
    </div>
  );
}
