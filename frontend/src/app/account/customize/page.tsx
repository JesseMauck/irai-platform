"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { DEFAULT_PREFS, type Preferences } from "@/lib/api";
import { applyPrefs, useAuth } from "@/components/AuthProvider";
import { TickerInput } from "@/components/TickerInput";
import { Button, Card, ErrorNote } from "@/components/ui";

const ACCENTS: { key: Preferences["accent"]; label: string; color: string }[] = [
  { key: "solar", label: "Solar", color: "#f5a524" }, { key: "ocean", label: "Ocean", color: "#3b8ef5" },
  { key: "emerald", label: "Emerald", color: "#22b07d" }, { key: "violet", label: "Violet", color: "#8b6cf6" }, { key: "mono", label: "Graphite", color: "#9aa4b5" },
];
const LANDINGS: [string, string][] = [["/", "Home"], ["/terminal", "Terminal"], ["/research", "Research workspace"], ["/monitor/adr", "ADR monitor"],
  ["/valuebot/reports", "My ValueBot reports"], ["/community", "Community"], ["/lab", "Strategy Lab"], ["/account", "Account"]];
const TABS: [string, string][] = [["summary", "Summary"], ["analyst", "Analyst"], ["chart", "Chart"], ["financials", "Financials"], ["earnings", "Earnings"],
  ["dividends", "Dividends"], ["peers-ratios", "Peers & ratios"], ["technicals", "Technicals"], ["filings", "Filings"], ["news", "News"]];
