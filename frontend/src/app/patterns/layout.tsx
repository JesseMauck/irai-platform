import type { Metadata } from "next";
import { pageMeta } from "@/lib/seo";

export const metadata: Metadata = pageMeta("Pattern Lab: stress-tested market patterns, regimes and lead-lag",
  "Six precisely defined chart patterns tested on stocks, ETFs, rates, currencies, commodities and crypto from 15-minute to weekly bars, with holdout, permutation and regime tests. Plus market regimes, recurring states, lead-lag links and a live crypto order-book pulse.", "/patterns");

export default function Layout({ children }: { children: React.ReactNode }) { return children; }
