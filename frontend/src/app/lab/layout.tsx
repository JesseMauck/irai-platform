import { pageMeta } from "@/lib/seo";

export const metadata = pageMeta("Strategy Lab — backtest trading strategies free", "Backtest moving-average, RSI, Bollinger, MACD and breakout strategies on live market data, with commissions, slippage, drawdowns and out-of-sample checks.", "/lab");

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
