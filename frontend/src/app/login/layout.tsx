import { pageMeta } from "@/lib/seo";

export const metadata = pageMeta("Sign in", "Sign in to Irradiance.AI.", "/login", { noindex: true });

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
