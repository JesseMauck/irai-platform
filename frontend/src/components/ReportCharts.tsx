/* Print-quality SVG charts for the Analyst report. Vector (crisp in PDF), themed with the site's CSS tokens and fonts. */
const W = 720;
const C = { up: "var(--color-up)", down: "var(--color-down)", line: "var(--color-line)", muted: "var(--color-muted)", fg: "var(--color-fg)",
  brand: "#E0605A", d1: "var(--color-data-1)", d2: "var(--color-data-2)", d4: "var(--color-data-4)", primary: "var(--color-primary)" };
const fmtPct = (x: number, d = 0) => `${x >= 0 ? "" : "−"}${Math.abs(x * 100).toFixed(d)}%`;

function scale(min: number, max: number, a: number, b: number) {
  const span = max - min || 1;
  return (v: number) => a + ((v - min) / span) * (b - a);
}
function ticks(min: number, max: number, n = 4) {
  const step = (max - min) / n;
  return Array.from({ length: n + 1 }, (_, i) => min + step * i);
}
function Frame({ h, children, title }: { h: number; children: React.ReactNode; title?: string }) {
  return <figure className="print-avoid-break">{title && <figcaption className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted">{title}</figcaption>}
    <svg viewBox={`0 0 ${W} ${h}`} className="h-auto w-full" style={{ fontFamily: "var(--font-sans)" }} role="img" aria-label={title}>{children}</svg></figure>;
}
function XLabels({ dates, x, y, n = 5 }: { dates: string[]; x: (i: number) => number; y: number; n?: number }) {
  if (!dates.length) return null;
  const idx = Array.from({ length: n }, (_, i) => Math.round((i * (dates.length - 1)) / (n - 1)));
  return <>{idx.map((i, k) => <text key={k} x={x(i)} y={y} fontSize="10" fill={C.muted} textAnchor={k === 0 ? "start" : k === n - 1 ? "end" : "middle"}>{dates[i]?.slice(0, 7)}</text>)}</>;
}
const path = (vals: (number | null)[], x: (i: number) => number, y: (v: number) => number) =>
  vals.reduce((acc, v, i) => v == null ? acc : acc + `${acc && vals[i - 1] != null ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`, "");

/** Price with 50/200-day averages, key levels and a volume pane. */
export function PriceChart({ dates, close, sma50, sma200, volume, levels = [] }: { dates: string[]; close: number[]; sma50: (number | null)[]; sma200: (number | null)[]; volume?: number[]; levels?: { label: string; price: number }[] }) {
  const H = 300, top = 10, bot = volume ? 220 : 270, L = 8, R = W - 56;
  const vals = [...close, ...sma50.filter(Boolean) as number[], ...sma200.filter(Boolean) as number[]];
  const lo = Math.min(...vals) * 0.98, hi = Math.max(...vals) * 1.02;
  const x = scale(0, close.length - 1, L, R), y = scale(lo, hi, bot, top);
  const vmax = volume ? Math.max(...volume) || 1 : 1;
  const area = `${path(close, x, y)}L${x(close.length - 1)},${bot}L${x(0)},${bot}Z`;
  return (
    <Frame h={H}>
      <defs><linearGradient id="pc-fill" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor={C.brand} stopOpacity="0.22" /><stop offset="1" stopColor={C.brand} stopOpacity="0" /></linearGradient></defs>
      {ticks(lo, hi).map(t => <g key={t}><line x1={L} x2={R} y1={y(t)} y2={y(t)} stroke={C.line} strokeWidth="0.6" /><text x={R + 4} y={y(t) + 3} fontSize="10" fill={C.muted}>{t.toFixed(t > 100 ? 0 : 2)}</text></g>)}
      {levels.filter(l => l.price > lo && l.price < hi).map(l => <g key={l.label}><line x1={L} x2={R} y1={y(l.price)} y2={y(l.price)} stroke={C.primary} strokeDasharray="3 3" strokeWidth="0.8" opacity="0.8" />
        <text x={R - 2} y={y(l.price) - 2} fontSize="9" fill={C.primary} textAnchor="end">{l.label} {l.price.toFixed(2)}</text></g>)}
      <path d={area} fill="url(#pc-fill)" />
      <path d={path(close, x, y)} fill="none" stroke={C.brand} strokeWidth="1.6" />
      <path d={path(sma50, x, y)} fill="none" stroke={C.d1} strokeWidth="1.1" />
      <path d={path(sma200, x, y)} fill="none" stroke={C.d2} strokeWidth="1.1" />
      {volume && volume.map((v, i) => <rect key={i} x={x(i) - 0.9} width="1.8" y={H - 22 - (v / vmax) * 52} height={(v / vmax) * 52} fill={i && close[i] >= close[i - 1] ? C.up : C.down} opacity="0.55" />)}
      <XLabels dates={dates} x={x} y={H - 6} />
      <g fontSize="10"><rect x={L} y={top} width="9" height="2.5" fill={C.brand} /><text x={L + 12} y={top + 4} fill={C.fg}>Price</text>
        <rect x={L + 52} y={top} width="9" height="2.5" fill={C.d1} /><text x={L + 64} y={top + 4} fill={C.fg}>50-day</text>
        <rect x={L + 112} y={top} width="9" height="2.5" fill={C.d2} /><text x={L + 124} y={top + 4} fill={C.fg}>200-day</text>
        {volume && <text x={L + 172} y={top + 4} fill={C.muted}>· volume (green up day, orange down day)</text>}</g>
    </Frame>
  );
}

/** Single-series line or area (relative strength, drawdown, volatility). */
export function SeriesChart({ dates, values, title, baseline, area = false, color = C.d1, pct = false, height = 160 }: { dates: string[]; values: number[]; title?: string; baseline?: number; area?: boolean; color?: string; pct?: boolean; height?: number }) {
  const H = height, top = 8, bot = H - 20, L = 8, R = W - 52;
  const lo = Math.min(...values, baseline ?? Infinity), hi = Math.max(...values, baseline ?? -Infinity);
  const pad = (hi - lo) * 0.08 || 0.01;
  const x = scale(0, values.length - 1, L, R), y = scale(lo - pad, hi + pad, bot, top);
  const b = baseline ?? lo - pad;
  return (
    <Frame h={H} title={title}>
      {ticks(lo - pad, hi + pad, 3).map(t => <g key={t}><line x1={L} x2={R} y1={y(t)} y2={y(t)} stroke={C.line} strokeWidth="0.6" /><text x={R + 4} y={y(t) + 3} fontSize="10" fill={C.muted}>{pct ? fmtPct(t) : t.toFixed(2)}</text></g>)}
      {baseline != null && <line x1={L} x2={R} y1={y(baseline)} y2={y(baseline)} stroke={C.muted} strokeDasharray="2 3" />}
      {area && <path d={`${path(values, x, y)}L${x(values.length - 1)},${y(b)}L${x(0)},${y(b)}Z`} fill={color} opacity="0.18" />}
      <path d={path(values, x, y)} fill="none" stroke={color} strokeWidth="1.5" />
      <XLabels dates={dates} x={x} y={H - 5} n={4} />
    </Frame>
  );
}

/** Oscillator with bands (RSI) or a histogram around zero (MACD). */
export function Oscillator({ dates, values, kind, title }: { dates: string[]; values: (number | null)[]; kind: "rsi" | "hist"; title?: string }) {
  const H = 120, top = 6, bot = H - 18, L = 8, R = W - 40;
  const v = values.map(z => z ?? 0);
  const lo = kind === "rsi" ? 0 : Math.min(...v), hi = kind === "rsi" ? 100 : Math.max(...v);
  const m = kind === "hist" ? Math.max(Math.abs(lo), Math.abs(hi)) || 1 : 0;
  const x = scale(0, v.length - 1, L, R), y = kind === "rsi" ? scale(0, 100, bot, top) : scale(-m, m, bot, top);
  return (
    <Frame h={H} title={title}>
      {kind === "rsi" ? <>
        <rect x={L} width={R - L} y={y(70)} height={y(30) - y(70)} fill={C.primary} opacity="0.07" />
        {[30, 50, 70].map(t => <g key={t}><line x1={L} x2={R} y1={y(t)} y2={y(t)} stroke={t === 50 ? C.line : C.muted} strokeDasharray={t === 50 ? "" : "3 3"} strokeWidth="0.7" /><text x={R + 4} y={y(t) + 3} fontSize="10" fill={C.muted}>{t}</text></g>)}
        <path d={path(values, x, y)} fill="none" stroke={C.d4} strokeWidth="1.4" />
      </> : <>
        <line x1={L} x2={R} y1={y(0)} y2={y(0)} stroke={C.muted} strokeWidth="0.7" />
        {v.map((z, i) => <rect key={i} x={x(i) - 1.4} width="2.8" y={Math.min(y(0), y(z))} height={Math.abs(y(z) - y(0))} fill={z >= 0 ? C.up : C.down} opacity="0.8" />)}
      </>}
      <XLabels dates={dates} x={x} y={H - 4} n={4} />
    </Frame>
  );
}

/** Grouped bars (e.g. stock vs SPY vs sector by period), values as fractions. */
export function GroupedBars({ groups, series, title }: { groups: string[]; series: { label: string; color: string; values: (number | null)[] }[]; title?: string }) {
  const H = 190, top = 22, bot = H - 22, L = 36, R = W - 8;
  const all = series.flatMap(s => s.values.filter((z): z is number => z != null));
  const m = Math.max(0.02, ...all.map(Math.abs)) * 1.15;
  const y = scale(-m, m, bot, top);
  const gw = (R - L) / groups.length, bw = Math.min(22, (gw - 10) / series.length);
  return (
    <Frame h={H} title={title}>
      {ticks(-m, m, 4).map(t => <g key={t}><line x1={L} x2={R} y1={y(t)} y2={y(t)} stroke={t === 0 ? C.muted : C.line} strokeWidth="0.6" /><text x={L - 4} y={y(t) + 3} fontSize="9" fill={C.muted} textAnchor="end">{fmtPct(t)}</text></g>)}
      {groups.map((g, gi) => <g key={g}>
        {series.map((s, si) => { const val = s.values[gi]; if (val == null) return null; const x0 = L + gi * gw + (gw - bw * series.length) / 2 + si * bw;
          return <g key={s.label}><rect x={x0} width={bw - 2} y={Math.min(y(0), y(val))} height={Math.abs(y(val) - y(0))} fill={s.color} rx="1.5" />
            <text x={x0 + (bw - 2) / 2} y={val >= 0 ? y(val) - 3 : y(val) + 10} fontSize="8" fill={C.fg} textAnchor="middle">{fmtPct(val)}</text></g>; })}
        <text x={L + gi * gw + gw / 2} y={H - 6} fontSize="10" fill={C.muted} textAnchor="middle">{g}</text></g>)}
      <g fontSize="10">{series.map((s, i) => <g key={s.label}><rect x={L + i * 90} y={4} width="10" height="8" fill={s.color} rx="1" /><text x={L + i * 90 + 14} y={11} fill={C.fg}>{s.label}</text></g>)}</g>
    </Frame>
  );
}

/** Simple signed bars with labels (seasonality, EPS surprise). */
export function SignedBars({ labels, values, title, sub, decimals = 1, unit = "pct" }: { labels: string[]; values: (number | null)[]; title?: string; sub?: (string | null)[]; decimals?: number; unit?: "pct" | "raw" }) {
  const H = 160, top = 14, bot = H - (sub ? 30 : 20), L = 8, R = W - 8;
  const m = Math.max(...values.map(v => Math.abs(v ?? 0)), unit === "pct" ? 0.005 : 0.5) * 1.2;
  const y = scale(-m, m, bot, top);
  const bw = (R - L) / labels.length;
  const f = (v: number) => unit === "pct" ? fmtPct(v, decimals) : `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(decimals)}%`;
  return (
    <Frame h={H} title={title}>
      <line x1={L} x2={R} y1={y(0)} y2={y(0)} stroke={C.muted} strokeWidth="0.7" />
      {labels.map((l, i) => { const v = values[i]; return <g key={l + i}>
        {v != null && <><rect x={L + i * bw + bw * 0.18} width={bw * 0.64} y={Math.min(y(0), y(v))} height={Math.max(0.5, Math.abs(y(v) - y(0)))} fill={v >= 0 ? C.up : C.down} rx="1.5" opacity="0.85" />
          <text x={L + i * bw + bw / 2} y={v >= 0 ? y(v) - 3 : y(v) + 10} fontSize="9" fill={C.fg} textAnchor="middle">{f(v)}</text></>}
        <text x={L + i * bw + bw / 2} y={bot + 13} fontSize="10" fill={C.muted} textAnchor="middle">{l}</text>
        {sub?.[i] && <text x={L + i * bw + bw / 2} y={bot + 25} fontSize="8.5" fill={C.muted} textAnchor="middle">{sub[i]}</text>}</g>; })}
    </Frame>
  );
}

/** Daily return distribution with VaR marker. */
export function Histogram({ edges, counts, varLine, title }: { edges: number[]; counts: number[]; varLine?: number; title?: string }) {
  const H = 150, top = 10, bot = H - 20, L = 8, R = W - 8;
  const x = scale(edges[0], edges[edges.length - 1], L, R), y = scale(0, Math.max(...counts) || 1, bot, top);
  return (
    <Frame h={H} title={title}>
      {counts.map((c, i) => <rect key={i} x={x(edges[i]) + 0.5} width={Math.max(1, x(edges[i + 1]) - x(edges[i]) - 1)} y={y(c)} height={bot - y(c)} fill={edges[i] < 0 ? C.down : C.up} opacity="0.75" />)}
      <line x1={x(0)} x2={x(0)} y1={top} y2={bot} stroke={C.muted} strokeWidth="0.7" />
      {varLine != null && <g><line x1={x(-varLine)} x2={x(-varLine)} y1={top} y2={bot} stroke={C.brand} strokeDasharray="3 2" /><text x={x(-varLine) - 3} y={top + 9} fontSize="9" fill={C.brand} textAnchor="end">95% VaR {fmtPct(-varLine, 1)}</text></g>}
      {[-0.08, -0.04, 0, 0.04, 0.08].map(t => <text key={t} x={x(t)} y={H - 5} fontSize="10" fill={C.muted} textAnchor="middle">{fmtPct(t)}</text>)}
    </Frame>
  );
}

/** Regime timeline strip (Calm / Normal / Stressed). */
export function RegimeStrip({ dates, state, title }: { dates: string[]; state: number[]; title?: string }) {
  const H = 58, L = 8, R = W - 8, cols = [C.up, C.primary, C.down], names = ["Calm", "Normal", "Stressed"];
  const w = (R - L) / Math.max(1, state.length);
  return (
    <Frame h={H} title={title}>
      {state.map((s, i) => <rect key={i} x={L + i * w} width={w + 0.4} y={6} height={22} fill={cols[s]} opacity="0.8" />)}
      <text x={L} y={42} fontSize="10" fill={C.muted}>{dates[0]?.slice(0, 7)}</text><text x={R} y={42} fontSize="10" fill={C.muted} textAnchor="end">{dates[dates.length - 1]?.slice(0, 7)}</text>
      <g fontSize="10">{names.map((n, i) => <g key={n}><rect x={W / 2 - 110 + i * 78} y={46} width="10" height="8" fill={cols[i]} /><text x={W / 2 - 96 + i * 78} y={53} fill={C.fg}>{n}</text></g>)}</g>
    </Frame>
  );
}

/** A horizontal range with markers (52-week range, Street target range, statistical ranges). */
export function RangeBar({ low, high, marks, title }: { low: number; high: number; marks: { label: string; value: number; strong?: boolean }[]; title?: string }) {
  const H = 64, L = 60, R = W - 60, x = scale(low, high, L, R);
  return (
    <Frame h={H} title={title}>
      <rect x={L} y={26} width={R - L} height={8} rx="4" fill="var(--color-accent)" stroke={C.line} />
      <text x={L - 6} y={34} fontSize="10" fill={C.muted} textAnchor="end">{low.toFixed(2)}</text><text x={R + 6} y={34} fontSize="10" fill={C.muted}>{high.toFixed(2)}</text>
      {marks.filter(m => m.value >= low && m.value <= high).map((m, i) => <g key={m.label}>
        <line x1={x(m.value)} x2={x(m.value)} y1={20} y2={40} stroke={m.strong ? C.brand : C.d1} strokeWidth={m.strong ? 2.5 : 1.5} />
        <text x={x(m.value)} y={i % 2 ? 54 : 15} fontSize="9.5" fill={m.strong ? C.brand : C.fg} textAnchor="middle" fontWeight={m.strong ? 700 : 400}>{m.label} {m.value.toFixed(2)}</text></g>)}
    </Frame>
  );
}

/** Factor scorecard dots. */
export function ScoreDots({ read }: { read: string }) {
  const i = read === "Positive" ? 2 : read === "Neutral" ? 1 : read === "Negative" ? 0 : -1;
  const col = [C.down, C.primary, C.up];
  return <svg viewBox="0 0 54 12" className="inline-block h-3 w-14" aria-label={read}>{[0, 1, 2].map(k => <circle key={k} cx={6 + k * 21} cy="6" r="5" fill={k === i ? col[k] : "var(--color-accent)"} stroke={C.line} strokeWidth="0.6" />)}</svg>;
}
