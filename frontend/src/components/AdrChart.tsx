"use client";
import type { AdrRow } from "@/lib/api";
import { LineChart } from "./Chart";

/** Premium history vs the structural basis with a ±2σ band. */
export function AdrChart({ row, height = 220 }: { row: AdrRow; height?: number }) {
  const h = row.premium_history ?? [];
  if (h.length < 2 || row.basis == null) return <div className="p-6 text-sm text-muted">Not enough shared history for a chart.</div>;
  const b = row.basis;
  const devs = h.map(p => p.premium - b);
  const sd = Math.sqrt(devs.reduce((s, d) => s + d * d, 0) / devs.length);
  return (
    <LineChart height={height} dates={h.map(p => p.date)} format={v => `${(v * 100).toFixed(1)}%`}
      band={{ lo: h.map(() => b - 2 * sd), hi: h.map(() => b + 2 * sd), color: "#56b4e91a" }}
      series={[
        { values: h.map(p => p.premium), color: "#f5a524", label: "Premium" },
        { values: h.map(() => b), color: "var(--color-muted)", dashed: true, label: "Basis" },
      ]} />
  );
}
