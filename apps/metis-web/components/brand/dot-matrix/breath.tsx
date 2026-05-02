import type { CSSProperties } from "react";

interface DotMatrixSubProps {
  size: number;
  className?: string;
  ariaLabel: string;
}

/**
 * 5×5 grid coordinates (col, row) for the 25 circles.
 * Generated once at module load.
 */
const CELLS: ReadonlyArray<readonly [number, number]> = (() => {
  const out: Array<[number, number]> = [];
  for (let row = 0; row < 5; row++) {
    for (let col = 0; col < 5; col++) {
      out.push([col, row]);
    }
  }
  return out;
})();

/** Cell-centre coordinates in the 50×50 viewBox (10 px per cell). */
const cx = (col: number) => col * 10 + 5;
const cy = (row: number) => row * 10 + 5;
const DOT_RADIUS = 2;

export function BreathLoader({ size, className, ariaLabel }: DotMatrixSubProps) {
  return (
    <svg
      role="img"
      aria-label={ariaLabel}
      viewBox="0 0 50 50"
      width={size}
      height={size}
      className={["dm-breath", className].filter(Boolean).join(" ")}
      data-dot-matrix-loader="breath"
    >
      {CELLS.map(([col, row], i) => (
        <circle
          key={i}
          cx={cx(col)}
          cy={cy(row)}
          r={DOT_RADIUS}
          fill="currentColor"
        />
      ))}
    </svg>
  );
}
