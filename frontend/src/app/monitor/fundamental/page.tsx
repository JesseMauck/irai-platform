"use client";
import { useMemo, useState } from "react";
import type { Gated, RvRow } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { RvTable } from "@/components/Monitors";
import { Card, DataNote, ErrorNote, LockedRows, PageHeader, Skeleton } from "@/components/ui";

export default function Fundamental() {
  const { data, error } = useApi<Gated<RvRow>>("/api/monitors/fundamental");
  const [group, setGroup] = useState("All");
  const groups = useMemo(() => ["All", ...Array.from(new Set((data?.rows ?? []).map(r => r.peer_group)))], [data]);
  const rows = (data?.rows ?? []).filter(r => group === "All" || r.peer_group === group);
  return (
    <div className="mx-auto max-w-7xl px-4 py-12">
      <PageHeader title="Fundamental Relative Value" intro="How far each company sits from the valuation its peers justify: cheap for its quality, not just cheap. Computed from live fundamentals." />
      <div className="mb-4 flex flex-wrap gap-2">
        {groups.map(g => <button key={g} onClick={() => setGroup(g)} className={`rounded-full px-3 py-1 text-sm ${g === group ? "bg-primary/15 text-primary" : "bg-card text-muted hover:text-fg"}`}>{g}</button>)}
      </div>
      <ErrorNote error={error} />
      <Card>{data ? <><RvTable rows={rows} /><LockedRows locked={data.locked} what="names" /></> : <Skeleton rows={10} />}</Card>
      <DataNote />
      <section className="mt-12">
        <h2 className="text-xl font-semibold">How the score is built</h2>
        <ol className="mt-4 list-decimal space-y-2 pl-5 text-muted">
          <li>Group companies by industry with comparable size and disclosure.</li>
          <li>Build a quality composite: standardized ROE + operating margin − leverage.</li>
          <li>Regress log(EV/EBITDA) (or P/E where EV/EBITDA is missing) on quality within the group.</li>
          <li>The residual becomes a percentile and a letter grade. Each computation is stored point-in-time and never restated.</li>
        </ol>
      </section>
    </div>
  );
}
