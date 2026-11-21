"use client";
import Link from "next/link";
import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useApi } from "@/lib/hooks";
import { compact, pct, tone } from "@/lib/format";
import { useAuth } from "@/components/AuthProvider";
import { Button, Card, ErrorNote, Skeleton, SourceBadge } from "@/components/ui";

interface Trade { id: number; chamber: string; member: string; party: string | null; state: string | null; district: string | null; owner: string | null; ticker: string | null; asset: string;
  type: string; amount: string; traded: string | null; filed: string | null; disclosure_lag_days: number | null; url: string; price_change_since?: number | null; move_30d?: number; directional_move_30d?: number }
interface TradesResp { trades: Trade[]; total: number; page: number; per: number; locked: boolean; hidden: number; updated_at: string | null; note: string; source: string | null; provider: { label: string; url: string } }
interface Summary { trades: number; trades_30d: number; buys: number; sells: number; members: number; locked: boolean; method: string;
  most_traded: { ticker: string; buys: number; sells: number; members: number; est_volume: number }[];
  leaderboard: { member: string; party: string | null; chamber: string | null; state: string | null; trades: number; buys: number; sells: number; est_volume: number; last_trade: string | null; avg_directional_move: number | null; scored_trades: number }[];
  large_moves_after_trade: Trade[]; notable: Trade[] }

const PARTY: Record<string, string> = { Democrat: "text-[#3b82f6]", Republican: "text-[#ef4444]" };
const party = (p: string | null) => p ? <span className={`text-[11px] ${PARTY[p] ?? "text-muted"}`}>{p[0]}</span> : null;
const kind = (t: string) => t === "buy" ? <span className="rounded bg-up/15 px-1.5 py-0.5 text-[11px] font-semibold text-up">Buy</span>
  : t.startsWith("sell") ? <span className="rounded bg-down/15 px-1.5 py-0.5 text-[11px] font-semibold text-down">{t === "sell_partial" ? "Sell (partial)" : "Sell"}</span>
    : <span className="rounded bg-accent px-1.5 py-0.5 text-[11px]">{t}</span>;

export default function CongressPage() {
  return <Suspense fallback={<div className="mx-auto max-w-7xl px-4 py-10"><Skeleton rows={8} /></div>}><Congress /></Suspense>;
}

