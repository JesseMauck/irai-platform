import { pageMeta } from "@/lib/seo";

export const metadata = pageMeta("Admin", "Admin console.", "/admin", { noindex: true });

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
