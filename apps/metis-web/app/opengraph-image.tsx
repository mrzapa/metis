import { ImageResponse } from "next/og";
import {
  METIS_MARK_PATH_D,
  METIS_MARK_VIEWBOX,
} from "@/components/brand";

/**
 * Open Graph social card, 1200×630. Lockup on the left (lowercase
 * 'metis' wordmark + tagline), glowing mark on the right with static
 * ripple rings.
 *
 * Static ripple rings are approximated as concentric border-radius
 * divs rather than SVG feMorphology — Satori (the ImageResponse
 * renderer) supports a subset of CSS and doesn't render filter
 * primitives faithfully. Visually equivalent at OG resolution.
 */

export const runtime = "edge";
export const alt = "Metis — a local-first frontier AI workspace";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const RING_OFFSETS = [60, 44, 30, 18, 8] as const;
const RING_OPACITIES = [0.08, 0.13, 0.20, 0.30, 0.45] as const;

export default function OpenGraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          background:
            "linear-gradient(180deg, #06080e 0%, #0a1024 60%, #060812 100%)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0 96px",
          fontFamily: "system-ui, sans-serif",
        }}
      >
        {/* Left — lockup */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "24px",
          }}
        >
          <span
            style={{
              fontSize: "144px",
              fontWeight: 500,
              color: "#f4f6fa",
              letterSpacing: "-0.04em",
              lineHeight: 1,
            }}
          >
            metis
          </span>
          <span
            style={{
              fontSize: "32px",
              color: "rgba(244, 246, 250, 0.72)",
              maxWidth: "560px",
              lineHeight: 1.3,
            }}
          >
            A local-first frontier AI workspace.
          </span>
        </div>

        {/* Right — mark with static ripple rings + glow */}
        <div
          style={{
            position: "relative",
            width: "360px",
            height: "360px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          {RING_OFFSETS.map((r, i) => (
            <div
              key={r}
              style={{
                position: "absolute",
                top: `${-r * 0.5}px`,
                bottom: `${-r * 0.5}px`,
                left: `${-r * 0.5}px`,
                right: `${-r * 0.5}px`,
                border: `1.5px solid rgba(150, 190, 255, ${RING_OPACITIES[i]})`,
                borderRadius: "50%",
              }}
            />
          ))}
          <svg width="280" height="280" viewBox={METIS_MARK_VIEWBOX}>
            <path
              d={METIS_MARK_PATH_D}
              fill="#f4f6fa"
              fillRule="evenodd"
            />
          </svg>
        </div>
      </div>
    ),
    size,
  );
}
