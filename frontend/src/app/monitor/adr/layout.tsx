import { pageMeta } from "@/lib/seo";

export const metadata = pageMeta("ADR Monitor — live ADR premiums vs local shares", "Every covered ADR against its home-market line in USD, net of its structural basis, with z-scores, half-lives and the reasons a gap may not be tradable.", "/monitor/adr");

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
