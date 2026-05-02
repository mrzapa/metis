import { CELLS, cx, cy, DOT_RADIUS, VIEWBOX } from "./cells";

interface DotMatrixSubProps {
  size: number;
  className?: string;
  ariaLabel: string;
}

/** Inner 3×3 cells around centre (2,2) — the ring that fades. */
const RING_CELLS = new Set([
  "1,1", "2,1", "3,1",
  "1,2",        "3,2",
  "1,3", "2,3", "3,3",
]);

export function HaltLoader({ size, className, ariaLabel }: DotMatrixSubProps) {
  return (
    <svg
      role="img"
      aria-label={ariaLabel}
      viewBox={VIEWBOX}
      width={size}
      height={size}
      className={["dm-halt", className].filter(Boolean).join(" ")}
      data-dot-matrix-loader="halt"
    >
      {CELLS.map(([col, row], i) => {
        const isCentre = col === 2 && row === 2;
        const isRing = RING_CELLS.has(`${col},${row}`);
        const haltAttr = isCentre ? "centre" : isRing ? "ring" : undefined;
        return (
          <circle
            key={i}
            cx={cx(col)}
            cy={cy(row)}
            r={DOT_RADIUS}
            fill="currentColor"
            data-halt={haltAttr}
          />
        );
      })}
    </svg>
  );
}
