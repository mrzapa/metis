import type { CSSProperties } from "react";
import { CELLS, cx, cy, DOT_RADIUS, VIEWBOX } from "./cells";

interface DotMatrixSubProps {
  size: number;
  className?: string;
  ariaLabel: string;
}

const COL_STAGGER_MS = 800;
const ROW_STAGGER_MS = 120; // within a column, bottom-up

/** Delay (ms) for cell at (col, row).
 *  col 0 starts at 0; each next col +800ms.
 *  Within a col, row 4 (bottom) is first, then 3, 2, 1, 0.
 */
function compileDelay(col: number, row: number): number {
  const colStart = col * COL_STAGGER_MS;
  const inCol = (4 - row) * ROW_STAGGER_MS; // bottom-up
  return colStart + inCol;
}

export function CompileLoader({ size, className, ariaLabel }: DotMatrixSubProps) {
  return (
    <svg
      role="img"
      aria-label={ariaLabel}
      viewBox={VIEWBOX}
      width={size}
      height={size}
      className={["dm-compile", className].filter(Boolean).join(" ")}
      data-dot-matrix-loader="compile"
    >
      {CELLS.map(([col, row], i) => {
        const style: CSSProperties = {
          animationDelay: `${compileDelay(col, row)}ms`,
        };
        return (
          <circle
            key={i}
            cx={cx(col)}
            cy={cy(row)}
            r={DOT_RADIUS}
            fill="currentColor"
            style={style}
          />
        );
      })}
    </svg>
  );
}
