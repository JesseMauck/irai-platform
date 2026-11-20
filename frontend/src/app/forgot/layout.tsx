import { pageMeta } from "@/lib/seo";

export const metadata = pageMeta("Reset your password", "Reset your Irradiance.AI password.", "/forgot", { noindex: true });

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
