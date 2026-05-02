import { CELLS, cx, cy, DOT_RADIUS, VIEWBOX } from "./cells";

interface DotMatrixSubProps {
  size: number;
  className?: string;
  ariaLabel: string;
}

export function BreathLoader({ size, className, ariaLabel }: DotMatrixSubProps) {
  return (
    <svg
      role="img"
      aria-label={ariaLabel}
      viewBox={VIEWBOX}
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
