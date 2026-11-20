import { pageMeta } from "@/lib/seo";

export const metadata = pageMeta("ValueBot \u2014 AI DCF stock valuation from SEC filings", "Tell a company's story and ValueBot turns it into a full DCF valuation: SEC filings, cost of capital, story tests, reverse DCF, Monte Carlo and an editable Excel model.", "/valuebot");

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
