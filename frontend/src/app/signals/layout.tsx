import type { Metadata } from "next";
import { pageMeta } from "@/lib/seo";

export const metadata: Metadata = pageMeta("Premium Signals", "Every evening IRAI scans the most-traded US stocks and ETFs for trend crosses, RSI extremes, 52-week breakouts, unusual moves, attention spikes and ADR dislocations, and keeps score of how each signal type has played out.", "/signals");

export default function Layout({ children }: { children: React.ReactNode }) { return children; }
