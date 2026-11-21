import type { Metadata } from "next";
import { pageMeta } from "@/lib/seo";

export const metadata: Metadata = pageMeta("Options Discover", "Options chains, implied volatility, put/call ratios, expected move and unusual activity.", "/options");

export default function Layout({ children }: { children: React.ReactNode }) { return children; }
