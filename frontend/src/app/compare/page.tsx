"use client";
import Link from "next/link";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import ReactMarkdown from "react-markdown";
import { api } from "@/lib/api";
import { num, pct, tone } from "@/lib/format";
import { useAuth } from "@/components/AuthProvider";
import { fmtRatio, SourceLine } from "@/components/research";
import { Button, Card, ErrorNote, PageHeader, Skeleton, SourceBadge } from "@/components/ui";

interface Row { symbol: string; name: string; price: number | null; change_pct: number | null; source: string; sector: string | null; rating_label: string | null; [k: string]: unknown }
interface Result { rows: Row[]; columns: { key: string; label: string }[]; missing: string[]; provider: string; as_of: string;
  analysis?: { engine: string; model?: string; markdown: string; note?: string } }

const GRADE_KEYS = new Set(["rating", "valuation", "quality", "growth", "momentum", "risk"]);
const LOWER_BETTER = new Set(["trailing_pe", "forward_pe", "ev_ebitda", "price_to_sales", "price_to_book", "peg_ratio", "debt_to_equity", "vol_1y", "beta"]);
const GRADES = ["F", "D-", "D", "D+", "C-", "C", "C+", "B-", "B", "B+", "A-", "A", "A+"];

function Compare() {
  const sp = useSearchParams();
  const { user } = useAuth();
  const [input, setInput] = useState(sp.get("symbols") ?? "AAPL,MSFT,GOOGL");
  const [question, setQuestion] = useState("");
  const [res, setRes] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<Error | null>(null);
  const run = async (syms = input) => {
    setBusy(true); setErr(null);
    try {
      setRes(await api<Result>("/api/workspace/compare", { method: "POST", json: { symbols: syms.split(/[\s,]+/).filter(Boolean), question: question || null } }));
      history.replaceState(null, "", `?symbols=${encodeURIComponent(syms.toUpperCase())}`);
    } catch (e) { setErr(e as Error); } finally { setBusy(false); }
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (sp.get("symbols")) run(sp.get("symbols")!); }, []);
  const bestIdx = (key: string): number | null => {
    if (!res) return null;
    const vals = res.rows.map(r => r[key]);
    if (GRADE_KEYS.has(key)) {
      const ix = vals.map(v => (typeof v === "string" ? GRADES.indexOf(v) : -1));
      const m = Math.max(...ix); return m >= 0 ? ix.indexOf(m) : null;
    }
    const nums = vals.map(v => (typeof v === "number" && isFinite(v) ? v : null));
    if (nums.filter(v => v != null).length < 2 || key === "market_cap" || key === "buzz") return null;
    const valid = nums.map((v, i) => [v, i] as const).filter(([v]) => v != null && (!LOWER_BETTER.has(key) || (v as number) > 0));
    if (!valid.length) return null;
    valid.sort((a, b) => (LOWER_BETTER.has(key) ? (a[0]! - b[0]!) : (b[0]! - a[0]!)));
    return valid[0][1];
  };
  const fmt = (k: string, v: unknown) => GRADE_KEYS.has(k) ? (v as string) ?? "—" : k === "buzz" ? (typeof v === "number" ? v.toFixed(0) : "—")
    : ["ret_1y", "vol_1y", "target_upside"].includes(k) ? pct(v as number, 1, k !== "vol_1y") : fmtRatio(k, v);
  return (
    <div className="mx-auto max-w-7xl px-4 py-10">
      <PageHeader title="Compare companies" intro="Side-by-side valuation, quality, growth, momentum, risk and attention for up to eight tickers, with a written read-through of the trade-offs." />
      <Card className="mt-6 p-5">
        <form onSubmit={e => { e.preventDefault(); run(); }} className="grid gap-3 md:grid-cols-[1fr_1fr_auto]">
          <input value={input} onChange={e => setInput(e.target.value)} placeholder="Tickers, comma separated" aria-label="Tickers" className="rounded-lg border border-line bg-bg px-3 py-2 text-sm uppercase" />
          <input value={question} onChange={e => setQuestion(e.target.value)} placeholder="Optional question, e.g. which looks cheapest for its growth?" aria-label="Question" className="rounded-lg border border-line bg-bg px-3 py-2 text-sm" />
          <Button type="submit" disabled={busy}>{busy ? "Comparing…" : "Compare"}</Button>
        </form>
        {!user && <p className="mt-2 text-xs text-muted"><Link href="/login?next=/compare" className="text-primary">Sign in</Link> to compare up to eight companies and get the AI-written analysis.</p>}
        <ErrorNote error={err} />
      </Card>
      {busy && !res && <Skeleton rows={10} />}
      {res && (
        <>
          <div className="mt-6 overflow-x-auto rounded-xl border border-line">
            <table className="w-full min-w-[760px] text-sm">
              <thead className="bg-card"><tr><th className="sticky left-0 bg-card p-3 text-left text-xs font-normal text-muted">Metric</th>
                {res.rows.map(r => <th key={r.symbol} className="p-3 text-right"><Link href={`/ticker/${r.symbol}`} className="hover:text-primary">{r.symbol}</Link>
                  <div className="truncate text-[11px] font-normal text-muted">{r.name}</div><div className="mt-1 flex justify-end"><SourceBadge source={r.source} /></div></th>)}</tr></thead>
              <tbody className="divide-y divide-line">
                <tr><td className="sticky left-0 bg-bg p-3 text-muted">Price</td>{res.rows.map(r => <td key={r.symbol} className="p-3 text-right num">{num(r.price)} <span className={`text-xs ${tone(r.change_pct)}`}>{pct(r.change_pct)}</span></td>)}</tr>
                <tr><td className="sticky left-0 bg-bg p-3 text-muted">Sector</td>{res.rows.map(r => <td key={r.symbol} className="p-3 text-right text-xs">{r.sector ?? "—"}</td>)}</tr>
                {res.columns.map(c => { const b = bestIdx(c.key); return (
                  <tr key={c.key}><td className="sticky left-0 bg-bg p-3 text-muted">{c.label}</td>
                    {res.rows.map((r, i) => <td key={r.symbol} className={`p-3 text-right num ${i === b ? "font-semibold text-up" : ""}`}>{fmt(c.key, r[c.key])}</td>)}</tr>); })}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-[11px] text-muted">Green marks the most favourable value in each row (lower is better for multiples, leverage and volatility). {res.missing.length > 0 && `No data for ${res.missing.join(", ")}.`}</p>
          <SourceLine provider={{ label: res.provider }} asOf={res.as_of} />
          {res.analysis && (
            <Card className="mt-6 p-6">
              <div className="flex items-center justify-between"><h2 className="text-xl">Analysis</h2>
                <span className="text-xs text-muted">{res.analysis.engine === "claude" ? `Written by Claude (${res.analysis.model}) from the table above` : "Rule-based summary"}</span></div>
              <div className="prose-irai mt-2"><ReactMarkdown>{res.analysis.markdown}</ReactMarkdown></div>
              {res.analysis.note && <p className="mt-3 text-xs text-muted">{res.analysis.note}</p>}
              <p className="mt-3 text-[11px] text-muted">AI-generated from the data shown; verify before relying on it. Research and education only, not investment advice.</p>
            </Card>
          )}
        </>
      )}
    </div>
  );
}

export default function Page() { return <Suspense><Compare /></Suspense>; }
