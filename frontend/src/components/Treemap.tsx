"use client";
/** Squarified treemap layout (Bruls, Huizing & van Wijk). Returns rectangles in the same order as the input. */
export interface Rect { x: number; y: number; w: number; h: number }

export function squarify(values: number[], x: number, y: number, w: number, h: number): Rect[] {
  const total = values.reduce((a, b) => a + b, 0);
  const out: Rect[] = new Array(values.length);
  if (!total || w <= 0 || h <= 0) return values.map(() => ({ x, y, w: 0, h: 0 }));
  const idx = values.map((v, i) => i).sort((a, b) => values[b] - values[a]);
  const area = idx.map(i => (values[i] / total) * w * h);
  let rx = x, ry = y, rw = w, rh = h, row: number[] = [], k = 0;
  const worst = (r: number[], side: number) => {
    const s = r.reduce((a, i) => a + area[i], 0);
    const mx = Math.max(...r.map(i => area[i])), mn = Math.min(...r.map(i => area[i]));
    return Math.max((side * side * mx) / (s * s), (s * s) / (side * side * mn));
  };
  const layout = (r: number[]) => {
    const s = r.reduce((a, i) => a + area[i], 0);
    if (rw >= rh) {
      const cw = s / rh; let cy = ry;
      for (const i of r) { const hh = area[i] / cw; out[idx[i]] = { x: rx, y: cy, w: cw, h: hh }; cy += hh; }
      rx += cw; rw -= cw;
    } else {
      const ch = s / rw; let cx = rx;
      for (const i of r) { const ww = area[i] / ch; out[idx[i]] = { x: cx, y: ry, w: ww, h: ch }; cx += ww; }
      ry += ch; rh -= ch;
    }
  };
  const order = idx.map((_, i) => i);
  while (k < order.length) {
    const side = Math.min(rw, rh);
    const cand = [...row, order[k]];
    if (!row.length || worst(cand, side) <= worst(row, side)) { row = cand; k++; }
    else { layout(row); row = []; }
  }
  if (row.length) layout(row);
  return out;
}

export function heatColor(change: number | null | undefined, scale: number) {
  if (change == null) return "rgba(128,128,140,0.25)";
  const t = Math.max(-1, Math.min(1, change / scale));
  const a = 0.18 + Math.abs(t) * 0.72;
  return t >= 0 ? `rgba(34,176,125,${a})` : `rgba(224,72,72,${a})`;
}
