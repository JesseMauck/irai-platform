import type { Section } from "./terms";

export const DISCLAIMER_UPDATED = "November 20, 2026";

export const DISCLAIMER: Section[] = [
  { id: "education", title: "1. Educational and impersonal research only (no financial advice)", blocks: [
    "Irradiance.AI (irradiance.ai) is a financial research and education platform. All content, articles, data visualizations, tools and model outputs published on the site are impersonal, informational and educational.",
    "Nothing on Irradiance is, or should be read as, investment, financial, legal, accounting or tax advice, or a solicitation, recommendation, endorsement or offer to buy, sell or hold any security, cryptocurrency, derivative or other financial instrument in any jurisdiction. Labels such as letter grades, \"quant ratings\", \"opportunities\", buzz levels or consensus summaries describe characteristics of the data; they are not instructions to trade.",
  ] },
  { id: "no-fiduciary", title: "2. No fiduciary relationship or personalized advice", blocks: [
    "Irradiance is not a registered broker-dealer, registered investment adviser (RIA), fiduciary or financial planner.",
    { list: [
      "No individual assessment: we do not know, evaluate or take into account your financial situation, risk tolerance, investment objectives or liquidity needs.",
      "No trade execution: Irradiance does not hold customer funds, manage portfolios or execute trades on your behalf.",
      "Consult a professional: do your own independent due diligence and consult a qualified, licensed financial adviser, lawyer or tax professional before making any investment or financial decision.",
    ] },
  ] },
  { id: "models", title: "3. Model outputs, AI tools and ValueBot valuations", blocks: [
    "Automated tools, quantitative models and AI features on Irradiance — including ValueBot valuations, intrinsic-value and price estimates, scenario and Monte Carlo analyses, Strategy Lab backtests, quant ratings, ADR and ETF signals, buzz scores and screening metrics — are hypothetical estimates built from historical data, mathematical formulas and assumptions that may be incomplete, flawed or proved wrong by future events.",
    { list: [
      "Probabilistic and subject to error: model and AI outputs may contain inaccuracies, omissions or computational errors. They are never guarantees of intrinsic value or future market prices.",
      "Assumptions drive results: small changes to inputs such as growth, margins or discount rates can change a valuation materially. Every ValueBot report shows its assumptions so you can test them.",
      "Past performance: past performance, backtested results and historical simulations do not indicate or guarantee future results. Backtests benefit from hindsight and may not reflect real trading costs, liquidity or taxes.",
    ] },
  ] },
  { id: "data", title: "4. Third-party market data and exchange terms", blocks: [
    "Market quotes, financial statements, fundamental metrics, filings and news shown on Irradiance come from third-party data vendors, public sources (such as SEC EDGAR, the European Central Bank, the U.S. Treasury and GDELT) and exchanges.",
    { list: [
      "No guarantee of accuracy or timeliness: market data may be delayed, interrupted, incomplete or inaccurate. Many non-U.S. quotes are delayed 15–20 minutes. Irradiance makes no representation or warranty about the accuracy, reliability or timeliness of third-party data and has no obligation to update or correct information after publication.",
      "Source labels: every figure carries a source label. LIVE is the market feed; EOD is official end-of-day data; STALE is the last stored value; DEMO is a synthetic placeholder shown only when no real data is available and must never be relied on.",
      "Vendor and exchange restrictions: all market data is subject to the terms, conditions and redistribution restrictions of its providers and exchanges.",
    ] },
  ] },
  { id: "conflicts", title: "5. Potential conflicts of interest", blocks: [
    "Irradiance, its founders, employees, contributors and affiliates may from time to time hold long or short positions in, or buy and sell, securities or assets discussed on the platform, subject to our Disclosure Policy (including the restriction on trading covered securities before and shortly after publication). Authors disclose relevant positions with their articles.",
    "Opinions and research reflect the views of the author, or the output of the model, at the time of publication and may change without notice. Community posts are the views of the members who wrote them, not of Irradiance.",
  ] },
  { id: "risk", title: "6. Assumption of risk and limitation of liability", blocks: [
    "Investing and trading involve substantial risk, including the loss of all principal. By using Irradiance you acknowledge that you are solely responsible for your own research and financial decisions.",
    "To the fullest extent permitted by law, Irradiance disclaims all liability for any direct, indirect, incidental or consequential loss or damage — including trading losses or lost profits — arising from or in reliance on any content, market data, or ValueBot or other model output on the site. See our Terms of Service for the full limitation of liability.",
  ] },
];
