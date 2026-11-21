import { pageMeta } from "@/lib/seo";

export const metadata = pageMeta("Terminal", "Your Irradiance.AI research terminal.", "/terminal", { noindex: true });

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
