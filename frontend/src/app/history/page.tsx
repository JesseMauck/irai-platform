"use client";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { useApi } from "@/lib/hooks";
import { ago } from "@/lib/format";
import { openIrai } from "@/lib/assistant";
import { useAuth } from "@/components/AuthProvider";
import { Button, Card, Skeleton } from "@/components/ui";

interface Ev { at: string | null; kind: string; title: string; detail?: string; href: string; chat_id?: number }
const KINDS: Record<string, string> = { all: "Everything", chat: "IRAI chats", trade: "Bot trades", signal: "Webhook signals", valuation: "Valuations", analyst: "Analyst Bot", lab: "Lab" };

export default function HistoryPage() { return <Suspense fallback={null}><History /></Suspense>; }

function History() {
  const { user, ready } = useAuth();
  const [kind, setKind] = useState(useSearchParams().get("kind") ?? "all");
  const { data } = useApi<Ev[]>(user ? "/api/me/history" : null);
  if (!ready) return null;
  if (!user) return <div className="mx-auto max-w-md px-4 py-20 text-center"><p>Sign in to see your history.</p><Button href="/login?next=/history" className="mt-4">Sign in</Button></div>;
  const rows = (data ?? []).filter(e => kind === "all" || e.kind === kind);
  return (
    <div className="mx-auto max-w-4xl px-4 py-10">
      <h1 className="text-3xl">History</h1>
      <p className="mt-1 text-sm text-muted">Your recent activity across Irradiance, newest first.</p>
      <div className="mt-5 flex flex-wrap gap-1.5 text-xs">{Object.entries(KINDS).map(([k, l]) => <button key={k} onClick={() => setKind(k)} className={`rounded-full border px-3 py-1 ${kind === k ? "border-primary bg-primary/10" : "border-line text-muted"}`}>{l}</button>)}</div>
      {!data ? <div className="mt-6"><Skeleton rows={10} /></div> : !rows.length ? <Card className="mt-6 p-8 text-center text-sm text-muted">Nothing here yet.</Card> : (
        <Card className="mt-5 p-0"><ul className="divide-y divide-line">{rows.map((e, i) => (
          <li key={i} className="flex items-start justify-between gap-3 px-5 py-3 text-sm">
            <div><span className="mr-2 rounded bg-accent px-1.5 py-0.5 text-[10px] uppercase text-muted">{KINDS[e.kind]?.replace(/s$/, "") ?? e.kind}</span>
              {e.chat_id ? <button onClick={() => openIrai({ chatId: e.chat_id })} className="hover:text-primary">{e.title}</button> : <Link href={e.href} className="hover:text-primary">{e.title}</Link>}
              {e.detail && <span className="ml-2 text-[11px] text-muted">{e.detail}</span>}</div>
            <span className="shrink-0 text-[11px] text-muted">{e.at ? ago(e.at) : ""}</span></li>))}</ul></Card>)}
    </div>
  );
}
