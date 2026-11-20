"use client";
import Link from "next/link";
import { useState } from "react";
import { useApi } from "@/lib/hooks";
import { pct, signed } from "@/lib/format";
import { useAuth } from "@/components/AuthProvider";
import { CustomScreens } from "@/components/CustomScreens";
import { Button, Card, DataNote, ErrorNote, PageHeader, Skeleton, SourceBadge } from "@/components/ui";

interface Preset { key: string; title: string; rule: string }
interface ScreenRow { name: string; symbol: string; value: number | null; z?: number | null; half_life_days?: number | null; grade?: string; peer_group?: string; source: string }

export default function Screeners() {
  const { data: presets } = useApi<Preset[]>("/api/monitors/screeners");
  const [key, setKey] = useState("adr-discounts");
  const { data, error, loading } = useApi<{ title: string; rule: string; rows: ScreenRow[] }>(`/api/monitors/screeners/${key}`, undefined, [key]);
  const { user } = useAuth();
  const isPct = key.startsWith("adr") || key === "etf-gaps";
  const csv = async () => {
    const r = await fetch(`/api/monitors/screeners/${key}/csv`, { headers: { Authorization: `Bearer ${localStorage.getItem("irai_token") ?? ""}` } });
    if (!r.ok) { alert("CSV export needs Pro"); return; }
    const url = URL.createObjectURL(await r.blob()); const a = document.createElement("a"); a.href = url; a.download = `${key}.csv`; a.click();
  };
  return (
    <div className="mx-auto max-w-6xl px-4 py-12">
      <PageHeader title="Screeners" intro="Preset screens run across the live monitors. Free accounts get two presets; members get all of them, Pro adds CSV export.">
        <Button variant="outline" onClick={csv} disabled={user?.plan !== "pro"}>Export CSV {user?.plan !== "pro" && "(Pro)"}</Button>
      </PageHeader>
      <div className="grid gap-3 md:grid-cols-5">
        {(presets ?? []).map(p => (
          <button key={p.key} onClick={() => setKey(p.key)} className={`rounded-xl border p-4 text-left ${p.key === key ? "border-primary/60 bg-card" : "border-line bg-card/60 hover:bg-card"}`}>
            <div className="text-sm font-semibold">{p.title}</div><div className="mt-1 text-xs text-muted">{p.rule}</div>
          </button>
        ))}
      </div>
      <Card className="mt-6">
        <div className="border-b border-line p-4"><h2 className="font-semibold">{data?.title ?? "…"}</h2></div>
        {error ? <div className="p-6 text-center"><ErrorNote error={error} />{error.status === 402 && <div className="mt-3"><Button href="/pricing">Upgrade</Button></div>}</div>
          : loading && !data ? <Skeleton /> : (
          <table className="w-full text-sm">
            <thead className="border-b border-line text-left text-xs uppercase text-muted"><tr><th className="p-3">Name</th><th className="p-3">{isPct ? "Premium" : "Percentile"}</th><th className="p-3">{isPct ? "Z" : "Grade"}</th><th className="p-3">{isPct ? "Half-life" : "Peer group"}</th><th className="p-3">Source</th></tr></thead>
            <tbody className="divide-y divide-line">
              {data?.rows.map(r => (
                <tr key={r.symbol + r.name}><td className="p-3"><Link href={key.startsWith("adr") ? `/monitor/adr/${r.symbol}` : `/ticker/${r.symbol}`} className="font-semibold hover:text-primary">{r.name}</Link></td>
                  <td className="p-3 num">{isPct ? pct(r.value) : r.value?.toFixed(0)}</td>
                  <td className="p-3 num">{isPct ? signed(r.z) : r.grade}</td>
                  <td className="p-3 num text-muted">{isPct ? (r.half_life_days ? `${r.half_life_days.toFixed(1)}d` : "—") : r.peer_group}</td>
                  <td className="p-3"><SourceBadge source={r.source} /></td></tr>
              ))}
              {data?.rows.length === 0 && <tr><td colSpan={5} className="p-6 text-center text-muted">No names match right now.</td></tr>}
            </tbody>
          </table>
        )}
      </Card>
      <DataNote />
      <CustomScreens />
    </div>
  );
}
