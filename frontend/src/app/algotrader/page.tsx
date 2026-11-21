"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/components/AuthProvider";
import { BrokerStrip } from "@/components/Bots";
import { Button, Card, ErrorNote } from "@/components/ui";
import { AUDIENCES } from "./audiences";

const BROKER_KEYS: [string, string][] = [["webull", "Webull"], ["robinhood", "Robinhood"], ["fidelity", "Fidelity"], ["schwab", "Charles Schwab"],
  ["ibkr", "Interactive Brokers"], ["etrade", "E*TRADE"], ["vanguard", "Vanguard"], ["merrill", "Merrill"], ["tastytrade", "tastytrade"], ["public", "Public"], ["alpaca", "Alpaca"], ["other", "Other"]];

const STEPS = [
  { n: "1", t: "Create", d: "Describe a strategy in plain English, or pick a tested rule. IRAI builds it, sets the parameters and backtests it on two years of history before it trades." },
  { n: "2", t: "Connect", d: "Fund it from one or many paper accounts, each with its own allocation. Live broker connections are coming soon; every live order will need your confirmation." },
  { n: "3", t: "Send", d: "Let the rule run on daily closes, or fire signals from TradingView alerts to the bot's private webhook. Every signal and fill is logged." },
];

const FEATURES = [
  { t: "Plain English to strategy", d: "Type “golden cross on SPY with a 10% stop” and get a configured bot with parameters and risk controls you can review." },
  { t: "Per-bot risk controls", d: "Allocation, maximum position size, stop-loss, take-profit and daily auto-close, checked every five minutes while the market is open." },
  { t: "Paper trading first", d: "Every bot starts on simulated money with realistic slippage and commission, so you see how it behaves before risking anything." },
  { t: "Webhook signals", d: "Send TradingView alerts to a bot's private URL. One strategy can feed many accounts at once, each sized to its own capital." },
  { t: "57-metric tear sheet", d: "CAGR, Sharpe, Sortino, Calmar, drawdowns, VaR, capture ratios, win rate, profit factor, streaks and more, for backtest and live." },
  { t: "Live vs backtest", d: "Each bot keeps an end-of-day track record next to the backtest that justified it, so drift shows up early." },
  { t: "Monte Carlo", d: "Run thousands of simulated paths for a bot's symbols or your whole portfolio to see the range of outcomes, not just the average." },
  { t: "Portfolio analysis", d: "Import holdings from any broker's CSV export for P&L, concentration, sector mix, risk, income, quant grades and an AI review." },
  { t: "AI on every screen", d: "Ask IRAI questions about the ticker, theme, portfolio or bot you're looking at; read AI summaries of the latest news on every ticker." },
];

const FAQ: [string, string][] = [
  ["Does Irradiance hold my money or place trades?", "No. Irradiance is non-custodial: it never holds, transmits or manages customer funds. Today bots trade paper accounts only. When live broker connections launch, orders will be routed to your own brokerage account and you'll confirm them; you can disconnect at any time."],
  ["Is this investment advice?", "No. Irradiance provides research tools and automation for self-directed investors. We don't recommend securities or strategies, and AI features describe data rather than telling you what to buy or sell. You decide what your bots do."],
  ["How realistic is paper trading?", "Fills use the latest quoted price plus 2 basis points of slippage and 1 basis point of commission. Real fills can be worse, especially for illiquid stocks, large orders or fast markets, so treat paper results as an upper bound."],
  ["Which brokers will connect?", "We're building connections for Webull, Robinhood, Fidelity, Charles Schwab, Interactive Brokers, E*TRADE and other platforms through regulated connection partners. Availability depends on each broker. Join the waitlist and tell us which you use."],
  ["Can automated trading lose money?", "Yes. Automated strategies can lose money quickly, backtests can overstate results, and past performance doesn't predict future returns. Start small, use risk controls, and only trade money you can afford to lose."],
];

