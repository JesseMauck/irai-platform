import type { Metadata } from "next";
import { pageMeta } from "@/lib/seo";

export const metadata: Metadata = pageMeta("Market heatmap", "US large caps by sector, sized by market cap and coloured by return.", "/heatmap");

export default function Layout({ children }: { children: React.ReactNode }) { return children; }