function Congress() {
  const sp = useSearchParams();
  const { user } = useAuth();
  const [symbol, setSymbol] = useState(sp.get("symbol")?.toUpperCase() ?? "");
  const [member, setMember] = useState(sp.get("member") ?? "");
  const [chamber, setChamber] = useState("");
  const [partyF, setParty] = useState("");
  const [type, setType] = useState("");
  const [minAmt, setMinAmt] = useState("");
  const [page, setPage] = useState(1);
  const qs = new URLSearchParams(Object.entries({ symbol, member, chamber, party: partyF, type, min_amount: minAmt, page: String(page) }).filter(([, v]) => v)).toString();
  const { data, error } = useApi<TradesResp>(`/api/congress/trades?${qs}`, 0, [user?.id]);
  const { data: s } = useApi<Summary>("/api/congress/summary", 0, [user?.id]);
  return (
    <div className="mx-auto max-w-7xl px-4 py-10">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><div className="text-xs uppercase tracking-wide text-primary">Public disclosures</div><h1 className="text-3xl">Congress Trading</h1>
          <p className="mt-1 max-w-3xl text-sm text-muted">Every stock trade members of the House and Senate disclose under the STOCK Act, read straight from the official filings. See who is buying and selling what, how late each trade was disclosed, and how the stock has moved since.</p></div>
        {data?.updated_at && <div className="text-right text-xs text-muted">Updated {new Date(data.updated_at).toLocaleString()} <SourceBadge source={data.source ?? undefined} /></div>}
      </div>

      {s && <div className="mt-6 grid grid-cols-2 gap-3 md:grid-cols-5">{([["Trades (12 months)", s.trades.toLocaleString()], ["Last 30 days", s.trades_30d.toLocaleString()], ["Buys · sells", `${s.buys} · ${s.sells}`],
        ["Members trading", String(s.members)], ["Most traded", s.most_traded[0]?.ticker ?? "—"]] as const).map(([k, v]) => <Card key={k} className="p-4"><div className="text-xs text-muted">{k}</div><div className="mt-1 stat text-xl">{v}</div></Card>)}</div>}

      <div className="mt-6 flex flex-wrap gap-2 text-sm">
        <input value={symbol} onChange={e => { setSymbol(e.target.value.toUpperCase()); setPage(1); }} placeholder="Ticker" className="w-28 rounded border border-line bg-bg px-2 py-1" />
        <input value={member} onChange={e => { setMember(e.target.value); setPage(1); }} placeholder="Member name" className="w-44 rounded border border-line bg-bg px-2 py-1" />
        {([["", "Both chambers"], ["house", "House"], ["senate", "Senate"]] as const).map(([k, l]) => <button key={k} onClick={() => { setChamber(k); setPage(1); }} className={`rounded-full border px-3 py-1 text-xs ${chamber === k ? "border-primary bg-primary/10" : "border-line text-muted"}`}>{l}</button>)}
        <select value={partyF} onChange={e => { setParty(e.target.value); setPage(1); }} className="rounded border border-line bg-bg px-2 py-1 text-xs"><option value="">All parties</option><option>Democrat</option><option>Republican</option><option>Independent</option></select>
        <select value={type} onChange={e => { setType(e.target.value); setPage(1); }} className="rounded border border-line bg-bg px-2 py-1 text-xs"><option value="">Buys and sells</option><option value="buy">Buys</option><option value="sell">Sells</option></select>
        <select value={minAmt} onChange={e => { setMinAmt(e.target.value); setPage(1); }} className="rounded border border-line bg-bg px-2 py-1 text-xs"><option value="">Any size</option><option value="15001">$15K+</option><option value="50001">$50K+</option><option value="250001">$250K+</option><option value="1000001">$1M+</option></select>
      </div>

      <ErrorNote error={error} />
      {!data ? <div className="mt-4"><Skeleton rows={10} /></div> : <Card className="mt-4 overflow-x-auto p-0"><table className="w-full min-w-[980px] text-sm">
        <thead className="text-xs text-muted"><tr>{["Member", "Ticker", "Transaction", "Size", "Traded", "Disclosed", "Lag", "Since trade", ""].map((h, i) => <th key={i} className={`px-3 py-2 font-normal ${i >= 6 && i < 8 ? "text-right" : "text-left"}`}>{h}</th>)}</tr></thead>
        <tbody className="divide-y divide-line">{data.trades.map(t => <tr key={t.id}>
          <td className="px-3 py-2"><button onClick={() => { setMember(t.member); setPage(1); }} className="font-medium hover:text-primary">{t.member}</button>
            <div className="text-[11px] text-muted">{party(t.party)} {t.state}{t.district ? `-${t.district}` : ""} · {t.chamber === "house" ? "House" : "Senate"}{t.owner && t.owner !== "self" ? ` · ${t.owner}` : ""}</div></td>
          <td className="px-3">{t.ticker ? <Link href={`/ticker/${t.ticker}`} className="font-semibold hover:text-primary">{t.ticker}</Link> : "—"}<div className="max-w-[220px] truncate text-[11px] text-muted" title={t.asset}>{t.asset}</div></td>
          <td className="px-3">{kind(t.type)}</td><td className="px-3 num text-xs">{t.amount}</td>
          <td className="px-3 num text-xs">{t.traded ?? "—"}</td><td className="px-3 num text-xs">{t.filed ?? "—"}</td>
          <td className="px-3 text-right num text-xs">{t.disclosure_lag_days != null ? `${t.disclosure_lag_days}d` : "—"}</td>
          <td className={`px-3 text-right num ${tone(t.price_change_since)}`}>{pct(t.price_change_since, 1)}</td>
          <td className="px-3 text-right"><a href={t.url} target="_blank" rel="noopener noreferrer" className="text-xs text-primary">Filing ↗</a></td></tr>)}</tbody></table>
        {!data.trades.length && <p className="p-6 text-center text-sm text-muted">No disclosed trades match these filters yet.</p>}
        {data.locked && data.hidden > 0 ? <div className="border-t border-line p-5 text-center text-sm"><b>{data.hidden.toLocaleString()} more trades</b> match. Pro unlocks the full history, filters by size and the member leaderboard.<Button className="ml-3" href={user ? "/pricing" : "/signup?plan=pro&next=/congress"}>Unlock with Pro</Button></div>
          : data.total > data.per && <div className="flex items-center justify-between border-t border-line px-4 py-2 text-xs"><span className="text-muted">Page {data.page} of {Math.ceil(data.total / data.per)}</span>
            <span className="flex gap-2"><button disabled={page <= 1} onClick={() => setPage(p => p - 1)} className="rounded border border-line px-2 py-1 disabled:opacity-40">Previous</button><button disabled={page * data.per >= data.total} onClick={() => setPage(p => p + 1)} className="rounded border border-line px-2 py-1 disabled:opacity-40">Next</button></span></div>}
      </Card>}

      {s && <div className="mt-6 grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <Card className="overflow-x-auto p-0"><div className="px-4 pt-3 text-sm font-semibold">Member leaderboard <span className="text-xs font-normal text-muted">by estimated trade volume, last 12 months</span></div>
          <table className="mt-2 w-full min-w-[620px] text-sm"><thead className="text-xs text-muted"><tr>{["Member", "Trades", "Buys / sells", "Est. volume", "Avg move in traded direction", "Last trade"].map(h => <th key={h} className="px-3 py-1.5 text-left font-normal">{h}</th>)}</tr></thead>
            <tbody className="divide-y divide-line">{s.leaderboard.map(m => <tr key={m.member}><td className="px-3 py-2"><button onClick={() => setMember(m.member)} className="font-medium hover:text-primary">{m.member}</button> {party(m.party)} <span className="text-[11px] text-muted">{m.state}</span></td>
              <td className="px-3 num">{m.trades}</td><td className="px-3 num text-xs">{m.buys} / {m.sells}</td><td className="px-3 num">${compact(m.est_volume)}</td>
              <td className={`px-3 num ${tone(m.avg_directional_move)}`}>{pct(m.avg_directional_move, 1)} <span className="text-[10px] text-muted">({m.scored_trades})</span></td><td className="px-3 num text-xs">{m.last_trade ?? "—"}</td></tr>)}</tbody></table>
          {s.locked && <p className="border-t border-line p-3 text-center text-xs text-muted">Pro shows the top 25 members.</p>}</Card>
        <Card className="p-0"><div className="px-4 pt-3 text-sm font-semibold">Most traded tickers</div>
          <ul className="mt-2 divide-y divide-line text-sm">{s.most_traded.map(x => { const tot = x.buys + x.sells; return <li key={x.ticker} className="flex items-center gap-3 px-4 py-2">
            <button onClick={() => setSymbol(x.ticker)} className="w-16 text-left font-semibold hover:text-primary">{x.ticker}</button>
            <div className="flex h-2 flex-1 overflow-hidden rounded bg-accent"><div className="bg-up/70" style={{ width: `${(x.buys / tot) * 100}%` }} /><div className="bg-down/70" style={{ width: `${(x.sells / tot) * 100}%` }} /></div>
            <span className="w-24 text-right num text-xs text-muted">{x.buys}B · {x.sells}S · {x.members}m</span></li>; })}</ul></Card>
      </div>}

      {s && s.large_moves_after_trade.length > 0 && <Card className="mt-6 overflow-x-auto p-0"><div className="px-4 pt-3"><div className="text-sm font-semibold">Trades followed by large moves</div>
        <p className="text-[11px] text-muted">Trades where the stock moved 15% or more in the traded direction within 30 days. Descriptive only: it says nothing about any member&apos;s knowledge or intent.</p></div>
        <table className="mt-2 w-full min-w-[720px] text-sm"><tbody className="divide-y divide-line">{s.large_moves_after_trade.map(t => <tr key={t.id}><td className="px-3 py-2 font-medium">{t.member} {party(t.party)}</td>
          <td className="px-3"><Link href={`/ticker/${t.ticker}`} className="font-semibold hover:text-primary">{t.ticker}</Link></td><td className="px-3">{kind(t.type)}</td><td className="px-3 num text-xs">{t.amount}</td>
          <td className="px-3 num text-xs">{t.traded}</td><td className={`px-3 text-right num ${tone(t.move_30d)}`}>{pct(t.move_30d, 1)} in 30 days</td></tr>)}</tbody></table></Card>}

      <p className="mt-6 text-[11px] text-muted">{data?.note} {s?.method} Source: {data?.provider?.label}. Scanned paper filings can&apos;t be read automatically; open the filing link for those.</p>
    </div>
  );
}
