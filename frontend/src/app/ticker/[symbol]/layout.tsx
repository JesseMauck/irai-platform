import type { Metadata } from "next";
import { pageMeta } from "@/lib/seo";

export async function generateMetadata({ params }: { params: Promise<{ symbol: string }> }): Promise<Metadata> {
  const symbol = decodeURIComponent((await params).symbol).toUpperCase();
  return pageMeta(`${symbol} stock price, chart, valuation & relative-value grade`,
    `${symbol}: live quote and chart, key statistics, quality-adjusted relative-value grade versus peers, and a one-click ValueBot DCF valuation and strategy backtest.`,
    `/ticker/${encodeURIComponent(symbol)}`);
}

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
