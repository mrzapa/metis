"use client";

import { useCallback, useMemo, useRef } from "react";
import {
  searchCatalogueIndex,
  type CatalogueSearchEntry,
  type CatalogueSearchKind,
} from "@/lib/star-catalogue";

export interface CatalogueSearchOverlayProps {
  expanded: boolean;
  query: string;
  index: readonly CatalogueSearchEntry[];
  onExpandedChange: (next: boolean) => void;
  onQueryChange: (next: string) => void;
  onSelect: (entry: CatalogueSearchEntry) => void;
}

const KIND_CHIP_LABEL: Record<CatalogueSearchKind, string> = {
  landmark: "Landmark",
  user: "User",
  catalogue: "Field",
};

function formatMagnitude(m: number | undefined): string | null {
  if (m === undefined || !Number.isFinite(m)) return null;
  return `m ${m.toFixed(1)}`;
}

export function CatalogueSearchOverlay({
  expanded,
  query,
  index,
  onExpandedChange,
  onQueryChange,
  onSelect,
}: CatalogueSearchOverlayProps) {
  const results = useMemo(
    () => searchCatalogueIndex(query, index, 8),
    [query, index],
  );

  const hasQuery = query.trim().length > 0;
  const showEmptyState = expanded && hasQuery && results.length === 0;
  const showResults = expanded && hasQuery && results.length > 0;

  const inputRef = useRef<HTMLInputElement>(null);
  const resultRefs = useRef<Array<HTMLButtonElement | null>>([]);

  const focusResult = useCallback((index: number) => {
    const node = resultRefs.current[index];
    if (node) node.focus();
  }, []);

  const handleInputKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLInputElement>) => {
      if (event.key === "Escape") {
        onQueryChange("");
        onExpandedChange(false);
        return;
      }
      if (event.key === "ArrowDown" && results.length > 0) {
        event.preventDefault();
        focusResult(0);
      }
    },
    [focusResult, onExpandedChange, onQueryChange, results.length],
  );

  const handleResultKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLButtonElement>, position: number) => {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        if (position < results.length - 1) {
          focusResult(position + 1);
        }
        return;
      }
      if (event.key === "ArrowUp") {
        event.preventDefault();
        if (position === 0) {
          inputRef.current?.focus();
        } else {
          focusResult(position - 1);
        }
        return;
      }
      if (event.key === "Escape") {
        onQueryChange("");
        onExpandedChange(false);
      }
    },
    [focusResult, onExpandedChange, onQueryChange, results.length],
  );

  return (
    <div
      className={`metis-catalogue-search ${expanded ? "is-expanded" : ""}`}
      data-testid="catalogue-search-overlay"
    >
      <button
        type="button"
        className="metis-catalogue-search-toggle"
        aria-label="Toggle catalogue search"
        aria-expanded={expanded}
        onClick={() => onExpandedChange(!expanded)}
      >
        ✧
      </button>
      <input
        ref={inputRef}
        className="metis-catalogue-search-input"
        type="search"
        value={query}
        placeholder="Search the star catalogue by name…"
        aria-label="Catalogue search"
        onChange={(event) => onQueryChange(event.target.value)}
        onKeyDown={handleInputKeyDown}
      />
      {showResults && (
        <ul
          className="metis-catalogue-search-results"
          aria-label="Catalogue search results"
        >
          {results.map((entry, position) => {
            const magnitudeLabel = formatMagnitude(entry.magnitude);
            return (
              <li key={entry.id} className="metis-catalogue-search-result-row">
                <button
                  type="button"
                  ref={(node) => {
                    resultRefs.current[position] = node;
                  }}
                  className="metis-catalogue-search-result"
                  onClick={() => onSelect(entry)}
                  onKeyDown={(event) => handleResultKeyDown(event, position)}
                >
                  <span className="metis-catalogue-search-result-name">{entry.name}</span>
                  <span className="metis-catalogue-search-result-meta">
                    <span
                      className="metis-catalogue-search-result-kind"
                      data-kind={entry.kind}
                    >
                      {KIND_CHIP_LABEL[entry.kind]}
                    </span>
                    {entry.spectralClass && (
                      <span className="metis-catalogue-search-result-class">
                        {entry.spectralClass}
                      </span>
                    )}
                    {magnitudeLabel && (
                      <span className="metis-catalogue-search-result-mag">
                        {magnitudeLabel}
                      </span>
                    )}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
      {showEmptyState && (
        <div className="metis-catalogue-search-empty" role="status">
          No matches.
        </div>
      )}
    </div>
  );
}
