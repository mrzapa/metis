/** 25-cell flat array, row-major: index = row * 5 + col. */
export const CELLS: ReadonlyArray<readonly [number, number]> = (() => {
  const out: Array<[number, number]> = [];
  for (let row = 0; row < 5; row++) {
    for (let col = 0; col < 5; col++) {
      out.push([col, row]);
    }
  }
  return out;
})();

export const cx = (col: number) => col * 10 + 5;
export const cy = (row: number) => row * 10 + 5;
export const DOT_RADIUS = 2;
export const VIEWBOX = "0 0 50 50";

export const isInnerCluster = (col: number, row: number) =>
  col >= 1 && col <= 3 && row >= 1 && row <= 3;
