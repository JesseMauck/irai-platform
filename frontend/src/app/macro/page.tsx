"use client";
import Link from "next/link";
import { useApi } from "@/lib/hooks";
import { num, pct, tone } from "@/lib/format";
import { Sparkline } from "@/components/Chart";
import { SourceLine } from "@/components/research";
import { heatColor } from "@/components/Treemap";
import { Card, Skeleton } from "@/components/ui";

interface Item { symbol: string; label: string; country?: string; code?: string; price: number | null; change_pct: number | null; ret_1m: number | null; ret_1y: number | null; source: string | null; spark: number[] }
interface Macro { regions: { region: string; avg_change: number | null; markets: Item[] }[]; groups: { group: string; items: Item[] }[]; source: string; as_of: string; provider: { label: string; url: string } }
// Stylised world tile map: [column, row] on a 14 x 5 grid, roughly geographic.
const POS: Record<string, [number, number]> = {
  "^GSPTSE": [2, 1], "^GSPC": [2, 2], "^IXIC": [3, 2], "^MXX": [2, 3], "^BVSP": [4, 4],
  "^FTSE": [6, 1], "^STOXX50E": [7, 1], "^FCHI": [7, 2], "^GDAXI": [8, 2], "^SSMI": [8, 3],
  "^BSESN": [10, 3], "000001.SS": [12, 2], "^HSI": [12, 3], "^KS11": [13, 2], "^N225": [14, 2], "^TWII": [13, 3], "^AXJO": [14, 5],
};

export default function MacroMap() {
  const { data } = useApi<Macro>("/api/discover/macro", 180_000);
  const markets = (data?.regions ?? []).flatMap(r => r.markets);
  return (
    <div className="mx-auto max-w-7xl px-4 py-10">
      <h1 className="text-3xl">Macro map</h1>
      <p className="mt-1 max-w-2xl text-sm text-muted">Today&apos;s move in the world&apos;s major stock markets, with rates, currencies, commodities and risk gauges. Tiles are coloured by today&apos;s change.</p>
      {!data ? <div className="mt-6"><Skeleton rows={10} /></div> : <>
        <div className="mt-6 grid gap-3 md:grid-cols-3">{data.regions.map(r => (
          <Card key={r.region} className="p-4"><div className="text-xs text-muted">{r.region}</div><div className={`stat text-2xl num ${tone(r.avg_change)}`}>{pct(r.avg_change, 2)}</div><div className="text-[11px] text-muted">average index move today</div></Card>))}</div>
        <Card className="mt-4 overflow-x-auto p-4">
          <div className="grid min-w-[860px] gap-1.5" style={{ gridTemplateColumns: "repeat(14, minmax(0, 1fr))", gridTemplateRows: "repeat(5, 92px)" }}>
            {markets.map(m => { const p = POS[m.symbol]; if (!p) return null; return (
              <Link key={m.symbol} href={`/ticker/${encodeURIComponent(m.symbol)}`} title={`${m.label} (${m.country})`}
                className="flex flex-col justify-between rounded-lg border border-line p-2 text-xs hover:outline hover:outline-2 hover:outline-fg"
                style={{ gridColumn: p[0], gridRow: p[1], background: heatColor(m.change_pct, 0.02) }}>
                <div className="flex items-center justify-between"><span className="stat text-sm">{m.code}</span><span className="text-[9px] text-muted">{m.source}</span></div>
                <div className="truncate text-[10px] text-muted">{m.label}</div>
                <div className="stat text-sm num">{pct(m.change_pct, 2)}</div></Link>); })}
            <div className="flex items-end text-[10px] uppercase tracking-widest text-muted" style={{ gridColumn: "1 / 5", gridRow: 5 }}>Americas</div>
            <div className="flex items-end text-[10px] uppercase tracking-widest text-muted" style={{ gridColumn: "6 / 9", gridRow: 5 }}>Europe</div>
            <div className="flex items-end text-[10px] uppercase tracking-widest text-muted" style={{ gridColumn: "10 / 13", gridRow: 5 }}>Asia-Pacific</div>
          </div>
        </Card>
        <div className="mt-4 grid gap-4 md:grid-cols-2">{data.groups.map(g => (
          <Card key={g.group} className="p-5"><h2 className="font-semibold">{g.group}</h2>
            <table className="mt-2 w-full text-sm num"><thead className="text-[11px] text-muted"><tr><th className="text-left font-normal" /><th className="text-right font-normal">Last</th><th className="text-right font-normal">Today</th><th className="text-right font-normal">1M</th><th className="text-right font-normal">1Y</th><th /></tr></thead>
              <tbody className="divide-y divide-line">{g.items.map(i => (
                <tr key={i.symbol}><td className="py-1.5 font-sans"><Link href={`/ticker/${encodeURIComponent(i.symbol)}`} className="hover:text-primary">{i.label}</Link></td>
                  <td className="text-right">{num(i.price, i.price && i.price < 10 ? 3 : 2)}{g.group === "Rates" ? "%" : ""}</td><td className={`text-right ${tone(i.change_pct)}`}>{pct(i.change_pct, 2)}</td>
                  <td className={`text-right ${tone(i.ret_1m)}`}>{pct(i.ret_1m, 1)}</td><td className={`text-right ${tone(i.ret_1y)}`}>{pct(i.ret_1y, 1)}</td>
                  <td className="pl-2">{i.spark.length > 5 && <Sparkline values={i.spark} width={64} height={18} />}</td></tr>))}</tbody></table></Card>))}</div>
      </>}
      <SourceLine provider={data?.provider} source={data?.source} asOf={data?.as_of} />
    </div>
  );
}
