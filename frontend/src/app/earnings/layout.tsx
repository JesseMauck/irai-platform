import type { Metadata } from "next";
import { pageMeta } from "@/lib/seo";

export const metadata: Metadata = pageMeta("Earnings Hub", "Never be surprised by a report date: upcoming earnings for the companies you follow, recent EPS surprises and the price reaction.", "/earnings");

export default function Layout({ children }: { children: React.ReactNode }) { return children; }
