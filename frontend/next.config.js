/** @type {import('next').NextConfig} */

// Single source of truth for the backend origin. The SSE client
// (lib/api.ts) reads the same variable for its direct connection.
const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${API_BASE}/:path*`,
      },
    ];
  },
  // Increase proxy timeout from default 30s to 180s for long LLM calls
  experimental: {
    proxyTimeout: 180_000,
  },
};

module.exports = nextConfig;
