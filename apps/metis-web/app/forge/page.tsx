"use client";

import { useEffect, useState } from "react";
import { Hammer, Loader2, TriangleAlert } from "lucide-react";
import { PageChrome } from "@/components/shell/page-chrome";
import { EmptyState } from "@/components/ui/empty-state";
import { AnimatedLucideIcon } from "@/components/ui/animated-lucide-icon";
import { TechniqueGallery } from "@/components/forge/technique-gallery";
import { fetchForgeTechniques, type ForgeTechnique } from "@/lib/api";
import { useHashScroll } from "@/lib/use-hash-scroll";

export default function ForgePage() {
  const [techniques, setTechniques] = useState<ForgeTechnique[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchForgeTechniques()
      .then((payload) => {
        if (cancelled) return;
        setTechniques(payload.techniques);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Failed to load Forge techniques.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Honour `/forge#<technique-id>` deep-links once the inventory has
  // rendered. Browsers run automatic fragment navigation before the
  // client-side fetch completes, so without this the constellation's
  // Skills-sector stars (Phase 2b) and the dock's "absorbed X" event
  // copy (Phase 3) would land at the top of the page on first load.
  useHashScroll(techniques !== null);

  return (
    <PageChrome
      eyebrow="METIS · The Forge"
      title="The Forge"
      description="Every frontier technique your METIS already carries. Active cards are running on every query; standby cards are waiting for you to wake them up."
    >
      <div className="mx-auto flex max-w-5xl flex-col gap-6 py-2">
        {error ? (
          <div className="flex items-center gap-2 rounded-xl border border-destructive/25 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            <TriangleAlert className="size-4 shrink-0" />
            <span>{error}</span>
          </div>
        ) : techniques === null ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="size-6 animate-spin text-muted-foreground/50" />
          </div>
        ) : techniques.length === 0 ? (
          <EmptyState
            icon={<AnimatedLucideIcon icon={Hammer} mode="idlePulse" className="size-6" />}
            title="No techniques registered yet"
            description="The Forge inventory is empty in this build. Phase 2 will populate the registry."
          />
        ) : (
          <>
            <TechniqueGallery techniques={techniques} />
            <p className="text-xs text-muted-foreground/60">
              Phase 2a ships read-only cards reflecting your live settings. Phase 3 wires
              the toggle so flipping a card writes through to <code>settings_store</code> and
              fires a companion-dock activation event.
            </p>
          </>
        )}
      </div>
    </PageChrome>
  );
}
