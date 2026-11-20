"use client";
import Link from "next/link";
import { useState } from "react";
import { api, type ThreadRow } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { ago } from "@/lib/format";
import { useAuth } from "@/components/AuthProvider";
import { HomeCommunity } from "@/components/HomeLive";
import { Button, Card, ErrorNote, PageHeader } from "@/components/ui";

interface Comm { slug: string; name: string; description: string; threads: number; pro_only: boolean }

export default function CommunityPage() {
  const { data: comms } = useApi<Comm[]>("/api/community/communities");
  const [filter, setFilter] = useState<string | null>(null);
  const { data: threads, reload } = useApi<ThreadRow[]>(`/api/community/threads${filter ? `?community=${filter}` : ""}`, undefined, [filter]);
  const { user } = useAuth();
  const [form, setForm] = useState({ community: "adr-arbitrage", title: "", body: "", tickers: "" });
  const [err, setErr] = useState<Error | null>(null);
  const [open, setOpen] = useState(false);

  const post = async () => {
    setErr(null);
    try {
      await api("/api/community/threads", { method: "POST", json: { ...form, tickers: form.tickers.split(/[,\s]+/).filter(Boolean) } });
      setOpen(false); setForm({ ...form, title: "", body: "", tickers: "" }); reload();
    } catch (e) { setErr(e as Error); }
  };

  return (
    <div className="mx-auto max-w-7xl px-4 py-12">
      <PageHeader title="Community" intro="Research discussion. Trade posts record the market price at the time of posting.">
        <div className="flex gap-2"><Button href="/trades" variant="outline">Trade feed</Button><Button href="/leaderboards" variant="outline">Leaderboards</Button>
          {user ? <Button onClick={() => setOpen(o => !o)}>New thread</Button> : <Button href="/login">Sign in to post</Button>}</div>
      </PageHeader>
      {open && (
        <Card className="mb-6 space-y-3 p-5">
          <select value={form.community} onChange={e => setForm({ ...form, community: e.target.value })} className="rounded-lg border border-line bg-bg px-3 py-2 text-sm">
            {(comms ?? []).map(c => <option key={c.slug} value={c.slug}>{c.name}{c.pro_only ? " (Pro)" : ""}</option>)}
          </select>
          <input placeholder="Title" value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} className="w-full rounded-lg border border-line bg-bg px-3 py-2" />
          <textarea placeholder="What's your read? Link the data." rows={4} value={form.body} onChange={e => setForm({ ...form, body: e.target.value })} className="w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm" />
          <input placeholder="Tickers (comma-separated)" value={form.tickers} onChange={e => setForm({ ...form, tickers: e.target.value })} className="w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm" />
          <ErrorNote error={err} /><Button onClick={post}>Post</Button>
        </Card>
      )}
      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <div className="flex items-center justify-between border-b border-line p-4"><h2 className="font-semibold">{filter ? comms?.find(c => c.slug === filter)?.name : "Trending threads"}</h2>
            {filter && <button onClick={() => setFilter(null)} className="text-xs text-muted hover:text-fg">Clear filter</button>}</div>
          <ul className="divide-y divide-line">
            {(threads ?? []).map(t => (
              <li key={t.id} className="flex items-start gap-4 p-4">
                <div className="w-10 text-center text-sm text-muted num">▲<div>{t.score}</div></div>
                <div className="flex-1"><Link href={`/community/threads/${t.id}`} className="font-medium hover:text-primary">{t.title}</Link>
                  <div className="mt-1 text-xs text-muted">{t.community} · @{t.author} · {t.replies} replies · {ago(t.last_activity_at)}
                    {t.tickers.map(x => <Link key={x} href={`/ticker/${x}`} className="ml-2 hover:text-primary">${x}</Link>)}</div></div>
              </li>
            ))}
            {threads?.length === 0 && <li className="p-6 text-center text-sm text-muted">No threads yet.</li>}
          </ul>
        </Card>
        <div className="space-y-3">
          {(comms ?? []).map(c => (
            <button key={c.slug} onClick={() => setFilter(c.slug)} className="block w-full rounded-xl border border-line bg-card p-4 text-left hover:border-primary/40">
              <div className="flex justify-between font-medium">{c.name}<span className="text-xs text-muted">{c.threads} threads</span></div>
              <p className="mt-1 text-sm text-muted">{c.description}</p>
            </button>
          ))}
          <Card className="p-4 text-sm">
            <h3 className="font-semibold">Community rules</h3>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-muted">
              <li>Disclose positions; no undisclosed promotion.</li><li>No pump-and-dump or coordinated campaigns.</li>
              <li>Trade posts can be closed, never edited.</li><li>Moderation actions are logged and can be appealed.</li>
            </ul>
            <Link href="/legal/community-guidelines" className="mt-2 inline-block text-primary">Full guidelines →</Link>
          </Card>
        </div>
      </div>
      <div className="mt-10"><HomeCommunity /></div>
    </div>
  );
}
