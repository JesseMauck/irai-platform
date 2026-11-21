import type { Metadata } from "next";
import { pageMeta } from "@/lib/seo";

export const metadata: Metadata = pageMeta("Trade: ready-made strategies and broker connections",
  "Explore ready-made, backtested trading strategies and launch them as paper-trading bots with risk controls. Broker connections for Webull, Robinhood, Fidelity, Charles Schwab, Interactive Brokers and E*TRADE are coming soon.", "/trade");

export default function Layout({ children }: { children: React.ReactNode }) { return children; }
