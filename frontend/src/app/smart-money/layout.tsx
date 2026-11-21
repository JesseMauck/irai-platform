import type { Metadata } from "next";
import { pageMeta } from "@/lib/seo";

export const metadata: Metadata = pageMeta("Smart Money Trackers: 13F holdings of top investors", "What Berkshire Hathaway, Pershing Square, Bridgewater, Duquesne, Appaloosa and 20 more report owning each quarter, with new, added, trimmed and closed positions and the stocks most held across funds.", "/smart-money");

export default function Layout({ children }: { children: React.ReactNode }) { return children; }
