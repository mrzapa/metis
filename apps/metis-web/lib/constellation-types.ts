export const CONSTELLATION_USER_STAR_LIMIT: number | null = null;

export interface UserStar {
  id: string;
  x: number;
  y: number;
  size: number;
  createdAt: number;
  label?: string;
  linkedManifestPath?: string;
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export function normalizeUserStar(input: Partial<UserStar> & { id: string }): UserStar {
  const label = typeof input.label === "string" ? input.label.slice(0, 80) : undefined;
  const linkedManifestPath =
    typeof input.linkedManifestPath === "string" ? input.linkedManifestPath : undefined;
  return {
    id: input.id,
    x: clamp(Number(input.x ?? 0.5), 0, 1),
    y: clamp(Number(input.y ?? 0.5), 0, 1),
    size: clamp(Number(input.size ?? 1), 0.5, 2.2),
    createdAt: Number(input.createdAt ?? Date.now()),
    label,
    linkedManifestPath,
  };
}

export function isUserStar(value: unknown): value is UserStar {
  if (!value || typeof value !== "object") {
    return false;
  }
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.id === "string" &&
    typeof candidate.x === "number" &&
    typeof candidate.y === "number" &&
    typeof candidate.size === "number" &&
    typeof candidate.createdAt === "number" &&
    (candidate.label === undefined || typeof candidate.label === "string") &&
    (candidate.linkedManifestPath === undefined || typeof candidate.linkedManifestPath === "string")
  );
}

export function parseUserStars(value: unknown): UserStar[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .filter(isUserStar)
    .map((star) => normalizeUserStar(star));
}

export function capUserStars(stars: UserStar[]): UserStar[] {
  if (CONSTELLATION_USER_STAR_LIMIT === null) {
    return stars;
  }
  return stars.slice(0, CONSTELLATION_USER_STAR_LIMIT);
}

export function getRemainingUserStarSlots(currentCount: number): number | null {
  if (CONSTELLATION_USER_STAR_LIMIT === null) {
    return null;
  }
  return Math.max(0, CONSTELLATION_USER_STAR_LIMIT - currentCount);
}
