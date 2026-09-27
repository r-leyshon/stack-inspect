import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  transpilePackages: [
    "@stack-inspect/browser",
    "@stack-inspect/core",
    "@stack-inspect/next",
    "@stack-inspect/react",
  ],
};

export default nextConfig;
