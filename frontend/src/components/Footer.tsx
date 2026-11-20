import Link from "next/link";
import { Logo } from "./Header";

const COLS: [string, [string, string][]][] = [
  ["Research", [["Articles", "/research"], ["ADR Monitor", "/monitor/adr"], ["ETF Monitor", "/monitor/etf"], ["Fundamental RV", "/monitor/fundamental"], ["ValueBot", "/valuebot"], ["Strategy Lab", "/lab"], ["Screeners", "/screeners"]]],
  ["Community", [["Forum", "/community"], ["Trade feed", "/trades"], ["Leaderboards", "/leaderboards"]]],
  ["Company", [["Pricing", "/pricing"], ["Methodology", "/methodology"], ["Learn", "/learn"], ["Account", "/account"]]],
  ["Legal", [["Terms", "/legal/terms"], ["Privacy", "/legal/privacy"], ["Disclaimer", "/legal/disclaimer"], ["Community guidelines", "/legal/community-guidelines"], ["Disclosure policy", "/legal/disclosure-policy"]]],
];

export function Footer() {
  return (
    <footer className="mt-24 border-t border-line">
      <div className="mx-auto grid max-w-7xl gap-10 px-4 py-12 md:grid-cols-5">
        <div className="md:col-span-1"><Logo /><p className="mt-3 text-sm text-muted">Illuminating the market research.</p></div>
        {COLS.map(([h, links]) => (
          <div key={h}>
            <h3 className="text-sm font-semibold">{h}</h3>
            <ul className="mt-3 space-y-2">{links.map(([l, href]) => <li key={href}><Link href={href} className="text-sm text-muted hover:text-fg">{l}</Link></li>)}</ul>
          </div>
        ))}
      </div>
      <div className="border-t border-line">
        <p className="mx-auto max-w-7xl px-4 py-6 text-xs leading-relaxed text-muted">
          Research and education only. Not investment advice. Irradiance is a publisher of impersonal research for a general paid
          readership; it does not provide personalized recommendations and does not execute trades. Past performance does not guarantee
          future results. Market data may be delayed and is labelled by source (LIVE, PROXY, STALE, DEMO). Market data display is
          subject to vendor and exchange agreements.
        </p>
        <p className="mx-auto max-w-7xl px-4 pb-6 text-xs text-muted">© 2026 Irradiance Research, Inc.
        </p>
      </div>
    </footer>
  );
}
