/** @type {import('next').NextConfig} */
const API_ORIGIN = process.env.API_ORIGIN || "http://127.0.0.1:8000";

const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    // Proxy GET/API calls to the FastAPI backend so the app is single-origin.
    // NOTE: Next 15's rewrite proxy buffers request bodies with a 10MB cap
    // (proxyClientMaxBodySize only exists in Next 16), which truncates large
    // EDF/H5 uploads and causes ECONNRESET -> HTTP 500. Uploads therefore go
    // directly to the API (see NEXT_PUBLIC_API_ORIGIN in lib/api.ts).
    return [{ source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` }];
  },
};

export default nextConfig;
