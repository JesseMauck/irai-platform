"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useState } from "react";
import { api, type HistoryPoint, type TickerPage } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { ago, compact, num, ord, pct, tone } from "@/lib/format";
import { useAuth } from "@/components/AuthProvider";
import { LineChart } from "@/components/Chart";
import { GradeChip } from "@/components/Monitors";
import { Button, Card, DataNote, Skeleton, SourceBadge } from "@/components/ui";

const RANGES = ["1mo", "3mo", "6mo", "1y", "2y", "5y"] as const;

export default function Ticker({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol: raw } = use(params);
  const symbol = decodeURIComponent(raw).toUpperCase();
  const { data, error, loading } = useApi<TickerPage>(`/api/market/ticker/${encodeURIComponent(symbol)}`, 30_000);
  const [range, setRange] = useState<(typeof RANGES)[number]>("1y");
  const { data: chart } = useApi<{ history: HistoryPoint[] }>(range === "1y" ? null : `/api/market/chart/${encodeURIComponent(symbol)}?range=${range}`);
  const hist = range === "1y" ? data?.history ?? [] : chart?.history ?? [];
  const { user } = useAuth();
  const router = useRouter();
  const [msg, setMsg] = useState<string | null>(null);

  const addToWatchlist = async () => {
    if (!user) { router.push("/login"); return; }
    try {
      const wls = await api<{ id: number }[]>("/api/me/watchlists");
      await api(`/api/me/watchlists/${wls[0].id}/items`, { method: "POST", json: { symbol } });
      setMsg("Added to your watchlist");
    } catch (e) { setMsg((e as Error).message); }
  };

  if (loading && !data) return <div className="mx-auto max-w-7xl px-4 py-12"><Skeleton rows={12} /></div>;
  if (error || !data) return (
    <div className="mx-auto max-w-3xl px-4 py-20 text-center">
      <h1 className="text-2xl font-semibold">{symbol}</h1>
      <p className="mt-3 text-muted">{error?.message ?? "No data"}. Check the symbol — non-US listings use an exchange suffix, e.g. 7203.T, BP.L, 0005.HK.</p>
    </div>
  );
  const { quote: q, info, grade } = data;
  const closes = hist.map(h => h.close);
  const first = closes[0], last = closes[closes.length - 1];
  const isEquity = (info.quote_type ?? "EQUITY") === "EQUITY";

  return (
    <div className="mx-auto max-w-7xl px-4 py-10">
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <div className="flex items-center gap-3 text-sm text-muted">
            <span>{q.exchange}</span><span>·</span><span>{q.currency}</span><SourceBadge source={q.source} />
            <span>{q.market_open ? "Market open" : "Market closed"} · updated {ago(q.market_time)}</span>
          </div>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight">{symbol} <span className="text-xl font-normal text-muted">{info.name ?? q.name}</span></h1>
          <div className="mt-2 flex items-baseline gap-3 num">
            <span className="text-4xl font-semibold">{num(q.price, q.price < 10 ? 4 : 2)}</span>
            <span className={`text-lg ${tone(q.change)}`}>{q.change != null ? `${q.change > 0 ? "+" : ""}${num(q.change)}` : ""} ({pct(q.change_pct)})</span>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={addToWatchlist}>+ Watchlist</Button>
          <Button variant="outline" href={`/lab?symbol=${encodeURIComponent(symbol)}`}>Backtest</Button>
          {isEquity && <Button href={`/valuebot?ticker=${encodeURIComponent(symbol)}`}>Value with ValueBot</Button>}
        </div>
      </div>
      {msg && <p className="mt-2 text-sm text-primary">{msg}</p>}

      <div className="mt-6 grid gap-4 lg:grid-cols-3">
        <Card className="p-4 lg:col-span-2">
          <div className="mb-2 flex items-center justify-between">
            <div className="flex gap-1">
              {RANGES.map(r => <button key={r} onClick={() => setRange(r)} className={`rounded px-2 py-1 text-xs ${r === range ? "bg-accent text-fg" : "text-muted hover:text-fg"}`}>{r.toUpperCase()}</button>)}
            </div>
            {first && <span className={`text-sm num ${tone(last - first)}`}>{pct(last / first - 1)} over {range}</span>}
          </div>
          <LineChart height={300} dates={hist.map(h => h.date)} series={[{ values: closes, color: last >= first ? "#2fbf8f" : "#f07538", label: symbol }]} format={v => num(v, v < 10 ? 3 : 2)} />
        </Card>
        <Card className="p-5">
          <h2 className="font-semibold">Key statistics</h2>
          <dl className="mt-3 grid grid-cols-2 gap-y-2 text-sm num">
            {([
              ["Day range", q.day_low && q.day_high ? `${num(q.day_low)} – ${num(q.day_high)}` : "—"],
              ["52-week range", q.fifty_two_week_low ? `${num(q.fifty_two_week_low)} – ${num(q.fifty_two_week_high)}` : "—"],
              ["Volume", compact(q.volume)],
              ["Market cap", compact(info.market_cap)],
              ["P/E (ttm)", num(info.trailing_pe, 1)], ["Forward P/E", num(info.forward_pe, 1)],
              ["EV/EBITDA", num(info.ev_ebitda, 1)], ["Price/Book", num(info.price_to_book, 2)],
              ["ROE", pct(info.roe, 1, false)], ["Operating margin", pct(info.operating_margin, 1, false)],
              ["Revenue growth", pct(info.revenue_growth, 1)], ["Beta", num(info.beta, 2)],
              ["Dividend yield", info.dividend_yield != null ? pct(info.dividend_yield > 1 ? info.dividend_yield / 100 : info.dividend_yield, 2, false) : "—"],
              ...(info.nav_price && info.quote_type === "ETF" ? [["NAV", num(info.nav_price)], ["Premium to NAV", pct(q.price / info.nav_price - 1)], ["Expense ratio", pct(info.expense_ratio, 2, false)]] : []),
            ] as [string, string][]).map(([k, v]) => <div key={k} className="contents"><dt className="text-muted">{k}</dt><dd className="text-right">{v}</dd></div>)}
          </dl>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card className="p-5 lg:col-span-2">
          <h2 className="font-semibold">About</h2>
          <p className="mt-2 text-sm text-muted">{[info.sector, info.industry, info.country].filter(Boolean).join(" · ")}</p>
          <p className="mt-3 line-clamp-6 text-sm leading-relaxed text-slate-300">{info.summary ?? "No description available."}</p>
          {info.target_mean_price && <p className="mt-3 text-sm text-muted">Analyst mean target {num(info.target_mean_price)} · consensus {info.recommendation ?? "—"}</p>}
        </Card>
        <Card className="p-5">
          <h2 className="font-semibold">Relative Value</h2>
          {grade?.locked ? <>
            <div className="mt-3 flex items-center gap-3"><GradeChip grade={grade.grade} /><span className="text-sm text-muted">in {grade.peer_group} ({grade.peer_count} names)</span></div>
            <p className="mt-3 select-none text-sm text-muted blur-sm">EV/EBITDA 00.0x vs peer median 00.0x · quality 00th</p>
            <p className="mt-3 text-sm">Percentiles, residuals and peer multiples are on <Link href="/pricing" className="text-primary">Essential</Link>.</p>
          </> : grade ? <>
            <div className="mt-3 flex items-center gap-3"><GradeChip grade={grade.grade} /><span className="text-2xl font-semibold num">{ord(grade.rv_percentile)}</span><span className="text-sm text-muted">in {grade.peer_group}</span></div>
            <p className="mt-2 text-sm text-muted">{grade.multiple_name} {grade.multiple?.toFixed(1)}x vs peer median {grade.peer_median_multiple?.toFixed(1)}x · quality {ord(grade.quality_percentile)}</p>
            <ul className="mt-3 divide-y divide-line text-sm">
              {grade.peers.map(p => (
                <li key={p.symbol} className="flex items-center justify-between py-1.5">
                  <Link href={`/ticker/${p.symbol}`} className={p.symbol === symbol ? "font-semibold text-primary" : "hover:text-primary"}>{p.symbol}</Link>
                  <span className="flex items-center gap-2 num text-muted">{p.multiple ? `${p.multiple.toFixed(1)}x` : "—"} <GradeChip grade={p.grade} /></span>
                </li>
              ))}
            </ul>
          </> : <p className="mt-2 text-sm text-muted">{symbol} isn&apos;t in a covered peer group yet. Run a ValueBot valuation for an intrinsic-value view instead.</p>}
        </Card>
      </div>
      {data.grade_history.length > 1 && (
        <Card className="mt-4 p-5">
          <h2 className="font-semibold">Relative Value history <span className="text-xs font-normal text-muted">point-in-time, never restated</span></h2>
          <LineChart height={180} dates={data.grade_history.map(h => h.as_of.slice(0, 10))} format={v => `${v.toFixed(0)}th`}
            series={[{ values: data.grade_history.map(h => h.rv_percentile), color: "#f5a524", label: "RV percentile" }]} />
        </Card>
      )}
      <DataNote />
    </div>
  );
}
