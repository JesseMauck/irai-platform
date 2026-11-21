import type { Metadata } from "next";
import { pageMeta } from "@/lib/seo";

export const metadata: Metadata = pageMeta("Options Discover", "Read what the options market expects: chains, implied volatility, put/call ratios, the expected move into earnings and unusual activity.", "/options");

export default function Layout({ children }: { children: React.ReactNode }) { return children; }
