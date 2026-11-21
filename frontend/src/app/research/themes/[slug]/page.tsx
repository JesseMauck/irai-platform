"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { ago, compact, num, pct, tone } from "@/lib/format";
import { LineChart, Sparkline } from "@/components/Chart";
import { PinButton, ThemeEditor, type Theme } from "@/components/Workspace";
import { SourceLine } from "@/components/research";
import { useAuth } from "@/components/AuthProvider";
import { Button, Card, ErrorNote, Skeleton, SourceBadge } from "@/components/ui";

interface Row {
  symbol: string; name: string | null; price: number | null; change_pct: number | null; ret_1m: number | null; ret_3m: number | null; ret_ytd: number | null; ret_1y: number | null;
  volatility: number | null; max_drawdown: number | null; from_high: number | null; above_50d: boolean; above_200d: boolean; market_cap: number | null; forward_pe: number | null;
  ev_ebitda: number | null; revenue_growth: number | null; operating_margin: number | null; dividend_yield: number | null; beta: number | null; sector: string | null;
  source: string; buzz: { score: number; level: string } | null;
}
interface Stats { ret_1m: number | null; ret_3m: number | null; ret_ytd: number | null; ret_1y: number | null; volatility: number | null; max_drawdown?: number | null; beta_vs_bench?: number | null; corr_vs_bench?: number | null }
interface Detail extends Theme {
  constituents: Row[];
  breadth: { above_50d_pct: number | null; above_200d_pct: number | null; advancing_pct: number | null; median_1m: number | null; dispersion_1m: number | null; count: number };
  index: { series: { date: string; theme: number; bench?: number }[]; stats: Stats; bench: (Stats & { symbol: string; source: string }) | null; method: string };
  correlation: { avg_pairwise_6m: number | null; pairs: number };
  valuation: { median_forward_pe: number | null; median_ev_ebitda: number | null; median_revenue_growth: number | null; median_operating_margin: number | null; median_dividend_yield: number | null; total_market_cap: number | null };
  leaders: { symbol: string; ret_1m: number }[]; laggards: { symbol: string; ret_1m: number }[]; sectors: { sector: string; count: number }[];
  drivers: { name: string; why: string; symbol?: string; reading: { symbol: string; price: number | null; change_pct: number | null; source: string; ret_1m?: number | null; ret_3m?: number | null; spark?: number[] } | null }[];
}
interface Pestel { theme_tone?: number | null; cached_at?: string | null; computed_at?: string; factors: { key: string; label: string; attention: number | null; tone: number | null; articles_7d_avg?: number | null; articles_30d_avg?: number | null; error?: string;
  headlines: { title: string; url: string; domain: string; seen: string }[] }[]; provider: { label: string; url: string }; source: string; note?: string }
interface News { headlines: { title: string; url: string; source: string; symbol: string; published_iso: string | null }[]; catalysts: { symbol: string; date: string; eps_estimate: number | null }[]; source: string; provider: { label: string }; as_of: string }

const attnLabel = (a: number | null) => a == null ? "—" : a >= 2 ? "Very high" : a >= 1.5 ? "High" : a >= 0.8 ? "Normal" : "Low";
type View = "performance" | "risk" | "valuation";
const COLS: Record<View, [keyof Row, string, (v: number | null) => string, boolean?][]> = {
  performance: [["change_pct", "Day", v => pct(v), true], ["ret_1m", "1M", v => pct(v, 1), true], ["ret_3m", "3M", v => pct(v, 1), true], ["ret_ytd", "YTD", v => pct(v, 1), true], ["ret_1y", "1Y", v => pct(v, 1), true], ["from_high", "From 52w high", v => pct(v, 1), true]],
  risk: [["volatility", "Volatility", v => pct(v, 0, false)], ["max_drawdown", "Max drawdown", v => pct(v, 1), true], ["beta", "Beta", v => num(v, 2)], ["from_high", "From high", v => pct(v, 1), true]],
  valuation: [["market_cap", "Mkt cap", v => compact(v)], ["forward_pe", "Fwd P/E", v => num(v, 1)], ["ev_ebitda", "EV/EBITDA", v => num(v, 1)], ["revenue_growth", "Rev growth", v => pct(v, 1), true], ["operating_margin", "Op margin", v => pct(v, 1, false)], ["dividend_yield", "Yield", v => pct(v, 2, false)]],
};

