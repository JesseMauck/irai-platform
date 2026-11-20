import type { Metadata } from "next";
import { JsonLd } from "@/components/JsonLd";
import { SITE, backendJson, pageMeta } from "@/lib/seo";

interface Card { slug: string; title: string; summary: string; author: string; published_at: string | null; category: string; tickers: string[] }

async function load(slug: string) {
  return backendJson<Card>(`/api/research/articles/${encodeURIComponent(slug)}`);
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const a = await load(slug);
  if (!a) return pageMeta("Research", "Irradiance.AI research note.", `/research/${slug}`);
  const m = pageMeta(a.title, a.summary, `/research/${a.slug}`);
  return { ...m, openGraph: { ...m.openGraph, type: "article", publishedTime: a.published_at ?? undefined, authors: [a.author] } };
}

export default async function Layout({ children, params }: { children: React.ReactNode; params: Promise<{ slug: string }> }) {
  const a = await load((await params).slug);
  return (
    <>
      {a && <JsonLd data={{ "@context": "https://schema.org", "@type": "Article", headline: a.title, description: a.summary,
        datePublished: a.published_at, author: { "@type": "Person", name: a.author },
        publisher: { "@type": "Organization", name: SITE.name, logo: { "@type": "ImageObject", url: `${SITE.url}/icon.svg` } },
        mainEntityOfPage: `${SITE.url}/research/${a.slug}`, about: a.tickers }} />}
      {children}
    </>
  );
}
