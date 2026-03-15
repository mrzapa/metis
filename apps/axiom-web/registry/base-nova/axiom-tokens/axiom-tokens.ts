/**
 * Axiom design-token constants.
 *
 * The canonical values live in `registry.json → cssVars` and are injected into
 * the consuming project's CSS by `shadcn add axiom-tokens`.  This module
 * re-exports the semantic names so that TypeScript code (e.g. chart configs or
 * runtime style calculations) can reference the same tokens without hard-coding
 * raw OKLch strings.
 */

/** Semantic color token names available as CSS custom properties (--<name>). */
export const AXIOM_COLOR_TOKENS = [
  "background",
  "foreground",
  "card",
  "card-foreground",
  "popover",
  "popover-foreground",
  "primary",
  "primary-foreground",
  "secondary",
  "secondary-foreground",
  "muted",
  "muted-foreground",
  "accent",
  "accent-foreground",
  "destructive",
  "border",
  "input",
  "ring",
  "chart-1",
  "chart-2",
  "chart-3",
  "chart-4",
  "chart-5",
  "sidebar",
  "sidebar-foreground",
  "sidebar-primary",
  "sidebar-primary-foreground",
  "sidebar-accent",
  "sidebar-accent-foreground",
  "sidebar-border",
  "sidebar-ring",
] as const;

export type AxiomColorToken = (typeof AXIOM_COLOR_TOKENS)[number];

/** Helper: returns a CSS `var()` reference for a given token. */
export function tokenVar(token: AxiomColorToken): string {
  return `var(--${token})`;
}
