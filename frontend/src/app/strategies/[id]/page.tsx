"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { pct, tone } from "@/lib/format";
import { useAuth } from "@/components/AuthProvider";
import { usd } from "@/components/Bots";
import { LineChart } from "@/components/Chart";
import { Button, Card, ErrorNote, Skeleton } from "@/components/ui";
import type { Listing } from "../page";

interface Detail extends Listing { backtest_series?: { dates: string[]; equity: number[]; bench: number[] | null }; backtest_full?: Record<string, number | null> }

export default function ListingPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const { user } = useAuth();
  const { data: x, error } = useApi<Detail>(`/api/marketplace/${id}`);
  const pro = user?.plan === "pro";
  const { data: accts } = useApi<{ id: number; name: string; cash: number }[]>(pro ? "/api/paper/accounts" : null);
  const [acct, setAcct] = useState<number | null>(null);
  const [cap, setCap] = useState("10000");
  const [err, setErr] = useState<Error | null>(null);
  const [busy, setBusy] = useState(false);
  if (error) return <div className="mx-auto max-w-3xl px-4 py-16 text-center text-muted">{error.message}</div>;
  if (!x) return <div className="mx-auto max-w-5xl px-4 py-12"><Skeleton rows={10} /></div>;
  const c = x.config as Record<string, unknown>;
  const copy = async () => {
    const a = acct ?? accts?.[0]?.id; if (!a) return;
    setBusy(true); setErr(null);
    try { const b = await api<{ id: number }>(`/api/marketplace/${id}/copy`, { method: "POST", json: { accounts: [{ account_id: a, capital: parseFloat(cap.replace(/[,$]/g, "")) }] } }); router.push(`/bots/${b.id}`); }
    catch (e) { setErr(e as Error); setBusy(false); }
  };
  const s = x.backtest_series;
  return (
    <div className="mx-auto max-w-6xl px-4 py-10">
      <Link href="/strategies" className="text-sm text-muted hover:text-fg">← Strategy marketplace</Link>
      <div className="mt-3 flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-3xl"><h1 className="text-3xl">{x.title}</h1>
          <div className="mt-1 text-sm text-muted">by @{x.author.handle}{x.author.verified && " ✓ verified trader"} · {x.category.replace("-", " ")} · {x.copies} cop{x.copies === 1 ? "y" : "ies"}</div></div>
        <div className="text-right"><div className="stat text-3xl">{x.price_monthly ? `$${x.price_monthly}` : "Free"}</div>{x.price_monthly > 0 && <div className="text-xs text-muted">per month</div>}</div>
      </div>
      <div className="mt-6 grid gap-4 lg:grid-cols-3">
        <Card className="p-5 lg:col-span-2">
          <p className="whitespace-pre-line text-sm leading-relaxed">{x.summary}</p>
          {s && s.dates.length > 1 && <div className="mt-4"><div className="text-xs text-muted">Backtest equity ($100k)</div>
            <LineChart height={220} dates={s.dates} format={v => usd(v)} series={[{ values: s.equity, color: "#E0605A", label: "Strategy" }, ...(s.bench ? [{ values: s.bench, color: "#8a94a6", dashed: true, label: "SPY" }] : [])]} /></div>}
          <div className="mt-4 grid grid-cols-3 gap-3 text-center text-sm num md:grid-cols-6">
            {([["CAGR", x.backtest.cagr], ["Total", x.backtest.total_return], ["Volatility", x.backtest.volatility], ["Max DD", x.backtest.max_drawdown], ["Sharpe", null], ["In market", x.backtest.exposure]] as [string, number | null][]).map(([k, v]) =>
              <div key={k}><div className="text-[10px] text-muted">{k}</div><div>{k === "Sharpe" ? (x.backtest.sharpe?.toFixed(2) ?? "—") : pct(v, 1)}</div></div>)}
          </div>
          {x.live && <p className="mt-3 text-sm">Live paper record since {x.live.since}: <b className={tone(x.live.total_return)}>{pct(x.live.total_return, 2)}</b> over {x.live.days} days, max drawdown {pct(x.live.max_drawdown, 1)}.</p>}
        </Card>
        <Card className="p-5">
          <h2 className="font-semibold">Configuration</h2>
          <dl className="mt-2 grid grid-cols-2 gap-y-1 text-sm"><dt className="text-muted">Type</dt><dd>{c.mode === "webhook" ? "Webhook signals" : String(c.strategy)}</dd>
            <dt className="text-muted">Symbols</dt><dd>{(c.symbols as string[])?.join(", ") || "any"}</dd>
            <dt className="text-muted">Parameters</dt><dd>{Object.entries((c.params as Record<string, number>) || {}).map(([k, v]) => `${k} ${v}`).join(", ") || "defaults"}</dd>
            <dt className="text-muted">Stop-loss</dt><dd>{c.stop_loss_pct ? pct(c.stop_loss_pct as number, 0, false) : "none"}</dd>
            <dt className="text-muted">Take-profit</dt><dd>{c.take_profit_pct ? pct(c.take_profit_pct as number, 0, false) : "none"}</dd>
            <dt className="text-muted">Daily close</dt><dd>{c.daily_auto_close ? "yes" : "no"}</dd></dl>
          <div className="mt-5 border-t border-line pt-4">
            {!user ? <Button href={`/login?next=/strategies/${id}`}>Sign in to copy</Button>
              : !pro ? <><p className="text-sm text-muted">Copying strategies into paper bots is part of Pro.</p><Button className="mt-2" href="/pricing">See Pro</Button></>
              : x.price_monthly > 0 ? <p className="text-sm text-muted">Paid strategies open when creator payouts launch. We&apos;ll let you know.</p>
              : !accts?.length ? <><p className="text-sm text-muted">Create a paper account first.</p><Button className="mt-2" href="/bots">Paper accounts</Button></>
              : <><h3 className="text-sm font-semibold">Copy to a paper account</h3>
                <select value={acct ?? accts[0].id} onChange={e => setAcct(parseInt(e.target.value))} className="mt-2 w-full rounded border border-line bg-bg px-2 py-1.5 text-sm">{accts.map(a => <option key={a.id} value={a.id}>{a.name} ({usd(a.cash)} free)</option>)}</select>
                <input value={cap} onChange={e => setCap(e.target.value)} className="mt-2 w-full rounded border border-line bg-bg px-2 py-1.5 text-sm num" placeholder="Capital" />
                <Button className="mt-3 w-full" onClick={copy} disabled={busy}>{busy ? "Copying…" : "Copy strategy"}</Button></>}
            <ErrorNote error={err} />
          </div>
        </Card>
      </div>
      <p className="mt-6 text-[11px] text-muted">Published by a member, not Irradiance; not a recommendation. Backtests and paper results are hypothetical and don&apos;t guarantee future results.</p>
    </div>
  );
}
