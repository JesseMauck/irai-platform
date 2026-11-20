import type { NextConfig } from "next";

// The browser talks to /api/* on the same origin; Next proxies it to FastAPI so auth cookies just work.
const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${BACKEND_URL}/api/:path*` }];
  },
};

export default nextConfig;
