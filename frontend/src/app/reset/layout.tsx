import { pageMeta } from "@/lib/seo";

export const metadata = pageMeta("Choose a new password", "Choose a new Irradiance.AI password.", "/reset", { noindex: true });

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
