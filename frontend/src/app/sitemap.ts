import type { MetadataRoute } from "next";
import { SITE, backendJson } from "@/lib/seo";

export const revalidate = 3600;

const STATIC: [string, number, MetadataRoute.Sitemap[number]["changeFrequency"]][] = [
  ["/", 1, "daily"], ["/valuebot", 0.9, "weekly"], ["/pricing", 0.9, "monthly"], ["/monitor/adr", 0.8, "hourly"],
  ["/monitor/etf", 0.8, "hourly"], ["/monitor/fundamental", 0.8, "daily"], ["/monitor/pairs", 0.6, "daily"],
  ["/research", 0.8, "daily"], ["/lab", 0.7, "weekly"], ["/algotrader", 0.8, "weekly"], ["/trade", 0.7, "weekly"], ["/strategies", 0.7, "daily"], ["/signals", 0.7, "daily"], ["/patterns", 0.7, "daily"], ["/congress", 0.7, "daily"], ["/smart-money", 0.7, "weekly"], ["/earnings", 0.7, "daily"], ["/heatmap", 0.7, "daily"], ["/macro", 0.7, "daily"], ["/options", 0.6, "daily"], ["/algotrader/for/long-term-investors", 0.6, "monthly"], ["/algotrader/for/income-investors", 0.6, "monthly"], ["/algotrader/for/active-traders", 0.6, "monthly"], ["/algotrader/for/systematic-traders", 0.6, "monthly"], ["/screeners", 0.7, "daily"], ["/methodology", 0.6, "monthly"],
  ["/learn", 0.6, "monthly"], ["/community", 0.5, "daily"], ["/trades", 0.5, "daily"], ["/leaderboards", 0.4, "daily"],
  ["/signup", 0.5, "yearly"], ["/legal/terms", 0.2, "yearly"], ["/legal/privacy", 0.2, "yearly"], ["/legal/disclaimer", 0.2, "yearly"],
];

interface Coverage { adr: string[]; etf: string[]; equities: string[]; articles: { slug: string; published_at: string | null }[] }

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const now = new Date();
  const out: MetadataRoute.Sitemap = STATIC.map(([p, priority, changeFrequency]) => ({ url: `${SITE.url}${p}`, lastModified: now, priority, changeFrequency }));
  const cov = await backendJson<Coverage>("/api/coverage");
  if (cov) {
    for (const a of cov.articles) out.push({ url: `${SITE.url}/research/${a.slug}`, lastModified: a.published_at ? new Date(a.published_at) : now, priority: 0.7, changeFrequency: "monthly" });
    for (const s of cov.adr) out.push({ url: `${SITE.url}/monitor/adr/${encodeURIComponent(s)}`, lastModified: now, priority: 0.6, changeFrequency: "daily" });
    for (const s of new Set([...cov.adr, ...cov.etf, ...cov.equities])) out.push({ url: `${SITE.url}/ticker/${encodeURIComponent(s)}`, lastModified: now, priority: 0.5, changeFrequency: "daily" });
  }
  return out;
}
