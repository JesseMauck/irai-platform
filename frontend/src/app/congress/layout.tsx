import type { Metadata } from "next";
import { pageMeta } from "@/lib/seo";

export const metadata: Metadata = pageMeta("Congress Trading: stock trades disclosed by members of Congress", "Every House and Senate stock trade disclosed under the STOCK Act, from the official filings: member, ticker, size range, trade and disclosure dates, disclosure lag and the move since.", "/congress");

export default function Layout({ children }: { children: React.ReactNode }) { return children; }
