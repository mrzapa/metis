import { classifyLandingStarRenderTier } from "@/lib/landing-stars/landing-star-lod";
import type { LandingProjectedStar } from "@/lib/landing-stars/landing-star-types";

function getLandingStarInteractionTier(
  star: LandingProjectedStar,
  zoomFactor: number,
) {
  return classifyLandingStarRenderTier(star, zoomFactor);
}

export function getLandingStarSelectableApparentSize(
  star: LandingProjectedStar,
  zoomFactor: number,
): number {
  const renderTier = getLandingStarInteractionTier(star, zoomFactor);

  return renderTier === "point" ? star.apparentSize : Math.max(star.apparentSize, 0.44);
}

export function getLandingStarInteractionHitRadius(
  star: LandingProjectedStar,
  zoomFactor: number,
): number {
  const renderTier = getLandingStarInteractionTier(star, zoomFactor);
  const minimumHitRadius =
    renderTier === "hero"
      ? 18
      : renderTier === "sprite"
        ? 12
        : 8;

  return Math.max(minimumHitRadius, star.apparentSize * 5.5);
}
