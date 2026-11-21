"use client";
import Link from "next/link";
import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useApi } from "@/lib/hooks";
import { compact, pct, tone } from "@/lib/format";
import { useAuth } from "@/components/AuthProvider";
import { Button, Card, ErrorNote, Skeleton } from "@/components/ui";

interface Fund { key: string; manager: string; fund: string; style: string; period: string; filed: string; aum_13f: number; prev_aum_13f: number | null; positions: number;
  top_holding: { ticker: string | null; name: string; weight: number | null } | null; top5_weight: number; stale: boolean; sec_url: string }
interface Holding { cusip: string; ticker: string | null; name: string; class: string; put_call: string | null; value: number; shares: number; weight: number | null;
  status: string | null; shares_change: number | null; prev_weight: number | null }
interface FundDetail extends Fund { holdings: Holding[]; hidden: number; locked: boolean; top_buys: Holding[]; top_sells: Holding[]; counts: Record<string, number>; prev_period: string | null; note: string }
interface ConsRow { ticker: string; name: string; holders: number; value: number; new: string[]; added: string[]; reduced: string[]; sold_out: string[]; net_buyers: number;
  top_holders: { fund: string; manager: string; weight: number | null }[] }
interface Consensus { most_held: ConsRow[]; most_bought: ConsRow[]; most_sold: ConsRow[]; new_positions: ConsRow[]; period: string | null; locked?: boolean; note: string }
interface SymResp { symbol: string; smart_money: ConsRow | null; congress: { id: number; member: string; party: string | null; type: string; amount: string; traded: string | null }[]; period: string | null }

