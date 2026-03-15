import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // output: 'export' enables static HTML export for production Tauri desktop bundling (WOR-13).
  // `next dev` is unaffected; `next build` will write static files to `out/`.
  output: "export",
};

export default nextConfig;
