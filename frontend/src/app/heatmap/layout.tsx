import type { Metadata } from "next";
import { pageMeta } from "@/lib/seo";

export const metadata: Metadata = pageMeta("Market heatmap", "See where money is moving today: US large caps by sector, sized by market value and coloured by return, with one click to any ticker.", "/heatmap");

export default function Layout({ children }: { children: React.ReactNode }) { return children; }
