import type { Metadata } from "next";
import { pageMeta } from "@/lib/seo";

export async function generateMetadata({ params }: { params: Promise<{ symbol: string }> }): Promise<Metadata> {
  const symbol = decodeURIComponent((await params).symbol).toUpperCase();
  return pageMeta(`${symbol} ADR premium vs local shares`,
    `${symbol} ADR against its home-market line in USD: premium history, structural basis, ±2σ band, z-score and half-life.`,
    `/monitor/adr/${encodeURIComponent(symbol)}`);
}

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
