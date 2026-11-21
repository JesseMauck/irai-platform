"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import type { Quote, TickerBarItem } from "@/lib/api";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { ago, num, pct, tone } from "@/lib/format";
import { useAuth } from "@/components/AuthProvider";
import { BuzzCard, BuzzMeter, FilingsPanel, NewsPanel, RatingsCard, TradingViewChart } from "@/components/research";
import { AdrOpportunityStrip } from "@/components/AdrOpportunities";
import { Card, SourceBadge } from "@/components/ui";

interface WL { id: number; name: string; symbols: string[]; quotes: Record<string, Quote> }
interface Trend { symbol: string; name: string | null; kind: string | null; score: number; level: string; as_of: string | null }
interface Pin { kind: string; ref: string; label: string }
interface Report { id: string; title: string; ticker: string; upside: number | null; status: string; pinned: boolean }
interface AlertEv { symbol: string; message: string; triggered_at: string }

const Panel = ({ title, right, children, className = "" }: { title: string; right?: React.ReactNode; children: React.ReactNode; className?: string }) => (
  <Card className={`flex min-h-0 flex-col p-0 ${className}`}>
    <div className="flex items-center justify-between border-b border-line px-3 py-2"><h2 className="text-xs uppercase tracking-wider text-muted">{title}</h2>{right}</div>
    <div className="min-h-0 flex-1 overflow-auto p-3">{children}</div>
  </Card>
);

