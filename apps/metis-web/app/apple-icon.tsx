import { ImageResponse } from "next/og";
import {
  METIS_MARK_PATH_D,
  METIS_MARK_VIEWBOX,
} from "@/components/brand";

/**
 * Apple touch icon, 180×180. White mark on dark navy with rounded
 * corners. Uses the FULL mark (M cutout intact) since 180 px is
 * plenty of resolution for the notches to read cleanly.
 */

export const runtime = "edge";
export const size = { width: 180, height: 180 };
export const contentType = "image/png";

export default function AppleIcon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          background: "#06080e",
          borderRadius: "32px",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <svg width="120" height="120" viewBox={METIS_MARK_VIEWBOX}>
          <path d={METIS_MARK_PATH_D} fill="#f4f6fa" fillRule="evenodd" />
        </svg>
      </div>
    ),
    size,
  );
}
