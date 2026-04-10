import { CONSTELLATION_FACULTIES } from "@/lib/constellation-home";

export interface ConstellationFacultyArtDefinition {
  src: string;
  scale: number;
  offsetY: number;
  idleOpacity: number;
  activeOpacity: number;
  dialogScale: number;
  dialogOffsetY: number;
}

export const FACULTY_ART_MANIFEST = {
  autonomy: {
    src: "/constellation/faculties/autonomy-figure.svg",
    scale: 0.4,
    offsetY: 0.02,
    idleOpacity: 0.18,
    activeOpacity: 0.36,
    dialogScale: 1.04,
    dialogOffsetY: -0.03,
  },
  emergence: {
    src: "/constellation/faculties/emergence-figure.svg",
    scale: 0.38,
    offsetY: 0.08,
    idleOpacity: 0.16,
    activeOpacity: 0.34,
    dialogScale: 1.06,
    dialogOffsetY: -0.01,
  },
  knowledge: {
    src: "/constellation/faculties/knowledge-brain.png",
    scale: 0.36,
    offsetY: 0.01,
    idleOpacity: 0.16,
    activeOpacity: 0.32,
    dialogScale: 1.02,
    dialogOffsetY: -0.02,
  },
  memory: {
    src: "/constellation/faculties/memory-hourglass.png",
    scale: 0.42,
    offsetY: 0.01,
    idleOpacity: 0.16,
    activeOpacity: 0.32,
    dialogScale: 1.03,
    dialogOffsetY: 0.01,
  },
  perception: {
    src: "/constellation/faculties/perception-horus.png",
    scale: 0.4,
    offsetY: 0,
    idleOpacity: 0.17,
    activeOpacity: 0.34,
    dialogScale: 1,
    dialogOffsetY: 0,
  },
  personality: {
    src: "/constellation/faculties/personality-figure.svg",
    scale: 0.37,
    offsetY: 0.02,
    idleOpacity: 0.16,
    activeOpacity: 0.32,
    dialogScale: 1.04,
    dialogOffsetY: 0,
  },
  reasoning: {
    src: "/constellation/faculties/reasoning-scale.png",
    scale: 0.4,
    offsetY: 0.01,
    idleOpacity: 0.15,
    activeOpacity: 0.3,
    dialogScale: 1,
    dialogOffsetY: -0.02,
  },
  skills: {
    src: "/constellation/faculties/skills-figure.svg",
    scale: 0.38,
    offsetY: 0.02,
    idleOpacity: 0.15,
    activeOpacity: 0.31,
    dialogScale: 1.02,
    dialogOffsetY: -0.02,
  },
  strategy: {
    src: "/constellation/faculties/strategy-figure.svg",
    scale: 0.39,
    offsetY: 0.02,
    idleOpacity: 0.17,
    activeOpacity: 0.34,
    dialogScale: 1.03,
    dialogOffsetY: -0.01,
  },
  synthesis: {
    src: "/constellation/faculties/synthesis-figure.svg",
    scale: 0.39,
    offsetY: 0.02,
    idleOpacity: 0.17,
    activeOpacity: 0.34,
    dialogScale: 1.06,
    dialogOffsetY: -0.01,
  },
  values: {
    src: "/constellation/faculties/values-figure.svg",
    scale: 0.38,
    offsetY: 0.03,
    idleOpacity: 0.16,
    activeOpacity: 0.31,
    dialogScale: 1.02,
    dialogOffsetY: -0.02,
  },
} as const satisfies Record<string, ConstellationFacultyArtDefinition>;

export function getFacultyArtDefinition(
  facultyId?: string | null,
): ConstellationFacultyArtDefinition | null {
  if (!facultyId) {
    return null;
  }

  return FACULTY_ART_MANIFEST[facultyId as keyof typeof FACULTY_ART_MANIFEST] ?? null;
}

export function getFacultyArtManifestEntries(): Array<
  readonly [string, ConstellationFacultyArtDefinition]
> {
  return Object.entries(FACULTY_ART_MANIFEST);
}

export function hasFacultyArtForEveryFaculty(): boolean {
  return CONSTELLATION_FACULTIES.every((faculty) => Boolean(getFacultyArtDefinition(faculty.id)));
}
