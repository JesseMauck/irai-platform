import Link from "next/link";
import { HomeAdrPreview, HomeCommunity, HomeGradeCard } from "@/components/HomeLive";
import { Faq, PricingCards } from "@/components/Pricing";
import { Button, Card } from "@/components/ui";

const ENGINES = [
  { href: "/monitor/adr", title: "ADR Monitor", body: "Cross-listed shares against their local lines, net of each pair’s structural basis. Every gap comes with the reasons it may not be tradable.",
    points: ["Premium vs basis ± 2σ band", "Z-score with entry/exit thresholds", "Half-life and borrow context"] },
  { href: "/monitor/etf", title: "ETF Monitor", body: "Fund premiums and discounts against an estimate of portfolio value — and the implementation tier that tells you how much to trust it.",
    points: ["NAV with implementation tiers", "Expense ratio and fund assets", "Flags for gaps that matter"] },
  { href: "/monitor/fundamental", title: "Fundamental RV", body: "Peer-relative valuation: cheap or expensive for their quality, growth and risk — shown as a residual against a peer regression, not a raw multiple.",
    points: ["Quality-adjusted residuals", "Peer groups with regression line", "Point-in-time grades"] },
];

const STEPS = [
  ["Build the peer group", "Names in the same industry with comparable size and disclosure."],
  ["Regress multiple on quality", "Log multiple vs a composite of returns on capital, margins and leverage."],
  ["Measure the residual", "Below the line is cheap for its quality; above is rich. The residual becomes a percentile."],
  ["Show the uncertainty", "Coverage confidence, data source, and the peer group itself are printed next to every score."],
];

export default function Home() {
  return (
    <>
      <section className="hero-glow border-b border-line">
        <div className="mx-auto max-w-7xl px-4 py-20 md:py-28">
          <span className="inline-flex items-center gap-2 rounded-full border border-line bg-card px-3 py-1 text-xs text-muted">
            <span className="h-1.5 w-1.5 rounded-full bg-up" /> Live market data — type any ticker with ⌘K
          </span>
          <h1 className="mt-6 max-w-4xl text-5xl font-semibold tracking-tight md:text-6xl">
            Illuminating the <span className="solar-text">market research</span>
          </h1>
          <p className="mt-6 max-w-2xl text-lg leading-relaxed text-muted">
            Relative-value research across ADRs, ETFs and fundamentals — with the methodology shown. Every signal ships with its
            inputs, its uncertainty, and the reasons it might not be tradable.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Button href="/signup?plan=essential">Start 7-day trial →</Button>
            <Button href="/research" variant="outline">See a sample report</Button>
          </div>
          <p className="mt-3 text-xs text-muted">No card needed for the 7-day trial · reminder email 48 hours before it ends</p>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-4 py-16">
        <div className="mb-6 flex items-end justify-between gap-4">
          <div><h2 className="text-2xl font-semibold">The ADR Monitor, as a reader sees it</h2>
            <p className="mt-1 text-muted">Deviations from structural basis, with confidence and fair-value source on every row.</p></div>
          <Link href="/monitor/adr" className="shrink-0 text-sm hover:text-primary">Open the full monitor →</Link>
        </div>
        <HomeAdrPreview />
      </section>

      <section className="mx-auto max-w-7xl px-4 py-16">
        <h2 className="text-2xl font-semibold">Three engines, one standard of proof</h2>
        <p className="mt-2 max-w-3xl text-muted">Each monitor is a separate research engine, but they share one rule: show the inputs, the uncertainty, and the reasons a signal might fail.</p>
        <div className="mt-6 grid gap-4 md:grid-cols-3">
          {ENGINES.map(e => (
            <Link key={e.href} href={e.href} className="group rounded-xl border border-line bg-card p-6 transition hover:border-primary/50">
              <h3 className="font-semibold group-hover:text-primary">{e.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-muted">{e.body}</p>
              <ul className="mt-4 space-y-1 text-sm text-fg-2">{e.points.map(x => <li key={x}>– {x}</li>)}</ul>
            </Link>
          ))}
        </div>
      </section>

      <section className="mx-auto grid max-w-7xl gap-10 px-4 py-16 lg:grid-cols-2">
        <div>
          <h2 className="text-2xl font-semibold">Transparent by design</h2>
          <p className="mt-2 text-muted">A grade is not a vibe. Take the Relative Value grade: it starts with a peer regression of valuation multiple on a quality composite, then measures how far each name sits from the line its peers justify.</p>
          <ol className="mt-6 space-y-4">
            {STEPS.map(([t, b], i) => (
              <li key={t} className="flex gap-4">
                <span className="solar-bg flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-sm font-bold text-primary-fg">{i + 1}</span>
                <div><div className="font-medium">{t}</div><div className="text-sm text-muted">{b}</div></div>
              </li>
            ))}
          </ol>
          <Link href="/methodology" className="mt-6 inline-block text-sm hover:text-primary">Read the full methodology →</Link>
        </div>
        <HomeGradeCard />
      </section>

      <section className="mx-auto max-w-7xl px-4 py-16">
        <Card className="grid gap-8 p-8 md:grid-cols-2">
          <div>
            <span className="text-xs uppercase tracking-wide text-primary">ValueBot</span>
            <h2 className="mt-2 text-2xl font-semibold">Put your thesis to the test</h2>
            <p className="mt-3 text-muted">Pick any public company and tell its story — growth, profitability, reinvestment, risk, moat. ValueBot pulls SEC filings and live market data, measures earnings right, and runs an 18-stage narrative-and-numbers valuation.</p>
            <ul className="mt-4 space-y-1 text-sm text-fg-2">
              <li>• FCFF DCF, excess-return (banks) or dividend discount, picked automatically</li>
              <li>• Possible / plausible / probable story tests</li>
              <li>• Break-evens, Monte Carlo and an exact reverse DCF</li>
              <li>• Editable Excel model with live formulas, plus bull, bear and market-implied workbooks</li>
            </ul>
            <div className="mt-6"><Button href="/valuebot">Value a company →</Button></div>
          </div>
          <div className="rounded-lg border border-line bg-bg p-5 font-mono text-xs leading-6 text-fg-2">
            <div className="text-muted">$ valuebot AAPL --stance bearish</div>
            {["Resolve company", "Pull filings and market data", "Estimate cost of capital", "Measure earnings right", "Translate the story into numbers", "Run the valuation", "Test the story", "Break-evens, scenarios and simulation", "Build the Excel model", "Write the report"].map(s => (
              <div key={s}><span className="text-up">✓</span> {s}</div>
            ))}
          </div>
        </Card>
      </section>

      <section className="mx-auto max-w-7xl px-4 py-16">
        <div className="mb-6 flex items-end justify-between">
          <div><h2 className="text-2xl font-semibold">A community that shows its work</h2>
            <p className="mt-1 text-muted">Trade posts capture entry prices from market data at posting time — members can prove when they called it, not just that they say they did.</p></div>
          <Link href="/community" className="text-sm hover:text-primary">Browse the forum →</Link>
        </div>
        <HomeCommunity />
      </section>

      <section id="pricing" className="mx-auto max-w-7xl px-4 py-16">
        <h2 className="mb-2 text-center text-2xl font-semibold">Membership</h2>
        <p className="mb-8 text-center text-muted">Monthly prices shown. Annual billing gets two months free.</p>
        <PricingCards />
      </section>

      <section className="mx-auto max-w-3xl px-4 py-16">
        <h2 className="mb-6 text-2xl font-semibold">Frequently asked</h2>
        <Faq />
      </section>
    </>
  );
}
