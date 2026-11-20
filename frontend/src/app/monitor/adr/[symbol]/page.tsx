"use client";
import Link from "next/link";
import { use } from "react";
import type { AdrRow } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { num, pct, signed } from "@/lib/format";
import { AdrChart } from "@/components/AdrChart";
import { Card, DataNote, ErrorNote, PageHeader, Skeleton, SourceBadge } from "@/components/ui";

export default function AdrPair({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol } = use(params);
  const { data: r, error } = useApi<AdrRow>(`/api/monitors/adr/${symbol}`, 60_000);
  return (
    <div className="mx-auto max-w-6xl px-4 py-12">
      <Link href="/monitor/adr" className="text-sm text-muted hover:text-fg">← ADR Monitor</Link>
      <ErrorNote error={error} />
      {!r ? <Skeleton rows={10} /> : <>
        <PageHeader title={`${r.adr_symbol} vs ${r.local_symbol}`} intro={`${r.name} · ${r.country} · 1 ADR = ${r.ratio} local share(s)`}><SourceBadge source={r.source} /></PageHeader>
        <div className="grid gap-4 md:grid-cols-4">
          {[["Premium", pct(r.premium)], ["Structural basis", pct(r.basis)], ["Z-score", signed(r.z)], ["Half-life", r.half_life_days ? `${r.half_life_days.toFixed(1)} days` : "—"]].map(([k, v]) => (
            <Card key={k} className="p-4"><div className="text-xs text-muted">{k}</div><div className="mt-1 text-2xl font-semibold num">{v}</div></Card>
          ))}
        </div>
        <Card className="mt-4 p-4"><AdrChart row={r} height={300} /></Card>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <Card className="p-5">
            <h2 className="font-semibold">Fair value</h2>
            <dl className="mt-3 grid grid-cols-2 gap-y-2 text-sm num">
              <dt className="text-muted">ADR price</dt><dd><Link href={`/ticker/${r.adr_symbol}`} className="hover:text-primary">{num(r.adr_price)} USD</Link></dd>
              <dt className="text-muted">Local price</dt><dd><Link href={`/ticker/${r.local_symbol}`} className="hover:text-primary">{num(r.local_price)} {r.local_currency}</Link></dd>
              <dt className="text-muted">FX (USD per {r.local_currency})</dt><dd>{num(r.fx, 5)}</dd>
              <dt className="text-muted">Implied ADR value</dt><dd>{num(r.implied_usd)} USD</dd>
              <dt className="text-muted">Confidence</dt><dd>{r.confidence != null ? `${Math.round(r.confidence)}%` : "—"}</dd>
              <dt className="text-muted">History used</dt><dd>{r.history_days} days</dd>
            </dl>
          </Card>
          <Card className="p-5">
            <h2 className="font-semibold">{r.tradable ? "No rejections" : "Why this may not be tradable"}</h2>
            <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-muted">{r.reasons.map(x => <li key={x}>{x}</li>)}</ul>
          </Card>
        </div>
        <DataNote />
      </>}
    </div>
  );
}
