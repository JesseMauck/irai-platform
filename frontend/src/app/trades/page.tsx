"use client";
import { useState } from "react";
import { api, type Trade } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { ago, num, pct, tone } from "@/lib/format";
import { useAuth } from "@/components/AuthProvider";
import { Button, Card, ErrorNote, PageHeader, SourceBadge, TickerLink } from "@/components/ui";

export default function Trades() {
  const [status, setStatus] = useState<string>("");
  const { data, reload } = useApi<Trade[]>(`/api/community/trades${status ? `?status=${status}` : ""}`, 30_000, [status]);
  const { user } = useAuth();
  const [f, setF] = useState({ long: "", short: "", thesis: "" });
  const [err, setErr] = useState<Error | null>(null);
  const post = async () => {
    setErr(null);
    try { await api("/api/community/trades", { method: "POST", json: { long: f.long, short: f.short || null, thesis: f.thesis } }); setF({ long: "", short: "", thesis: "" }); reload(); }
    catch (e) { setErr(e as Error); }
  };
  const close = async (id: number) => { try { await api(`/api/community/trades/${id}/close`, { method: "POST" }); reload(); } catch (e) { setErr(e as Error); } };
  return (
    <div className="mx-auto max-w-5xl px-4 py-12">
      <PageHeader title="Trade feed" intro="Structured trade posts. The platform captures the live entry price when you publish, and the exit price when you close. Posts can't be edited." />
      {user && (
        <Card className="mb-6 grid gap-3 p-5 md:grid-cols-4">
          <input placeholder="Long ticker" value={f.long} onChange={e => setF({ ...f, long: e.target.value.toUpperCase() })} className="rounded-lg border border-line bg-bg px-3 py-2" />
          <input placeholder="Short leg (optional)" value={f.short} onChange={e => setF({ ...f, short: e.target.value.toUpperCase() })} className="rounded-lg border border-line bg-bg px-3 py-2" />
          <input placeholder="Thesis (why, and what would make you wrong)" value={f.thesis} onChange={e => setF({ ...f, thesis: e.target.value })} className="rounded-lg border border-line bg-bg px-3 py-2 md:col-span-2" />
          <div className="md:col-span-4"><ErrorNote error={err} /><Button onClick={post} disabled={!f.long || f.thesis.length < 10}>Publish at live price</Button></div>
        </Card>
      )}
      <div className="mb-4 flex gap-2">{["", "open", "closed"].map(s => <button key={s} onClick={() => setStatus(s)} className={`rounded-full px-3 py-1 text-sm ${s === status ? "bg-primary/15 text-primary" : "bg-card text-muted"}`}>{s || "All"}</button>)}</div>
      <div className="space-y-3">
        {(data ?? []).map(t => (
          <Card key={t.id} className="p-5">
            <div className="flex flex-wrap items-center gap-3">
              <span className="text-up">▲ <TickerLink symbol={t.long} /></span>{t.short && <span className="text-down">▼ <TickerLink symbol={t.short} /></span>}
              <span className="rounded bg-accent px-2 py-0.5 text-xs text-muted">{t.verification}</span><SourceBadge source={t.entry_source} />
              <span className="ml-auto text-sm text-muted">{t.status === "open" ? `Open · ${ago(t.created_at)}` : `Closed · ${ago(t.closed_at)}`}</span>
            </div>
            <p className="mt-2 text-sm text-fg-2">{t.thesis}</p>
            <div className="mt-2 flex items-center gap-4 text-xs text-muted num">
              <span>@{t.author}</span><span>entry {num(t.entry_long)}{t.entry_short != null && ` / ${num(t.entry_short)}`}</span>
              {t.exit_long != null && <span>exit {num(t.exit_long)}{t.exit_short != null && ` / ${num(t.exit_short)}`}</span>}
              {t.return_pct != null && <span className={`font-semibold ${tone(t.return_pct)}`}>{pct(t.return_pct)}</span>}
              {user?.is_admin && <button onClick={async () => { const reason = prompt("Reason for hiding (logged)"); if (reason) { await api(`/api/admin/moderate/trade/${t.id}`, { method: "POST", json: { action: "hide", reason } }); reload(); } }} className="text-down">Hide</button>}
              {user?.handle === t.author && t.status === "open" && <button onClick={() => close(t.id)} className="ml-auto text-primary">Close at live price</button>}
            </div>
          </Card>
        ))}
        {data?.length === 0 && <p className="text-center text-muted">No trades yet.</p>}
      </div>
    </div>
  );
}
