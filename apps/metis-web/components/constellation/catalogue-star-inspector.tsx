"use client";

import { useEffect } from "react";
import {
  formatLuminositySolar,
  formatSpectralClassLabel,
  formatTemperatureK,
  formatVisualArchetypeLabel,
} from "@/lib/landing-stars";
import type { StellarProfile } from "@/lib/landing-stars";

export interface CatalogueStarInspectorStar {
  id: string;
  name: string | null;
  profile: StellarProfile;
  apparentMagnitude: number;
  worldX: number;
  worldY: number;
}

export interface CatalogueStarInspectorProps {
  open: boolean;
  star: CatalogueStarInspectorStar | null;
  addable: boolean;
  promoteDisabledReason?: string | null;
  onClose: () => void;
  onPromote: () => void;
}

const DEFAULT_PROMOTE_DISABLED_REASON =
  "Pan closer to your existing stars, or add your first star first.";

function formatCoordinate(n: number): string {
  if (!Number.isFinite(n)) return "—";
  const fixed = n.toFixed(3);
  if (n < 0) {
    return `−${Math.abs(n).toFixed(3)}`;
  }
  return fixed;
}

function formatMagnitude(m: number): string {
  if (!Number.isFinite(m)) return "—";
  return m.toFixed(2);
}

function shortIdSuffix(id: string): string {
  const parts = id.split("-");
  if (parts.length <= 2) return id;
  return parts.slice(-2).join("-");
}

function miniPreviewBackground(profile: StellarProfile): string {
  const [r, g, b] = profile.baseColor;
  const core = `rgb(${r}, ${g}, ${b})`;
  const halo = `rgba(${r}, ${g}, ${b}, 0.55)`;
  return `radial-gradient(circle at 50% 45%, ${core} 0%, ${core} 18%, ${halo} 52%, rgba(8, 11, 20, 0.95) 78%, rgba(8, 11, 20, 1) 100%)`;
}

export function CatalogueStarInspector({
  open,
  star,
  addable,
  promoteDisabledReason,
  onClose,
  onPromote,
}: CatalogueStarInspectorProps) {
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  if (!open || !star) return null;

  const title = star.name ?? `Field star · ${shortIdSuffix(star.id)}`;
  const spectral = formatSpectralClassLabel(star.profile);
  const temperature = formatTemperatureK(star.profile.temperatureK);
  const luminosity = formatLuminositySolar(star.profile.luminositySolar);
  const archetype = formatVisualArchetypeLabel(star.profile.visualArchetype);
  const magnitude = formatMagnitude(star.apparentMagnitude);
  const coords = `${formatCoordinate(star.worldX)}, ${formatCoordinate(star.worldY)}`;
  const disabledReason = promoteDisabledReason ?? DEFAULT_PROMOTE_DISABLED_REASON;

  return (
    <aside
      aria-label="Catalogue star inspector"
      role="dialog"
      aria-modal="false"
      className="metis-catalogue-inspector"
      data-testid="catalogue-star-inspector"
    >
      <header className="metis-catalogue-inspector-head">
        <h2
          className="metis-catalogue-inspector-title"
          data-testid="catalogue-star-inspector-title"
        >
          {title}
        </h2>
        <button
          type="button"
          className="metis-catalogue-inspector-close"
          aria-label="Close"
          onClick={onClose}
        >
          ×
        </button>
      </header>

      <div className="metis-catalogue-inspector-preview">
        <div
          aria-hidden="true"
          className="metis-catalogue-inspector-preview-disc"
          style={{ background: miniPreviewBackground(star.profile) }}
        />
      </div>

      <dl className="metis-catalogue-inspector-fields">
        <div className="metis-catalogue-inspector-field">
          <dt>Spectral class</dt>
          <dd data-field="spectral-class">{spectral}</dd>
        </div>
        <div className="metis-catalogue-inspector-field">
          <dt>Temperature</dt>
          <dd data-field="temperature">{temperature} K</dd>
        </div>
        <div className="metis-catalogue-inspector-field">
          <dt>Luminosity</dt>
          <dd data-field="luminosity">{luminosity} L☉</dd>
        </div>
        <div className="metis-catalogue-inspector-field">
          <dt>Apparent magnitude</dt>
          <dd data-field="magnitude">{magnitude}</dd>
        </div>
        <div className="metis-catalogue-inspector-field">
          <dt>Archetype</dt>
          <dd data-field="archetype">{archetype}</dd>
        </div>
        <div className="metis-catalogue-inspector-field">
          <dt>Coordinates</dt>
          <dd data-field="coordinates">{coords}</dd>
        </div>
      </dl>

      <footer className="metis-catalogue-inspector-foot">
        <button
          type="button"
          className="metis-catalogue-inspector-promote"
          onClick={onPromote}
          disabled={!addable}
          title={!addable ? disabledReason : undefined}
          aria-describedby={!addable ? "catalogue-star-inspector-reason" : undefined}
        >
          Promote to my constellation
        </button>
        {!addable && (
          <p
            id="catalogue-star-inspector-reason"
            className="metis-catalogue-inspector-reason"
          >
            {disabledReason}
          </p>
        )}
      </footer>
    </aside>
  );
}
