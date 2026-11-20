import { pageMeta } from "@/lib/seo";

export const metadata = pageMeta("ETF Monitor — premiums and discounts to NAV", "ETF prices against estimated net asset value, with implementation tiers, expense ratios and flags for the gaps that matter.", "/monitor/etf");

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
