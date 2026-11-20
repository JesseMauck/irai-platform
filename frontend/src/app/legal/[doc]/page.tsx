import { notFound } from "next/navigation";
import Link from "next/link";
import { PageHeader } from "@/components/ui";
import { GOVERNING_LAW, TERMS, TERMS_UPDATED, VENUE, type Section } from "@/content/terms";
import { PRIVACY, PRIVACY_EFFECTIVE, PRIVACY_UPDATED } from "@/content/privacy";
import { DISCLAIMER, DISCLAIMER_UPDATED } from "@/content/disclaimer";

const DOCS: Record<string, [string, string[]]> = {
  "community-guidelines": ["Community Guidelines", ["Disclose any position you hold in a security you discuss.", "No undisclosed promotion, paid content, pump-and-dump schemes or coordinated campaigns.", "Trade posts record platform prices and cannot be edited; they can only be closed.", "Be civil. Critique ideas, not people.", "Moderation actions are logged and can be appealed."]],
  "disclosure-policy": ["Disclosure Policy", ["Irradiance staff may not trade securities discussed in unpublished research until 48 hours after publication.", "Authors disclose positions at the end of each article.", "We receive no compensation from issuers covered in our research."]],
};

export function generateStaticParams() { return [...Object.keys(DOCS), "terms", "privacy", "disclaimer"].map(doc => ({ doc })); }

export async function generateMetadata({ params }: { params: Promise<{ doc: string }> }) {
  const { doc } = await params;
  const title = doc === "terms" ? "Terms of Service" : doc === "privacy" ? "Privacy Policy" : doc === "disclaimer" ? "Disclaimer" : DOCS[doc]?.[0] ?? "Legal";
  return { title, alternates: { canonical: `https://irradiance.ai/legal/${doc}` } };
}

const fill = (t: string) => t.replace("{LAW}", GOVERNING_LAW ?? "[governing law to be confirmed]").replace("{VENUE}", VENUE ?? "[venue to be confirmed]");

function StructuredDoc({ title, dates, summary, sections }: { title: string; dates: string; summary: React.ReactNode; sections: Section[] }) {
  return (
    <div className="mx-auto max-w-3xl px-4 py-12">
      <PageHeader title={title} intro={dates} />
      <div className="mt-4 rounded-xl border border-line bg-card p-4 text-sm text-fg-2"><strong className="text-fg">In short:</strong> {summary}</div>
      <nav aria-label="Contents" className="mt-8 rounded-xl border border-line p-4 text-sm">
        <div className="mb-2 font-semibold">Contents</div>
        <ol className="grid gap-1 sm:grid-cols-2">{sections.map(s => <li key={s.id}><a href={`#${s.id}`} className="text-muted hover:text-primary">{s.title}</a></li>)}</ol>
      </nav>
      <div className="mt-8 space-y-8">
        {sections.map(s => (
          <section key={s.id} id={s.id} className="scroll-mt-24">
            <h2 className="text-xl">{s.title}</h2>
            <div className="mt-3 space-y-3 text-sm leading-7 text-fg-2">
              {s.blocks.map((b, i) => typeof b === "string" ? (/^[A-Z]\. /.test(b) ? <h3 key={i} className="pt-2 text-base text-fg">{b}</h3> : <p key={i}>{fill(b)}</p>)
                : "list" in b ? <ul key={i} className="list-disc space-y-1 pl-6">{b.list.map(x => <li key={x}>{x}</li>)}</ul>
                : <p key={i} className="text-xs leading-6 tracking-wide">{b.caps}</p>)}
            </div>
          </section>
        ))}
      </div>
      <p className="mt-10 text-xs text-muted">See also: <Link href="/legal/terms" className="hover:text-fg">Terms of Service</Link> · <Link href="/legal/privacy" className="hover:text-fg">Privacy Policy</Link> · <Link href="/legal/disclaimer" className="hover:text-fg">Disclaimer</Link> · <Link href="/legal/community-guidelines" className="hover:text-fg">Community Guidelines</Link></p>
    </div>
  );
}

export default async function Legal({ params }: { params: Promise<{ doc: string }> }) {
  const { doc } = await params;
  if (doc === "terms") return <StructuredDoc title="Terms of Service" dates={`Last updated ${TERMS_UPDATED}`} sections={TERMS}
    summary="Irradiance.AI is research and education, not investment advice. Paid plans renew until you cancel; trials never charge you. Data is for your personal use. You own what you post." />;
  if (doc === "privacy") return <StructuredDoc title="Privacy Policy" dates={`Effective ${PRIVACY_EFFECTIVE} · Last updated ${PRIVACY_UPDATED}`} sections={PRIVACY}
    summary="We collect what we need to run your account and research, never your card number. We don't sell your data or use advertising trackers. You can export or delete your data from your account at any time." />;
  if (doc === "disclaimer") return <StructuredDoc title="Disclaimer" dates={`Last updated ${DISCLAIMER_UPDATED}`} sections={DISCLAIMER}
    summary="Everything on Irradiance.AI is impersonal research and education. We are not your adviser, we don't execute trades, models can be wrong, and data can be delayed. You are responsible for your decisions." />;
  const d = DOCS[doc];
  if (!d) notFound();
  return (
    <div className="mx-auto max-w-3xl px-4 py-12">
      <PageHeader title={d[0]} intro="Last updated November 2026" />
      <div className="space-y-4 text-fg-2">{d[1].map(p => <p key={p}>{p}</p>)}</div>
    </div>
  );
}
