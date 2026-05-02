import type { CSSProperties } from "react";
import { CELLS, cx, cy, DOT_RADIUS, VIEWBOX, isInnerCluster } from "./cells";

interface DotMatrixSubProps {
  size: number;
  className?: string;
  ariaLabel: string;
}

/** Per-cell delays (ms) for the inner 3×3 cluster, indexed by (col, row).
 *  Manually authored to read as random-but-deterministic firing.
 *  Cells: (col,row) → delay ms.
 */
const INNER_DELAYS: Record<string, number> = {
  "1,1": 0,
  "2,1": 200,
  "3,1": 400,
  "1,2": 600,
  "2,2": 100,
  "3,2": 300,
  "1,3": 500,
  "2,3": 700,
  "3,3": 50,
};

export function ThinkingLoader({ size, className, ariaLabel }: DotMatrixSubProps) {
  return (
    <svg
      role="img"
      aria-label={ariaLabel}
      viewBox={VIEWBOX}
      width={size}
      height={size}
      className={["dm-thinking", className].filter(Boolean).join(" ")}
      data-dot-matrix-loader="thinking"
    >
      {CELLS.map(([col, row], i) => {
        const inner = isInnerCluster(col, row);
        const delay = inner ? INNER_DELAYS[`${col},${row}`] : undefined;
        const style: CSSProperties | undefined =
          delay !== undefined ? { animationDelay: `${delay}ms` } : undefined;
        return (
          <circle
            key={i}
            cx={cx(col)}
            cy={cy(row)}
            r={DOT_RADIUS}
            fill="currentColor"
            data-inner={inner ? "1" : "0"}
            style={style}
          />
        );
      })}
    </svg>
  );
}
