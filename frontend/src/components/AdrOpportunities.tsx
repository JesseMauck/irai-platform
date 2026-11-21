"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import type { AdrRow } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { ago, num, pct } from "@/lib/format";
import { Card, SourceBadge } from "@/components/ui";

interface Opp { rows: (AdrRow & { opportunity: number; scanned_at?: string; sector?: string })[]; total: number; locked: number; scanned_at: string | null; countries: string[]; sectors: string[] }

/** Rotating strip of the scanner's current best dislocations (refreshes every minute, rotates every 6 seconds). */
export function AdrOpportunityStrip({ minZ = 1.5, limit = 12 }: { minZ?: number; limit?: number }) {
  const { data } = useApi<Opp>(`/api/monitors/adr/opportunities?min_abs_z=${minZ}&limit=${limit}`, 60_000);
  const [i, setI] = useState(0);
  const [paused, setPaused] = useState(false);
  const n = data?.rows.length ?? 0;
  useEffect(() => {
    if (!n || paused) return;
    const id = setInterval(() => setI(x => (x + 1) % n), 6000);
    return () => clearInterval(id);
  }, [n, paused]);
  if (!data) return null;
  if (!n) return <Card className="p-4 text-sm text-muted">Scanner: no ADR pairs beyond |z| ≥ {minZ} right now{data.scanned_at ? ` (scanned ${ago(data.scanned_at)})` : ""}.</Card>;
  const shown = [0, 1, 2].map(k => data.rows[(i + k) % n]).filter((r, k, a) => a.indexOf(r) === k);
  return (
    <div onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)} aria-live="polite">
      <div className="mb-2 flex items-center justify-between text-xs text-muted">
        <span><span className="mr-1 inline-block h-2 w-2 animate-pulse rounded-full bg-up" />Scanner: {data.total} pair{data.total === 1 ? "" : "s"} beyond |z| ≥ {minZ}{data.scanned_at ? ` · scanned ${ago(data.scanned_at)}` : ""}</span>
        <span className="flex gap-1">{data.rows.map((_, k) => <button key={k} aria-label={`Show ${k + 1}`} onClick={() => setI(k)} className={`h-1.5 w-4 rounded ${k === i ? "bg-primary" : "bg-accent"}`} />)}</span>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        {shown.map(r => (
          <Link key={r.adr_symbol} href={`/monitor/adr/${r.adr_symbol}`} className="rounded-xl border border-line bg-card p-4 transition hover:border-primary/50">
            <div className="flex items-center justify-between"><span className="font-semibold">{r.adr_symbol} <span className="text-xs font-normal text-muted">vs {r.local_symbol}</span></span><SourceBadge source={r.source} /></div>
            <div className="mt-1 truncate text-xs text-muted">{r.name} · {r.country}{r.sector ? ` · ${r.sector}` : ""}</div>
            <div className="mt-3 flex items-end justify-between">
              <div><div className="text-xs text-muted">Deviation from basis</div><div className={`stat text-2xl ${(r.deviation ?? 0) > 0 ? "text-down" : "text-up"}`}>{pct(r.deviation, 2)}</div></div>
              <div className="text-right text-sm num"><div>z {num(r.z, 1)}</div><div className="text-xs text-muted">conf {num(r.confidence, 0)} · ½-life {r.half_life_days ? `${num(r.half_life_days, 0)}d` : "—"}</div></div>
            </div>
            <div className="mt-2 text-xs">{r.tradable ? <span className="text-up">No known frictions flagged</span> : <span className="text-muted">{r.reasons[0]}</span>}</div>
          </Link>
        ))}
      </div>
      {data.locked > 0 && <p className="mt-2 text-xs text-muted">{data.locked} more on <Link href="/pricing" className="text-primary">Essential</Link>.</p>}
    </div>
  );
}

export function useAdrFacets() {
  return useApi<Opp>("/api/monitors/adr/opportunities?min_abs_z=0&limit=1").data;
}