const STATUS: Record<string, string> = { new: "bg-up/20 text-up", added: "bg-up/10 text-up", reduced: "bg-down/10 text-down", sold_out: "bg-down/20 text-down", unchanged: "bg-accent text-muted" };
const label = (s: string | null) => s ? <span className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${STATUS[s] ?? ""}`}>{s === "sold_out" ? "Sold out" : s[0].toUpperCase() + s.slice(1)}</span> : null;

export default function SmartMoneyPage() {
  return <Suspense fallback={<div className="mx-auto max-w-7xl px-4 py-10"><Skeleton rows={8} /></div>}><SmartMoney /></Suspense>;
}

function SmartMoney() {
  const sp = useSearchParams();
  const { user } = useAuth();
  const [fund, setFund] = useState<string | null>(sp.get("fund"));
  const [sym, setSym] = useState(sp.get("symbol")?.toUpperCase() ?? "");
  const [q, setQ] = useState(sym);
  const { data, error } = useApi<{ funds: Fund[]; note: string; provider: { label: string; url: string }; loaded: number; tracked: number }>("/api/smart-money/funds");
  const { data: cons } = useApi<Consensus>("/api/smart-money/consensus", 0, [user?.id]);
  const { data: one } = useApi<SymResp>(sym ? `/api/smart-money/symbol/${encodeURIComponent(sym)}` : null);
  return (
    <div className="mx-auto max-w-7xl px-4 py-10">
      <div className="text-xs uppercase tracking-wide text-primary">13F filings · SEC EDGAR</div>
      <h1 className="text-3xl">Smart Money Trackers</h1>
      <p className="mt-1 max-w-3xl text-sm text-muted">Follow what the best-known investors own. Every quarter IRAI reads each manager&apos;s 13F filing straight from the SEC and shows their biggest positions, what they started, added, trimmed and closed, and where the crowd agrees.</p>
      <form onSubmit={e => { e.preventDefault(); setSym(q.trim().toUpperCase()); }} className="mt-4 flex gap-2"><input value={q} onChange={e => setQ(e.target.value.toUpperCase())} placeholder="Who owns… (ticker)" className="w-48 rounded border border-line bg-bg px-3 py-1.5 text-sm" /><Button type="submit">Look up</Button></form>
      {one && <Card className="mt-3 p-4 text-sm">{one.smart_money ? <><b>{one.symbol}</b> is held by <b>{one.smart_money.holders}</b> tracked funds ({one.period}): {one.smart_money.top_holders.map(h => `${h.manager} (${pct(h.weight, 1, false)})`).join(", ")}.
        {one.smart_money.new.length + one.smart_money.added.length > 0 && <> Bought or added: {[...one.smart_money.new, ...one.smart_money.added].join(", ")}.</>}{one.smart_money.reduced.length + one.smart_money.sold_out.length > 0 && <> Trimmed or sold: {[...one.smart_money.reduced, ...one.smart_money.sold_out].join(", ")}.</>}</>
        : <>None of the tracked funds reported {one.symbol} in their latest 13F.</>}
        {one.congress.length > 0 && <div className="mt-2 text-xs text-muted">Congress: {one.congress.slice(0, 4).map(c => `${c.member} ${c.type.startsWith("sell") ? "sold" : "bought"} ${c.amount} (${c.traded})`).join(" · ")} <Link href={`/congress?symbol=${one.symbol}`} className="text-primary">All →</Link></div>}</Card>}
      <ErrorNote error={error} />
      {!data ? <div className="mt-6"><Skeleton rows={6} /></div> : !data.funds.length ? <Card className="mt-6 p-6 text-sm text-muted">The first 13F load runs in the background; check back shortly.</Card> : (
        <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{data.funds.map(f => (
          <button key={f.key} onClick={() => setFund(f.key)} className={`rounded-xl border bg-card p-4 text-left transition hover:border-primary ${fund === f.key ? "border-primary" : "border-line"} ${f.stale ? "opacity-60" : ""}`}>
            <div className="text-sm font-semibold">{f.manager}</div><div className="text-[11px] text-muted">{f.fund} · {f.style}</div>
            <div className="mt-3 flex items-end justify-between"><div><div className="text-[10px] text-muted">13F value</div><div className="stat text-lg">${compact(f.aum_13f)}</div></div>
              {f.prev_aum_13f ? <div className={`text-xs num ${tone(f.aum_13f / f.prev_aum_13f - 1)}`}>{pct(f.aum_13f / f.prev_aum_13f - 1, 1)} q/q</div> : null}</div>
            <div className="mt-2 text-[11px] text-muted">Top holding <b className="text-fg">{f.top_holding?.ticker ?? f.top_holding?.name}</b> {pct(f.top_holding?.weight, 1, false)} · {f.positions} positions</div>
            <div className="text-[10px] text-muted">Quarter ending {f.period}{f.stale ? " · no recent filing" : ""}</div></button>))}</div>)}

      {fund && <FundView k={fund} onClose={() => setFund(null)} />}

      {cons && <div className="mt-8 grid gap-6 lg:grid-cols-3">
        {([["Most held across tracked funds", cons.most_held, (r: ConsRow) => `${r.holders} funds`], ["Most bought last quarter", cons.most_bought, (r: ConsRow) => `${r.new.length} new · ${r.added.length} added`],
          ["Most sold last quarter", cons.most_sold, (r: ConsRow) => `${r.reduced.length} trimmed · ${r.sold_out.length} exited`]] as const).map(([t, rows, f]) => (
          <Card key={t} className="p-0"><div className="px-4 pt-3 text-sm font-semibold">{t}</div><div className="px-4 text-[11px] text-muted">Quarter ending {cons.period}</div>
            <ul className="mt-2 divide-y divide-line text-sm">{rows.map(r => <li key={r.ticker} className="flex items-center justify-between gap-2 px-4 py-2">
              <span><button onClick={() => { setSym(r.ticker); setQ(r.ticker); }} className="font-semibold hover:text-primary">{r.ticker}</button> <span className="text-[11px] text-muted">{r.name}</span></span>
              <span className="shrink-0 text-xs num text-muted">{f(r)}</span></li>)}</ul>
            {cons.locked && <p className="border-t border-line p-3 text-center text-xs text-muted">Pro shows the full lists.</p>}</Card>))}
      </div>}
      <p className="mt-6 text-[11px] text-muted">{data?.note} Source: {data?.provider.label}. Tickers are matched from CUSIPs; a few may be missing.</p>
    </div>
  );
}

function FundView({ k, onClose }: { k: string; onClose: () => void }) {
  const { user } = useAuth();
  const { data, error } = useApi<FundDetail>(`/api/smart-money/funds/${k}`, 0, [user?.id]);
  if (error) return <div className="mt-6"><ErrorNote error={error} /></div>;
  if (!data) return <div className="mt-6"><Skeleton rows={8} /></div>;
  return (
    <Card className="mt-6 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="text-xl">{data.manager} · {data.fund}</h2>
        <p className="text-xs text-muted">13F for the quarter ending {data.period}, filed {data.filed}{data.prev_period ? `, compared with ${data.prev_period}` : ""}. {data.positions} positions, ${compact(data.aum_13f)} reported.
          <a href={data.sec_url} target="_blank" rel="noopener noreferrer" className="ml-1 text-primary">SEC filings ↗</a></p></div>
        <div className="flex gap-2 text-xs">{Object.entries(data.counts).filter(([s]) => s !== "null").map(([s, n]) => <span key={s}>{label(s)} {n}</span>)}<button onClick={onClose} className="ml-2 text-muted hover:text-fg">✕</button></div></div>
      <div className="mt-4 grid gap-4 md:grid-cols-2">
        {([["Biggest buys", data.top_buys], ["Biggest sells", data.top_sells]] as const).map(([t, rows]) => <div key={t}><div className="text-xs font-semibold uppercase tracking-wide text-muted">{t}</div>
          <ul className="mt-1 divide-y divide-line text-sm">{rows.map(r => <li key={r.cusip + (r.put_call ?? "")} className="flex justify-between py-1.5"><span>{r.ticker ? <Link href={`/ticker/${r.ticker}`} className="font-semibold hover:text-primary">{r.ticker}</Link> : r.name} {label(r.status)}</span>
            <span className="num text-xs text-muted">{pct(r.prev_weight, 1, false)} → {pct(r.weight, 1, false)}</span></li>)}{!rows.length && <li className="py-1.5 text-xs text-muted">None this quarter.</li>}</ul></div>)}
      </div>
      <div className="mt-4 overflow-x-auto"><table className="w-full min-w-[760px] text-sm"><thead className="text-xs text-muted"><tr>{["Holding", "Weight", "Value", "Shares", "Change in shares", "Status"].map((h, i) => <th key={h} className={`py-1.5 font-normal ${i && i < 5 ? "text-right" : "text-left"}`}>{h}</th>)}</tr></thead>
        <tbody className="divide-y divide-line">{data.holdings.map(h => <tr key={h.cusip + (h.put_call ?? "") + h.status}><td className="py-1.5">{h.ticker ? <Link href={`/ticker/${h.ticker}`} className="font-semibold hover:text-primary">{h.ticker}</Link> : <span className="text-muted">—</span>} <span className="text-[11px] text-muted">{h.name}{h.put_call ? ` (${h.put_call})` : ""}</span></td>
          <td className="text-right num"><div className="ml-auto flex items-center justify-end gap-2"><div className="h-1.5 w-16 rounded bg-accent"><div className="h-1.5 rounded bg-primary" style={{ width: `${Math.min(100, (h.weight ?? 0) * 300)}%` }} /></div>{pct(h.weight, 1, false)}</div></td>
          <td className="text-right num">${compact(h.value)}</td><td className="text-right num">{compact(h.shares)}</td>
          <td className={`text-right num ${tone(h.shares_change)}`}>{h.status === "new" ? "new" : pct(h.shares_change, 1)}</td><td className="pl-3">{label(h.status)}</td></tr>)}</tbody></table></div>
      {data.locked && data.hidden > 0 && <div className="mt-3 text-center text-sm"><b>{data.hidden} more positions</b> and every quarter-over-quarter change are part of Pro. <Button className="ml-2" href={user ? "/pricing" : "/signup?plan=pro&next=/smart-money"}>Unlock with Pro</Button></div>}
    </Card>
  );
}
