import { notFound } from "next/navigation";
import { PageHeader } from "@/components/ui";

const DOCS: Record<string, [string, string[]]> = {
  terms: ["Terms of Service", ["By using Irradiance you agree to these terms. Content is provided for research and education.", "Paid memberships renew automatically until cancelled and are processed by Square. Free trials do not convert to paid plans automatically; at the end of a trial the account returns to the Free plan unless you subscribe.", "You may not redistribute market data or research beyond personal use without written permission.", "We may suspend accounts that violate the community guidelines.", "[Draft — have counsel review before launch.]"]],
  privacy: ["Privacy Policy", ["We collect your email, handle and the content you post, plus usage data needed to run the service.", "Payments are processed by Square; we never see or store card numbers.", "We do not sell personal data. You can request export or deletion of your data at any time.", "[Draft — have counsel review before launch.]"]],
  disclaimer: ["Disclaimer", ["Irradiance publishes impersonal research and education. Nothing on this site is investment, legal or tax advice, or a recommendation to buy or sell any security.", "We do not know your circumstances, do not provide personalized advice and do not execute trades.", "Market data comes from third-party feeds, may be delayed or inaccurate, and is subject to vendor and exchange terms.", "Model outputs, including ValueBot valuations, are estimates based on assumptions that may prove wrong. Past performance does not guarantee future results."]],
  "community-guidelines": ["Community Guidelines", ["Disclose any position you hold in a security you discuss.", "No undisclosed promotion, paid content, pump-and-dump schemes or coordinated campaigns.", "Trade posts record platform prices and cannot be edited; they can only be closed.", "Be civil. Critique ideas, not people.", "Moderation actions are logged and can be appealed."]],
  "disclosure-policy": ["Disclosure Policy", ["Irradiance staff may not trade securities discussed in unpublished research until 48 hours after publication.", "Authors disclose positions at the end of each article.", "We receive no compensation from issuers covered in our research."]],
};

export function generateStaticParams() { return Object.keys(DOCS).map(doc => ({ doc })); }

export default async function Legal({ params }: { params: Promise<{ doc: string }> }) {
  const { doc } = await params;
  const d = DOCS[doc];
  if (!d) notFound();
  return (
    <div className="mx-auto max-w-3xl px-4 py-12">
      <PageHeader title={d[0]} intro="Last updated November 2026" />
      <div className="space-y-4 text-slate-300">{d[1].map(p => <p key={p}>{p}</p>)}</div>
    </div>
  );
}
