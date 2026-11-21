"use client";
import Link from "next/link";
import { useState } from "react";
import { useApi } from "@/lib/hooks";
import { num, pct, tone } from "@/lib/format";
import { useAuth } from "@/components/AuthProvider";
import { SourceLine } from "@/components/research";
import { Button, Card, Skeleton } from "@/components/ui";

interface Sig { id: number; date: string; symbol: string; kind: string; kind_label: string; direction: string; strength: number; title: string; detail: string | null; price_at_signal: number | null; since_signal: number | null }
interface Resp { date: string | null; signals: Sig[]; locked: number; counts: Record<string, number>; kinds: Record<string, string>; pro: boolean; universe?: number; method?: string; note?: string; provider?: { label: string } }
interface Track { signals: Sig[]; summary: Record<string, { label: string; count: number; hit_rate: number; avg_move_in_direction: number }>; since: string; note: string }
const DIR = { bullish: "text-up", bearish: "text-down", neutral: "text-muted" } as Record<string, string>;

export default function Signals() {
  const { user } = useAuth();
  const [kind, setKind] = useState("");
  const [dir, setDir] = useState("");
  const { data } = useApi<Resp>(`/api/signals?${kind ? `kind=${kind}&` : ""}${dir ? `direction=${dir}` : ""}`, 300_000, [user?.id]);
  const { data: tr } = useApi<Track>(data?.pro ? "/api/signals/track-record?days=60" : null);
  return (
    <div className="mx-auto max-w-7xl px-4 py-10">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><div className="text-xs uppercase tracking-wide text-primary">Built by IRAI</div><h1 className="text-3xl">Premium Signals</h1>
          <p className="mt-1 max-w-2xl text-sm text-muted">Every trading day after the close, IRAI scans {data?.universe ?? "50+"} of the most-traded US stocks and ETFs for trend crosses, RSI extremes, 52-week breakouts, unusual moves, media-attention spikes and ADR dislocations.</p></div>
        {data?.date && <div className="text-right text-sm"><div className="text-muted">Scan date</div><div className="stat text-xl">{data.date}</div></div>}
      </div>
      <div className="mt-5 flex flex-wrap gap-2 text-xs">
        <select value={kind} onChange={e => setKind(e.target.value)} className="rounded border border-line bg-bg px-2 py-1"><option value="">All signal types</option>{Object.entries(data?.kinds ?? {}).map(([k, l]) => <option key={k} value={k}>{l} {data?.counts?.[k] ? `(${data.counts[k]})` : ""}</option>)}</select>
        {["", "bullish", "bearish", "neutral"].map(d => <button key={d} onClick={() => setDir(d)} className={`rounded-full border px-3 py-1 capitalize ${dir === d ? "border-primary bg-primary/10" : "border-line text-muted"}`}>{d || "all"}</button>)}
      </div>
      {!data ? <div className="mt-6"><Skeleton rows={8} /></div> : !data.date ? <Card className="mt-6 p-8 text-center text-sm text-muted">{data.note}</Card> : (
        <Card className="mt-5 overflow-x-auto p-0"><table className="w-full min-w-[760px] text-sm">
          <thead className="text-xs text-muted"><tr>{["Symbol", "Signal", "What happened", "Strength", ""].map((h, i) => <th key={i} className={`px-4 py-2 font-normal ${i === 3 ? "text-right" : "text-left"}`}>{h}</th>)}</tr></thead>
          <tbody className="divide-y divide-line">{data.signals.map(s => (
            <tr key={s.id}><td className="px-4 py-2.5"><Link href={`/ticker/${s.symbol}`} className="font-semibold hover:text-primary">{s.symbol}</Link></td>
              <td className="px-4"><span className={`text-xs font-medium ${DIR[s.direction]}`}>{s.direction === "bullish" ? "▲" : s.direction === "bearish" ? "▼" : "●"} {s.kind_label}</span></td>
              <td className="px-4"><div>{s.title.replace(`${s.symbol}: `, "")}</div>{s.detail && <div className="text-[11px] text-muted">{s.detail}</div>}</td>
              <td className="px-4 text-right"><div className="ml-auto h-1.5 w-20 rounded bg-accent"><div className="h-1.5 rounded bg-primary" style={{ width: `${s.strength}%` }} /></div><div className="text-[11px] num text-muted">{s.strength.toFixed(0)}</div></td>
              <td className="px-4 text-right"><Link href={`/ticker/${s.symbol}#analyst`} className="text-xs text-primary">Analyze →</Link></td></tr>))}</tbody></table>
          {data.locked > 0 && <div className="border-t border-line p-5 text-center"><p className="text-sm"><b>{data.locked} more signals</b> in today&apos;s scan, plus their track record.</p><Button className="mt-2" href={user ? "/pricing" : "/signup?next=/signals"}>Unlock with Pro</Button></div>}
        </Card>)}
      {tr && Object.keys(tr.summary).length > 0 && (
        <Card className="mt-5 p-5"><h2 className="font-semibold">Track record <span className="text-xs font-normal text-muted">since {tr.since}</span></h2>
          <div className="mt-3 grid gap-3 md:grid-cols-3 lg:grid-cols-4">{Object.entries(tr.summary).map(([k, v]) => (
            <div key={k} className="rounded-lg border border-line p-3"><div className="text-xs text-muted">{v.label} · {v.count} signals</div>
              <div className="mt-1 text-sm num">Moved the signalled way <b>{pct(v.hit_rate, 0, false)}</b> of the time</div>
              <div className={`text-xs num ${tone(v.avg_move_in_direction)}`}>Average {pct(v.avg_move_in_direction, 2)} in the signalled direction</div></div>))}</div>
          <p className="mt-2 text-[11px] text-muted">{tr.note}</p>
          <details className="mt-3 text-sm"><summary className="cursor-pointer text-muted">Every signal</summary>
            <table className="mt-2 w-full text-xs num"><tbody className="divide-y divide-line">{tr.signals.slice(0, 150).map(s => <tr key={s.id}><td className="py-1">{s.date}</td><td className="font-sans">{s.symbol}</td><td className="font-sans">{s.kind_label}</td><td className="text-right">{num(s.price_at_signal)}</td><td className={`text-right ${tone(s.since_signal)}`}>{pct(s.since_signal, 1)}</td></tr>)}</tbody></table></details>
        </Card>)}
      {data?.method && <p className="mt-4 text-[11px] text-muted">{data.method} Signals describe events in the data; they are not recommendations to buy or sell.</p>}
      <SourceLine provider={data?.provider} />
    </div>
  );
}
