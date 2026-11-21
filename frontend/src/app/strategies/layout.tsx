import type { Metadata } from "next";
import { pageMeta } from "@/lib/seo";

export const metadata: Metadata = pageMeta("Strategy marketplace: trading bots built by the community",
  "Browse trading strategies published by Irradiance members, with backtests and live paper track records, and copy them into your own paper-trading bots.", "/strategies");

export default function Layout({ children }: { children: React.ReactNode }) { return children; }
