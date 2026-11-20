import { pageMeta } from "@/lib/seo";

export const metadata = pageMeta("Leaderboards", "Members ranked by the verified performance of their published trade ideas.", "/leaderboards");

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
