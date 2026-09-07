/** @type {import('next').NextConfig} */

// In production the Next server proxies /api/v1/* to the backend so the browser
// talks to a single origin (clean SSE, no CORS). Locally it targets :8000.
const API_PROXY_TARGET = process.env.API_PROXY_TARGET || "http://localhost:8000";

const nextConfig = {
  // "standalone" is only for the self-hosted Docker image (the Dockerfile sets
  // BUILD_STANDALONE=1). Everywhere else — Vercel, local dev — leave it unset so
  // the platform's own Next.js handling applies.
  output: process.env.BUILD_STANDALONE === "1" ? "standalone" : undefined,
  reactStrictMode: true,
  async rewrites() {
    return [
      { source: "/api/v1/:path*", destination: `${API_PROXY_TARGET}/api/v1/:path*` },
    ];
  },
};

export default nextConfig;