export default function ThemePage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params);
  const router = useRouter();
  const { prefs } = useAuth();
  const { data: t, error, reload } = useApi<Detail>(`/api/workspace/themes/${slug}?bench=${prefs.benchmark}`, 120_000);
  const { data: p } = useApi<Pestel>(`/api/workspace/themes/${slug}/pestel`);
  const { data: news } = useApi<News>(`/api/workspace/themes/${slug}/news`);
  const [editing, setEditing] = useState(false);
  const [err, setErr] = useState<Error | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [view, setView] = useState<View>("performance");
  const [sort, setSort] = useState<{ k: keyof Row; d: 1 | -1 }>({ k: "ret_1m", d: -1 });
  const rows = useMemo(() => [...(t?.constituents ?? [])].sort((a, b) => {
    const x = a[sort.k] as number | null, y = b[sort.k] as number | null;
    return x == null ? 1 : y == null ? -1 : (x - y) * sort.d;
  }), [t, sort]);
  if (error) return <div className="mx-auto max-w-3xl px-4 py-16 text-center text-muted">{error.message}</div>;
  if (!t) return <div className="mx-auto max-w-6xl px-4 py-12"><Skeleton rows={12} /></div>;
  const del = async () => { if (!confirm("Delete this theme?")) return; try { await api(`/api/workspace/themes/${slug}`, { method: "DELETE" }); router.push("/research"); } catch (e) { setErr(e as Error); } };
  const b = t.breadth, s = t.index.stats, bench = t.index.bench, v = t.valuation;
  const regime = b.above_50d_pct == null ? "—" : b.above_50d_pct >= 0.65 ? "Broad strength: most names above their 50-day average" : b.above_50d_pct <= 0.35 ? "Broad weakness: most names below their 50-day average" : "Mixed: leadership is narrow";
  const rel = s.ret_1y != null && bench?.ret_1y != null ? s.ret_1y - bench.ret_1y : null;
  const corr = t.correlation.avg_pairwise_6m;
  const tone7 = p?.theme_tone ?? null;
  const hot = (p?.factors ?? []).filter(f => (f.attention ?? 0) >= 1.5).map(f => f.label);
  const sortBy = (k: keyof Row) => setSort(o => ({ k, d: o.k === k ? (o.d === 1 ? -1 : 1) : -1 }));

  return (
    <div className="mx-auto max-w-6xl px-4 py-10">
      <Link href="/research" className="text-sm text-muted hover:text-fg">← Research workspace</Link>
      <div className="mt-3 flex flex-wrap items-start justify-between gap-3">
        <div><h1 className="text-3xl">{t.name} <PinButton kind="theme" refId={t.slug} pinned={t.pinned} /></h1><p className="mt-1 max-w-3xl text-muted">{t.description}</p>
          {t.keywords?.length > 0 && <div className="mt-2 flex flex-wrap gap-1">{t.keywords.map(k => <span key={k} className="rounded-full bg-accent px-2 py-0.5 text-[11px] text-muted">{k}</span>)}</div>}</div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" href={`/compare?symbols=${t.tickers.slice(0, 8).join(",")}`}>Compare constituents</Button>
          <Button variant="outline" href={`/lab/montecarlo?symbols=${t.tickers.slice(0, 8).join(",")}`}>Monte Carlo basket</Button>
          {t.mine && <><Button variant="outline" onClick={() => setEditing(true)}>Edit</Button><Button variant="ghost" onClick={del}>Delete</Button></>}
        </div>
      </div>
      <ErrorNote error={err} />
      {editing && <div className="mt-4"><ThemeEditor initial={t} onSaved={() => { setEditing(false); reload(); }} onCancel={() => setEditing(false)} /></div>}

      <Card className="mt-5 p-4 text-sm">
        <div className="text-xs font-semibold uppercase tracking-wide text-muted">Theme read-out</div>
        <p className="mt-1 leading-relaxed">
          The equal-weight {t.name} basket is <b className={tone(s.ret_1y)}>{pct(s.ret_1y, 1)}</b> over 12 months{bench && <> versus <b className={tone(bench.ret_1y)}>{pct(bench.ret_1y, 1)}</b> for {bench.symbol} ({rel != null ? <span className={tone(rel)}>{rel >= 0 ? "outperforming" : "lagging"} by {pct(Math.abs(rel), 1, false)}</span> : "—"})</>}.
          {" "}{regime}. {corr != null && <>Constituents move {corr > 0.6 ? "closely together" : corr > 0.35 ? "moderately together" : "fairly independently"} (average correlation {num(corr, 2)}), {corr > 0.6 ? "so the basket behaves like a single bet" : "which gives some diversification inside the theme"}. </>}
          {hot.length > 0 ? <>News attention is elevated for {hot.join(", ")}.</> : p ? <>News attention is near normal across PESTEL factors.</> : null}
        </p>
      </Card>

      <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
        <Kpi k="1-year return" v={pct(s.ret_1y, 1)} c={tone(s.ret_1y)} sub={bench ? `${bench.symbol} ${pct(bench.ret_1y, 1)}` : ""} />
        <Kpi k="YTD" v={pct(s.ret_ytd, 1)} c={tone(s.ret_ytd)} sub={bench ? `${bench.symbol} ${pct(bench.ret_ytd, 1)}` : ""} />
        <Kpi k="Volatility" v={pct(s.volatility, 0, false)} sub={`beta ${num(s.beta_vs_bench, 2)} vs ${bench?.symbol ?? "—"}`} />
        <Kpi k="Above 50 / 200-day" v={`${pct(b.above_50d_pct, 0, false)} / ${pct(b.above_200d_pct, 0, false)}`} sub={`${b.count} names · ${pct(b.advancing_pct, 0, false)} up today`} />
        <Kpi k="Median forward P/E" v={num(v.median_forward_pe, 1)} sub={`EV/EBITDA ${num(v.median_ev_ebitda, 1)}`} />
        <Kpi k="News tone (7d)" v={tone7 == null ? "—" : tone7.toFixed(1)} c={tone(tone7)} sub="GDELT, −10 to +10" />
      </div>

      <Card className="mt-4 p-5">
        <div className="flex flex-wrap items-baseline justify-between gap-2"><h2 className="font-semibold">Theme index vs {bench?.symbol ?? "benchmark"}</h2><span className="text-xs text-muted">rebased to 100</span></div>
        {t.index.series.length > 1 ? <LineChart height={240} dates={t.index.series.map(x => x.date)} format={x => x.toFixed(1)}
          series={[{ values: t.index.series.map(x => x.theme), color: "#E0605A", label: t.name }, { values: t.index.series.map(x => x.bench ?? null), color: "#8a94a6", dashed: true, label: bench?.symbol ?? "" }]} />
          : <p className="mt-2 text-sm text-muted">Not enough price history yet.</p>}
        <div className="mt-3 overflow-x-auto"><table className="w-full min-w-[560px] text-sm num">
          <thead className="text-xs text-muted"><tr><th className="text-left font-normal" /><th className="text-right font-normal">1M</th><th className="text-right font-normal">3M</th><th className="text-right font-normal">YTD</th><th className="text-right font-normal">1Y</th><th className="text-right font-normal">Volatility</th><th className="text-right font-normal">Max drawdown</th></tr></thead>
          <tbody className="divide-y divide-line">
            {[{ n: "Theme (equal weight)", x: s }, ...(bench ? [{ n: bench.symbol, x: bench as Stats }] : [])].map(({ n, x }) => (
              <tr key={n}><td className="py-1.5">{n}</td>{[x.ret_1m, x.ret_3m, x.ret_ytd, x.ret_1y].map((r, i) => <td key={i} className={`text-right ${tone(r)}`}>{pct(r, 1)}</td>)}
                <td className="text-right">{pct(x.volatility, 0, false)}</td><td className="text-right text-down">{x.max_drawdown != null ? pct(x.max_drawdown, 1) : "—"}</td></tr>))}
          </tbody></table></div>
        <p className="mt-2 text-[11px] text-muted">{t.index.method} Hypothetical basket for research; not an investable index.</p>
      </Card>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card className="p-5"><h2 className="font-semibold">Leaders and laggards <span className="text-xs font-normal text-muted">1 month</span></h2>
          <ul className="mt-3 space-y-1.5 text-sm">{t.leaders.map(x => <li key={x.symbol} className="flex justify-between"><Link href={`/ticker/${x.symbol}`} className="hover:text-primary">{x.symbol}</Link><span className="num text-up">{pct(x.ret_1m, 1)}</span></li>)}</ul>
          {t.laggards.length > 0 && <ul className="mt-3 space-y-1.5 border-t border-line pt-3 text-sm">{t.laggards.map(x => <li key={x.symbol} className="flex justify-between"><Link href={`/ticker/${x.symbol}`} className="hover:text-primary">{x.symbol}</Link><span className={`num ${tone(x.ret_1m)}`}>{pct(x.ret_1m, 1)}</span></li>)}</ul>}
          <p className="mt-3 text-[11px] text-muted">Dispersion (spread of 1-month returns): {pct(b.dispersion_1m, 1, false)}. High dispersion means stock selection matters more than the theme call.</p>
        </Card>
        <Card className="p-5"><h2 className="font-semibold">Fundamentals (medians)</h2>
          <dl className="mt-3 grid grid-cols-2 gap-y-2 text-sm num">
            {([["Forward P/E", num(v.median_forward_pe, 1)], ["EV/EBITDA", num(v.median_ev_ebitda, 1)], ["Revenue growth", pct(v.median_revenue_growth, 1)], ["Operating margin", pct(v.median_operating_margin, 1, false)], ["Dividend yield", pct(v.median_dividend_yield, 2, false)], ["Combined market cap", compact(v.total_market_cap)]] as [string, string][]).map(([k, x]) => <div key={k} className="contents"><dt className="text-muted">{k}</dt><dd className="text-right">{x}</dd></div>)}
          </dl>
          {t.sectors.length > 0 && <div className="mt-3 border-t border-line pt-3"><div className="text-xs text-muted">Sector mix</div>
            <div className="mt-1.5 flex flex-wrap gap-1">{t.sectors.map(x => <span key={x.sector} className="rounded bg-accent px-2 py-0.5 text-[11px]">{x.sector} · {x.count}</span>)}</div></div>}
        </Card>
        <Card className="p-5"><h2 className="font-semibold">Upcoming catalysts</h2>
          {!news ? <Skeleton rows={4} /> : !news.catalysts.length ? <p className="mt-2 text-sm text-muted">No scheduled earnings dates found for the largest constituents.</p> : (
            <ul className="mt-3 space-y-1.5 text-sm">{news.catalysts.slice(0, 8).map(c => <li key={c.symbol} className="flex justify-between"><span><Link href={`/ticker/${c.symbol}#earnings`} className="font-medium hover:text-primary">{c.symbol}</Link> earnings</span><span className="num text-muted">{c.date}{c.eps_estimate != null && ` · est ${num(c.eps_estimate)}`}</span></li>)}</ul>)}
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card className="p-5">
          <h2 className="font-semibold">Key drivers</h2>
          {!t.drivers.length ? <p className="mt-2 text-sm text-muted">No drivers yet.</p> : (
            <ul className="mt-3 divide-y divide-line">{t.drivers.map(d => (
              <li key={d.name} className="py-2.5">
                <div className="flex items-center justify-between gap-2"><span className="font-medium">{d.name}</span>
                  {d.reading && <Link href={`/ticker/${encodeURIComponent(d.reading.symbol)}`} className="flex items-center gap-2 text-sm num hover:text-primary">
                    {d.reading.spark && d.reading.spark.length > 5 && <Sparkline values={d.reading.spark} width={70} height={20} />}
                    {d.reading.symbol} {num(d.reading.price)} <span className={tone(d.reading.change_pct)}>{pct(d.reading.change_pct)}</span><SourceBadge source={d.reading.source} /></Link>}</div>
                <p className="text-sm text-muted">{d.why}</p>
                {d.reading?.ret_3m != null && <p className="text-[11px] text-muted num">1M <span className={tone(d.reading.ret_1m)}>{pct(d.reading.ret_1m, 1)}</span> · 3M <span className={tone(d.reading.ret_3m)}>{pct(d.reading.ret_3m, 1)}</span></p>}
              </li>))}</ul>)}
        </Card>
        <Card className="p-5">
          <h2 className="font-semibold">PESTEL radar <span className="text-xs font-normal text-muted">news attention vs the 30-day norm</span></h2>
          {!p ? <Skeleton rows={6} /> : (
            <ul className="mt-3 divide-y divide-line">{p.factors.map(f => (
              <li key={f.key} className="py-2">
                <button onClick={() => setOpen(open === f.key ? null : f.key)} className="flex w-full items-center gap-3 text-left">
                  <span className="w-28 text-sm">{f.label}</span>
                  <div className="h-2 flex-1 rounded bg-accent"><div className="h-2 rounded" style={{ width: `${Math.min(100, (f.attention ?? 0) * 40)}%`, background: (f.attention ?? 0) >= 1.5 ? "#f07538" : "#2fbf8f" }} /></div>
                  <span className="w-20 text-right text-xs">{attnLabel(f.attention)}</span>
                  <span className="w-16 text-right text-[11px] text-muted num">{f.articles_7d_avg != null ? `${f.articles_7d_avg.toFixed(0)}/day` : ""}</span>
                </button>
                {open === f.key && (f.headlines.length ? <ul className="mt-2 space-y-1 pl-28 text-sm">{f.headlines.map(h => <li key={h.url}><a href={h.url} target="_blank" rel="noopener noreferrer" className="hover:text-primary">{h.title}</a> <span className="text-[11px] text-muted">{h.domain}</span></li>)}</ul>
                  : <p className="mt-1 pl-28 text-xs text-muted">{f.error ? `Unavailable (${f.error})` : "No headlines this week."}</p>)}
              </li>))}</ul>)}
          {p?.note && <p className="mt-2 text-[11px] text-muted">{p.note} Click a factor to see its headlines.</p>}
          <SourceLine provider={p?.provider} source={p?.source} asOf={p?.cached_at ?? p?.computed_at} />
        </Card>
      </div>

      <Card className="mt-4 p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-semibold">Constituents</h2>
          <div className="flex gap-1 rounded bg-accent p-0.5 text-xs">{(["performance", "risk", "valuation"] as View[]).map(x =>
            <button key={x} onClick={() => setView(x)} className={`rounded px-2.5 py-1 capitalize ${view === x ? "bg-card text-fg shadow-sm" : "text-muted"}`}>{x}</button>)}</div>
        </div>
        <div className="mt-3 overflow-x-auto"><table className="w-full min-w-[720px] text-sm">
          <thead className="text-xs text-muted"><tr><th className="py-1 text-left font-normal">Ticker</th><th className="text-right font-normal">Price</th>
            {COLS[view].map(([k, label]) => <th key={k} className="text-right font-normal"><button onClick={() => sortBy(k)} className="hover:text-fg">{label}{sort.k === k ? (sort.d === 1 ? " ↑" : " ↓") : ""}</button></th>)}
            <th className="text-right font-normal">Trend</th><th className="text-right font-normal">Buzz</th><th /></tr></thead>
          <tbody className="divide-y divide-line">{rows.map(c => (
            <tr key={c.symbol}><td className="py-1.5"><Link href={`/ticker/${encodeURIComponent(c.symbol)}`} className="font-medium hover:text-primary">{c.symbol}</Link> <span className="text-xs text-muted">{c.name}</span></td>
              <td className="text-right num">{num(c.price)}</td>
              {COLS[view].map(([k, , f, colored]) => { const x = c[k] as number | null; return <td key={k} className={`text-right num ${colored ? tone(x) : ""}`}>{f(x)}</td>; })}
              <td className={`text-right text-xs ${c.above_50d && c.above_200d ? "text-up" : !c.above_50d && !c.above_200d ? "text-down" : "text-muted"}`}>{c.above_50d && c.above_200d ? "Uptrend" : !c.above_50d && !c.above_200d ? "Downtrend" : "Mixed"}</td>
              <td className="text-right text-xs">{c.buzz ? c.buzz.level : "—"}</td>
              <td className="text-right"><SourceBadge source={c.source} /></td></tr>))}</tbody></table></div>
        <SourceLine provider={{ label: "Market feed and key statistics (Yahoo Finance); returns, risk and trend computed by Irradiance; buzz from the Irradiance scanner" }} />
      </Card>

      <Card className="mt-4 p-5">
        <div className="flex items-baseline justify-between"><h2 className="font-semibold">Theme news feed</h2>{news && <span className="text-[11px] text-muted">updated {ago(news.as_of)}</span>}</div>
        {!news ? <Skeleton rows={6} /> : !news.headlines.length ? <p className="mt-2 text-sm text-muted">No recent headlines.</p> : (
          <ul className="mt-3 divide-y divide-line text-sm">{news.headlines.slice(0, 20).map(h => (
            <li key={h.url} className="flex items-start justify-between gap-3 py-2"><a href={h.url} target="_blank" rel="noopener noreferrer" className="hover:text-primary">{h.title}</a>
              <span className="shrink-0 text-right text-[11px] text-muted"><Link href={`/ticker/${h.symbol}#news`} className="font-medium text-fg hover:text-primary">{h.symbol}</Link> · {h.source}{h.published_iso && <> · {ago(h.published_iso)}</>}</span></li>))}</ul>)}
        <SourceLine provider={news?.provider} source={news?.source} asOf={news?.as_of} />
      </Card>

      <details className="mt-4 rounded-lg border border-line bg-card/60 p-4 text-sm">
        <summary className="cursor-pointer font-medium"><span className="mr-2 text-primary">ⓘ</span>How to read a theme page</summary>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-muted">
          <li><b className="text-fg">Theme index</b>: an equal-weight basket of the constituents, so a small company counts as much as a large one. Compare it with {bench?.symbol ?? "the benchmark"} to see whether the theme is leading or lagging the market.</li>
          <li><b className="text-fg">Breadth</b>: the share of names above their 50- and 200-day averages. Rising prices with falling breadth means fewer stocks are carrying the theme.</li>
          <li><b className="text-fg">Correlation and dispersion</b>: high correlation means the names trade as one bet; high dispersion means picking the right names matters more than the theme itself.</li>
          <li><b className="text-fg">Drivers</b>: the macro or industry variables the theme depends on, with a live market proxy where one exists.</li>
          <li><b className="text-fg">PESTEL radar</b>: news attention on Political, Economic, Social, Technological, Environmental and Legal topics against its 30-day norm, from the GDELT open news database.</li>
        </ul>
      </details>
      {t.mine && t.notes_md && <Card className="mt-4 p-5"><h2 className="font-semibold">Your notes</h2><div className="prose-irai"><ReactMarkdown>{t.notes_md}</ReactMarkdown></div></Card>}
      <p className="mt-4 text-[11px] text-muted">Themes describe exposures and news flow; they are not recommendations. Research and education only.</p>
    </div>
  );
}

function Kpi({ k, v, sub, c = "" }: { k: string; v: string; sub?: string; c?: string }) {
  return <Card className="p-3"><div className="text-[11px] text-muted">{k}</div><div className={`stat mt-0.5 text-xl num ${c}`}>{v}</div>{sub && <div className="text-[11px] text-muted num">{sub}</div>}</Card>;
}
