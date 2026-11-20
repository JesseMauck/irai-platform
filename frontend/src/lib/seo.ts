import type { Metadata } from "next";

export const SITE = {
  url: "https://irradiance.ai",
  name: "Irradiance.AI",
  tagline: "Illuminating the market research",
  description:
    "AI-powered equity research: ValueBot DCF valuations from SEC filings, ADR and ETF premium monitors, and quality-adjusted relative-value grades — with every input and assumption shown.",
  twitter: "@irradianceai",
};

/** Server-side base URL for the FastAPI backend (Vercel env BACKEND_URL). */
export const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

/** Page metadata with canonical URL, Open Graph and Twitter cards filled in consistently. */
export function pageMeta(title: string, description: string, path: string, opts: { noindex?: boolean } = {}): Metadata {
  const url = `${SITE.url}${path}`;
  return {
    title,
    description,
    alternates: { canonical: url },
    openGraph: { title: `${title} · ${SITE.name}`, description, url, siteName: SITE.name, type: "website" },
    twitter: { card: "summary_large_image", title: `${title} · ${SITE.name}`, description },
    ...(opts.noindex ? { robots: { index: false, follow: false } } : {}),
  };
}

export async function backendJson<T>(path: string, revalidate = 3600): Promise<T | null> {
  try {
    const r = await fetch(`${BACKEND}${path}`, { next: { revalidate } });
    return r.ok ? ((await r.json()) as T) : null;
  } catch {
    return null;
  }
}
