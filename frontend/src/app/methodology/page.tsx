import { pageMeta } from "@/lib/seo";
import { PageHeader } from "@/components/ui";

export const metadata = pageMeta("Methodology — how every number is calculated",
  "The formulas behind Irradiance.AI: ADR premium and structural basis, ETF NAV tiers, quality-adjusted relative-value regressions, and ValueBot's DCF stages.", "/methodology");

const SECTIONS: [string, string, [string, string][]][] = [
  ["ADR Monitor", "Premium = ADR price ÷ (local price × depositary ratio × spot FX) − 1. Quotes in pence or cents are converted to major units first.", [
    ["Structural basis", "The pair's median premium over the trailing year of shared trading days."],
    ["Z-score", "Today's deviation from basis divided by the standard deviation of historical deviations."],
    ["Half-life", "From an AR(1) fit of daily changes in the deviation on its lagged level: −ln 2 / ln(1 + b)."],
    ["Fair-value source", "LIVE when the local market is open and its quote is under 30 minutes old; PROXY when it is closed (last close at live FX); STALE when a quote is older; DEMO for synthetic fallback data."],
    ["Confidence", "Starts at 100 and is reduced for PROXY or STALE sources, short shared history and noisy pairs."],
    ["Rejection reasons", "Deviation below estimated round-trip costs, |z| under 2, unborrowable local shares, closed local market, stale prices or missing history."],
  ]],
  ["ETF Monitor", "Premium = fund price ÷ issuer NAV − 1, using the NAV the issuer struck at the prior close.", [
    ["Tier", "NAV (prior close). An intraday iNAV requires a licensed holdings feed; the column will say so when one is connected."],
    ["Flags", "Gaps of 0.5% or more are flagged as a prompt to check liquidity and creation/redemption costs."],
  ]],
  ["Fundamental Relative Value", "Within each peer group we ask whether a company is cheap for its quality.", [
    ["Quality composite", "Average of standardized ROE, operating margin and inverted leverage (debt/equity)."],
    ["Multiple", "EV/EBITDA when most of the group reports it, otherwise trailing P/E. Negative multiples are excluded."],
    ["Residual", "log(multiple) minus the fitted value from a regression on quality. Negative = cheaper than its quality justifies."],
    ["Grade", "The residual's percentile in the group (A+ ≥ 95th … F < 15th). Each computation is stored point-in-time and never restated."],
  ]],
  ["ValueBot", "A Damodaran-style narrative-and-numbers DCF, run in 18 stages.", [
    ["Data", "SEC EDGAR XBRL facts for US filers, Yahoo Finance statements otherwise; price, beta and consensus from Yahoo Finance."],
    ["Framework", "Banks and insurers → excess return; high-payout utilities and REITs → dividend discount; everything else → FCFF."],
    ["Risk", "Risk-free = 10-year Treasury minus the US default spread; bottom-up beta; ERP weighted by where revenue is earned; synthetic rating → cost of debt."],
    ["Earnings", "R&D capitalized, operating leases treated as debt, one-time items removed."],
    ["Tests and outputs", "Possible / plausible / probable checks, sensitivity, break-evens, correlated Monte Carlo, exact reverse DCF, and Excel models whose formulas reproduce the Python value to 1e-9."],
  ]],
];

export default function Methodology() {
  return (
    <div className="mx-auto max-w-4xl px-4 py-12">
      <PageHeader title="Methodology" intro="How every grade, score and signal is computed — inputs, formulas and limitations. Nothing on this site is a recommendation." />
      {SECTIONS.map(([h, intro, items]) => (
        <section key={h} className="mb-12">
          <h2 className="text-2xl font-semibold">{h}</h2><p className="mt-2 text-muted">{intro}</p>
          <dl className="mt-4 divide-y divide-line rounded-xl border border-line bg-card">
            {items.map(([k, v]) => <div key={k} className="grid gap-2 p-4 md:grid-cols-4"><dt className="font-medium">{k}</dt><dd className="text-sm text-muted md:col-span-3">{v}</dd></div>)}
          </dl>
        </section>
      ))}
      <section><h2 className="text-2xl font-semibold">Known limitations</h2>
        <ul className="mt-3 list-disc space-y-1 pl-5 text-muted">
          <li>Free market data is delayed for many non-US exchanges and can be revised.</li>
          <li>Depositary ratios change after splits and restructurings; verify them before acting.</li>
          <li>Peer groups are judgement calls and are reviewed quarterly.</li>
          <li>Filed data lags and is restated; half-life estimates assume regimes persist.</li>
        </ul></section>
    </div>
  );
}
