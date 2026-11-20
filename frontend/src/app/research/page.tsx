"use client";
import Link from "next/link";
import { useState } from "react";
import type { ArticleCard } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { Card, PageHeader, Pill, Skeleton } from "@/components/ui";

const TABS = ["All", "ADR", "ETF", "Fundamental", "Methodology"];

export default function Research() {
  const [tab, setTab] = useState("All");
  const { data } = useApi<ArticleCard[]>(`/api/research/articles?category=${tab}`, undefined, [tab]);
  return (
    <div className="mx-auto max-w-5xl px-4 py-12">
      <PageHeader title="Research" intro="Article-first research. Every piece links its tickers, its data and its methodology." />
      <div className="mb-6 flex flex-wrap gap-2">
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
