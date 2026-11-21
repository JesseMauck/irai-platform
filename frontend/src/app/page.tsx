import Link from "next/link";
import { HomeAdrPreview, HomeCommunity, HomeGradeCard } from "@/components/HomeLive";
import { Faq, PricingCards } from "@/components/Pricing";
import { Button, Card } from "@/components/ui";
import { JsonLd } from "@/components/JsonLd";
import { FeatureShowcase, type Showcase, TiltShot } from "@/components/Tilt";
import { backendJson, pageMeta } from "@/lib/seo";

const ENGINES = [
  { href: "/monitor/adr", title: "ADR Monitor", body: "Cross-listed shares against their local lines, net of each pair’s structural basis. Every gap comes with the reasons it may not be tradable.",
    points: ["Premium vs basis ± 2σ band", "Z-score with entry/exit thresholds", "Half-life and borrow context"] },
  { href: "/monitor/etf", title: "ETF Monitor", body: "Fund premiums and discounts against an estimate of portfolio value, plus the implementation tier that tells you how much to trust it.",
    points: ["NAV with implementation tiers", "Expense ratio and fund assets", "Flags for gaps that matter"] },
  { href: "/monitor/fundamental", title: "Fundamental RV", body: "Peer-relative valuation: cheap or expensive for their quality, growth and risk, measured as a residual against a peer regression, not a raw multiple.",
    points: ["Quality-adjusted residuals", "Peer groups with regression line", "Point-in-time grades"] },
];

const PLATFORM: { href: string; tag: string; title: string; body: string }[] = [
  { href: "/valuebot", tag: "Value", title: "ValueBot", body: "Tell it your thesis; get a full DCF from SEC filings, the price the market is assuming, and an Excel model you can edit." },
  { href: "/ticker/AAPL#analyst", tag: "Understand", title: "Analyst Bot", body: "A complete research note on any ticker in under a minute: business, valuation, technicals, news and risks, with sources." },
  { href: "/patterns", tag: "Discover", title: "Pattern Lab", body: "Market regimes, recurring states and lead-lag links, plus six patterns tested on every asset class. We publish the ones that fail." },
  { href: "/signals", tag: "Monitor", title: "Premium Signals", body: "Every evening IRAI scans the most-traded US names for breakouts, trend crosses, unusual moves and attention spikes." },
  { href: "/algotrader", tag: "Automate", title: "IRAI AlgoTrader", body: "Describe a strategy in plain English, backtest it with a 57-metric tear sheet, then run it on paper before anything else." },
  { href: "/terminal", tag: "Ask", title: "Ask IRAI", body: "An AI research copilot on every screen that knows the ticker, theme or portfolio you are looking at." },
];

const SHOWCASE: Showcase[] = [
  { src: "/showcase/valuebot.webp", alt: "ValueBot valuation report with value per share, upside, scenario range and editable drivers", url: "irradiance.ai/valuebot",
    eyebrow: "ValueBot · AI valuation", title: "A full DCF from SEC filings, in the time it takes to make coffee",
    body: "Type a ticker and the story you believe. ValueBot reads the filings, prices the cost of capital from live markets and hands back a value per share, the range from bear to bull, and the price the market is already assuming.",
    bullets: ["Change any driver and the value reprices instantly", "Editable Excel model with live formulas", "Bull, bear and market-implied workbooks"],
    href: "/valuebot", cta: "Value a stock free", chips: [{ text: "Reverse DCF included", pos: "tr" }, { text: "Every input editable", pos: "bl" }] },
  { src: "/showcase/patterns.webp", alt: "Pattern Lab scorecard of six patterns across six asset classes with stress-test results", url: "irradiance.ai/patterns",
    eyebrow: "Pattern Lab", title: "Know whether a pattern is real before you trade it",
    body: "Six precisely defined patterns, tested every night on stocks, ETFs, rates, currencies, commodities and crypto, from 15-minute to weekly bars. Each cell shows how many of nine stress tests it passed, and why the rest failed.",
    bullets: ["Holdout, walk-forward and permutation tests", "Corrected for the number of patterns tried", "Market regimes, recurring states and lead-lag maps"],
    href: "/patterns", cta: "Open the Pattern Lab", chips: [{ text: "9 stress tests per cell", pos: "tl" }, { text: "6 asset classes · 4 timeframes", pos: "br" }] },
  { src: "/showcase/signals.webp", alt: "Premium Signals table of the day's breakouts, RSI extremes and unusual moves with strength scores", url: "irradiance.ai/signals",
    eyebrow: "Premium Signals", title: "The day's unusual moves, ranked before you log in",
    body: "After every close IRAI scans the most-traded US stocks and ETFs for trend crosses, RSI extremes, 52-week breakouts, outsized moves and attention spikes, then ranks them by strength with one click to a full analysis.",
    bullets: ["Plain-English explanation for every signal", "Track record of each signal type for Pro", "Analyze any name with the Analyst Bot"],
    href: "/signals", cta: "See today's signals", chips: [{ text: "Scanned after every close", pos: "tr" }] },
  { src: "/showcase/bot.webp", alt: "AlgoTrader bot page with backtest equity curve, live-vs-backtest metrics and risk controls", url: "irradiance.ai/bots",
    eyebrow: "IRAI AlgoTrader", title: "Turn a rule into a bot, and watch it on paper first",
    body: "Describe a strategy in plain English. IRAI configures it, backtests it with a 57-metric tear sheet and runs it on paper accounts with stop-loss, take-profit and daily auto-close, keeping the live record beside the backtest.",
    bullets: ["TradingView webhooks; one strategy, many accounts", "Live-vs-backtest drift, metric by metric", "Live broker connections coming next"],
    href: "/algotrader", cta: "Explore AlgoTrader", chips: [{ text: "57-metric tear sheet", pos: "tl" }, { text: "Paper first", pos: "br" }] },
];

