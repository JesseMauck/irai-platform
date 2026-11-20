export const pct = (x: number | null | undefined, d = 2, sign = true) =>
  x == null || !isFinite(x) ? "—" : `${sign && x > 0 ? "+" : ""}${(x * 100).toFixed(d)}%`;
export const num = (x: number | null | undefined, d = 2) =>
  x == null || !isFinite(x) ? "—" : x.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
export const signed = (x: number | null | undefined, d = 1) =>
  x == null || !isFinite(x) ? "—" : `${x > 0 ? "+" : ""}${x.toFixed(d)}`;
export const compact = (x: number | null | undefined) =>
  x == null || !isFinite(x) ? "—" : Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(x);
export const ord = (x: number | null | undefined) => {
  if (x == null) return "—";
  const n = Math.round(x); const s = ["th", "st", "nd", "rd"]; const v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
};
export const ago = (iso: string | null | undefined) => {
  if (!iso) return "—";
  const m = (Date.now() - new Date(iso).getTime()) / 60000;
  if (m < 1) return "just now"; if (m < 60) return `${Math.round(m)}m ago`;
  if (m < 1440) return `${Math.round(m / 60)}h ago`; return `${Math.round(m / 1440)}d ago`;
};
export const tone = (x: number | null | undefined) => (x == null ? "text-muted" : x > 0 ? "text-up" : x < 0 ? "text-down" : "text-muted");
