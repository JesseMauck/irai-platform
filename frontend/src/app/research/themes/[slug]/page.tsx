"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useState } from "react";
import ReactMarkdown from "react-markdown";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { num, pct, tone } from "@/lib/format";
import { PinButton, ThemeEditor, type Theme } from "@/components/Workspace";
import { SourceLine } from "@/components/research";
import { Button, Card, ErrorNote, Skeleton, SourceBadge } from "@/components/ui";

interface Detail extends Theme {
  constituents: { symbol: string; name: string | null; price: number | null; change_pct: number | null; ret_1m: number | null; ret_ytd: number | null; above_50d: boolean; source: string }[];
  breadth: { above_50d_pct: number | null; median_1m: number | null; count: number };
  drivers: { name: string; why: string; symbol?: string; reading: { symbol: string; price: number | null; change_pct: number | null; source: string } | null }[];
}
interface Pestel { factors: { key: string; label: string; attention: number | null; tone: number | null; articles_7d_avg?: number | null; articles_30d_avg?: number | null; error?: string;
  headlines: { title: string; url: string; domain: string; seen: string }[] }[]; provider: { label: string; url: string }; source: string; note?: string }

const attnLabel = (a: number | null) => a == null ? "—" : a >= 2 ? "Very high" : a >= 1.5 ? "High" : a >= 0.8 ? "Normal" : "Low";

