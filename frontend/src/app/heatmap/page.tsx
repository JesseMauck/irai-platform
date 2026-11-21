"use client";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useApi } from "@/lib/hooks";
import { compact, num, pct } from "@/lib/format";
import { SourceLine } from "@/components/research";
import { heatColor, squarify } from "@/components/Treemap";
import { Skeleton } from "@/components/ui";

interface Tile { symbol: string; name: string | null; sector: string; market_cap: number; change: number | null; price: number; source: string }
interface Heat { period: string; sectors: { sector: string; market_cap: number; change: number | null; tiles: Tile[] }[]; count: number; source: string; provider: { label: string; url: string }; as_of: string }
const PERIODS: [string, string, number][] = [["1d", "Today", 0.03], ["1m", "1 month", 0.12], ["3m", "3 months", 0.2], ["1y", "1 year", 0.4]];

export default function Heatmap() {
  const [period, setPeriod] = useState("1d");
  const { data } = useApi<Heat>(`/api/discover/heatmap?period=${period}`, period === "1d" ? 120_000 : undefined);
  const box = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(1200);
  const [hover, setHover] = useState<Tile | null>(null);
  const router = useRouter();
  useEffect(() => {
    const el = box.current; if (!el) return;
    const ro = new ResizeObserver(() => setW(el.clientWidth || 1200)); ro.observe(el); setW(el.clientWidth || 1200);
    return () => ro.disconnect();
  }, []);
  const H = Math.max(420, Math.min(720, w * 0.55));
  const scale = PERIODS.find(p => p[0] === period)?.[2] ?? 0.03;
  const secs = data?.sectors ?? [];
  const srects = squarify(secs.map(s => Math.max(s.market_cap, 1)), 0, 0, w, H);
  return (
    <div className="mx-auto max-w-[1600px] px-4 py-10">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><h1 className="text-3xl">Heatmaps</h1><p className="mt-1 text-sm text-muted">US large caps sized by market cap and coloured by return. Click a tile to open the ticker.</p></div>
        <div className="flex gap-1 rounded-lg bg-accent p-1 text-xs">{PERIODS.map(([k, l]) => <button key={k} onClick={() => setPeriod(k)} className={`rounded-md px-3 py-1 ${period === k ? "bg-card shadow-sm" : "text-muted"}`}>{l}</button>)}</div>
      </div>
      <div ref={box} className="relative mt-5 w-full" style={{ height: H }}>
        {!data ? <Skeleton rows={12} /> : secs.map((s, i) => {
          const r = srects[i];
          const head = r.h > 40 ? 18 : 0;
          const trs = squarify(s.tiles.map(t => Math.max(t.market_cap, 1)), 0, 0, r.w - 2, r.h - head - 2);
          return (
            <div key={s.sector} className="absolute overflow-hidden border border-bg" style={{ left: r.x, top: r.y, width: r.w, height: r.h }}>
              {head > 0 && <div className="truncate px-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted" style={{ height: head }}>{s.sector} <span className="num">{pct(s.change, 1)}</span></div>}
              <div className="relative" style={{ height: r.h - head }}>{s.tiles.map((t, j) => {
                const q = trs[j]; const big = q.w > 56 && q.h > 34;
                return (
                  <button key={t.symbol} onClick={() => router.push(`/ticker/${t.symbol}`)} onMouseEnter={() => setHover(t)} onMouseLeave={() => setHover(null)}
                    className="absolute flex flex-col items-center justify-center overflow-hidden border border-bg/70 text-center hover:z-10 hover:outline hover:outline-2 hover:outline-fg"
                    style={{ left: q.x, top: q.y, width: q.w, height: q.h, background: heatColor(t.change, scale) }}>
                    {q.w > 28 && q.h > 16 && <span className={`stat leading-none ${big ? "text-sm" : "text-[10px]"}`}>{t.symbol}</span>}
                    {big && <span className="mt-0.5 text-[11px] num">{pct(t.change, 1)}</span>}
                  </button>);
              })}</div>
            </div>);
        })}
        {hover && <div className="pointer-events-none absolute right-2 top-2 z-20 rounded-lg border border-line bg-card px-3 py-2 text-sm shadow-lg">
          <div className="font-semibold">{hover.symbol} <span className="font-normal text-muted">{hover.name}</span></div>
          <div className="num text-xs">{num(hover.price)} · {pct(hover.change, 2)} · cap {compact(hover.market_cap)}</div><div className="text-[11px] text-muted">{hover.sector} · {hover.source}</div></div>}
      </div>
      <div className="mt-3 flex items-center gap-2 text-[11px] text-muted"><span>{pct(-scale, 0)}</span>
        <div className="h-2 w-48 rounded" style={{ background: `linear-gradient(to right, ${heatColor(-scale, scale)}, ${heatColor(0, scale)}, ${heatColor(scale, scale)})` }} /><span>{pct(scale, 0)}</span></div>
      <SourceLine provider={data?.provider} source={data?.source} asOf={data?.as_of} />
    </div>
  );
}
