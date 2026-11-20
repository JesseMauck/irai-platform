"use client";
import Link from "next/link";
import { useApi } from "@/lib/hooks";
import { num, ord } from "@/lib/format";
import { LineChart } from "@/components/Chart";
import { GradeChip } from "@/components/Monitors";
import { Button, Card, DataNote, PageHeader, Skeleton, SourceBadge } from "@/components/ui";

interface Leg { symbol: string; name: string; grade: string; multiple: number | null; rv_percentile: number | null }
interface Idea { peer_group: string; long: Leg; short: Leg; multiple_name: string; spread_sigma: number; spread_history: { date: string; spread: number }[]; source: string; caveats: string[] }

export default function Pairs() {
  const { data, error } = useApi<Idea[]>("/api/monitors/pair-ideas");
  return (
    <div className="mx-auto max-w-6xl px-4 py-12">
      <PageHeader title="Pair ideas" intro="Within each peer group: the name cheapest for its quality against the richest. The score spread is the gap between their regression residuals, in standard deviations. Research ideas, not recommendations." />
      {error?.status === 402 ? (
        <Card className="p-10 text-center"><p className="font-medium">Pair ideas and score-spread history are part of Pro.</p><div className="mt-4"><Button href="/pricing">See plans</Button></div></Card>
      ) : !data ? <Skeleton rows={8} /> : (
        <div className="grid gap-4 md:grid-cols-2">
          {data.map(i => (
            <Card key={i.peer_group} className="p-5">
              <div className="flex items-center justify-between"><h2 className="font-semibold">{i.peer_group}</h2><SourceBadge source={i.source} /></div>
              <div className="mt-3 grid grid-cols-2 gap-3 text-sm">
                {([["▲ Cheap for quality", i.long, "text-up"], ["▼ Rich for quality", i.short, "text-down"]] as const).map(([label, leg, c]) => (
                  <div key={label} className="rounded-lg bg-accent/50 p-3"><div className={`text-xs ${c}`}>{label}</div>
                    <Link href={`/ticker/${leg.symbol}`} className="text-lg font-semibold hover:text-primary">{leg.symbol}</Link> <GradeChip grade={leg.grade} />
                    <div className="text-xs text-muted">{leg.name}</div>
                    <div className="mt-1 num text-muted">{i.multiple_name} {num(leg.multiple, 1)}x · {ord(leg.rv_percentile)}</div></div>))}
              </div>
              <p className="mt-3 text-sm">Score spread <b className="num">{i.spread_sigma.toFixed(1)}σ</b></p>
              {i.spread_history.length > 1 ? <LineChart height={120} dates={i.spread_history.map(h => h.date)} format={v => v.toFixed(2)} series={[{ values: i.spread_history.map(h => h.spread), color: "#56b4e9", label: "Spread" }]} />
                : <p className="mt-1 text-xs text-muted">Spread history builds up from daily point-in-time grades on live data.</p>}
              <ul className="mt-3 list-disc pl-5 text-xs text-muted">{i.caveats.map(c => <li key={c}>{c}</li>)}</ul>
            </Card>
          ))}
        </div>
      )}
      <DataNote />
    </div>
  );
}
