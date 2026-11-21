import type { Metadata } from "next";
import "@fontsource-variable/inter";
import "@fontsource-variable/inter/opsz-italic.css";
import "@fontsource-variable/space-grotesk";
import "./globals.css";
import { AuthProvider } from "@/components/AuthProvider";
import { Footer } from "@/components/Footer";
import { AskIrai } from "@/components/AskIrai";
import { Header } from "@/components/Header";
import { TickerBar } from "@/components/TickerBar";
import { JsonLd } from "@/components/JsonLd";
import { SITE } from "@/lib/seo";

export const metadata: Metadata = {
  metadataBase: new URL(SITE.url),
  title: { default: "Irradiance.AI: AI stock valuation & relative-value research", template: "%s · Irradiance.AI" },
  description: SITE.description,
  applicationName: SITE.name,
  keywords: ["stock valuation", "DCF calculator", "AI stock analysis", "intrinsic value", "reverse DCF", "ADR arbitrage",
    "ADR premium", "ETF premium discount", "relative value", "equity research", "SEC filings", "backtesting"],
  alternates: { canonical: SITE.url },
  openGraph: { type: "website", siteName: SITE.name, url: SITE.url, title: "Irradiance.AI: Illuminating markets", description: SITE.description },
  twitter: { card: "summary_large_image", site: SITE.twitter, title: "Irradiance.AI: Illuminating markets", description: SITE.description },
  robots: { index: true, follow: true, googleBot: { index: true, follow: true, "max-image-preview": "large", "max-snippet": -1 } },
  category: "finance",
};

const ORG_LD = [
  { "@context": "https://schema.org", "@type": "Organization", name: SITE.name, url: SITE.url, logo: `${SITE.url}/icon.svg`,
    email: "support@irradiance.ai", description: SITE.description },
  { "@context": "https://schema.org", "@type": "WebSite", name: SITE.name, url: SITE.url,
    potentialAction: { "@type": "SearchAction", target: `${SITE.url}/ticker/{symbol}`, "query-input": "required name=symbol" } },
  { "@context": "https://schema.org", "@type": "SoftwareApplication", name: "Irradiance.AI", applicationCategory: "FinanceApplication",
    operatingSystem: "Web", url: SITE.url, description: SITE.description,
    offers: [
      { "@type": "Offer", name: "Free", price: "0", priceCurrency: "USD" },
      { "@type": "Offer", name: "Essential", price: "49", priceCurrency: "USD", description: "Monthly membership, 7-day free trial" },
      { "@type": "Offer", name: "Pro", price: "100", priceCurrency: "USD", description: "Monthly membership, 7-day free trial" },
    ] },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="dark" suppressHydrationWarning>
      <head>
        {/* Apply the saved or system theme before paint, so there's no flash. */}
        <script dangerouslySetInnerHTML={{ __html: `try{var d=document.documentElement,t=localStorage.getItem("irai-theme");if(t!=="light"&&t!=="dark")t=matchMedia("(prefers-color-scheme: light)").matches?"light":"dark";d.dataset.theme=t;var a=localStorage.getItem("irai-accent");if(a)d.dataset.accent=a;var n=localStorage.getItem("irai-density");if(n)d.dataset.density=n}catch(e){}` }} />
        <JsonLd data={ORG_LD} />
      </head>
      <body className="min-h-screen">
        <AuthProvider>
          <TickerBar />
          <Header />
          <main>{children}</main>
          <Footer />
          <AskIrai />
        </AuthProvider>
      </body>
    </html>
  );
}
