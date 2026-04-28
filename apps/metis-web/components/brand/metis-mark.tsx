import type { SVGProps } from "react";

import { cn } from "@/lib/utils";

import { METIS_MARK_PATH_D, METIS_MARK_VIEWBOX } from "./metis-mark-path";

export interface MetisMarkProps extends Omit<SVGProps<SVGSVGElement>, "title"> {
  /** Pixel size (square). Defaults to 32. */
  size?: number;
  /**
   * Accessible label. When set, the SVG gets `role="img"` and an
   * `<title>` child so screen readers announce it. When omitted, the
   * SVG is treated as decorative (`aria-hidden="true"`).
   */
  title?: string;
}

/**
 * Static M-star mark. Inherits color from CSS via `currentColor` on the
 * path; defaults to `var(--brand-mark)` (near-white) so callers don't
 * accidentally inherit the surrounding text color.
 *
 * Pair with `<MetisGlow>` when the surface needs the cyan halo + ripple
 * rings; the mark itself ships no glow.
 *
 * @example
 *   <MetisMark size={28} />                      // decorative, in chrome
 *   <MetisMark size={28} title="Metis home" />   // standalone, named
 */
export function MetisMark({
  size = 32,
  title,
  className,
  ...rest
}: MetisMarkProps) {
  const isDecorative = title === undefined;
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox={METIS_MARK_VIEWBOX}
      width={size}
      height={size}
      role={isDecorative ? undefined : "img"}
      aria-hidden={isDecorative ? "true" : undefined}
      aria-label={isDecorative ? undefined : title}
      className={cn("text-[color:var(--brand-mark)]", className)}
      {...rest}
    >
      {!isDecorative && <title>{title}</title>}
      <path d={METIS_MARK_PATH_D} fill="currentColor" fillRule="evenodd" />
    </svg>
  );
}
