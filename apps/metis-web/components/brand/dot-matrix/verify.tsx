import type { CSSProperties } from "react";
import { CELLS, cx, cy, DOT_RADIUS, VIEWBOX } from "./cells";

interface DotMatrixSubProps {
  size: number;
  className?: string;
  ariaLabel: string;
}

/** Checkmark trace cells in time order: (col, row).
 *  Short stroke (3,0) → (4,1), then long stroke (4,1) → (1,4).
 */
const CHECK_PATH: ReadonlyArray<readonly [number, number]> = [
  [3, 0], [4, 1], [3, 2], [2, 3], [1, 4],
];
const CHECK_STAGGER_MS = 180;

export function VerifyLoader({ size, className, ariaLabel }: DotMatrixSubProps) {
  return (
    <svg
      role="img"
      aria-label={ariaLabel}
      viewBox={VIEWBOX}
      width={size}
      height={size}
      className={["dm-verify", className].filter(Boolean).join(" ")}
      data-dot-matrix-loader="verify"
    >
      {CELLS.map(([col, row], i) => {
        const checkIndex = CHECK_PATH.findIndex(([c, r]) => c === col && r === row);
        const onCheck = checkIndex !== -1;
        const style: CSSProperties | undefined = onCheck
          ? { animationDelay: `${checkIndex * CHECK_STAGGER_MS}ms` }
          : undefined;
        return (
          <circle
            key={i}
            cx={cx(col)}
            cy={cy(row)}
            r={DOT_RADIUS}
            fill="currentColor"
            data-check={onCheck ? "1" : "0"}
            style={style}
          />
        );
      })}
    </svg>
  );
}
