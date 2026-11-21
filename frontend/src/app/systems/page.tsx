"use client";
import Link from "next/link";
import { useApi } from "@/lib/hooks";
import { pct, tone } from "@/lib/format";
import { useAuth } from "@/components/AuthProvider";
import { usd } from "@/components/Bots";
import { Button, Card } from "@/components/ui";

export default function Systems() {
  const { user, ready } = useAuth();
  const pro = user?.plan === "pro";
  const { data: bots } = useApi<{ id: number; name: string; status: string; equity: number; return: number | null }[]>(pro ? "/api/bots" : null);
  const { data: accts } = useApi<{ id: number; name: string; equity: number }[]>(pro ? "/api/paper/accounts" : null);
  const { data: health } = useApi<{ status: string; market_mode?: string }>("/api/health");
  if (!ready) return null;
  if (!user) return <div className="mx-auto max-w-md px-4 py-20 text-center"><p>Sign in to manage your systems.</p><Button href="/login?next=/systems" className="mt-4">Sign in</Button></div>;
  const running = (bots ?? []).filter(b => b.status === "running").length;
  const tiles: [string, string, string][] = [
    ["Account and billing", "/account", `${user.plan[0].toUpperCase()}${user.plan.slice(1)} plan, password, data export`],
    ["Customize", "/account/customize", "Theme, accent, start page, ticker bar, defaults"],
    ["Alerts and webhooks", "/account#alerts", "Price, screen and webhook alerts"],
    ["API keys", "/account#api", pro ? "Read-only API access" : "Pro feature"],
    ["Broker connections", "/trade", "IRAI paper connected · live brokers coming soon"],
    ["Strategy marketplace", "/strategies", "Your published strategies and copies"],
  ];
  return (
    <div className="mx-auto max-w-6xl px-4 py-10">
      <h1 className="text-3xl">My systems</h1>
      <p className="mt-1 text-sm text-muted">Your automation, connections and settings in one place.</p>
      <div className="mt-6 grid gap-3 md:grid-cols-4">
        <Card className="p-4"><div className="text-[11px] text-muted">Bots running</div><div className="stat text-2xl">{pro ? `${running} / ${bots?.length ?? 0}` : "—"}</div></Card>
        <Card className="p-4"><div className="text-[11px] text-muted">Paper equity</div><div className="stat text-2xl num">{pro ? usd((accts ?? []).reduce((a, x) => a + x.equity, 0)) : "—"}</div></Card>
        <Card className="p-4"><div className="text-[11px] text-muted">Plan</div><div className="stat text-2xl capitalize">{user.plan}</div></Card>
        <Card className="p-4"><div className="text-[11px] text-muted">Platform status</div><div className={`stat text-2xl ${health?.status === "ok" ? "text-up" : "text-muted"}`}>{health?.status === "ok" ? "Operational" : health ? health.status : "…"}</div></Card>
      </div>
      {pro && bots && bots.length > 0 && <Card className="mt-4 p-5"><div className="flex items-center justify-between"><h2 className="font-semibold">Automation</h2><Link href="/bots" className="text-xs text-primary">All bots →</Link></div>
        <ul className="mt-2 divide-y divide-line text-sm">{bots.map(b => <li key={b.id} className="flex justify-between py-1.5"><Link href={`/bots/${b.id}`} className="hover:text-primary">{b.name}</Link>
          <span className="num text-xs"><span className={`mr-3 rounded px-1.5 ${b.status === "running" ? "bg-up/15 text-up" : "bg-accent text-muted"}`}>{b.status}</span>{usd(b.equity)} <span className={tone(b.return)}>{pct(b.return, 2)}</span></span></li>)}</ul></Card>}
      <div className="mt-4 grid gap-3 md:grid-cols-3">{tiles.map(([t, href, d]) => (
        <Link key={t} href={href} className="rounded-xl border border-line bg-card p-5 hover:border-primary"><div className="font-semibold">{t}</div><div className="mt-1 text-sm text-muted">{d}</div></Link>))}</div>
    </div>
  );
}
