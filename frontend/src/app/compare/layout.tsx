import { pageMeta } from "@/lib/seo";

export const metadata = pageMeta("Compare stocks side by side", "Compare valuation multiples, margins, growth, quant grades, momentum, risk and media buzz for up to eight stocks, with an AI-written read-through.", "/compare");

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
