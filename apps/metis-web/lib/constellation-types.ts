export const CONSTELLATION_USER_STAR_LIMIT: number | null = null;

export type UserStarStage = "seed" | "growing" | "integrated";

export interface UserStar {
  id: string;
  x: number;
  y: number;
  size: number;
  createdAt: number;
  label?: string;
  primaryDomainId?: string;
  relatedDomainIds?: string[];
  stage?: UserStarStage;
  intent?: string;
  notes?: string;
  linkedManifestPaths?: string[];
  activeManifestPath?: string;
  linkedManifestPath?: string;
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function isUserStarStage(value: unknown): value is UserStarStage {
  return value === "seed" || value === "growing" || value === "integrated";
}

function normalizeString(value: unknown): string | undefined {
  if (typeof value !== "string") {
    return undefined;
  }
  const next = value.trim();
  return next.length > 0 ? next : undefined;
}

function normalizeStringList(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }

  const next: string[] = [];
  value.forEach((entry) => {
    if (typeof entry !== "string") {
      return;
    }
    const trimmed = entry.trim();
    if (trimmed.length === 0 || next.includes(trimmed)) {
      return;
    }
    next.push(trimmed);
  });
  return next;
}

function moveValueToFront(values: string[], value: string): string[] {
  const next = values.filter((entry) => entry !== value);
  next.unshift(value);
  return next;
}

function resolveStarStage(
  inputStage: unknown,
  linkedManifestPaths: string[],
  notes: string | undefined,
): UserStarStage {
  if (isUserStarStage(inputStage)) {
    return inputStage;
  }
  if (linkedManifestPaths.length >= 2) {
    return "integrated";
  }
  if (linkedManifestPaths.length === 1 || notes) {
    return "growing";
  }
  return "seed";
}

export function normalizeUserStar(input: Partial<UserStar> & { id: string }): UserStar {
  const label = typeof input.label === "string" ? input.label.slice(0, 80) : undefined;
  const primaryDomainId = normalizeString(input.primaryDomainId);
  const intent = normalizeString(input.intent);
  const notes = normalizeString(input.notes);
  const activeManifestPath = normalizeString(input.activeManifestPath);
  const legacyManifestPath = normalizeString(input.linkedManifestPath);
  const linkedManifestPaths = normalizeStringList(input.linkedManifestPaths);

  let normalizedLinkedManifestPaths = [...linkedManifestPaths];
  if (activeManifestPath && !normalizedLinkedManifestPaths.includes(activeManifestPath)) {
    normalizedLinkedManifestPaths.push(activeManifestPath);
  }
  if (legacyManifestPath && !normalizedLinkedManifestPaths.includes(legacyManifestPath)) {
    normalizedLinkedManifestPaths.push(legacyManifestPath);
  }
  if (legacyManifestPath) {
    normalizedLinkedManifestPaths = moveValueToFront(normalizedLinkedManifestPaths, legacyManifestPath);
  } else if (activeManifestPath) {
    normalizedLinkedManifestPaths = moveValueToFront(normalizedLinkedManifestPaths, activeManifestPath);
  }

  const resolvedActiveManifestPath =
    activeManifestPath ?? legacyManifestPath ?? normalizedLinkedManifestPaths[0];
  const resolvedLinkedManifestPath = resolvedActiveManifestPath ?? normalizedLinkedManifestPaths[0];
  const relatedDomainIds = normalizeStringList(input.relatedDomainIds).filter(
    (domainId) => domainId !== primaryDomainId,
  );

  return {
    id: input.id,
    x: clamp(Number(input.x ?? 0.5), 0, 1),
    y: clamp(Number(input.y ?? 0.5), 0, 1),
    size: clamp(Number(input.size ?? 1), 0.5, 2.2),
    createdAt: Number(input.createdAt ?? Date.now()),
    label,
    primaryDomainId,
    relatedDomainIds: relatedDomainIds.length > 0 ? relatedDomainIds : undefined,
    stage: resolveStarStage(input.stage, normalizedLinkedManifestPaths, notes),
    intent,
    notes,
    linkedManifestPaths: normalizedLinkedManifestPaths.length > 0 ? normalizedLinkedManifestPaths : undefined,
    activeManifestPath: resolvedActiveManifestPath,
    linkedManifestPath: resolvedLinkedManifestPath,
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
    (candidate.primaryDomainId === undefined || typeof candidate.primaryDomainId === "string") &&
    (candidate.relatedDomainIds === undefined || Array.isArray(candidate.relatedDomainIds)) &&
    (candidate.stage === undefined || typeof candidate.stage === "string") &&
    (candidate.intent === undefined || typeof candidate.intent === "string") &&
    (candidate.notes === undefined || typeof candidate.notes === "string") &&
    (candidate.linkedManifestPaths === undefined || Array.isArray(candidate.linkedManifestPaths)) &&
    (candidate.activeManifestPath === undefined || typeof candidate.activeManifestPath === "string") &&
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
