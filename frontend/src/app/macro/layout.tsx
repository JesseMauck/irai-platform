import type { Metadata } from "next";
import { pageMeta } from "@/lib/seo";

export const metadata: Metadata = pageMeta("Macro map", "The whole world on one screen: global stock markets, Treasury yields, currencies, commodities and risk gauges, updated through the day.", "/macro");

export default function Layout({ children }: { children: React.ReactNode }) { return children; }