export default function ThemePage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params);
  const router = useRouter();
  const { data: t, error, reload } = useApi<Detail>(`/api/workspace/themes/${slug}`, 120_000);
  const { data: p } = useApi<Pestel>(`/api/workspace/themes/${slug}/pestel`);
  const [editing, setEditing] = useState(false);
  const [err, setErr] = useState<Error | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  if (error) return <div className="mx-auto max-w-3xl px-4 py-16 text-center text-muted">{error.message}</div>;
  if (!t) return <div className="mx-auto max-w-6xl px-4 py-12"><Skeleton rows={10} /></div>;
  const del = async () => { if (!confirm("Delete this theme?")) return; try { await api(`/api/workspace/themes/${slug}`, { method: "DELETE" }); router.push("/research"); } catch (e) { setErr(e as Error); } };
  const breadth = t.breadth.above_50d_pct;
  const sentiment = breadth == null ? "—" : breadth >= 0.65 ? "Risk-on: most names above their 50-day average" : breadth <= 0.35 ? "Risk-off: most names below their 50-day average" : "Mixed";
  const avgTone = p?.factors.filter(f => f.tone != null).map(f => f.tone!) ?? [];
  const tone7 = avgTone.length ? avgTone.reduce((a, b) => a + b, 0) / avgTone.length : null;
  return (
    <div className="mx-auto max-w-6xl px-4 py-10">
      <Link href="/research" className="text-sm text-muted hover:text-fg">← Research workspace</Link>
      <div className="mt-3 flex flex-wrap items-start justify-between gap-3">
        <div><h1 className="text-3xl">{t.name} <PinButton kind="theme" refId={t.slug} pinned={t.pinned} /></h1><p className="mt-1 max-w-3xl text-muted">{t.description}</p></div>
        <div className="flex gap-2">
          <Button variant="outline" href={`/compare?symbols=${t.tickers.slice(0, 8).join(",")}`}>Compare constituents</Button>
          {t.mine && <><Button variant="outline" onClick={() => setEditing(true)}>Edit</Button><Button variant="ghost" onClick={del}>Delete</Button></>}
        </div>
      </div>
      <ErrorNote error={err} />
      {editing && <div className="mt-4"><ThemeEditor initial={t} onSaved={() => { setEditing(false); reload(); }} onCancel={() => setEditing(false)} /></div>}

      <div className="mt-6 grid gap-3 md:grid-cols-3">
        <Card className="p-4"><div className="text-xs text-muted">Breadth</div><div className="stat mt-1 text-2xl">{pct(breadth, 0, false)}</div><div className="text-xs text-muted">of {t.breadth.count} names above their 50-day average</div></Card>
        <Card className="p-4"><div className="text-xs text-muted">Median 1-month return</div><div className={`stat mt-1 text-2xl ${tone(t.breadth.median_1m)}`}>{pct(t.breadth.median_1m, 1)}</div><div className="text-xs text-muted">{sentiment}</div></Card>
        <Card className="p-4"><div className="text-xs text-muted">News tone (7 days, PESTEL average)</div><div className={`stat mt-1 text-2xl ${tone(tone7)}`}>{tone7 == null ? "—" : tone7.toFixed(1)}</div><div className="text-xs text-muted">GDELT tone, roughly −10 (negative) to +10 (positive)</div></Card>
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <Card className="p-5">
          <h2 className="font-semibold">Key drivers</h2>
          {!t.drivers.length ? <p className="mt-2 text-sm text-muted">No drivers yet.</p> : (
            <ul className="mt-3 divide-y divide-line">{t.drivers.map(d => (
              <li key={d.name} className="py-2.5">
                <div className="flex items-center justify-between gap-2"><span className="font-medium">{d.name}</span>
                  {d.reading && <Link href={`/ticker/${encodeURIComponent(d.reading.symbol)}`} className="flex items-center gap-2 text-sm num hover:text-primary">{d.reading.symbol} {num(d.reading.price)} <span className={tone(d.reading.change_pct)}>{pct(d.reading.change_pct)}</span><SourceBadge source={d.reading.source} /></Link>}</div>
                <p className="text-sm text-muted">{d.why}</p></li>))}</ul>)}
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
                  <span className={`w-12 text-right text-xs num ${tone(f.tone)}`}>{f.tone == null ? "—" : f.tone.toFixed(1)}</span>
                </button>
                {open === f.key && (f.headlines.length ? <ul className="mt-2 space-y-1 pl-28 text-sm">{f.headlines.map(h => <li key={h.url}><a href={h.url} target="_blank" rel="noopener noreferrer" className="hover:text-primary">{h.title}</a> <span className="text-[11px] text-muted">{h.domain}</span></li>)}</ul>
                  : <p className="mt-1 pl-28 text-xs text-muted">{f.error ? `Unavailable (${f.error})` : "No headlines this week."}</p>)}
              </li>))}</ul>)}
          {p?.note && <p className="mt-2 text-[11px] text-muted">{p.note}</p>}
          <SourceLine provider={p?.provider} source={p?.source} />
        </Card>
      </div>

      <Card className="mt-4 p-5">
        <h2 className="font-semibold">Constituents</h2>
        <div className="mt-3 overflow-x-auto"><table className="w-full min-w-[640px] text-sm">
          <thead className="text-xs text-muted"><tr><th className="py-1 text-left font-normal">Ticker</th><th className="text-right font-normal">Price</th><th className="text-right font-normal">Day</th><th className="text-right font-normal">1 month</th><th className="text-right font-normal">YTD</th><th className="text-right font-normal">vs 50-day</th><th /></tr></thead>
          <tbody className="divide-y divide-line">{t.constituents.map(c => (
            <tr key={c.symbol}><td className="py-1.5"><Link href={`/ticker/${encodeURIComponent(c.symbol)}`} className="font-medium hover:text-primary">{c.symbol}</Link> <span className="text-xs text-muted">{c.name}</span></td>
              <td className="text-right num">{num(c.price)}</td><td className={`text-right num ${tone(c.change_pct)}`}>{pct(c.change_pct)}</td><td className={`text-right num ${tone(c.ret_1m)}`}>{pct(c.ret_1m, 1)}</td>
              <td className={`text-right num ${tone(c.ret_ytd)}`}>{pct(c.ret_ytd, 1)}</td><td className={`text-right ${c.above_50d ? "text-up" : "text-down"}`}>{c.above_50d ? "above" : "below"}</td><td className="text-right"><SourceBadge source={c.source} /></td></tr>))}</tbody></table></div>
        <SourceLine provider={{ label: "Market feed (Yahoo Finance); returns computed by Irradiance" }} />
      </Card>
      {t.mine && t.notes_md && <Card className="mt-4 p-5"><h2 className="font-semibold">Your notes</h2><div className="prose-irai"><ReactMarkdown>{t.notes_md}</ReactMarkdown></div></Card>}
      <p className="mt-4 text-[11px] text-muted">Themes describe exposures and news flow; they are not recommendations. Research and education only.</p>
    </div>
  );
}
