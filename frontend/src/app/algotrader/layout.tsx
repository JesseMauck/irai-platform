import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "IRAI AlgoTrader: AI portfolio analysis and strategy automation (Pro add-on)",
  description: "Connect your brokerage to IRAI for AI analysis of your holdings, risk and diversification checks, and rules-based strategies you approve. Coming soon for Irradiance Pro members.",
  alternates: { canonical: "/algotrader" },
};

export default function Layout({ children }: { children: React.ReactNode }) { return children; }
