/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://127.0.0.1:8000/:path*",
      },
    ];
  },
  // Increase proxy timeout from default 30s to 180s for long LLM calls
  experimental: {
    proxyTimeout: 180_000,
  },
};

module.exports = nextConfig;
