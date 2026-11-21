"use client";
import Link from "next/link";
import type { TickerBarItem } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { num, pct } from "@/lib/format";
import { useAuth } from "@/components/AuthProvider";

export function TickerBar() {
  const { user, prefs } = useAuth();
  const { data } = useApi<TickerBarItem[]>("/api/market/tickerbar", 30_000, [user?.id, prefs.ticker_bar.join(",")]);
  if (user && !prefs.show_ticker_bar) return null;
  const items = data ?? [];
  const demo = items.some(i => i.source !== "LIVE");
  return (
    <div className="flex h-9 items-center overflow-hidden border-b border-line bg-card/60 text-xs print:hidden">
      <span className="z-10 shrink-0 border-r border-line bg-card px-3 py-2 text-muted">
        {items.length === 0 ? "Loading markets…" : demo ? "Markets · some prices demo/stale" : "Markets · live"}
      </span>
      <div className="relative flex-1 overflow-hidden">
        <div className="animate-ticker flex w-max gap-8 whitespace-nowrap px-4">
          {[...items, ...items].map((t, i) => (
            <Link key={i} href={`/ticker/${encodeURIComponent(t.symbol)}`} className="flex items-center gap-2 hover:text-primary num">
              <span className="font-semibold">{t.label}</span>
              <span>{num(t.price, t.price > 1000 ? 2 : t.symbol.includes("=X") ? 4 : 2)}</span>
              <span className={(t.change_pct ?? 0) >= 0 ? "text-up" : "text-down"}>{(t.change_pct ?? 0) >= 0 ? "▲" : "▼"} {pct(t.change_pct, 2, false)}</span>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
