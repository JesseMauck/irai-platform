"use client";
import type { EtfRow, Gated } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { EtfTable } from "@/components/Monitors";
import { Card, DataNote, ErrorNote, LockedRows, PageHeader, Skeleton } from "@/components/ui";

export default function EtfMonitor() {
  const { data, error } = useApi<Gated<EtfRow>>("/api/monitors/etf", 60_000);
  return (
    <div className="mx-auto max-w-7xl px-4 py-12">
      <PageHeader title="ETF Monitor" intro="Fund prices against the issuer's published NAV. Sorted by the size of the premium or discount." />
      <ErrorNote error={error} />
      <Card>{data ? <><EtfTable rows={data.rows} /><LockedRows locked={data.locked} what="funds" /></> : <Skeleton rows={8} />}</Card>
      <DataNote />
      <section className="mt-12 grid gap-4 md:grid-cols-3">
        {[["NAV (prior close)", "The issuer's net asset value from the last close. For funds whose holdings trade in the same session (US large caps) the gap is meaningful; for bond and foreign funds NAV can be stale."],
          ["Intraday iNAV", "An estimate from live holdings prices. Not available from free feeds; connect a licensed vendor to upgrade the tier."],
          ["Treat big gaps as a question", "A premium on an illiquid fund is often the price of liquidity: a fee, not a signal. Check creation/redemption costs first."]].map(([t, b]) => (
          <Card key={t} className="p-5"><h3 className="font-semibold">{t}</h3><p className="mt-2 text-sm text-muted">{b}</p></Card>
        ))}
      </section>
    </div>
  );
}
