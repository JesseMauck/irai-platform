"use client";
import Link from "next/link";
import type { AdrRow, Gated, ThreadRow, TickerPage, Trade } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { ago, num, ord, pct } from "@/lib/format";
import { AdrChart } from "./AdrChart";
import { AdrTable, GradeChip } from "./Monitors";
import { Card, Skeleton, SourceBadge } from "./ui";

export function HomeAdrPreview() {
  const { data } = useApi<Gated<AdrRow>>("/api/monitors/adr", 60_000);
  const top = data?.rows[0];
  const { data: pair } = useApi<AdrRow>(top ? `/api/monitors/adr/${top.adr_symbol}` : null);
  return (
    <div className="grid gap-4 lg:grid-cols-5">
      <Card className="lg:col-span-3">{data ? <AdrTable rows={data.rows.slice(0, 5)} compactView /> : <Skeleton />}</Card>
      <Card className="p-4 lg:col-span-2">
        {pair ? <>
          <div className="mb-2 flex items-center justify-between">
            <h3 className="font-semibold">{pair.adr_symbol} vs {pair.local_symbol} — premium to local</h3><SourceBadge source={pair.source} />
          </div>
          <AdrChart row={pair} height={240} />
          <p className="mt-2 text-xs text-muted">Premium (amber) vs structural basis (dashed) with a ±2σ band.</p>
        </> : <Skeleton rows={6} />}
      </Card>
    </div>
  );
}

export function HomeGradeCard({ symbol = "NVDA" }: { symbol?: string }) {
  const { data } = useApi<TickerPage>(`/api/market/ticker/${symbol}`);
  const g = data?.grade;
  if (!g) return <Card className="p-6"><Skeleton rows={6} /></Card>;
  const x = (v: number | null | undefined) => (v ? `${v.toFixed(1)}x` : "—");
  const rows: [string, React.ReactNode][] = [
    ["Peer group", `${g.peer_group} (${g.peer_count} names)`],
    ["Multiple", `${x(g.multiple)} vs ${x(g.peer_median_multiple)} peer median`],
    ["Quality composite", `${ord(g.quality_percentile)} percentile`],
    ["Residual", g.residual_sigma != null ? `${g.residual_sigma > 0 ? "+" : ""}${g.residual_sigma.toFixed(1)}σ ${g.residual_sigma < 0 ? "below" : "above"} the regression line` : "—"],
    ["Coverage confidence", g.coverage],
  ];
  const cheap = (g.rv_percentile ?? 0) >= 50;
  return (
    <Card className="p-6">
      <div className="flex items-start justify-between">
        <h3 className="text-sm text-muted">Relative Value — <Link href={`/ticker/${g.symbol}`} className="font-semibold text-fg hover:text-primary">{g.symbol}</Link></h3>
        <SourceBadge source={g.source} />
      </div>
      <div className="mt-3 flex items-end gap-3"><div className="text-4xl font-semibold num">{ord(g.rv_percentile)} percentile</div><GradeChip grade={g.grade} /></div>
      <dl className="mt-5 divide-y divide-line text-sm">
        {rows.map(([k, v]) => <div key={k} className="flex justify-between gap-4 py-2"><dt className="text-muted">{k}</dt><dd className="text-right num">{v}</dd></div>)}
      </dl>
      <p className="mt-4 rounded-lg bg-accent/60 p-3 text-sm text-slate-300">
        <span className="font-medium text-fg">Plain language:</span> {g.name} trades at {x(g.multiple)} against a peer median of {x(g.peer_median_multiple)}.
        After adjusting for quality, the residual sits at the {ord(g.rv_percentile)} percentile — {cheap ? "cheap for what it is, not merely cheap" : "rich for what it is, not merely expensive"}.
      </p>
    </Card>
  );
}

export function HomeCommunity() {
  const { data: threads } = useApi<ThreadRow[]>("/api/community/threads");
  const { data: trades } = useApi<Trade[]>("/api/community/trades");
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card className="p-5">
        <h3 className="mb-3 font-semibold">Trending threads</h3>
        <ul className="divide-y divide-line">
          {(threads ?? []).slice(0, 5).map(t => (
            <li key={t.id} className="py-2.5"><Link href={`/community/threads/${t.id}`} className="text-sm font-medium hover:text-primary">{t.title}</Link>
              <div className="text-xs text-muted">{t.community} · @{t.author} · {t.replies} replies · {ago(t.last_activity_at)}</div></li>
          ))}
          {threads?.length === 0 && <li className="py-3 text-sm text-muted">No threads yet — start one.</li>}
        </ul>
      </Card>
      <Card className="p-5">
        <h3 className="mb-3 font-semibold">Trade feed</h3>
        <ul className="divide-y divide-line">
          {(trades ?? []).slice(0, 4).map(t => (
            <li key={t.id} className="py-2.5 text-sm">
              <div className="flex items-center gap-2"><span className="text-up">▲ {t.long}</span>{t.short && <span className="text-down">▼ {t.short}</span>}
                <span className="rounded bg-accent px-1.5 text-[10px] text-muted">{t.verification}</span><span className="ml-auto text-xs text-muted">{t.status}</span></div>
              <p className="mt-1 line-clamp-1 text-muted">{t.thesis}</p>
              <div className="text-xs text-muted num">@{t.author} · entry {num(t.entry_long)}{t.return_pct != null && ` · ${pct(t.return_pct)}`}</div>
            </li>
          ))}
          {trades?.length === 0 && <li className="py-3 text-sm text-muted">Trade posts capture the live price the moment you publish. Be the first.</li>}
        </ul>
      </Card>
    </div>
  );
}
