import type { CSSProperties } from "react";
import { CELLS, cx, cy, DOT_RADIUS, VIEWBOX } from "./cells";

interface DotMatrixSubProps {
  size: number;
  className?: string;
  ariaLabel: string;
}

const STAGGER_MS = 60;

export function StreamLoader({ size, className, ariaLabel }: DotMatrixSubProps) {
  return (
    <svg
      role="img"
      aria-label={ariaLabel}
      viewBox={VIEWBOX}
      width={size}
      height={size}
      className={["dm-stream", className].filter(Boolean).join(" ")}
      data-dot-matrix-loader="stream"
    >
      {CELLS.map(([col, row], i) => {
        const style: CSSProperties = {
          animationDelay: `${i * STAGGER_MS}ms`,
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
