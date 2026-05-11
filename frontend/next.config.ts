import type { NextConfig } from "next";

const BACKEND_URL = process.env.NEXUS_BACKEND_URL ?? "http://localhost:8100";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${BACKEND_URL}/api/:path*`,
      },
      {
        source: "/health",
        destination: `${BACKEND_URL}/health`,
      },
    ];
  },
};

export default nextConfig;
