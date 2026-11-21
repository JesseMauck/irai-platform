import Link from "next/link";
import { notFound } from "next/navigation";
import { pageMeta } from "@/lib/seo";
import { BrokerStrip } from "@/components/Bots";
import { Button, Card } from "@/components/ui";
import { AUDIENCES } from "../../audiences";

export function generateStaticParams() {
  return AUDIENCES.map(a => ({ audience: a.slug }));
}

export async function generateMetadata({ params }: { params: Promise<{ audience: string }> }) {
  const { audience } = await params;
  const a = AUDIENCES.find(x => x.slug === audience);
  return a ? pageMeta(a.title, a.description, `/algotrader/for/${a.slug}`) : {};
}

export default async function AudiencePage({ params }: { params: Promise<{ audience: string }> }) {
  const { audience } = await params;
  const a = AUDIENCES.find(x => x.slug === audience);
  if (!a) notFound();
  return (
    <div className="mx-auto max-w-5xl px-4 py-14">
      <Link href="/algotrader" className="text-sm text-muted hover:text-fg">← IRAI AlgoTrader</Link>
      <div className="mt-4 text-xs uppercase tracking-wide text-primary">For {a.who.toLowerCase()}</div>
      <h1 className="mt-2 max-w-3xl text-4xl md:text-5xl">{a.headline}</h1>
      <p className="mt-4 max-w-2xl text-lg text-muted">{a.intro}</p>
      <div className="mt-6 flex flex-wrap gap-3"><Button href="/bots/new">Build this kind of bot</Button><Button variant="outline" href="/pricing">Start a 7-day free trial</Button></div>

      <h2 className="mt-12 text-2xl">Bots you could build</h2>
      <p className="mt-1 text-sm text-muted">Examples of what the plain-English builder can configure. They are illustrations, not recommendations.</p>
      <div className="mt-4 grid gap-4 md:grid-cols-2">{a.bots.map(b => (
        <Card key={b.name} className="p-6"><h3 className="text-lg">{b.name}</h3><p className="mt-2 text-sm">“{b.idea}”</p><p className="mt-2 text-xs text-muted">{b.how}</p></Card>))}</div>

      <h2 className="mt-12 text-2xl">Tools that help</h2>
      <div className="mt-4 grid gap-4 md:grid-cols-3">{a.tools.map(([t, href, d]) => (
        <Link key={t} href={href} className="rounded-xl border border-line bg-card p-5 hover:border-primary"><h3 className="font-semibold">{t}</h3><p className="mt-1 text-sm text-muted">{d}</p></Link>))}</div>

      <h2 className="mt-12 text-2xl">How it works</h2>
      <ol className="mt-3 grid gap-4 md:grid-cols-3">{[["Create", "Describe the rule in plain English; IRAI builds and backtests it."], ["Connect", "Fund it from paper accounts today; live brokers are coming soon."], ["Send", "Let the rule run, or send TradingView alerts to its webhook."]].map(([t, d], i) => (
        <li key={t}><div className="stat text-3xl text-primary">{i + 1}</div><div className="mt-1 font-semibold">{t}</div><p className="text-sm text-muted">{d}</p></li>))}</ol>

      <div className="mt-12"><BrokerStrip /></div>
      <p className="mt-6 text-[11px] text-muted">Irradiance is non-custodial and does not provide investment advice. Bots trade simulated money until live connections launch. Backtests and paper results are hypothetical and do not guarantee future results; automated trading can lose money.</p>
    </div>
  );
}
