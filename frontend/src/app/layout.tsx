import type { Metadata } from "next";
import "@fontsource-variable/inter";
import "./globals.css";
import { AuthProvider } from "@/components/AuthProvider";
import { Footer } from "@/components/Footer";
import { Header } from "@/components/Header";
import { TickerBar } from "@/components/TickerBar";

export const metadata: Metadata = {
  title: { default: "Irradiance — Illuminating the market research", template: "%s · Irradiance" },
  description: "Relative-value research across ADRs, ETFs and fundamentals, plus ValueBot narrative-and-numbers DCF valuations — with the methodology shown.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen">
        <AuthProvider>
          <TickerBar />
          <Header />
          <main>{children}</main>
          <Footer />
        </AuthProvider>
      </body>
    </html>
  );
}
