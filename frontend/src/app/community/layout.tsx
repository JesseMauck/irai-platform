import { pageMeta } from "@/lib/seo";

export const metadata = pageMeta("Community — research discussion", "Discuss relative value, valuations and market structure with members who show their work.", "/community");

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
