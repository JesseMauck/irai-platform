import Link from "next/link";
import { HomeAdrPreview, HomeCommunity, HomeGradeCard } from "@/components/HomeLive";
import { Faq, PricingCards } from "@/components/Pricing";
import { Button, Card } from "@/components/ui";
import { JsonLd } from "@/components/JsonLd";
import { backendJson, pageMeta } from "@/lib/seo";

const ENGINES = [
  { href: "/monitor/adr", title: "ADR Monitor", body: "Cross-listed shares against their local lines, net of each pair’s structural basis. Every gap comes with the reasons it may not be tradable.",
    points: ["Premium vs basis ± 2σ band", "Z-score with entry/exit thresholds", "Half-life and borrow context"] },
  { href: "/monitor/etf", title: "ETF Monitor", body: "Fund premiums and discounts against an estimate of portfolio value — and the implementation tier that tells you how much to trust it.",
    points: ["NAV with implementation tiers", "Expense ratio and fund assets", "Flags for gaps that matter"] },
  { href: "/monitor/fundamental", title: "Fundamental RV", body: "Peer-relative valuation: cheap or expensive for their quality, growth and risk — shown as a residual against a peer regression, not a raw multiple.",
    points: ["Quality-adjusted residuals", "Peer groups with regression line", "Point-in-time grades"] },
];

const AUDIENCES: [string, string][] = [
  ["Self-directed investors", "Stress-test a thesis before you act on it. See what growth and margins the current price assumes, and where your story differs."],
  ["Analysts and students", "Get a complete, editable DCF in minutes — filings pulled, cost of capital priced, earnings normalised — then refine every input yourself."],
  ["Clubs, newsletters and small teams", "Share valuation reports and monitor views with a link. Every number carries its source, so the discussion is about assumptions, not data."],
];

const STEPS = [
  ["Build the peer group", "Names in the same industry with comparable size and disclosure."],
  ["Regress multiple on quality", "Log multiple vs a composite of returns on capital, margins and leverage."],
  ["Measure the residual", "Below the line is cheap for its quality; above is rich. The residual becomes a percentile."],
  ["Show the uncertainty", "Coverage confidence, data source, and the peer group itself are printed next to every score."],
];

export const metadata = {
  ...pageMeta("Irradiance.AI — AI stock valuation & relative-value research",
    "Value any stock in minutes with ValueBot: AI-built DCF valuations from SEC filings, plus live ADR and ETF premium monitors and quality-adjusted relative-value grades — every assumption shown.", "/"),
  title: { absolute: "Irradiance.AI — AI stock valuation & relative-value research" },
};

