"use client";

import { useCallback } from "react";
import {
  CATALOGUE_FILTER_DEFAULT,
  CATALOGUE_FILTER_MAX_MAGNITUDE,
  CATALOGUE_SPECTRAL_FAMILIES,
  isCatalogueFilterActive,
  type CatalogueFilterState,
  type CatalogueSpectralFamily,
} from "@/lib/star-catalogue";

export interface CatalogueFilterPanelProps {
  state: CatalogueFilterState;
  onStateChange: (next: CatalogueFilterState) => void;
}

const SLIDER_STEP = 0.1;

function formatMagnitude(value: number): string {
  return value.toFixed(1);
}

export function CatalogueFilterPanel({ state, onStateChange }: CatalogueFilterPanelProps) {
  const allActive = state.families.size === 0;
  const filterActive = isCatalogueFilterActive(state);

  const toggleFamily = useCallback(
    (family: CatalogueSpectralFamily) => {
      const next = new Set(state.families);
      if (next.has(family)) {
        next.delete(family);
      } else {
        next.add(family);
      }
      onStateChange({ families: next, maxMagnitude: state.maxMagnitude });
    },
    [onStateChange, state.families, state.maxMagnitude],
  );

  const clearFamilies = useCallback(() => {
    if (state.families.size === 0) return;
    onStateChange({ families: new Set(), maxMagnitude: state.maxMagnitude });
  }, [onStateChange, state.families.size, state.maxMagnitude]);

  const setMagnitude = useCallback(
    (value: number) => {
      if (Number.isNaN(value)) return;
      onStateChange({ families: state.families, maxMagnitude: value });
    },
    [onStateChange, state.families],
  );

  const reset = useCallback(() => {
    onStateChange({
      families: new Set(),
      maxMagnitude: CATALOGUE_FILTER_DEFAULT.maxMagnitude,
    });
  }, [onStateChange]);

  return (
    <section
      className="metis-catalogue-filter"
      aria-label="Catalogue filter"
      data-testid="catalogue-filter-panel"
    >
      <div className="metis-catalogue-filter-row" role="group" aria-label="Spectral class">
        <button
          type="button"
          className="metis-catalogue-filter-chip"
          aria-pressed={allActive}
          onClick={clearFamilies}
        >
          All
        </button>
        {CATALOGUE_SPECTRAL_FAMILIES.map((family) => {
          const pressed = state.families.has(family);
          return (
            <button
              key={family}
              type="button"
              className="metis-catalogue-filter-chip"
              data-family={family}
              aria-pressed={pressed}
              onClick={() => toggleFamily(family)}
            >
              {family}
            </button>
          );
        })}
      </div>
      <label className="metis-catalogue-filter-slider-label">
        <span className="metis-catalogue-filter-slider-text">
          Magnitude ≤ {formatMagnitude(state.maxMagnitude)}
        </span>
        <input
          type="range"
          min={0}
          max={CATALOGUE_FILTER_MAX_MAGNITUDE}
          step={SLIDER_STEP}
          value={state.maxMagnitude}
          aria-label="Magnitude ceiling"
          onChange={(event) => setMagnitude(Number.parseFloat(event.target.value))}
        />
      </label>
      {filterActive && (
        <button
          type="button"
          className="metis-catalogue-filter-reset"
          onClick={reset}
        >
          Reset
        </button>
      )}
    </section>
  );
}