const PRESETS: [string, string[]][] = [
  ["US indices", ["^GSPC", "^IXIC", "^DJI", "^RUT", "^VIX"]], ["Macro", ["^TNX", "DX-Y.NYB", "GC=F", "CL=F", "BTC-USD", "EURUSD=X"]],
  ["Mega-cap tech", ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META"]], ["Income", ["SCHD", "VYM", "JEPI", "TLT", "HYG"]],
];

export default function Customize() {
  const { user, ready, prefs, savePrefs } = useAuth();
  const [p, setP] = useState<Preferences>(prefs);
  const [add, setAdd] = useState("");
  const [err, setErr] = useState<Error | null>(null);
  const [saved, setSaved] = useState(false);
  const loaded = JSON.stringify(prefs);
  useEffect(() => { setP(JSON.parse(loaded)); }, [loaded]);
  if (!ready) return null;
  if (!user) return <div className="mx-auto max-w-md px-4 py-20 text-center"><p>Sign in to customize Irradiance.</p><Button href="/login?next=/account/customize" className="mt-4">Sign in</Button></div>;
  const set = <K extends keyof Preferences>(k: K, v: Preferences[K]) => {
    const n = { ...p, [k]: v }; setP(n); setSaved(false);
    if (k === "theme" || k === "accent" || k === "density") applyPrefs(n); // live preview
  };
  const addSym = (s: string) => { const x = s.trim().toUpperCase(); if (x && !p.ticker_bar.includes(x) && p.ticker_bar.length < 20) set("ticker_bar", [...p.ticker_bar, x]); setAdd(""); };
  const move = (i: number, d: number) => { const a = [...p.ticker_bar]; const j = i + d; if (j < 0 || j >= a.length) return; [a[i], a[j]] = [a[j], a[i]]; set("ticker_bar", a); };
  const save = async () => { setErr(null); try { await savePrefs(p); setSaved(true); } catch (e) { setErr(e as Error); } };
  const reset = () => { setP(DEFAULT_PREFS); applyPrefs(DEFAULT_PREFS); setSaved(false); };
  const seg = <K extends keyof Preferences>(k: K, opts: [Preferences[K], string][]) => (
    <div className="inline-flex flex-wrap gap-1 rounded-lg bg-accent p-1">{opts.map(([v, l]) =>
      <button key={String(v)} onClick={() => set(k, v)} className={`rounded-md px-3 py-1.5 text-sm ${p[k] === v ? "bg-card text-fg shadow-sm" : "text-muted hover:text-fg"}`}>{l}</button>)}</div>);
  return (
    <div className="mx-auto max-w-4xl px-4 py-10">
      <Link href="/account" className="text-sm text-muted hover:text-fg">← Account</Link>
      <div className="mt-3 flex flex-wrap items-end justify-between gap-3">
        <div><h1 className="text-3xl">Customize</h1><p className="mt-1 text-muted">Make Irradiance yours. Settings are saved to your account and follow you across devices.</p></div>
        <div className="flex gap-2"><Button variant="ghost" onClick={reset}>Reset to defaults</Button><Button onClick={save}>{saved ? "Saved ✓" : "Save changes"}</Button></div>
      </div>
      <ErrorNote error={err} />

      <div className="mt-6 space-y-4">
        <Card className="p-5"><h2 className="font-semibold">Appearance</h2>
          <div className="mt-4 grid gap-5 md:grid-cols-3">
            <div><div className="mb-2 text-sm text-muted">Theme</div>{seg("theme", [["system", "System"], ["light", "Light"], ["dark", "Dark"]])}</div>
            <div><div className="mb-2 text-sm text-muted">Density</div>{seg("density", [["comfortable", "Comfortable"], ["compact", "Compact"]])}</div>
            <div><div className="mb-2 text-sm text-muted">Accent colour</div>
              <div className="flex flex-wrap gap-2">{ACCENTS.map(a => (
                <button key={a.key} onClick={() => set("accent", a.key)} title={a.label} aria-label={a.label}
                  className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs ${p.accent === a.key ? "border-fg" : "border-line"}`}>
                  <span className="inline-block h-3.5 w-3.5 rounded-full" style={{ background: a.color }} />{a.label}</button>))}</div></div>
          </div>
          <p className="mt-3 text-[11px] text-muted">Changes preview live. Save to keep them.</p>
        </Card>

        <Card className="p-5"><h2 className="font-semibold">Ticker bar</h2>
          <label className="mt-3 flex items-center gap-2 text-sm"><input type="checkbox" checked={p.show_ticker_bar} onChange={e => set("show_ticker_bar", e.target.checked)} /> Show the scrolling ticker bar</label>
          <p className="mt-3 text-sm text-muted">Choose up to 20 symbols, or leave the list empty to use the Irradiance default (indices, rates, FX and crypto).</p>
          <div className="mt-3 flex flex-wrap gap-2">{p.ticker_bar.map((s, i) => (
            <span key={s} className="flex items-center gap-1 rounded-full border border-line bg-accent/60 py-0.5 pl-2.5 pr-1 text-sm num">
              <button onClick={() => move(i, -1)} className="text-muted hover:text-fg" aria-label={`Move ${s} left`}>‹</button>{s}
              <button onClick={() => move(i, 1)} className="text-muted hover:text-fg" aria-label={`Move ${s} right`}>›</button>
              <button onClick={() => set("ticker_bar", p.ticker_bar.filter(x => x !== s))} className="ml-1 rounded-full px-1 text-muted hover:text-down" aria-label={`Remove ${s}`}>×</button></span>))}
            {!p.ticker_bar.length && <span className="text-sm text-muted">Using the default bar.</span>}</div>
          <div className="mt-3 flex max-w-md gap-2"><div className="flex-1"><TickerInput value={add} onChange={setAdd} onPick={addSym} placeholder="Add a symbol (e.g. NVDA, ^VIX, BTC-USD)" /></div><Button variant="outline" onClick={() => addSym(add)} disabled={!add}>Add</Button></div>
          <div className="mt-3 flex flex-wrap gap-2 text-xs"><span className="text-muted">Presets:</span>{PRESETS.map(([n, syms]) =>
            <button key={n} onClick={() => set("ticker_bar", Array.from(new Set([...p.ticker_bar, ...syms])).slice(0, 20))} className="rounded border border-line px-2 py-0.5 hover:border-primary">+ {n}</button>)}
            {p.ticker_bar.length > 0 && <button onClick={() => set("ticker_bar", [])} className="rounded px-2 py-0.5 text-muted hover:text-fg">Clear</button>}</div>
        </Card>

        <Card className="p-5"><h2 className="font-semibold">Defaults</h2>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <Field label="Start page after sign-in"><select value={p.landing} onChange={e => set("landing", e.target.value)} className="w-full rounded border border-line bg-bg px-2 py-1.5 text-sm">{LANDINGS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></Field>
            <Field label="Default ticker tab"><select value={p.default_ticker_tab} onChange={e => set("default_ticker_tab", e.target.value)} className="w-full rounded border border-line bg-bg px-2 py-1.5 text-sm">{TABS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></Field>
            <Field label="Default chart range">{seg("chart_range", [["1mo", "1M"], ["3mo", "3M"], ["6mo", "6M"], ["1y", "1Y"], ["5y", "5Y"]])}</Field>
            <Field label="Benchmark for themes and comparisons">{seg("benchmark", [["SPY", "S&P 500"], ["QQQ", "Nasdaq-100"], ["IWM", "Russell 2000"], ["DIA", "Dow"], ["ACWI", "World"]])}</Field>
          </div>
          <label className="mt-4 flex items-center gap-2 text-sm"><input type="checkbox" checked={p.show_tab_guides} onChange={e => set("show_tab_guides", e.target.checked)} /> Show &quot;About this tab&quot; guides on ticker pages</label>
        </Card>
      </div>
      <div className="mt-6 flex justify-end"><Button onClick={save}>{saved ? "Saved ✓" : "Save changes"}</Button></div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div><div className="mb-1.5 text-sm text-muted">{label}</div>{children}</div>;
}
