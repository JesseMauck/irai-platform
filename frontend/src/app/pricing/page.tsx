import Link from "next/link";
import { pageMeta } from "@/lib/seo";
import { Faq, PricingCards } from "@/components/Pricing";
import { PageHeader } from "@/components/ui";

export const metadata = pageMeta("Pricing: Free, Essential and Pro plans",
  "Start free, or try Essential ($49/mo) or Pro ($100/mo) free for 7 days with no card. AI valuations, Analyst Bot, Pattern Lab, Premium Signals, paper-trading bots, monitors and screeners.", "/pricing");

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
  ["Analyst Bot (AI ticker notes)", "1 run / day", "10 runs / day", "Unlimited"],
  ["Ask IRAI assistant", "10 messages / day", "60 messages / day", "300 messages / day"],
  ["Pattern Lab (stress-tested patterns)", "Scorecard + today's regime and state", "Scorecard + today's regime and state", "Full evidence, every asset class and timeframe, your own tests, live order-book pulse"],
  ["Premium Signals (daily IRAI scan)", "Top 3 each day", "Top 3 each day", "Full scan + track record"],
  ["Portfolio analysis + AI review", "—", "—", "10 portfolios, CSV import from your broker"],
  ["AlgoTrader bots (paper trading)", "—", "—", "20 bots, 5 paper accounts, webhooks, tear sheets"],
  ["Data export / API", "—", "—", "CSV export + read-only API key"],
  ["Support", "—", "Email", "Priority"],
];

export default function Pricing() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-12">
      <PageHeader title="Start free. Go deeper when you are ready." intro="Start free with live quotes, an AI valuation every month and the full methodology. When you want more depth, try Essential or Pro free for 7 days with no card, then pay monthly or get two months free with annual billing. Square processes payments securely, and you can cancel from your account in two clicks." />
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
        <div><div className="text-xs uppercase tracking-wide text-primary">Included in Pro · live brokers coming soon</div>
          <h2 className="mt-1 text-xl font-semibold">IRAI AlgoTrader</h2>
          <p className="mt-1 max-w-2xl text-sm text-muted">Build a strategy in plain English, backtest it with a 57-metric tear sheet, and run it on paper accounts today. Live connection to Webull, Robinhood, Fidelity, Charles Schwab, Interactive Brokers, E*TRADE and other top platforms is next: join the waitlist to be first in.</p></div>
        <Link href="/algotrader" className="solar-bg rounded-lg px-4 py-2 text-sm font-semibold text-primary-fg">See AlgoTrader</Link>
      </div>
      <h2 className="mb-4 mt-16 text-xl font-semibold">Billing FAQ</h2>
      <Faq />
    </div>
  );
}
