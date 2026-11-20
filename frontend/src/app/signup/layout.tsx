import { pageMeta } from "@/lib/seo";

export const metadata = pageMeta("Start your free 7-day trial", "Create your Irradiance.AI account. Try Essential or Pro free for 7 days, no card needed.", "/signup");

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
