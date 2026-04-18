import type { UserStar } from "./constellation-types";
import type { StarContentType } from "./landing-stars/star-visual-archetype";

/**
 * Derive a {@link StarContentType} from a {@link UserStar} so that procedural
 * stellar-profile generation can choose an appropriate visual archetype per
 * ADR 0006.
 *
 * Inference is deliberately conservative — we only claim a specific content
 * type when the star's shape makes it unambiguous. Returns `null` to mean
 * "no signal"; callers should treat that as the default (`main_sequence`).
 *
 * - `learning_route`: star carries a composed learning route.
 * - `document`: star links at least one manifest/document path.
 * - `null`: plain notes or untagged seeds.
 */
export function deriveUserStarContentType(star: UserStar): StarContentType | null {
  if (star.learningRoute) {
    return "learning_route";
  }

  if (star.activeManifestPath || (star.linkedManifestPaths?.length ?? 0) > 0) {
    return "document";
  }

  return null;
}
