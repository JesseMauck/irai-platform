"use client";
import { BROKER_LOGOS } from "@/lib/brokerLogos";
import { num, pct } from "@/lib/format";

export interface Metric { key: string; label: string; group: string; format: "pct" | "ratio" | "num" | "days" | "money" | "int" }
export type Stats = Record<string, number | null>;
export interface StrategySchema { key: string; title: string; description: string; params: { key: string; label: string; default: number; min: number; max: number; step: number; kind: string }[] }

export const usd = (x: number | null | undefined, d = 0) =>
  x == null ? "—" : `${x < 0 ? "−" : ""}$${Math.abs(x).toLocaleString("en-US", { maximumFractionDigits: d, minimumFractionDigits: d })}`;

export function fmt(v: number | null | undefined, f: Metric["format"]) {
  if (v == null || Number.isNaN(v)) return "—";
  switch (f) {
    case "pct": return pct(v, Math.abs(v) < 0.1 ? 2 : 1, false);
    case "ratio": return num(v, 2);
    case "days": return `${Math.round(v)} d`;
    case "money": return usd(v, Math.abs(v) < 100 ? 2 : 0);
    case "int": return String(Math.round(v));
    default: return num(v, 2);
  }
}

export function TearSheet({ metrics, stats, compare }: { metrics: Metric[]; stats: Stats; compare?: Stats | null }) {
  const groups = Array.from(new Set(metrics.map(m => m.group)));
  return (
    <div className="grid gap-x-8 gap-y-5 md:grid-cols-2 xl:grid-cols-3">
      {groups.map(g => (
        <div key={g}>
          <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">{g}</div>
          <table className="w-full text-sm num">
            {compare && <thead><tr className="text-[10px] text-muted"><th /><th className="text-right font-normal">Live</th><th className="text-right font-normal">Backtest</th></tr></thead>}
            <tbody className="divide-y divide-line">{metrics.filter(m => m.group === g).map(m => (
              <tr key={m.key}><td className="py-1 font-sans text-muted">{m.label}</td>
                <td className="py-1 text-right">{fmt(stats[m.key], m.format)}</td>
                {compare && <td className="py-1 text-right text-muted">{fmt(compare[m.key], m.format)}</td>}</tr>))}</tbody>
          </table>
        </div>))}
    </div>
  );
}

export const BROKERS = ["Webull", "Robinhood", "Fidelity", "Charles Schwab", "Interactive Brokers", "E*TRADE"];
export const BROKER_LIST: { key: string; name: string }[] = [
  { key: "webull", name: "Webull" }, { key: "robinhood", name: "Robinhood" }, { key: "fidelity", name: "Fidelity" },
  { key: "schwab", name: "Charles Schwab" }, { key: "ibkr", name: "Interactive Brokers" }, { key: "etrade", name: "E*TRADE" },
  { key: "vanguard", name: "Vanguard" }, { key: "tastytrade", name: "tastytrade" }, { key: "alpaca", name: "Alpaca" },
];

/** A broker tile: the official logo when one has been added with permission (see lib/brokerLogos.ts), else a wordmark. */
export function BrokerTile({ k, name, size = "md" }: { k: string; name: string; size?: "sm" | "md" }) {
  const logo = BROKER_LOGOS[k];
  const h = size === "sm" ? "h-10 px-4 text-sm" : "h-14 px-6 text-base";
  return (
    <div className={`flex ${h} shrink-0 items-center justify-center rounded-xl border border-line bg-card`} title={name}>
      {/* eslint-disable-next-line @next/next/no-img-element -- small static SVGs */}
      {logo ? <img src={logo} alt={name} className="max-h-[60%] w-auto" /> : <span className="stat whitespace-nowrap tracking-tight">{name}</span>}
    </div>
  );
}

/** Broker tiles moving across the screen; pauses on hover. */
export function BrokerMarquee() {
  const row = [...BROKER_LIST, ...BROKER_LIST];
  return (
    <div className="group relative overflow-hidden py-2 [mask-image:linear-gradient(to_right,transparent,black_8%,black_92%,transparent)]">
      <div className="flex w-max animate-[marquee_32s_linear_infinite] gap-4 group-hover:[animation-play-state:paused]">
        {row.map((b, i) => <BrokerTile key={b.key + i} k={b.key} name={b.name} />)}
      </div>
    </div>
  );
}

export function BrokerStrip({ note = true }: { note?: boolean }) {
  return (
    <div>
      <div className="flex flex-wrap items-center gap-2">{BROKERS.map(b => <span key={b} className="rounded-full border border-line bg-card px-3 py-1 text-sm">{b}</span>)}
        <span className="text-sm text-muted">and other top platforms</span></div>
      {note && <p className="mt-2 text-[11px] text-muted">Live broker connections are coming soon; bots trade paper accounts today. Broker names are trademarks of their respective owners. Irradiance is independent and is not affiliated with, endorsed by or sponsored by any broker; listing a broker does not imply compatibility or endorsement.</p>}
    </div>
  );
}

export const REASON: Record<string, string> = { signal: "Strategy signal", stop_loss: "Stop-loss", take_profit: "Take-profit", auto_close: "Daily auto-close", webhook: "Webhook", manual: "Manual", close_bot: "Bot closed" };
