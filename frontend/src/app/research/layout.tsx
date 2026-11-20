import { pageMeta } from "@/lib/seo";

export const metadata = pageMeta("Research — ADR, ETF and valuation notes", "Research notes on relative value, ADR and ETF dislocations, and company valuations, with the methodology and data sources shown.", "/research");

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
