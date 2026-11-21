import type { Metadata } from "next";
import { pageMeta } from "@/lib/seo";

export const metadata: Metadata = pageMeta("Premium Signals", "Daily IRAI scan for trend crosses, RSI extremes, 52-week breakouts, unusual moves, buzz spikes and ADR dislocations.", "/signals");

export default function Layout({ children }: { children: React.ReactNode }) { return children; }
