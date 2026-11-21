import Link from "next/link";
import { pageMeta } from "@/lib/seo";
import { Faq, PricingCards } from "@/components/Pricing";
import { PageHeader } from "@/components/ui";

export const metadata = pageMeta("Pricing: Free, Essential and Pro plans",
  "Start free, or try Essential ($49/mo) or Pro ($100/mo) free for 7 days with no card. ValueBot valuations, full ADR, ETF and relative-value monitors, screeners and the Strategy Lab.", "/pricing");

const ROWS: [string, string, string, string][] = [
  ["Articles", "Headlines + 3 full / month", "Unlimited", "Unlimited"],
  ["Ticker pages", "Live quote, chart, stats", "+ Full grades + explanations", "+ Grade history + peer percentiles"],
  ["ADR / ETF Monitor", "Top 5 rows", "Full tables", "Full tables, real-time where licensed"],
  ["Fundamental scores", "Top 5 rows", "All covered names + peer groups", "+ Pair ideas"],
  ["ValueBot", "1 run / month", "10 runs / month", "Unlimited + all scenario workbooks"],
  ["Screeners", "2 preset screens", "All presets + 5 saved", "Unlimited saved + CSV export"],
  ["Watchlists", "1 list, 10 tickers", "10 lists, 100 tickers each", "Unlimited"],
  ["Alerts", "—", "Email (20 active)", "Email, push, webhook (100 active)"],
  ["Forum", "Read", "Read, post, comment, vote, post trades", "+ Verified-trader eligibility, Pro rooms"],
  ["Data export / API", "—", "—", "CSV export + read-only API key"],
  ["Support", "—", "Email", "Priority"],
];

export default function Pricing() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-12">
      <PageHeader title="Simple pricing for research you can check" intro="Start free with live quotes, one ValueBot valuation a month and the full methodology. Try Essential or Pro free for 7 days (no card needed), then pay monthly or save two months with annual billing. Payments are processed securely by Square, and you can cancel from your account at any time." />
      <PricingCards />
      <h2 className="mt-16 text-xl font-semibold">Compare plans</h2>
      <div className="mt-4 overflow-x-auto rounded-xl border border-line">
        <table className="w-full min-w-[720px] text-sm">
          <thead className="bg-card text-left"><tr><th className="p-3">Feature</th><th className="p-3">Free</th><th className="p-3">Essential</th><th className="p-3">Pro</th></tr></thead>
          <tbody className="divide-y divide-line">{ROWS.map(r => <tr key={r[0]}>{r.map((c, i) => <td key={i} className={`p-3 ${i ? "text-fg-2" : "font-medium"}`}>{c}</td>)}</tr>)}</tbody>
        </table>
      </div>
      <ul className="mt-4 space-y-1 text-sm text-muted">
        <li>Upgrades apply immediately with proration; downgrades take effect at the end of the billing period.</li>
        <li>Real-time data depends on both the Pro plan and data licensing, and is labelled per market.</li>
      </ul>
      <div className="mt-12 flex flex-wrap items-center justify-between gap-4 rounded-xl border border-primary/40 bg-card p-6">
        <div><div className="text-xs uppercase tracking-wide text-primary">Pro add-on · coming soon</div>
          <h2 className="mt-1 text-xl font-semibold">IRAI AlgoTrader</h2>
          <p className="mt-1 max-w-2xl text-sm text-muted">Seamless connection to Webull, Robinhood, Fidelity, Charles Schwab, Interactive Brokers, E*TRADE and other top platforms. AI analysis of your holdings, portfolio health checks, and rules-based strategies you approve.</p></div>
        <Link href="/algotrader" className="solar-bg rounded-lg px-4 py-2 text-sm font-semibold text-primary-fg">Join the waitlist</Link>
      </div>
      <h2 className="mb-4 mt-16 text-xl font-semibold">Billing FAQ</h2>
      <Faq />
    </div>
  );
}
