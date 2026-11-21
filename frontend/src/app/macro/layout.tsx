import type { Metadata } from "next";
import { pageMeta } from "@/lib/seo";

export const metadata: Metadata = pageMeta("Macro map", "World stock markets, rates, currencies, commodities and risk gauges at a glance.", "/macro");

export default function Layout({ children }: { children: React.ReactNode }) { return children; }
