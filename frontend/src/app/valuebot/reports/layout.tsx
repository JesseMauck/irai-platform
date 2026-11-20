import { pageMeta } from "@/lib/seo";

export const metadata = pageMeta("My ValueBot reports", "Your saved ValueBot valuations, notes and scenarios.", "/valuebot/reports", { noindex: true });

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
