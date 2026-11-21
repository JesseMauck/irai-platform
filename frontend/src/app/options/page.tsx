"use client";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { useApi } from "@/lib/hooks";
import { compact, num, pct } from "@/lib/format";
import { SourceLine } from "@/components/research";
import { TickerInput } from "@/components/TickerInput";
import { Card, Skeleton } from "@/components/ui";

interface Opt { contract: string; strike: number; last: number | null; bid: number | null; ask: number | null; change_pct: number; volume: number; open_interest: number; iv: number | null; itm: boolean; type?: string }
interface Chain { symbol: string; price?: number; price_source?: string; expiries: string[]; expiry?: string; days_to_expiry?: number; calls: Opt[]; puts: Opt[]; note?: string; source: string;
  summary?: { put_call_volume: number | null; put_call_oi: number | null; call_volume: number; put_volume: number; atm_strike: number | null; atm_iv: number | null; expected_move: number | null; expected_move_pct: number | null; max_pain: number | null };
  unusual?: Opt[]; provider?: { label: string; url: string } }

export default function OptionsPage() { return <Suspense fallback={null}><Options /></Suspense>; }

function Options() {
  const sp = useSearchParams();
  const router = useRouter();
  const sym = (sp.get("symbol") ?? "SPY").toUpperCase();
  const exp = sp.get("expiry");
  const [q, setQ] = useState(sym);
  const { data } = useApi<Chain>(`/api/discover/options/${encodeURIComponent(sym)}${exp ? `?expiry=${exp}` : ""}`);
  const go = (s: string, e?: string) => router.push(`/options?symbol=${encodeURIComponent(s.toUpperCase())}${e ? `&expiry=${e}` : ""}`);
  const near = (rows: Opt[]) => { if (!data?.price) return rows.slice(0, 30); return [...rows].sort((a, b) => Math.abs(a.strike - data.price!) - Math.abs(b.strike - data.price!)).slice(0, 24).sort((a, b) => a.strike - b.strike); };
  const s = data?.summary;
  return (
    <div className="mx-auto max-w-7xl px-4 py-10">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><h1 className="text-3xl">Options Discover</h1><p className="mt-1 text-sm text-muted">Chains, implied volatility, put/call ratios, the market&apos;s expected move and unusual activity for any optionable US ticker.</p></div>
        <div className="w-64"><TickerInput value={q} onChange={setQ} onPick={v => go(v)} placeholder="Ticker" /></div>
      </div>
      {!data ? <div className="mt-6"><Skeleton rows={10} /></div> : data.note && !data.expiries.length ? <Card className="mt-6 p-8 text-center text-sm text-muted">{data.note}</Card> : <>
        <div className="mt-5 flex flex-wrap gap-1.5 text-xs">{data.expiries.map(e => <button key={e} onClick={() => go(sym, e)} className={`rounded-full border px-2.5 py-1 num ${e === data.expiry ? "border-primary bg-primary/10" : "border-line text-muted"}`}>{e}</button>)}</div>
        {s && <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-6">
          {([["Price", `${num(data.price)} ${data.price_source ?? ""}`], ["Expected move", s.expected_move ? `±${num(s.expected_move)} (${pct(s.expected_move_pct, 1, false)})` : "—"], ["ATM implied vol", pct(s.atm_iv, 1, false)],
            ["Put/call volume", num(s.put_call_volume, 2)], ["Put/call open interest", num(s.put_call_oi, 2)], ["Max pain", num(s.max_pain)]] as [string, string][]).map(([k, v]) =>
            <Card key={k} className="p-3"><div className="text-[11px] text-muted">{k}</div><div className="stat mt-0.5 text-lg num">{v}</div></Card>)}</div>}
        <p className="mt-2 text-[11px] text-muted">{data.expiry} · {data.days_to_expiry} days to expiry. Expected move comes from the at-the-money straddle; it&apos;s the move the options market is pricing, not a forecast.</p>
        <div className="mt-4 grid gap-4 lg:grid-cols-2">{([["Calls", data.calls], ["Puts", data.puts]] as [string, Opt[]][]).map(([t, rows]) => (
          <Card key={t} className="overflow-x-auto p-4"><h2 className="font-semibold">{t} <span className="text-xs font-normal text-muted">near the money</span></h2>
            <table className="mt-2 w-full min-w-[520px] text-xs num"><thead className="text-muted"><tr>{["Strike", "Bid", "Ask", "Last", "Vol", "OI", "IV"].map(h => <th key={h} className="py-1 text-right font-normal first:text-left">{h}</th>)}</tr></thead>
              <tbody className="divide-y divide-line">{near(rows).map(o => (
                <tr key={o.contract} className={o.itm ? "bg-primary/5" : ""}><td className="py-1 font-semibold">{num(o.strike)}</td><td className="text-right">{num(o.bid)}</td><td className="text-right">{num(o.ask)}</td><td className="text-right">{num(o.last)}</td>
                  <td className={`text-right ${o.volume > o.open_interest && o.volume >= 500 ? "font-semibold text-primary" : ""}`}>{compact(o.volume)}</td><td className="text-right">{compact(o.open_interest)}</td><td className="text-right">{pct(o.iv, 0, false)}</td></tr>))}</tbody></table></Card>))}</div>
        {data.unusual && data.unusual.length > 0 && <Card className="mt-4 p-5"><h2 className="font-semibold">Unusual activity</h2><p className="text-xs text-muted">Contracts trading more today than their open interest (500+ contracts).</p>
          <ul className="mt-2 grid gap-1 text-sm num md:grid-cols-2">{data.unusual.map(o => <li key={o.contract} className="flex justify-between rounded border border-line px-3 py-1.5"><span className="font-sans"><b className={o.type === "call" ? "text-up" : "text-down"}>{o.type}</b> {num(o.strike)}</span><span>{compact(o.volume)} vol · {compact(o.open_interest)} OI · IV {pct(o.iv, 0, false)}</span></li>)}</ul></Card>}
      </>}
      <p className="mt-4 text-[11px] text-muted">Options are complex and risky; prices are delayed. Research and education only.</p>
      <SourceLine provider={data?.provider} source={data?.source} />
    </div>
  );
}
