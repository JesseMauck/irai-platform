"use client";
import type { AdrRow, Gated } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { AdrTable } from "@/components/Monitors";
import { Card, DataNote, ErrorNote, LockedRows, PageHeader, Skeleton } from "@/components/ui";

export default function AdrMonitor() {
  const { data, error } = useApi<Gated<AdrRow>>("/api/monitors/adr", 60_000);
  const rejected = (data?.rows ?? []).filter(r => r.reasons.length);
  return (
    <div className="mx-auto max-w-7xl px-4 py-12">
      <PageHeader title="ADR Monitor" intro="ADRs against their local lines, converted at live FX and the depositary ratio, net of each pair's structural basis. Sorted by |z|. Refreshes every minute." />
      <ErrorNote error={error} />
      <Card>{data ? <><AdrTable rows={data.rows} /><LockedRows locked={data.locked} what="pairs" /></> : <Skeleton rows={8} />}</Card>
      <DataNote />
      {rejected.length > 0 && (
        <section className="mt-12">
          <h2 className="text-xl font-semibold">Why some gaps are not opportunities</h2>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {rejected.map(r => (
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
