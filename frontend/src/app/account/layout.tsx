import { pageMeta } from "@/lib/seo";

export const metadata = pageMeta("Your account", "Manage your Irradiance.AI membership.", "/account", { noindex: true });

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
