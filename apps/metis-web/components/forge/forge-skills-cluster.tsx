"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useReducedMotion } from "motion/react";
import {
  CONSTELLATION_FACULTIES,
  FACULTY_PALETTE,
  type ConstellationFacultyMetadata,
} from "@/lib/constellation-home";
import { fetchForgeTechniques, type ForgeTechnique } from "@/lib/api";
import { cn } from "@/lib/utils";

// Phase 2b "v1 beacon": one small SVG-rendered star per active Forge
// technique, positioned in screen-space around the existing Skills
// faculty anchor. Layered on top of the home-page canvas as a fixed
// overlay; clicks deep-link to `/forge#<technique-id>`.
//
// **What this is not:** these stars are not part of the imperative
// Canvas2D faculty constellation in `app/page.tsx`. They do not zoom-
// track the canvas camera. Promoting them into the canvas pipeline is
// the deferred Phase 2c work — see `plans/the-forge/plan.md`.
//
// The cluster fans the active techniques in a tiny ring around the
// Skills-faculty anchor. Pillar accents the dot colour (Cortex purple,
// Companion emerald, Cosmos sky, cross-cutting white). Each dot has a
// button-shaped invisible hit target so keyboard activation routes
// the same way as a click.

const SKILLS_FACULTY: ConstellationFacultyMetadata | undefined =
  CONSTELLATION_FACULTIES.find((f) => f.id === "skills");

// Ring radius around the Skills anchor, in normalised constellation
// coords. Six stars at 0.06 keeps them tucked under the Skills
// constellation shape rather than sprawling across the viewport.
const CLUSTER_RING_RADIUS = 0.06;
// Twist offset so the first dot does not sit dead-on top of the
// faculty's leading shape star. -π/3 places dot #1 at "8 o'clock"
// relative to the anchor, leaving the constellation glyph visually
// undisturbed.
const CLUSTER_RING_PHASE = -Math.PI / 3;

interface ClusterDot {
  technique: ForgeTechnique;
  // Normalised constellation coords, [0, 1] in both axes.
  nx: number;
  ny: number;
  paletteRgb: [number, number, number];
}

function pillarPalette(pillar: ForgeTechnique["pillar"]): [number, number, number] {
  // Reuse the existing constellation palette tones rather than
  // introducing Forge-specific colours. The Skills faculty itself is
  // emerald (104, 219, 170); Companion techniques inherit that;
  // Cortex techniques borrow the reasoning tone for visual contrast;
  // Cosmos and cross-cutting fall back to neutral palette entries.
  switch (pillar) {
    case "companion":
      return FACULTY_PALETTE.skills;
    case "cortex":
      return FACULTY_PALETTE.reasoning;
    case "cosmos":
      return FACULTY_PALETTE.perception;
    case "cross-cutting":
    default:
      return [208, 216, 232];
  }
}

function clusterDots(active: ForgeTechnique[]): ClusterDot[] {
  if (!SKILLS_FACULTY || active.length === 0) return [];
  const anchorX = SKILLS_FACULTY.x;
  const anchorY = SKILLS_FACULTY.y;
  return active.map((technique, index) => {
    const theta = CLUSTER_RING_PHASE + (index / active.length) * Math.PI * 2;
    const nx = anchorX + Math.cos(theta) * CLUSTER_RING_RADIUS;
    const ny = anchorY + Math.sin(theta) * CLUSTER_RING_RADIUS;
    return {
      technique,
      nx,
      ny,
      paletteRgb: pillarPalette(technique.pillar),
    };
  });
}

export interface ForgeSkillsClusterProps {
  // Optional injected technique list — used by tests to bypass the
  // network fetch. Production callers leave this undefined and let the
  // component pull from the API.
  techniquesOverride?: ForgeTechnique[];
  // Hides the overlay completely. Useful when the home page is in a
  // mode (e.g. star-dive zoom past the threshold) where the cluster
  // would clash with the focused content.
  hidden?: boolean;
  className?: string;
}

export function ForgeSkillsCluster({
  techniquesOverride,
  hidden = false,
  className,
}: ForgeSkillsClusterProps) {
  const router = useRouter();
  const reducedMotion = useReducedMotion();
  const [fetched, setFetched] = useState<ForgeTechnique[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (techniquesOverride !== undefined) {
      setFetched(techniquesOverride);
      return;
    }
    let cancelled = false;
    fetchForgeTechniques()
      .then((payload) => {
        if (cancelled) return;
        setFetched(payload.techniques);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "forge fetch failed");
      });
    return () => {
      cancelled = true;
    };
  }, [techniquesOverride]);

  const dots = useMemo(() => {
    const list = fetched ?? [];
    const active = list.filter((t) => t.enabled);
    return clusterDots(active);
  }, [fetched]);

  if (hidden || error || dots.length === 0) {
    // No overlay surface when the gallery has no active techniques.
    // Encourages the user to *go and turn one on* (Phase 3) without
    // committing screen real-estate to a permanent empty cluster.
    return null;
  }

  return (
    <div
      aria-label="Active Forge techniques"
      className={cn(
        "pointer-events-none fixed inset-0 z-[6]",
        className,
      )}
      data-testid="forge-skills-cluster"
    >
      {dots.map((dot) => (
        <ClusterDotButton
          key={dot.technique.id}
          dot={dot}
          reducedMotion={reducedMotion ?? false}
          onActivate={() => router.push(`/forge#${dot.technique.id}`)}
        />
      ))}
    </div>
  );
}

interface ClusterDotButtonProps {
  dot: ClusterDot;
  reducedMotion: boolean;
  onActivate: () => void;
}

function ClusterDotButton({ dot, reducedMotion, onActivate }: ClusterDotButtonProps) {
  const { technique, nx, ny, paletteRgb } = dot;
  const [r, g, b] = paletteRgb;
  const colour = `rgb(${r}, ${g}, ${b})`;
  const halo = `rgba(${r}, ${g}, ${b}, 0.28)`;

  return (
    <button
      type="button"
      data-technique-id={technique.id}
      aria-label={`Open ${technique.name} in the Forge`}
      title={technique.name}
      onClick={onActivate}
      className={cn(
        "pointer-events-auto absolute -translate-x-1/2 -translate-y-1/2",
        "rounded-full border border-white/20 bg-transparent",
        "p-1.5 outline-none ring-0 focus-visible:ring-2 focus-visible:ring-white/55",
        !reducedMotion && "transition-transform duration-200 ease-out hover:scale-[1.18]",
      )}
      style={{
        left: `${nx * 100}%`,
        top: `${ny * 100}%`,
      }}
    >
      <span
        aria-hidden="true"
        className="block size-2.5 rounded-full"
        style={{
          background: colour,
          boxShadow: `0 0 12px 4px ${halo}`,
        }}
      />
    </button>
  );
}

// Internal helpers exposed for unit tests so the math stays
// independent of the rendering / DOM concerns.
export const __test = {
  clusterDots,
  pillarPalette,
  CLUSTER_RING_RADIUS,
  CLUSTER_RING_PHASE,
};
