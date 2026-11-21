import Link from "next/link";
import type { Source } from "@/lib/api";

export function SourceBadge({ source }: { source: Source | string | undefined }) {
  const s = (source ?? "—").toUpperCase();
  const cls: Record<string, string> = {
    LIVE: "bg-up/15 text-up ring-up/30", PROXY: "bg-data-1/15 text-data-1 ring-data-1/30",
    STALE: "bg-down/15 text-down ring-down/30", EOD: "bg-primary/15 text-primary ring-primary/30", DEMO: "bg-muted/15 text-muted ring-muted/30",
    ERROR: "bg-red-500/15 text-red-400 ring-red-500/30",
  };
  return <span className={`inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold tracking-wide ring-1 ${cls[s] ?? cls.DEMO}`}>{s}</span>;
}

export function Pill({ children, tone = "muted" }: { children: React.ReactNode; tone?: "muted" | "primary" | "up" | "down" }) {
  const t = { muted: "bg-accent text-muted", primary: "bg-primary/15 text-primary", up: "bg-up/15 text-up", down: "bg-down/15 text-down" }[tone];
  return <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${t}`}>{children}</span>;
}

export function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <div className={`rounded-xl border border-line bg-card ${className}`}>{children}</div>;
}

export function PageHeader({ title, intro, children }: { title: string; intro?: React.ReactNode; children?: React.ReactNode }) {
  return (
    <div className="mb-8 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight md:text-4xl">{title}</h1>
        {intro && <p className="mt-2 max-w-3xl text-muted">{intro}</p>}
      </div>
      {children}
    </div>
  );
}

export function Button({ href, children, variant = "primary", onClick, type = "button", disabled, className = "" }: {
  href?: string; children: React.ReactNode; variant?: "primary" | "ghost" | "outline"; onClick?: () => void;
  type?: "button" | "submit"; disabled?: boolean; className?: string;
}) {
  const v = {
    primary: "solar-bg text-primary-fg font-semibold hover:brightness-110",
    outline: "border border-line bg-card hover:bg-accent text-fg",
    ghost: "text-muted hover:text-fg hover:bg-accent",
  }[variant];
  const cls = `inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm transition disabled:opacity-50 ${v} ${className}`;
  if (href) return <Link href={href} className={cls}>{children}</Link>;
  return <button type={type} onClick={onClick} disabled={disabled} className={cls}>{children}</button>;
}

export function Skeleton({ rows = 5 }: { rows?: number }) {
  return <div className="space-y-2 p-4">{Array.from({ length: rows }).map((_, i) => <div key={i} className="h-6 animate-pulse rounded bg-accent" />)}</div>;
}

export function ErrorNote({ error }: { error: { message: string } | null }) {
  if (!error) return null;
  return <div className="rounded-lg border border-down/30 bg-down/10 p-3 text-sm text-down">{error.message}</div>;
}

export function LockedRows({ locked, what = "rows" }: { locked: number; what?: string }) {
  if (!locked) return null;
  return (
    <div className="flex flex-col items-center gap-2 border-t border-line bg-accent/40 p-5 text-center text-sm">
      <p className="text-muted">{locked} more {what} on Essential and Pro.</p>
      <Button href="/pricing">See plans</Button>
    </div>
  );
}

export function DataNote({ children }: { children?: React.ReactNode }) {
  return <p className="mt-3 text-xs text-muted">{children ?? "LIVE = market feed (US quotes usually real-time; many non-US exchanges delayed 15–20 min). EOD = official end-of-day open data (ECB FX reference rates, U.S. Treasury yields). STALE = last stored price. DEMO = synthetic placeholder shown only when no real data is available. Research and education only, not investment advice."}</p>;
}

export function TickerLink({ symbol, className = "" }: { symbol: string; className?: string }) {
  return <Link href={`/ticker/${encodeURIComponent(symbol)}`} className={`font-semibold text-fg hover:text-primary ${className}`}>{symbol}</Link>;
}
