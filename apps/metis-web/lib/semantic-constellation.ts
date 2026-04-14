import type { UserStar } from "@/lib/constellation-types";

export interface SemanticStarLink {
  fromId: string;
  sharedTerms: number;
  toId: string;
}

export interface SemanticSearchState {
  active: boolean;
  links: SemanticStarLink[];
  matchedIds: Set<string>;
  rankedIds: string[];
}

const SEMANTIC_STOP_TERMS = new Set([
  "a", "an", "and", "at", "by", "for", "from", "in", "is", "it", "of", "on", "or", "the", "to", "with",
]);

export function tokenizeSemanticText(value: string): string[] {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9\s]+/g, " ")
    .split(/\s+/)
    .map((term) => term.trim())
    .filter((term) => term.length >= 2 && !SEMANTIC_STOP_TERMS.has(term));
}

export function getSemanticCorpusForStar(star: UserStar): string {
  return [
    star.label ?? "",
    star.intent ?? "",
    star.notes ?? "",
    star.primaryDomainId ?? "",
    ...(star.relatedDomainIds ?? []),
    ...(star.linkedManifestPaths ?? []),
    star.activeManifestPath ?? "",
    star.linkedManifestPath ?? "",
  ].join(" ");
}

export function buildSemanticSearchState(query: string, stars: UserStar[]): SemanticSearchState {
  const queryTerms = tokenizeSemanticText(query);
  if (queryTerms.length === 0 || stars.length < 2) {
    return { active: false, links: [], matchedIds: new Set(), rankedIds: [] };
  }

  const rankedStars = stars
    .map((star) => {
      const corpus = getSemanticCorpusForStar(star);
      const tokens = tokenizeSemanticText(corpus);
      const tokenSet = new Set(tokens);
      const termHits = queryTerms.reduce((sum, term) => {
        if (tokenSet.has(term)) {
          return sum + 1;
        }
        return tokens.some((token) => token.includes(term) || term.includes(token)) ? sum + 0.7 : sum;
      }, 0);
      return { score: termHits, star, tokenSet };
    })
    .filter((entry) => entry.score > 0)
    .sort((left, right) => right.score - left.score)
    .slice(0, 8);

  if (rankedStars.length < 2) {
    return {
      active: rankedStars.length > 0,
      links: [],
      matchedIds: new Set(rankedStars.map((entry) => entry.star.id)),
      rankedIds: rankedStars.map((entry) => entry.star.id),
    };
  }

  const links: SemanticStarLink[] = [];
  for (let index = 0; index < rankedStars.length - 1; index += 1) {
    const left = rankedStars[index];
    const right = rankedStars[index + 1];
    const sharedTerms = queryTerms.filter((term) => left.tokenSet.has(term) && right.tokenSet.has(term)).length;
    links.push({
      fromId: left.star.id,
      sharedTerms,
      toId: right.star.id,
    });
  }

  return {
    active: true,
    links,
    matchedIds: new Set(rankedStars.map((entry) => entry.star.id)),
    rankedIds: rankedStars.map((entry) => entry.star.id),
  };
}

export function buildSemanticShiftOffsets(
  stars: UserStar[],
  semanticState: SemanticSearchState,
): Map<string, { x: number; y: number }> {
  const offsets = new Map<string, { x: number; y: number }>();
  if (!semanticState.active || semanticState.rankedIds.length === 0) {
    return offsets;
  }

  const starById = new Map(stars.map((star) => [star.id, star]));
  const matchedStars = semanticState.rankedIds
    .map((id) => starById.get(id))
    .filter((star): star is UserStar => star !== undefined);
  if (matchedStars.length === 0) {
    return offsets;
  }

  const centroid = matchedStars.reduce(
    (acc, star) => ({ x: acc.x + star.x, y: acc.y + star.y }),
    { x: 0, y: 0 },
  );
  centroid.x /= matchedStars.length;
  centroid.y /= matchedStars.length;

  const ringRadius = Math.min(0.2, 0.11 + matchedStars.length * 0.008);
  matchedStars.forEach((star, index) => {
    const angle = (-Math.PI / 2) + ((Math.PI * 2) * index) / Math.max(1, matchedStars.length);
    const targetX = centroid.x + Math.cos(angle) * ringRadius;
    const targetY = centroid.y + Math.sin(angle) * ringRadius * 0.75;
    offsets.set(star.id, {
      x: (targetX - star.x) * 0.32,
      y: (targetY - star.y) * 0.32,
    });
  });

  stars.forEach((star) => {
    if (offsets.has(star.id)) {
      return;
    }
    const dx = star.x - centroid.x;
    const dy = star.y - centroid.y;
    const distance = Math.hypot(dx, dy) || 1;
    offsets.set(star.id, {
      x: (dx / distance) * 0.009,
      y: (dy / distance) * 0.009,
    });
  });

  return offsets;
}
