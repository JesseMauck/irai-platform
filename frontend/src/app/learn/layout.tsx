import { pageMeta } from "@/lib/seo";

export const metadata = pageMeta("Learn: ADRs, ETFs, DCF and relative value explained", "Plain-English guides and a glossary for ADR ratios, ETF NAV, discounted cash flow, cost of capital and relative-value analysis.", "/learn");

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