export default function Terminal() {
  const { user, ready } = useAuth();
  const router = useRouter();
  useEffect(() => { if (ready && !user) router.push("/login?next=/terminal"); }, [ready, user, router]);
  const [sym, setSym] = useState("SPY");
  const [cmd, setCmd] = useState("");
  const [lower, setLower] = useState<"ratings" | "buzz" | "news" | "filings">("ratings");
  const cmdRef = useRef<HTMLInputElement>(null);
  const { data: bar } = useApi<TickerBarItem[]>("/api/market/tickerbar", 60_000);
  const { data: wls, reload: reloadWl } = useApi<WL[]>(user ? "/api/me/watchlists" : null, 30_000);
  const { data: trending } = useApi<Trend[]>("/api/buzz/trending?limit=12", 120_000);
  const { data: pins } = useApi<Pin[]>(user ? "/api/workspace/pins" : null);
  const { data: reports } = useApi<Report[]>(user ? "/api/valuebot/library" : null);
  const { data: events } = useApi<AlertEv[]>(user ? "/api/me/alerts/events" : null, 60_000);
  const { data: q } = useApi<Quote>(`/api/market/quote/${encodeURIComponent(sym)}`, 30_000);
  useEffect(() => {
    const first = wls?.[0]?.symbols?.[0];
    if (first) setSym(s => (s === "SPY" ? first : s));
  }, [wls]);
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "/" && document.activeElement?.tagName !== "INPUT" && document.activeElement?.tagName !== "TEXTAREA") { e.preventDefault(); cmdRef.current?.focus(); } };
    window.addEventListener("keydown", k); return () => window.removeEventListener("keydown", k);
  }, []);
  const run = async (raw: string) => {
    const parts = raw.trim().toUpperCase().split(/\s+/);
    if (!parts[0]) return;
    const [verb, ...rest] = parts;
    if (verb === "CMP" || verb === "COMPARE") router.push(`/compare?symbols=${rest.join(",")}`);
    else if (verb === "VB" || verb === "VALUE") router.push(`/valuebot?ticker=${rest[0] ?? sym}`);
    else if (verb === "MC") router.push(`/lab/montecarlo?symbol=${rest[0] ?? sym}`);
    else if (verb === "BT") router.push(`/lab?symbol=${rest[0] ?? sym}`);
    else if (verb === "DES" || verb === "GO") router.push(`/ticker/${rest[0] ?? sym}`);
    else if (verb === "ADD" && wls?.[0]) { await api(`/api/me/watchlists/${wls[0].id}/items`, { method: "POST", json: { symbol: rest[0] ?? sym } }).catch(() => {}); reloadWl(); }
    else setSym(verb);
    setCmd("");
  };
  if (!user) return null;
  const wl = wls?.[0];
  return (
    <div className="mx-auto max-w-[1600px] px-3 py-4">
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <form onSubmit={e => { e.preventDefault(); run(cmd); }} className="flex flex-1 items-center gap-2 rounded-lg border border-line bg-card px-3 py-2">
          <span className="font-mono text-primary">&gt;</span>
          <input ref={cmdRef} value={cmd} onChange={e => setCmd(e.target.value)} aria-label="Command"
            placeholder="Ticker to load (AAPL) · CMP AAPL MSFT · VB NVDA · MC TSLA · BT SPY · ADD AMD · DES KO   — press / to focus"
            className="w-full bg-transparent font-mono text-sm outline-none" />
        </form>
        <div className="flex gap-2 text-sm"><Link href="/research" className="rounded-lg border border-line px-3 py-2 hover:bg-accent">Research</Link><Link href="/compare" className="rounded-lg border border-line px-3 py-2 hover:bg-accent">Compare</Link><Link href="/screeners" className="rounded-lg border border-line px-3 py-2 hover:bg-accent">Screeners</Link></div>
      </div>
      <div className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-9">
        {(bar ?? []).map(b => (
          <button key={b.symbol} onClick={() => setSym(b.symbol)} className={`rounded-lg border p-2 text-left ${sym === b.symbol ? "border-primary" : "border-line"} bg-card`}>
            <div className="flex items-center justify-between text-[11px] text-muted"><span>{b.label}</span><SourceBadge source={b.source} /></div>
            <div className="num text-sm">{num(b.price, b.price < 10 ? 3 : 2)} <span className={`text-xs ${tone(b.change_pct)}`}>{pct(b.change_pct)}</span></div>
          </button>))}
      </div>
      <div className="grid gap-3 lg:grid-cols-[280px_1fr_320px]">
        <div className="space-y-3">
          <Panel title={wl?.name ?? "Watchlist"} right={<Link href="/account" className="text-[11px] text-primary">Edit</Link>} className="max-h-[420px]">
            {!wl?.symbols.length ? <p className="text-sm text-muted">Type <span className="font-mono">ADD AAPL</span> above to build your watchlist.</p> : (
              <table className="w-full text-sm"><tbody>{wl.symbols.map(s => { const x = wl.quotes?.[s]; return (
                <tr key={s} onClick={() => setSym(s)} className={`cursor-pointer ${sym === s ? "bg-accent" : "hover:bg-accent/50"}`}>
                  <td className="py-1 pl-1 font-medium">{s}</td><td className="text-right num">{num(x?.price)}</td><td className={`pr-1 text-right num ${tone(x?.change_pct)}`}>{pct(x?.change_pct, 1)}</td></tr>); })}</tbody></table>)}
          </Panel>
          <Panel title="Pinned" right={<Link href="/research" className="text-[11px] text-primary">Workspace</Link>}>
            {!pins?.length ? <p className="text-sm text-muted">Pin themes, tickers and lists from the research workspace.</p> : (
              <ul className="space-y-1 text-sm">{pins.map(p => <li key={p.kind + p.ref}>{p.kind === "ticker" ? <button onClick={() => setSym(p.ref)} className="hover:text-primary">{p.label}</button>
                : <Link href={p.kind === "theme" ? `/research/themes/${p.ref}` : "/account"} className="hover:text-primary">{p.label}</Link>} <span className="text-[10px] uppercase text-muted">{p.kind}</span></li>)}</ul>)}
          </Panel>
          <Panel title="Alerts fired">
            {!events?.length ? <p className="text-sm text-muted">No alerts yet. Set them on your <Link href="/account" className="text-primary">account</Link>.</p> :
              <ul className="space-y-1 text-xs">{events.slice(0, 10).map(e => <li key={e.symbol + e.triggered_at}><span className="font-medium">{e.symbol}</span> {e.message} <span className="text-muted">{ago(e.triggered_at)}</span></li>)}</ul>}
          </Panel>
        </div>
        <div className="space-y-3">
          <Card className="p-3">
            <div className="mb-2 flex flex-wrap items-center gap-3">
              <Link href={`/ticker/${encodeURIComponent(sym)}`} className="text-lg font-semibold hover:text-primary">{sym}</Link>
              <span className="truncate text-sm text-muted">{q?.name}</span>
              {q && <span className="num">{num(q.price)} <span className={tone(q.change_pct)}>{pct(q.change_pct)}</span></span>}
              {q && <SourceBadge source={q.source} />}
              <span className="ml-auto flex gap-2 text-xs">
                <Link href={`/valuebot?ticker=${sym}`} className="rounded border border-line px-2 py-1 hover:bg-accent">ValueBot</Link>
                <Link href={`/lab/montecarlo?symbol=${sym}`} className="rounded border border-line px-2 py-1 hover:bg-accent">Monte Carlo</Link>
                <Link href={`/lab?symbol=${sym}`} className="rounded border border-line px-2 py-1 hover:bg-accent">Backtest</Link>
                <Link href={`/community/write?ticker=${sym}`} className="rounded border border-line px-2 py-1 hover:bg-accent">Write analysis</Link>
              </span>
            </div>
            <TradingViewChart symbol={sym} height={460} />
          </Card>
          <div className="flex gap-1 text-sm">{(["ratings", "buzz", "news", "filings"] as const).map(t => <button key={t} onClick={() => setLower(t)} className={`rounded-md px-3 py-1 capitalize ${lower === t ? "bg-accent text-fg" : "text-muted"}`}>{t}</button>)}</div>
          {lower === "ratings" && <RatingsCard symbol={sym} />}
          {lower === "buzz" && <BuzzCard symbol={sym} />}
          {lower === "news" && <NewsPanel symbol={sym} />}
          {lower === "filings" && <FilingsPanel symbol={sym} limit={15} />}
        </div>
        <div className="space-y-3">
          <Panel title="Most talked about" right={<span className="text-[10px] text-muted">buzz 0–100</span>} className="max-h-[420px]">
            {!trending?.length ? <p className="text-sm text-muted">The buzz scanner fills this list as it runs.</p> : (
              <ul className="space-y-2">{trending.map(t => <li key={t.symbol}><button onClick={() => setSym(t.symbol)} className="w-full text-left">
                <div className="flex justify-between text-sm"><span className="font-medium">{t.symbol}</span><span className="truncate pl-2 text-[11px] text-muted">{t.name}</span></div>
                <BuzzMeter score={t.score} level={t.level} /></button></li>)}</ul>)}
          </Panel>
          <Panel title="My ValueBot reports" right={<Link href="/valuebot/reports" className="text-[11px] text-primary">All</Link>}>
            {!reports?.length ? <p className="text-sm text-muted"><Link href="/valuebot" className="text-primary">Value a company</Link> to start your library.</p> : (
              <ul className="space-y-1 text-sm">{reports.slice(0, 8).map(r => <li key={r.id} className="flex justify-between gap-2"><Link href={`/valuebot/${r.id}`} className="truncate hover:text-primary">{r.pinned ? "★ " : ""}{r.title}</Link>
                <span className={`num ${tone(r.upside)}`}>{r.status === "done" ? pct(r.upside, 0) : r.status}</span></li>)}</ul>)}
          </Panel>
        </div>
      </div>
      <section className="mt-4"><h2 className="mb-2 text-xs uppercase tracking-wider text-muted">ADR scanner</h2><AdrOpportunityStrip minZ={1.5} /></section>
      <p className="mt-4 text-[11px] text-muted">Every figure carries its source badge. Research and education only — not investment advice.</p>
    </div>
  );
}
