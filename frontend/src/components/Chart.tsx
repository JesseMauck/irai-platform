"use client";
import { useMemo, useState } from "react";

export interface Series { values: (number | null)[]; color: string; dashed?: boolean; label?: string }

/** Lightweight responsive SVG line chart with optional shaded band and hover readout. */
export function LineChart({ dates, series, band, height = 220, format = (v: number) => v.toFixed(2) }: {
  dates: string[]; series: Series[]; band?: { lo: number[]; hi: number[]; color?: string };
  height?: number; format?: (v: number) => string;
}) {
  const W = 800, H = height, P = { l: 8, r: 56, t: 10, b: 22 };
  const [hover, setHover] = useState<number | null>(null);
  const { min, max } = useMemo(() => {
    const all = [...series.flatMap(s => s.values), ...(band ? [...band.lo, ...band.hi] : [])].filter((v): v is number => v != null && isFinite(v));
    const lo = Math.min(...all), hi = Math.max(...all), pad = (hi - lo) * 0.08 || Math.abs(hi) * 0.01 || 1;
    return { min: lo - pad, max: hi + pad };
  }, [series, band]);
  const n = dates.length;
  if (n < 2) return <div className="flex h-40 items-center justify-center text-sm text-muted">Not enough history</div>;
  const x = (i: number) => P.l + (i / (n - 1)) * (W - P.l - P.r);
  const y = (v: number) => P.t + (1 - (v - min) / (max - min)) * (H - P.t - P.b);
  const path = (vals: (number | null)[]) => vals.map((v, i) => (v == null ? "" : `${i && vals[i - 1] != null ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`)).join("");
  const ticks = [0, 0.25, 0.5, 0.75, 1].map(f => min + f * (max - min));
  const labels = [0, Math.floor(n / 3), Math.floor((2 * n) / 3), n - 1];
  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Price chart"
        onMouseLeave={() => setHover(null)}
        onMouseMove={e => { const r = (e.currentTarget as SVGSVGElement).getBoundingClientRect(); const px = ((e.clientX - r.left) / r.width) * W; setHover(Math.max(0, Math.min(n - 1, Math.round(((px - P.l) / (W - P.l - P.r)) * (n - 1))))); }}>
        {ticks.map((t, i) => (
          <g key={i}><line x1={P.l} x2={W - P.r} y1={y(t)} y2={y(t)} stroke="var(--color-line)" strokeWidth={1} />
            <text x={W - P.r + 6} y={y(t) + 4} fontSize={11} fill="var(--color-muted)">{format(t)}</text></g>
        ))}
        {band && <path d={`${band.hi.map((v, i) => `${i ? "L" : "M"}${x(i)},${y(v)}`).join("")}${band.lo.map((v, i) => `L${x(band.lo.length - 1 - i)},${y(band.lo[band.lo.length - 1 - i])}`).join("")}Z`} fill={band.color ?? "#56b4e922"} />}
        {series.map((s, i) => <path key={i} d={path(s.values)} fill="none" stroke={s.color} strokeWidth={s.dashed ? 1.5 : 2} strokeDasharray={s.dashed ? "5 4" : undefined} />)}
        {labels.map(i => <text key={i} x={x(i)} y={H - 6} fontSize={11} fill="var(--color-muted)" textAnchor={i === 0 ? "start" : i === n - 1 ? "end" : "middle"}>{dates[i]}</text>)}
        {hover != null && <line x1={x(hover)} x2={x(hover)} y1={P.t} y2={H - P.b} stroke="var(--color-muted)" strokeDasharray="2 3" />}
      </svg>
      {hover != null && (
        <div className="pointer-events-none absolute left-2 top-2 rounded-md border border-line bg-bg/90 px-2 py-1 text-xs num">
          <div className="text-muted">{dates[hover]}</div>
          {series.map((s, i) => s.values[hover] != null && <div key={i} style={{ color: s.color }}>{s.label ?? ""} {format(s.values[hover] as number)}</div>)}
        </div>
      )}
    </div>
  );
}

export function Sparkline({ values, width = 90, height = 28 }: { values: number[]; width?: number; height?: number }) {
  if (values.length < 2) return null;
  const lo = Math.min(...values), hi = Math.max(...values), r = hi - lo || 1;
  const d = values.map((v, i) => `${i ? "L" : "M"}${((i / (values.length - 1)) * width).toFixed(1)},${(height - ((v - lo) / r) * height).toFixed(1)}`).join("");
  const up = values[values.length - 1] >= values[0];
  return <svg width={width} height={height} aria-hidden><path d={d} fill="none" stroke={up ? "var(--color-up)" : "var(--color-down)"} strokeWidth={1.5} /></svg>;
}
