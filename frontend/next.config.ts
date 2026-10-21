import type { NextConfig } from "next";
const config: NextConfig = {
  poweredByHeader: false,
  distDir: process.env.EVALUATOR_NEXT_DIST_DIR || ".next",
  async rewrites() {
    const backend = process.env.EVALUATOR_BACKEND_URL || "http://127.0.0.1:8001";
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
  async headers() {
    return [{source: "/:path*", headers: [
      {key: "X-Content-Type-Options", value: "nosniff"},
      {key: "Referrer-Policy", value: "no-referrer"},
      {key: "X-Frame-Options", value: "DENY"}
    ]}];
  }
};
export default config;
