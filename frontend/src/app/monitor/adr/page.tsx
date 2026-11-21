"use client";
import { useMemo, useState } from "react";
import type { AdrRow, Gated } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { ago } from "@/lib/format";
import { AdrTable } from "@/components/Monitors";
import { AdrOpportunityStrip, useAdrFacets } from "@/components/AdrOpportunities";
import { Card, DataNote, ErrorNote, LockedRows, PageHeader, Skeleton } from "@/components/ui";

type Row = AdrRow & { sector?: string; scanned_at?: string; opportunity?: number; ratio_suspect?: boolean };

export default function AdrMonitor() {
  const { data, error } = useApi<Gated<Row>>("/api/monitors/adr", 60_000);
  const facets = useAdrFacets();
  const [f, setF] = useState({ q: "", country: "", sector: "", minZ: "0", tradable: false, hideSuspect: true, sort: "z" });
  const rows = useMemo(() => {
    let r = (data?.rows ?? []).filter(x =>
      (!f.q || `${x.adr_symbol} ${x.local_symbol} ${x.name}`.toLowerCase().includes(f.q.toLowerCase())) &&
      (!f.country || x.country === f.country) && (!f.sector || x.sector === f.sector) &&
      Math.abs(x.z ?? 0) >= parseFloat(f.minZ) && (!f.tradable || x.tradable) && (!f.hideSuspect || !x.ratio_suspect));
    r = [...r].sort((a, b) => f.sort === "opportunity" ? (b.opportunity ?? 0) - (a.opportunity ?? 0)
      : f.sort === "premium" ? Math.abs(b.premium ?? 0) - Math.abs(a.premium ?? 0) : Math.abs(b.z ?? 0) - Math.abs(a.z ?? 0));
    return r;
  }, [data, f]);
  const rejected = rows.filter(r => r.reasons.length);
  const scanned = data?.rows.find(r => r.scanned_at)?.scanned_at;
  const sel = (k: "country" | "sector", opts: string[] | undefined, all: string) => (
    <select value={f[k]} onChange={e => setF({ ...f, [k]: e.target.value })} className="rounded border border-line bg-bg px-2 py-1.5 text-sm"><option value="">{all}</option>{opts?.map(o => <option key={o}>{o}</option>)}</select>);
  return (
    <div className="mx-auto max-w-7xl px-4 py-12">
      <PageHeader title="ADR Monitor" intro={`${data?.total ?? "60+"} ADRs against their home-market lines, converted at live FX and the depositary ratio, net of each pair's structural basis. A background scanner re-prices every pair every few minutes.`} />
      <ErrorNote error={error} />
      <section className="mb-6"><AdrOpportunityStrip /></section>
      <Card className="mb-3 flex flex-wrap items-center gap-2 p-3">
        <input value={f.q} onChange={e => setF({ ...f, q: e.target.value })} placeholder="Search ticker or name" className="w-48 rounded border border-line bg-bg px-2 py-1.5 text-sm" />
        {sel("country", facets?.countries, "All countries")}{sel("sector", facets?.sectors, "All sectors")}
        <select value={f.minZ} onChange={e => setF({ ...f, minZ: e.target.value })} className="rounded border border-line bg-bg px-2 py-1.5 text-sm">
          {[["0", "Any |z|"], ["1", "|z| ≥ 1"], ["1.5", "|z| ≥ 1.5"], ["2", "|z| ≥ 2"], ["3", "|z| ≥ 3"]].map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
        <select value={f.sort} onChange={e => setF({ ...f, sort: e.target.value })} className="rounded border border-line bg-bg px-2 py-1.5 text-sm">
          <option value="z">Sort: |z|</option><option value="opportunity">Sort: opportunity score</option><option value="premium">Sort: |premium|</option></select>
        <label className="flex items-center gap-1 text-sm text-muted"><input type="checkbox" checked={f.tradable} onChange={e => setF({ ...f, tradable: e.target.checked })} /> No frictions flagged</label>
        <label className="flex items-center gap-1 text-sm text-muted"><input type="checkbox" checked={f.hideSuspect} onChange={e => setF({ ...f, hideSuspect: e.target.checked })} /> Hide pairs with ratio warnings</label>
        <span className="ml-auto text-xs text-muted">{rows.length} shown{scanned ? ` · scanned ${ago(scanned)}` : ""}</span>
      </Card>
      <Card>{data ? <><AdrTable rows={rows} /><LockedRows locked={data.locked} what="pairs" /></> : <Skeleton rows={8} />}</Card>
      <p className="mt-2 text-xs text-muted">Opportunity score = |z| × confidence, reduced when frictions are flagged. A large z means the gap is unusual for this pair, not that it will close. Pairs flagged for a ratio review are excluded by default.</p>
      <DataNote />
      {rejected.length > 0 && (
        <section className="mt-12">
          <h2 className="text-xl font-semibold">Why some gaps are not opportunities</h2>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {rejected.slice(0, 20).map(r => (
              <Card key={r.adr_symbol} className="p-4">
                <div className="font-medium">{r.adr_symbol} vs {r.local_symbol}</div>
                <ul className="mt-1 list-disc pl-5 text-sm text-muted">{r.reasons.map(x => <li key={x}>{x}</li>)}</ul>
              </Card>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
