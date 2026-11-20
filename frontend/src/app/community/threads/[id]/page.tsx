"use client";
import Link from "next/link";
import { use, useState } from "react";
import ReactMarkdown from "react-markdown";
import { api, type ThreadRow } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { ago } from "@/lib/format";
import { useAuth } from "@/components/AuthProvider";
import { Button, Card, ErrorNote, Skeleton } from "@/components/ui";

type Full = ThreadRow & { body: string; posts: { id: number; author: string; body: string; created_at: string }[] };

export default function ThreadPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data: t, reload, setData } = useApi<Full>(`/api/community/threads/${id}`);
  const { user } = useAuth();
  const [body, setBody] = useState("");
  const [err, setErr] = useState<Error | null>(null);
  const reply = async () => { try { await api(`/api/community/threads/${id}/posts`, { method: "POST", json: { body } }); setBody(""); reload(); } catch (e) { setErr(e as Error); } };
  const vote = async (v: number) => { try { const r = await api<{ score: number }>(`/api/community/threads/${id}/vote`, { method: "POST", json: { value: v } }); if (t) setData({ ...t, score: r.score }); } catch (e) { setErr(e as Error); } };
  if (!t) return <div className="mx-auto max-w-3xl px-4 py-12"><Skeleton /></div>;
  return (
    <div className="mx-auto max-w-3xl px-4 py-12">
      <Link href="/community" className="text-sm text-muted hover:text-fg">← {t.community}</Link>
      <div className="mt-4 flex gap-4">
        <div className="flex flex-col items-center text-muted"><button onClick={() => vote(1)} className="hover:text-up">▲</button><span className="num">{t.score}</span><button onClick={() => vote(-1)} className="hover:text-down">▼</button></div>
        <div className="flex-1"><h1 className="text-2xl font-semibold">{t.title}</h1>
          <p className="mt-1 text-sm text-muted">@{t.author} · {ago(t.created_at)} {t.tickers.map(x => <Link key={x} href={`/ticker/${x}`} className="ml-2 hover:text-primary">${x}</Link>)}</p>
          <div className="prose-irai mt-4"><ReactMarkdown>{t.body}</ReactMarkdown></div></div>
      </div>
      <h2 className="mt-10 font-semibold">{t.posts.length} replies</h2>
      <div className="mt-3 space-y-3">{t.posts.map(p => <Card key={p.id} className="p-4"><div className="text-xs text-muted">@{p.author} · {ago(p.created_at)}</div><div className="prose-irai"><ReactMarkdown>{p.body}</ReactMarkdown></div></Card>)}</div>
      {user ? <div className="mt-6 space-y-2"><textarea rows={3} value={body} onChange={e => setBody(e.target.value)} className="w-full rounded-lg border border-line bg-bg p-3 text-sm" placeholder="Reply…" /><ErrorNote error={err} /><Button onClick={reply} disabled={!body.trim()}>Reply</Button></div>
        : <p className="mt-6 text-sm text-muted"><Link href="/login" className="text-primary">Sign in</Link> to reply.</p>}
    </div>
  );
}
