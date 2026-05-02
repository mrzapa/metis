/**
 * Brand primitives — the Metis logo system.
 *
 * See `./README.md` for usage guidance and `docs/plans/2026-04-28-metis-logo-rollout-design.md`
 * for the design rationale.
 */

export { MetisMark, type MetisMarkProps } from "./metis-mark";
export {
  MetisGlow,
  type MetisGlowProps,
  type MetisGlowAnimated,
} from "./metis-glow";
export { MetisLockup, type MetisLockupProps } from "./metis-lockup";
export { MetisLoader, type MetisLoaderProps } from "./metis-loader";
export {
  DotMatrixLoader,
  type DotMatrixLoaderName,
  type DotMatrixLoaderProps,
} from "./dot-matrix-loader";
export { METIS_MARK_PATH_D, METIS_MARK_VIEWBOX } from "./metis-mark-path";
