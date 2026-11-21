"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/components/AuthProvider";
import { Button, Card, ErrorNote } from "@/components/ui";

const BROKERS: [string, string][] = [["webull", "Webull"], ["robinhood", "Robinhood"], ["fidelity", "Fidelity"], ["schwab", "Charles Schwab"],
  ["ibkr", "Interactive Brokers"], ["etrade", "E*TRADE"], ["vanguard", "Vanguard"], ["merrill", "Merrill"], ["tastytrade", "tastytrade"], ["public", "Public"], ["alpaca", "Alpaca"], ["other", "Other"]];

const FEATURES = [
  { t: "One view of every account", d: "Link brokerage, IRA and 401(k) accounts through secure, read-only connections. IRAI pulls positions, cost basis and activity into a single dashboard; it never sees your broker password." },
  { t: "AI analysis of your holdings", d: "Each position gets the Analyst Bot treatment: today's news, filings, valuation, quant grades and technicals, plus what changed since you bought it." },
  { t: "Portfolio health checks", d: "Concentration, sector and factor exposure, correlation, drawdown risk, dividend income and fees, with a Monte Carlo range of outcomes for your actual portfolio." },
  { t: "Advanced strategies, your rules", d: "Build rules in the Strategy Lab (rebalancing bands, trailing stops, covered-call screens, pair spreads), backtest them, and get alerts when a rule fires." },
  { t: "You approve every trade", d: "When you choose to act, IRAI can stage the order at your broker for you to review and confirm. Nothing is placed without your explicit approval." },
  { t: "Built for safety", d: "Bank-grade encryption, read-only by default, revocable access, and a full audit log of every signal and order you approve." },
];

export default function AlgoTrader() {
  const { user } = useAuth();
  const [email, setEmail] = useState("");
  const [picked, setPicked] = useState<string[]>([]);
  const [joined, setJoined] = useState(false);
  const [err, setErr] = useState<Error | null>(null);
  useEffect(() => { if (user) api<{ joined: boolean; brokers: string[] }>("/api/waitlist/algotrader/me").then(r => { setJoined(r.joined); if (r.brokers.length) setPicked(r.brokers); }).catch(() => {}); }, [user]);
  const toggle = (b: string) => setPicked(p => p.includes(b) ? p.filter(x => x !== b) : [...p, b]);
  const join = async (e: React.FormEvent) => {
    e.preventDefault(); setErr(null);
    try { await api("/api/waitlist/algotrader", { method: "POST", json: { email: user ? undefined : email, brokers: picked } }); setJoined(true); } catch (x) { setErr(x as Error); }
  };
  return (
    <div>
      <section className="border-b border-line">
        <div className="mx-auto max-w-6xl px-4 py-16 md:py-24">
          <span className="rounded-full border border-primary/40 px-3 py-1 text-xs text-primary">Pro add-on · coming soon</span>
          <h1 className="mt-5 max-w-3xl text-4xl md:text-6xl">IRAI AlgoTrader. Your portfolio, analyzed and automated.</h1>
          <p className="mt-5 max-w-2xl text-lg text-muted">Connect your brokerage accounts to IRAI and get institutional-grade analysis of what you actually own, plus rules-based strategies you design, test and approve.</p>
          <p className="mt-6 max-w-3xl text-base">Seamless connection to <b>Webull, Robinhood, Fidelity, Charles Schwab, <a href="https://www.interactivebrokers.com/en/whyib/overview.php" target="_blank" rel="noopener noreferrer" className="underline decoration-primary/60 underline-offset-2 hover:text-primary">Interactive Brokers</a>, E*TRADE</b> and other top platforms.</p>
          <div className="mt-8 flex flex-wrap gap-3"><Button href="#waitlist">Join the waitlist</Button><Button variant="outline" href="/portfolio">Try portfolio analysis (Pro)</Button></div>
          <p className="mt-3 text-sm text-muted">Available today for Pro members: import your positions from a broker CSV and get the full portfolio analysis and AI review, ahead of live connections.</p>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-14">
        <div className="grid gap-4 md:grid-cols-3">{FEATURES.map(f => (
          <Card key={f.t} className="p-6"><h2 className="text-lg">{f.t}</h2><p className="mt-2 text-sm leading-relaxed text-muted">{f.d}</p></Card>))}</div>
      </section>

      <section className="border-y border-line bg-card/40">
        <div className="mx-auto grid max-w-6xl gap-8 px-4 py-14 md:grid-cols-3">
          {[["1", "Connect", "Link accounts in a couple of minutes with a secure, read-only connection. Disconnect any time."],
            ["2", "Understand", "IRAI analyzes every holding and the portfolio as a whole, and explains the results in plain language."],
            ["3", "Act on your terms", "Turn your rules into alerts or staged orders. You review and confirm each one at your broker."]].map(([n, t, d]) => (
            <div key={n}><div className="stat text-4xl text-primary">{n}</div><h3 className="mt-2 text-xl">{t}</h3><p className="mt-1 text-sm text-muted">{d}</p></div>))}
        </div>
      </section>

      <section id="waitlist" className="mx-auto max-w-3xl px-4 py-16">
        <Card className="p-8">
          <h2 className="text-2xl">Get early access</h2>
          <p className="mt-1 text-sm text-muted">AlgoTrader will be an add-on to the Pro plan. Tell us which brokers you use and we&apos;ll invite you as connections go live.</p>
          {joined ? <p className="mt-6 rounded-lg border border-up/40 bg-up/10 p-4 text-sm">You&apos;re on the list. We&apos;ll email you when AlgoTrader opens for your broker{picked.length > 1 ? "s" : ""}.</p> : (
            <form onSubmit={join} className="mt-6 space-y-4">
              {!user && <input type="email" required placeholder="Email" value={email} onChange={e => setEmail(e.target.value)} className="w-full rounded-lg border border-line bg-bg px-3 py-2" autoComplete="email" />}
              <div><div className="mb-2 text-sm text-muted">Which brokers do you use?</div>
                <div className="flex flex-wrap gap-2">{BROKERS.map(([k, l]) => (
                  <button type="button" key={k} onClick={() => toggle(k)} className={`rounded-full border px-3 py-1 text-sm ${picked.includes(k) ? "border-primary bg-primary/15 text-fg" : "border-line text-muted hover:text-fg"}`}>{l}</button>))}</div></div>
              <ErrorNote error={err} />
              <Button type="submit">Join the waitlist</Button>
            </form>)}
        </Card>
        <p className="mt-6 text-[11px] leading-relaxed text-muted">AlgoTrader is in development and features may change before launch. Broker availability depends on our connection partners and on each broker. Broker names are trademarks of their respective owners; Irradiance is not affiliated with or endorsed by them. Irradiance provides research and tools for self-directed investors and is not a broker-dealer or investment adviser; analysis is not personalized investment advice, and you remain responsible for every order you approve. Investing involves risk, including loss of principal. See our <Link href="/legal/disclaimer" className="underline">disclaimer</Link>.</p>
      </section>
    </div>
  );
}
