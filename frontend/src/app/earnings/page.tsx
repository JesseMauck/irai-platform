"use client";
import Link from "next/link";
import { useMemo, useState } from "react";
import { useApi } from "@/lib/hooks";
import { num, pct, tone } from "@/lib/format";
import { SourceLine } from "@/components/research";
import { Card, Skeleton } from "@/components/ui";

interface Row { symbol: string; mine: boolean; date: string; time: string; eps_estimate: number | null; eps_actual: number | null; surprise_pct: number | null }
interface Hub { upcoming: Row[]; recent: Row[]; tracked: number; mine: string[]; beat_rate: number | null; source: string; provider: { label: string; url: string }; as_of: string; note: string | null }

export default function EarningsHub() {
  const { data } = useApi<Hub>("/api/discover/earnings", 600_000);
  const [onlyMine, setOnlyMine] = useState(false);
  const byDay = useMemo(() => {
    const m: Record<string, Row[]> = {};
    for (const r of (data?.upcoming ?? []).filter(r => !onlyMine || r.mine)) (m[r.date] ||= []).push(r);
    return Object.entries(m);
  }, [data, onlyMine]);
  return (
    <div className="mx-auto max-w-7xl px-4 py-10">
      <h1 className="text-3xl">Earnings Hub</h1>
      <p className="mt-1 max-w-2xl text-sm text-muted">Upcoming reports for {data?.tracked ?? "the"} companies we track, starting with the ones in your watchlists and portfolios, plus how the latest reports compared with estimates.</p>
      {data?.note && <p className="mt-3 text-sm text-muted">{data.note}</p>}
      <div className="mt-6 grid gap-4 lg:grid-cols-3">
        <Card className="p-5 lg:col-span-2">
          <div className="flex items-center justify-between"><h2 className="font-semibold">Calendar <span className="text-xs font-normal text-muted">next 45 days</span></h2>
            {data && data.mine.length > 0 && <label className="flex items-center gap-1 text-xs"><input type="checkbox" checked={onlyMine} onChange={e => setOnlyMine(e.target.checked)} /> Only my symbols ({data.mine.length})</label>}</div>
          {!data ? <Skeleton rows={8} /> : !byDay.length ? <p className="mt-3 text-sm text-muted">No scheduled reports found.</p> : (
            <div className="mt-3 space-y-4">{byDay.map(([d, rows]) => (
              <div key={d}><div className="text-xs font-semibold text-muted">{new Date(d + "T12:00:00").toLocaleDateString("en-US", { weekday: "long", month: "short", day: "numeric" })}</div>
                <div className="mt-1.5 flex flex-wrap gap-2">{rows.map(r => (
                  <Link key={r.symbol} href={`/ticker/${r.symbol}#earnings`} className={`rounded-lg border px-3 py-2 text-sm hover:border-primary ${r.mine ? "border-primary/50 bg-primary/5" : "border-line"}`}>
                    <div className="font-semibold">{r.symbol}{r.mine && <span className="ml-1 text-[10px] text-primary">●</span>}</div>
                    <div className="text-[11px] text-muted num">EPS est. {num(r.eps_estimate)}{r.time && r.time !== "00:00" ? ` · ${r.time}` : ""}</div></Link>))}</div></div>))}</div>)}
        </Card>
        <Card className="p-5">
          <h2 className="font-semibold">Recent reports</h2>
          {data?.beat_rate != null && <p className="mt-1 text-sm"><b className="num">{pct(data.beat_rate, 0, false)}</b> beat the consensus estimate in the last three weeks.</p>}
          {!data ? <Skeleton rows={6} /> : <ul className="mt-3 divide-y divide-line text-sm">{data.recent.slice(0, 25).map(r => (
            <li key={r.symbol + r.date} className="flex justify-between py-1.5"><Link href={`/ticker/${r.symbol}#earnings`} className="font-medium hover:text-primary">{r.symbol}<span className="ml-2 text-[11px] font-normal text-muted">{r.date}</span></Link>
              <span className="num text-right text-xs">{num(r.eps_actual)} vs {num(r.eps_estimate)} <span className={tone(r.surprise_pct)}>{r.surprise_pct != null ? `${r.surprise_pct > 0 ? "+" : ""}${r.surprise_pct.toFixed(1)}%` : ""}</span></span></li>))}</ul>}
        </Card>
      </div>
      <SourceLine provider={data?.provider} source={data?.source} asOf={data?.as_of} />
    </div>
  );
}
