import type { NyxCatalogComponentSummary } from "@/lib/api";

export interface FeaturedNyxComponent {
  componentName: string;
  description: string;
  title: string;
}

export const FEATURED_NYX_COMPONENTS = [
  {
    componentName: "glow-card",
    description: "Accent-heavy card chrome for calls to action and layered feature blocks.",
    title: "Glow Card",
  },
  {
    componentName: "github-repo-card",
    description: "Repository summary UI with metadata, badges, and tighter information density.",
    title: "GitHub Repo Card",
  },
  {
    componentName: "music-player",
    description: "Compact control surface that is useful for previewing richer component composition.",
    title: "Music Player",
  },
] as const satisfies readonly FeaturedNyxComponent[];

const FEATURED_NYX_COMPONENT_NAME_SET: ReadonlySet<string> = new Set(
  FEATURED_NYX_COMPONENTS.map((component) => component.componentName),
);

export const NYX_CHAT_SEED_STORAGE_KEY = "metis_chat_seed_prompt";

export function getStableNyxComponentParams(): Array<{ componentName: string }> {
  return FEATURED_NYX_COMPONENTS.map(({ componentName }) => ({ componentName }));
}

export function hasStableNyxComponentPreview(componentName: string): boolean {
  return FEATURED_NYX_COMPONENT_NAME_SET.has(componentName);
}

type NyxChatSeedSource = Pick<
  NyxCatalogComponentSummary,
  | "component_name"
  | "curated_description"
  | "description"
  | "install_target"
  | "required_dependencies"
  | "targets"
  | "title"
>;

export function buildNyxChatSeed(component: NyxChatSeedSource): string {
  const description =
    component.curated_description.trim() || component.description.trim();
  const dependencies = component.required_dependencies.slice(0, 4);
  const targets = component.targets.slice(0, 3);
  const title = component.title.trim() || component.component_name;

  return [
    `I want to incorporate the Nyx UI component ${component.install_target} into Metis.`,
    description ? `Component summary: ${description}` : "",
    dependencies.length > 0
      ? `Required dependencies to account for: ${dependencies.join(", ")}.`
      : "",
    targets.length > 0
      ? `Planned file targets: ${targets.join(", ")}.`
      : "",
    `Help me decide where ${title} fits best before making code changes.`,
  ]
    .filter(Boolean)
    .join(" ");
}

export function buildNyxComponentHref(componentName: string): string {
  return `/library/${encodeURIComponent(componentName)}`;
}

export function getNyxComponentPreviewHref(componentName: string): string | null {
  return hasStableNyxComponentPreview(componentName)
    ? buildNyxComponentHref(componentName)
    : null;
}

export function seedNyxChatPrompt(prompt: string): void {
  if (typeof window === "undefined") {
    return;
  }

  window.localStorage.setItem(NYX_CHAT_SEED_STORAGE_KEY, prompt);
}