export default function AlgoTrader() {
  const { user } = useAuth();
  const [email, setEmail] = useState("");
  const [picked, setPicked] = useState<string[]>([]);
  const [joined, setJoined] = useState(false);
  const [err, setErr] = useState<Error | null>(null);
  const pro = user?.plan === "pro";
  useEffect(() => { if (user) api<{ joined: boolean; brokers: string[] }>("/api/waitlist/algotrader/me").then(r => { setJoined(r.joined); if (r.brokers.length) setPicked(r.brokers); }).catch(() => {}); }, [user]);
  const toggle = (b: string) => setPicked(p => p.includes(b) ? p.filter(x => x !== b) : [...p, b]);
  const join = async (e: React.FormEvent) => {
    e.preventDefault(); setErr(null);
    try { await api("/api/waitlist/algotrader", { method: "POST", json: { email: user ? undefined : email, brokers: picked } }); setJoined(true); } catch (x) { setErr(x as Error); }
  };
  const start = pro ? "/bots/new" : user ? "/pricing" : "/signup?next=/bots/new";
  return (
    <div>
      <section className="border-b border-line">
        <div className="mx-auto max-w-6xl px-4 py-16 md:py-24">
          <span className="rounded-full border border-primary/40 px-3 py-1 text-xs text-primary">IRAI AlgoTrader · included with Pro</span>
          <h1 className="mt-5 max-w-3xl text-4xl md:text-6xl">Turn your trading ideas into bots you control.</h1>
          <p className="mt-5 max-w-2xl text-lg text-muted">Describe a strategy in plain English, test it on years of data, and run it with real risk controls. Start on paper; connect your broker when you&apos;re ready.</p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Button href={start}>Build my first bot</Button>
            <Button variant="outline" href={pro ? "/portfolio" : "/pricing"}>Analyze my portfolio</Button>
            <Button variant="ghost" href="#waitlist">Get live-broker access</Button>
          </div>
          <div className="mt-10"><div className="mb-2 text-sm">Seamless connection to Webull, Robinhood, Fidelity, Charles Schwab, <a href="https://www.interactivebrokers.com/en/whyib/overview.php" target="_blank" rel="noopener noreferrer" className="underline decoration-primary/60 underline-offset-2 hover:text-primary">Interactive Brokers</a>, E*TRADE and other top platforms <span className="text-muted">(coming soon)</span>:</div><BrokerStrip /></div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-14">
        <h2 className="text-2xl">Create, connect, send</h2>
        <div className="mt-6 grid gap-6 md:grid-cols-3">{STEPS.map(s => (
          <div key={s.n}><div className="stat text-4xl text-primary">{s.n}</div><h3 className="mt-2 text-xl">{s.t}</h3><p className="mt-1 text-sm text-muted">{s.d}</p></div>))}</div>
      </section>

      <section className="border-y border-line bg-card/40">
        <div className="mx-auto max-w-6xl px-4 py-14">
          <h2 className="text-2xl">Everything a systematic investor needs</h2>
          <div className="mt-6 grid gap-4 md:grid-cols-3">{FEATURES.map(f => (
            <Card key={f.t} className="p-6"><h3 className="text-lg">{f.t}</h3><p className="mt-2 text-sm leading-relaxed text-muted">{f.d}</p></Card>))}</div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-14">
        <h2 className="text-2xl">Built for how you invest</h2>
        <div className="mt-6 grid gap-4 md:grid-cols-2 lg:grid-cols-4">{AUDIENCES.map(a => (
          <Link key={a.slug} href={`/algotrader/for/${a.slug}`} className="group rounded-xl border border-line bg-card p-5 hover:border-primary">
            <div className="text-xs uppercase tracking-wide text-primary">{a.who}</div><h3 className="mt-1 text-lg">{a.headline}</h3>
            <p className="mt-2 text-sm text-muted">{a.short}</p><span className="mt-3 inline-block text-sm text-primary">See how →</span></Link>))}</div>
      </section>

      <section className="border-y border-line bg-card/40">
        <div className="mx-auto grid max-w-6xl gap-8 px-4 py-14 md:grid-cols-2">
          <div>
            <h2 className="text-2xl">One simple price</h2>
            <p className="mt-2 text-muted">AlgoTrader is included with Irradiance Pro, alongside ValueBot, the Analyst Bot, every monitor and the Strategy Lab.</p>
            <div className="mt-5 flex items-baseline gap-2"><span className="stat text-5xl">$100</span><span className="text-muted">/ month, or $1,000 / year</span></div>
            <p className="mt-1 text-sm text-muted">7-day free trial, no card needed. Cancel any time.</p>
            <ul className="mt-4 space-y-1 text-sm">{["20 bots across 5 paper accounts", "AI strategy builder and Ask IRAI", "Webhooks, risk controls and daily auto-close", "Tear sheets, Monte Carlo and live-vs-backtest tracking", "Portfolio analysis with CSV import"].map(x => <li key={x}>✓ {x}</li>)}</ul>
            <Button className="mt-5" href={start}>{pro ? "Build a bot" : "Start free trial"}</Button>
            <p className="mt-2 text-[11px] text-muted">Pricing for live broker connections will be announced before launch.</p>
          </div>
          <div>
            <h2 className="text-2xl">You stay in control</h2>
            <ul className="mt-3 space-y-3 text-sm">
              <li><b>Non-custodial.</b> <span className="text-muted">Irradiance never holds, transmits or manages your money. Your funds stay at your broker.</span></li>
              <li><b>No advice.</b> <span className="text-muted">We provide tools, data and research. We don&apos;t recommend securities or strategies; you decide what each bot does.</span></li>
              <li><b>You approve live orders.</b> <span className="text-muted">When broker connections launch, orders are routed to your own account and confirmed by you. Revoke access any time.</span></li>
              <li><b>Everything logged.</b> <span className="text-muted">Every signal, fill and settings change is kept in the bot&apos;s audit log.</span></li>
            </ul>
          </div>
        </div>
      </section>

      <section id="waitlist" className="mx-auto max-w-3xl px-4 py-16">
        <Card className="p-8">
          <h2 className="text-2xl">Get early access to live trading</h2>
          <p className="mt-1 text-sm text-muted">Tell us which brokers you use and we&apos;ll invite you as connections go live.</p>
          {joined ? <p className="mt-6 rounded-lg border border-up/40 bg-up/10 p-4 text-sm">You&apos;re on the list. We&apos;ll email you when live trading opens for your broker{picked.length > 1 ? "s" : ""}.</p> : (
            <form onSubmit={join} className="mt-6 space-y-4">
              {!user && <input type="email" required placeholder="Email" value={email} onChange={e => setEmail(e.target.value)} className="w-full rounded-lg border border-line bg-bg px-3 py-2" autoComplete="email" />}
              <div><div className="mb-2 text-sm text-muted">Which brokers do you use?</div>
                <div className="flex flex-wrap gap-2">{BROKER_KEYS.map(([k, l]) => (
                  <button type="button" key={k} onClick={() => toggle(k)} className={`rounded-full border px-3 py-1 text-sm ${picked.includes(k) ? "border-primary bg-primary/15 text-fg" : "border-line text-muted hover:text-fg"}`}>{l}</button>))}</div></div>
              <ErrorNote error={err} />
              <Button type="submit">Join the waitlist</Button>
            </form>)}
        </Card>
      </section>

      <section className="mx-auto max-w-3xl px-4 pb-16">
        <h2 className="text-2xl">Questions</h2>
        <div className="mt-4 divide-y divide-line">{FAQ.map(([q, a]) => <details key={q} className="py-3"><summary className="cursor-pointer font-medium">{q}</summary><p className="mt-2 text-sm text-muted">{a}</p></details>)}</div>
        <p className="mt-8 text-[11px] leading-relaxed text-muted">Irradiance provides research and software tools for self-directed investors. It is not a broker-dealer or investment adviser, is non-custodial, and does not provide trading advice, signals or recommendations. Automated trading involves substantial risk, including loss of principal, and may not be suitable for every investor. Backtested and paper-trading results are hypothetical, have inherent limitations and do not represent actual trading; past performance does not guarantee future results. Testimonials, where shown, may not be representative and are not a guarantee. Broker names are trademarks of their respective owners; Irradiance is independent and not affiliated with or endorsed by them, and listing a broker does not imply compatibility or endorsement. See our <Link href="/legal/disclaimer" className="underline">disclaimer</Link>.</p>
      </section>
    </div>
  );
}
