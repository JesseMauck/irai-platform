"use client";
import Link from "next/link";
import { use } from "react";
import ReactMarkdown from "react-markdown";
import type { Article } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { Button, Card, ErrorNote, Pill, Skeleton } from "@/components/ui";

export default function ArticlePage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params);
  const { data: a, error } = useApi<Article>(`/api/research/articles/${slug}`);
  return (
    <article className="mx-auto max-w-3xl px-4 py-12">
      <Link href="/research" className="text-sm text-muted hover:text-fg">← Research</Link>
      <ErrorNote error={error} />
      {!a ? <Skeleton rows={10} /> : <>
        <div className="mt-6 flex flex-wrap items-center gap-2 text-xs"><Pill tone="primary">{a.category}</Pill>
          {a.tickers.map(t => <Link key={t} href={`/ticker/${t}`} className="text-muted hover:text-primary">${t}</Link>)}</div>
        <h1 className="mt-3 text-4xl font-semibold tracking-tight">{a.title}</h1>
        <p className="mt-3 text-lg text-muted">{a.summary}</p>
        <p className="mt-4 text-sm text-muted">{a.author} · {new Date(a.published_at).toLocaleDateString()} · {a.read_minutes} min read
          {a.free_remaining != null && !a.locked && ` · ${a.free_remaining} free article(s) left this month`}</p>
        <div className="prose-irai mt-8"><ReactMarkdown>{a.body_md}</ReactMarkdown></div>
        {a.locked && (
          <Card className="mt-8 p-6 text-center">
            <p className="font-medium">{a.lock_reason}</p>
            <p className="mt-1 text-sm text-muted">Essential members read everything, every month.</p>
            <div className="mt-4 flex justify-center gap-2"><Button href="/pricing">See plans</Button><Button href="/login" variant="outline">Sign in</Button></div>
          </Card>
        )}
        <p className="mt-12 border-t border-line pt-4 text-xs text-muted">Research and education only — not investment advice.</p>
      </>}
    </article>
  );
}
