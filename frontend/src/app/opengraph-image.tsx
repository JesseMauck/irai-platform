import { ImageResponse } from "next/og";

export const alt = "Irradiance.AI: AI-powered equity research with the methodology shown";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OgImage() {
  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", justifyContent: "space-between",
        padding: 72, background: "radial-gradient(70% 60% at 15% 0%, #3a1f12 0%, #0b1220 60%)", color: "#e5e7eb", fontFamily: "sans-serif" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
          <svg width="74" height="62" viewBox="15 13 39 33" fill="none">
            <defs><linearGradient id="g" x1="17" y1="44" x2="51" y2="16" gradientUnits="userSpaceOnUse"><stop stopColor="#C8364F" /><stop offset="0.55" stopColor="#E0605A" /><stop offset="1" stopColor="#F2923A" /></linearGradient></defs>
            <circle cx="27.8" cy="17.6" r="3" fill="url(#g)" />
            <path d="M24.6 24.4h6.2l-0.9 14.6h-6.1z" fill="url(#g)" />
            <path d="M17.6 44c2.6-1.4 5.2-2.4 7.6-2.2 2.6.2 4.7 2.2 7.2 1.6 2.6-.6 4-3 5.7-5.6l5.2-8.2" stroke="url(#g)" strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M51 16.4l-12 5.2 3.4 2.4-2.2 3.4 4.6 2.8 2.2-3.4 3.4 2.4z" fill="url(#g)" />
          </svg>
          <div style={{ display: "flex", fontSize: 44, fontStyle: "italic", fontWeight: 600, letterSpacing: -1 }}>
            IRRADIANCE<span style={{ color: "#f29b4b" }}>.AI</span>
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column" }}>
          <div style={{ fontSize: 68, fontWeight: 700, lineHeight: 1.05, letterSpacing: -2, maxWidth: 980 }}>Value any stock in minutes and see every assumption.</div>
          <div style={{ marginTop: 24, fontSize: 30, color: "#94a3b8", maxWidth: 960 }}>ValueBot DCF valuations from SEC filings · ADR &amp; ETF premium monitors · quality-adjusted relative-value grades</div>
        </div>
        <div style={{ display: "flex", fontSize: 24, color: "#f5a524" }}>irradiance.ai · Research and education, not investment advice</div>
      </div>
    ),
    size,
  );
}