export default async function Home() {
  const faq = await backendJson<{ q: string; a: string }[]>("/api/faq");
  return (
    <>
      {faq && faq.length > 0 && <JsonLd data={{ "@context": "https://schema.org", "@type": "FAQPage",
        mainEntity: faq.map(f => ({ "@type": "Question", name: f.q, acceptedAnswer: { "@type": "Answer", text: f.a } })) }} />}
      <section className="hero-glow border-b border-line">
        <div className="mx-auto max-w-7xl px-4 py-20 md:py-28">
          <span className="inline-flex items-center gap-2 rounded-full border border-line bg-card px-3 py-1 text-xs text-muted">
            <span className="h-1.5 w-1.5 rounded-full bg-up" /> Live market data — press ⌘K and type any ticker
          </span>
          <h1 className="mt-6 max-w-4xl text-5xl font-semibold tracking-tight md:text-6xl">
            Value any stock in minutes. <span className="solar-text">See every assumption.</span>
          </h1>
          <p className="mt-6 max-w-2xl text-lg leading-relaxed text-muted">
            Irradiance.AI turns SEC filings and live market data into research you can check: AI-built DCF valuations,
            ADR and ETF premium monitors, and relative-value grades that show their working — not black-box ratings.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Button href="/valuebot">Value a stock free →</Button>
            <Button href="/signup?plan=essential" variant="outline">Start 7-day trial</Button>
          </div>
          <p className="mt-3 text-xs text-muted">No card needed for the trial · cancel any time · research and education, not investment advice</p>
          <dl className="mt-12 grid max-w-3xl grid-cols-2 gap-6 text-sm md:grid-cols-4">
            {[["18-stage", "DCF engine per valuation"], ["SEC EDGAR", "filings read for every model"], ["14 ADR pairs", "tracked against home markets"], ["Excel", "models you can open and edit"]].map(([k, v]) => (
              <div key={k}><dt className="text-lg font-semibold text-fg">{k}</dt><dd className="text-muted">{v}</dd></div>
            ))}
          </dl>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-4 py-16">
        <Card className="grid gap-8 p-8 md:grid-cols-2">
          <div>
            <span className="text-xs uppercase tracking-wide text-primary">ValueBot · AI valuation</span>
            <h2 className="mt-2 text-3xl font-semibold tracking-tight">Your thesis, turned into a valuation you can defend</h2>
            <p className="mt-3 text-muted">Type a ticker and tell the story you believe — growth, margins, reinvestment, risk, moat. ValueBot reads the company&rsquo;s SEC filings, prices its cost of capital from live markets, and runs an 18-stage narrative-and-numbers DCF. In a few minutes you get an intrinsic value, the assumptions behind it, and what the market price already implies.</p>
            <ul className="mt-4 space-y-1 text-sm text-fg-2">
              <li>• FCFF DCF, excess-return (banks) or dividend discount, picked automatically</li>
              <li>• Possible / plausible / probable story tests</li>
              <li>• Break-evens, Monte Carlo and an exact reverse DCF</li>
              <li>• Editable Excel model with live formulas, plus bull, bear and market-implied workbooks</li>
              <li>• A shareable report link for your team, club or class</li>
            </ul>
            <div className="mt-6 flex flex-wrap gap-3"><Button href="/valuebot">Value a stock free →</Button><Button href="/methodology" variant="outline">How ValueBot works</Button></div>
            <p className="mt-2 text-xs text-muted">Free members get one valuation a month. Essential gets 10; Pro is unlimited.</p>
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
        <h2 className="text-2xl font-semibold">Built for people who want to check the work</h2>
        <div className="mt-6 grid gap-4 md:grid-cols-3">
          {AUDIENCES.map(([t, b]) => (
            <Card key={t} className="p-6"><h3 className="font-semibold">{t}</h3><p className="mt-2 text-sm leading-relaxed text-muted">{b}</p></Card>
          ))}
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
        <div className="mb-6 flex items-end justify-between">
          <div><h2 className="text-2xl font-semibold">A community that shows its work</h2>
            <p className="mt-1 text-muted">Trade posts capture entry prices from market data at posting time — members can prove when they called it, not just that they say they did.</p></div>
          <Link href="/community" className="text-sm hover:text-primary">Browse the forum →</Link>
        </div>
        <HomeCommunity />
      </section>

      <section id="pricing" className="mx-auto max-w-7xl px-4 py-16">
        <h2 className="mb-2 text-center text-3xl font-semibold tracking-tight">Start free. Upgrade when it pays for itself.</h2>
        <p className="mb-8 text-center text-muted">Monthly prices shown · annual billing gets two months free · 7-day trial on paid plans, no card needed</p>
        <PricingCards />
      </section>

      <section className="mx-auto max-w-3xl px-4 py-16">
        <h2 className="mb-6 text-2xl font-semibold">Frequently asked</h2>
        <Faq />
      </section>

      <section className="border-t border-line">
        <div className="mx-auto flex max-w-7xl flex-col items-start justify-between gap-6 px-4 py-14 md:flex-row md:items-center">
          <div>
            <h2 className="text-2xl font-semibold">See what the market is pricing in.</h2>
            <p className="mt-1 text-muted">Run your first ValueBot valuation free — it takes about as long as reading this page.</p>
          </div>
          <div className="flex gap-3"><Button href="/valuebot">Value a stock free →</Button><Button href="/pricing" variant="outline">Compare plans</Button></div>
        </div>
      </section>
    </>
  );
}
