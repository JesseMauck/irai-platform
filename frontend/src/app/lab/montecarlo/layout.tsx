import { pageMeta } from "@/lib/seo";

export const metadata = pageMeta("Monte Carlo stock & portfolio simulator", "Simulate thousands of future price paths for a stock or portfolio: outcome ranges, probability of hitting a target or stop, VaR and CVaR.", "/lab/montecarlo");

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
