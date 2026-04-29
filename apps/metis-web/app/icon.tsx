import { ImageResponse } from "next/og";

/**
 * Browser-tab favicon, 32×32. Next.js renders this at build time via
 * Satori (subset of CSS). We use a SIMPLIFIED 5-point star silhouette
 * here rather than the full M-star mark — at 32×32 the M's negative-
 * space notches mush together into a black blob in the tab. The full
 * mark with notches is used at 64 px and above (see apple-icon.tsx,
 * opengraph-image.tsx).
 */

// Static export: render at build time (next.config.ts has output: 'export'
// for Tauri bundling). No edge runtime — that's incompatible with static
// export. `dynamic = "force-static"` makes Next pre-render this once.
export const dynamic = "force-static";
export const size = { width: 32, height: 32 };
export const contentType = "image/png";

export default function Icon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          background: "#06080e",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <svg width="24" height="24" viewBox="0 0 100 100">
          <path
            d="M50 5 L62 38 L96 38 L68 58 L78 92 L50 72 L22 92 L32 58 L4 38 L38 38 Z"
            fill="#f4f6fa"
          />
        </svg>
      </div>
    ),
    size,
  );
}
