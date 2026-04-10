/**
 * Semantic colour variables for the HUD — delegates to METIS design tokens
 * wherever possible so the HUD inherits the app's theme automatically.
 */
export const HUD_VARS: Record<string, string> = {
  "--hud-primary":     "var(--primary)",
  "--hud-accent":      "var(--gold, oklch(0.72 0.12 78))",
  "--hud-text":        "var(--foreground)",
  "--hud-text-dim":    "var(--muted-foreground)",
  "--hud-border":      "var(--border)",
  "--hud-success":     "oklch(0.66 0.18 155)",
  "--hud-warning":     "oklch(0.72 0.14 65)",
  "--hud-error":       "var(--destructive)",
};
