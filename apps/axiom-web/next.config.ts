import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // output: 'export' enables static HTML export for production Tauri desktop bundling (WOR-13).
  // `next dev` is unaffected; `next build` will write static files to `out/`.
  output: "export",
  // trailingSlash: true ensures each page is exported as `<route>/index.html`.
  // Without this, Tauri's static file server on Windows redirects `/settings`
  // to `/settings/` and shows a directory listing instead of the settings page.
  trailingSlash: true,
  // unoptimized: true is required when using next/image with output: 'export'.
  // Static exports cannot use the server-side image optimization API.
  images: { unoptimized: true },
};

export default nextConfig;
