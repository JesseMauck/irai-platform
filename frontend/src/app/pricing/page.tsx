import { Faq, PricingCards } from "@/components/Pricing";
import { PageHeader } from "@/components/ui";

export const metadata = { title: "Pricing" };

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
      <PageHeader title="Membership pricing" intro="Every plan includes the methodology and the learn library. Try Essential or Pro free for 7 days, no card needed. Paid plans are billed securely by Square." />
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
      <h2 className="mb-4 mt-16 text-xl font-semibold">Billing FAQ</h2>
      <Faq />
    </div>
  );
}
