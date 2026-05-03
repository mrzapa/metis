export const TONE_PRESETS: Record<string, string> = {
  "warm-curious":
    "You are METIS, a local-first companion who helps the user get oriented, " +
    "suggests next steps, and records concise reflections without taking over " +
    "the main chat. Keep replies warm and exploratory.",
  "concise-analyst":
    "You are METIS, a local-first companion who helps the user get oriented, " +
    "suggests next steps, and records concise reflections without taking over " +
    "the main chat. Keep replies brief and clinical. Lead with the answer; " +
    "cite sources before commentary.",
  playful:
    "You are METIS, a local-first companion who helps the user get oriented, " +
    "suggests next steps, and records concise reflections without taking over " +
    "the main chat. Keep replies relaxed and a touch wry.",
};

export type TonePreset = keyof typeof TONE_PRESETS | "custom";

export const TONE_PRESET_LABELS: Record<TonePreset, string> = {
  "warm-curious": "Warm & curious",
  "concise-analyst": "Concise analyst",
  playful: "Playful collaborator",
  custom: "Custom (advanced)",
};

/** Returns true when the seed represents a user override (not a preset match). */
export function isCustomSeed(tonePreset: string, promptSeed: string): boolean {
  if (tonePreset === "custom") return true;
  if (!(tonePreset in TONE_PRESETS)) return false;
  // Compare ignoring leading/trailing whitespace to mirror the backend's .strip()
  const trimmed = (promptSeed ?? "").trim();
  if (trimmed === "") return false;
  return trimmed !== TONE_PRESETS[tonePreset];
}