const AUDIENCES: [string, string][] = [
  ["Self-directed investors", "Stress-test a thesis before you act on it. See what growth and margins the current price assumes, and where your story differs."],
  ["Analysts and students", "Get a complete, editable DCF in minutes: filings pulled, cost of capital priced, earnings normalised, then refine every input yourself."],
  ["Clubs, newsletters and small teams", "Share valuation reports and monitor views with a link. Every number carries its source, so the discussion is about assumptions, not data."],
];

const STEPS = [
  ["Build the peer group", "Names in the same industry with comparable size and disclosure."],
  ["Regress multiple on quality", "Log multiple vs a composite of returns on capital, margins and leverage."],
  ["Measure the residual", "Below the line is cheap for its quality; above is rich. The residual becomes a percentile."],
  ["Show the uncertainty", "Coverage confidence, data source, and the peer group itself are printed next to every score."],
];

export const metadata = {
  ...pageMeta("Irradiance.AI: AI stock valuation & relative-value research",
    "AI research you can check: DCF valuations from SEC filings, an AI analyst for any ticker, stress-tested market patterns, daily signals and paper-traded strategies. Every number shows its source.", "/"),
  title: { absolute: "Irradiance.AI: AI stock valuation & relative-value research" },
};

export default async function Home() {
  const faq = await backendJson<{ q: string; a: string }[]>("/api/faq");
  return (
    <>
      {faq && faq.length > 0 && <JsonLd data={{ "@context": "https://schema.org", "@type": "FAQPage",
        mainEntity: faq.map(f => ({ "@type": "Question", name: f.q, acceptedAnswer: { "@type": "Answer", text: f.a } })) }} />}
      <section className="hero-glow border-b border-line">
        <div className="mx-auto grid max-w-7xl items-center gap-12 px-4 py-20 md:py-28 lg:grid-cols-[1.05fr_1fr]">
          <div>
          <span className="inline-flex items-center gap-2 rounded-full border border-line bg-card px-3 py-1 text-xs text-muted">
            <span className="h-1.5 w-1.5 rounded-full bg-up" /> Live market data: press ⌘K and type any ticker
          </span>
          <h1 className="mt-6 max-w-4xl text-5xl font-semibold tracking-tight md:text-6xl lg:text-5xl xl:text-6xl">
            Research like a quant desk. <span className="solar-text">See every assumption.</span>
          </h1>
          <p className="mt-6 max-w-2xl text-lg leading-relaxed text-muted">
            Irradiance.AI puts an AI analyst, a valuation engine, a pattern lab and a strategy backtester in one workspace.
            Value a stock from its SEC filings in minutes, see which market regime you are in, and test an idea on paper before
            you risk a dollar. No black boxes: every number carries its source and every model shows its working.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Button href="/valuebot">Value a stock free →</Button>
            <Button href="/signup?plan=pro" variant="outline">Try Pro free for 7 days</Button>
          </div>
          <p className="mt-3 text-xs text-muted">No card needed for the trial · cancel any time · research and education, not investment advice</p>
          <dl className="mt-12 grid max-w-3xl grid-cols-2 gap-6 text-sm md:grid-cols-4 lg:grid-cols-2">
            {[["18-stage", "DCF engine per valuation"], ["6 asset classes", "tested nightly, 4 timeframes"], ["57 metrics", "in every strategy tear sheet"], ["Excel", "models you can open and edit"]].map(([k, v]) => (
              <div key={k}><dt className="stat text-xl text-fg">{k}</dt><dd className="text-muted">{v}</dd></div>
            ))}
          </dl>
          </div>
          <div className="hidden lg:block">
            <TiltShot src="/showcase/regimes.webp" alt="Pattern Lab market regime view: today's regime, model confidence and regime history" url="irradiance.ai/patterns" priority rest="right"
              chips={[{ text: "Market regime, refit nightly", pos: "tl" }, { text: "Every number sourced", pos: "br" }]} />
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-4 py-16">
        <div className="max-w-3xl"><span className="text-xs uppercase tracking-wide text-primary">One workspace</span>
          <h2 className="mt-2 text-3xl font-semibold tracking-tight">From first question to tested idea, without switching tools</h2>
          <p className="mt-2 text-muted">Most investors juggle a screener, a spreadsheet, a news feed and a backtester that never agree with each other. Here they share one data layer, one login and one standard of proof.</p></div>
        <div className="mt-8 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {PLATFORM.map(x => (
            <Link key={x.title} href={x.href} className="group rounded-xl border border-line bg-card p-6 transition hover:border-primary/50">
              <div className="text-xs uppercase tracking-wide text-primary">{x.tag}</div>
              <h3 className="mt-1 text-lg font-semibold group-hover:text-primary">{x.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-muted">{x.body}</p>
              <span className="mt-3 inline-block text-sm text-fg-2 group-hover:text-primary">Explore →</span>
            </Link>))}
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-4 py-16">
        <div className="mb-14 text-center"><span className="text-xs uppercase tracking-wide text-primary">See it in action</span>
          <h2 className="mt-2 text-3xl font-semibold tracking-tight md:text-4xl">Built to show its work</h2>
          <p className="mx-auto mt-2 max-w-2xl text-muted">Every screen answers the question a careful investor asks next: where did this number come from, and what would change it?</p></div>
        <FeatureShowcase items={SHOWCASE} />
      </section>

      <section className="border-y border-line bg-card/40">
        <div className="mx-auto grid max-w-7xl gap-10 px-4 py-16 lg:grid-cols-2">
          <div><span className="text-xs uppercase tracking-wide text-primary">Why trust it</span>
            <h2 className="mt-2 text-3xl font-semibold tracking-tight">We publish the patterns that fail</h2>
            <p className="mt-3 text-muted">Anyone can find a chart pattern that worked last year. The Pattern Lab tests six precisely defined patterns on stocks, ETFs,
              rates, currencies, commodities and crypto, from 15-minute bars to weekly. A pattern is only called robust if it beats random entries after
              trading costs, holds up on data it never saw, survives a permutation test, clears a hurdle that rises with every pattern tried, and works
              across market regimes. Most do not, and we show you that too.</p>
            <div className="mt-6 flex flex-wrap gap-3"><Button href="/patterns">Open the Pattern Lab →</Button><Button href="/methodology" variant="outline">Read the methodology</Button></div></div>
          <ol className="space-y-3 self-center">{[["Define it", "A rule with numeric thresholds, a direction and a holding period, so 'did it work' has one answer."],
            ["Normalise it", "Moves measured against each asset's own volatility, so a signal means the same on Bitcoin and on Treasuries."],
            ["Date-stamp it", "Only data available at the time; entry on the next bar; outcomes that never overlap."],
            ["Beat a baseline", "Random entries and a simple, readable model come first. No deep learning until the basics are beaten."],
            ["Try to break it", "Holdout, walk-forward, permutation, false-discovery control, regimes, threshold sensitivity, costs."]].map(([t, b], i) => (
            <li key={t} className="flex gap-4"><span className="solar-bg flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-sm font-bold text-primary-fg">{i + 1}</span>
              <div><div className="font-medium">{t}</div><div className="text-sm text-muted">{b}</div></div></li>))}</ol>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-4 py-16">
        <Card className="grid gap-8 p-8 md:grid-cols-2">
          <div>
            <span className="text-xs uppercase tracking-wide text-primary">ValueBot · AI valuation</span>
            <h2 className="mt-2 text-3xl font-semibold tracking-tight">Your thesis, turned into a valuation you can defend</h2>
            <p className="mt-3 text-muted">Type a ticker and tell the story you believe: growth, margins, reinvestment, risk, moat. ValueBot reads the company&rsquo;s SEC filings, prices its cost of capital from live markets, and runs an 18-stage narrative-and-numbers DCF. In a few minutes you get an intrinsic value, the assumptions behind it, and what the market price already implies.</p>
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
            <p className="mt-1 text-muted">Trade posts capture entry prices from market data at posting time, so members can prove when they called it, not just that they say they did.</p></div>
          <Link href="/community" className="text-sm hover:text-primary">Browse the forum →</Link>
        </div>
        <HomeCommunity />
      </section>

      <section id="pricing" className="mx-auto max-w-7xl px-4 py-16">
        <h2 className="mb-2 text-center text-3xl font-semibold tracking-tight">Start free. Go deeper when you are ready.</h2>
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
            <p className="mt-1 text-muted">Run your first AI valuation free. It takes about as long as reading this page, and you keep the Excel model.</p>
          </div>
          <div className="flex gap-3"><Button href="/valuebot">Value a stock free →</Button><Button href="/pricing" variant="outline">Compare plans</Button></div>
        </div>
      </section>
    </>
  );
}
