import type { Metadata } from "next";
import { pageMeta } from "@/lib/seo";

export const metadata: Metadata = pageMeta("Earnings Hub", "Upcoming earnings dates and recent EPS surprises for the companies you follow.", "/earnings");

export default function Layout({ children }: { children: React.ReactNode }) { return children; }
