import { pageMeta } from "@/lib/seo";

export const metadata = pageMeta("Trade ideas with verified entry prices", "Member trade ideas with entry prices captured from market data at posting time, so every call can be checked.", "/trades");

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
