"use client";

import { useCallback, useEffect, useState } from "react";
import { Hammer, Loader2, TriangleAlert } from "lucide-react";
import { PageChrome } from "@/components/shell/page-chrome";
import { EmptyState } from "@/components/ui/empty-state";
import { AnimatedLucideIcon } from "@/components/ui/animated-lucide-icon";
import { AbsorbForm } from "@/components/forge/absorb-form";
import { ProposalReviewPane } from "@/components/forge/proposal-review-pane";
import { TechniqueGallery } from "@/components/forge/technique-gallery";
import {
  fetchForgeTechniques,
  publishCompanionActivity,
  toggleForgeTechnique,
  type ForgeTechnique,
} from "@/lib/api";
import { useHashScroll } from "@/lib/use-hash-scroll";

export default function ForgePage() {
  const [techniques, setTechniques] = useState<ForgeTechnique[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  // M14 Phase 4b — bumping this prop re-fetches the proposal review
  // pane after a successful absorb, so a freshly-persisted proposal
  // surfaces immediately instead of after a manual reload.
  const [proposalRefreshKey, setProposalRefreshKey] = useState(0);

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

  // M14 Phase 3 — toggle handler shared with every card. Keeps state
  // optimistic so the switch flips immediately, calls the API, fires
  // a companion-dock event on success, reverts on failure.
  const handleToggle = useCallback(
    async (technique: ForgeTechnique, enabled: boolean) => {
      // Optimistic update.
      setTechniques((current) =>
        current === null
          ? current
          : current.map((entry) =>
              entry.id === technique.id ? { ...entry, enabled } : entry,
            ),
      );
      try {
        await toggleForgeTechnique(technique, enabled);
      } catch (err) {
        // Revert on failure so the gallery state matches what the
        // server actually saved.
        setTechniques((current) =>
          current === null
            ? current
            : current.map((entry) =>
                entry.id === technique.id ? { ...entry, enabled: !enabled } : entry,
              ),
        );
        throw err;
      }
      // Surface the toggle through the dock as a companion action,
      // not a settings write. Per ADR 0014 principle #4 — the Forge
      // sells "absorbing a capability", not "checking a box".
      publishCompanionActivity({
        source: "forge",
        kind: "technique_toggled",
        state: "completed",
        trigger: technique.id,
        summary: enabled
          ? `Companion absorbed ${technique.name}.`
          : `Companion stood down ${technique.name}.`,
        timestamp: Date.now(),
        payload: {
          technique_id: technique.id,
          technique_name: technique.name,
          enabled,
        },
      });
    },
    [],
  );

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
            <AbsorbForm
              onProposalPersisted={() => setProposalRefreshKey((n) => n + 1)}
            />
            <ProposalReviewPane refreshKey={proposalRefreshKey} />
            <TechniqueGallery techniques={techniques} onToggle={handleToggle} />
            <p className="text-xs text-muted-foreground/60">
              Flipping a card writes the technique&apos;s setting overrides through
              <code className="mx-1 font-mono">settings_store</code>
              and surfaces in the companion dock as an absorbed/stood-down acknowledgement.
              Read-only cards (Heretic, TimesFM forecasting) need a runtime pre-flight that&apos;s
              coming in a follow-up phase.
            </p>
          </>
        )}
      </div>
    </PageChrome>
  );
}
