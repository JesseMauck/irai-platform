import { pageMeta } from "@/lib/seo";

export const metadata = pageMeta("Stock screeners: ADR, ETF and value screens", "Preset and custom screens across ADR premiums, ETF discounts and quality-adjusted valuation, with CSV export for members.", "/screeners");

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
