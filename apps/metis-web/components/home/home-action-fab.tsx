"use client";

/**
 * HomeActionFab — single gold floating action button (bottom-right) that
 * reveals a small radial menu of three satellite actions.
 *
 * Replaces three previously separate floating affordances on the home page
 * (audit item 8 of `docs/preserve-and-productize-plan.md` — Web UI new-user
 * audit, 2026-04-25):
 *   1. Gold "Open chat" bubble → New Chat satellite.
 *   2. Purple semantic-search toggle → Threads-search satellite.
 *   3. Gold catalogue-search top-right sparkle → removed entirely; folded
 *      conceptually into Threads-search (which is the user's preferred
 *      navigation across their own added stars).
 *
 * Plus a Filters satellite that toggles the CatalogueFilterPanel which is
 * now hidden by default on the home page until the user opens the FAB.
 *
 * Animation:
 *   - GSAP staggers satellites outward in a quarter-arc on open (~200ms).
 *   - Reverse-stagger on close (or on outside click).
 *   - Honors `prefers-reduced-motion` via motion/react's `useReducedMotion`
 *     hook (snaps in/out, no transitions).
 *
 * Visual basis: matches the existing `metis-chat-bubble` gold styling per
 * explicit user direction ("the gold bubble looks the best").
 */

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { useReducedMotion } from "motion/react";
import gsap from "gsap";
import { MessageSquare, Search, SlidersHorizontal } from "lucide-react";

export interface HomeActionFabProps {
  /** Whether the FAB radial menu is open (controlled). */
  open: boolean;
  /** Setter for the open state. */
  onOpenChange: (next: boolean) => void;
  /** Whether the Filters satellite (CatalogueFilterPanel toggle) is active. */
  filtersOpen: boolean;
  /** Setter for the Filters satellite. */
  onFiltersOpenChange: (next: boolean) => void;
  /** Whether the Threads-search satellite (semantic search) is active. */
  searchOpen: boolean;
  /** Setter for the Threads-search satellite. */
  onSearchOpenChange: (next: boolean) => void;
  /**
   * When false the Threads-search satellite is omitted from the menu —
   * matches the gating from commit 607d802 (semantic search has nothing
   * to index until the user has added at least one star).
   */
  showSearchSatellite: boolean;
}

interface Satellite {
  key: string;
  label: string;
  ariaLabel: string;
  /** Quarter-arc target offset from FAB centre, in pixels. */
  offset: { x: number; y: number };
}

export function HomeActionFab({
  open,
  onOpenChange,
  filtersOpen,
  onFiltersOpenChange,
  searchOpen,
  onSearchOpenChange,
  showSearchSatellite,
}: HomeActionFabProps): React.JSX.Element {
  const reducedMotion = useReducedMotion();
  const containerRef = useRef<HTMLDivElement>(null);
  const satelliteRefs = useRef<Map<string, HTMLElement>>(new Map());
  // Hover state for the FAB trigger — drives the satellite "peek"
  // affordance so first-time users get a hint that there's a menu
  // before they click. Discarded once `open` flips true.
  const [triggerHovered, setTriggerHovered] = useState(false);

  // Build the satellite list. Order matters — index 0 sits closest to the
  // FAB, animating out first; the rest stagger after it. Memoized so the
  // GSAP effect doesn't re-fire on every render.
  const satellites = useMemo<Satellite[]>(() => {
    const list: Satellite[] = [
      {
        key: "chat",
        label: "New chat",
        // Label preserved verbatim so existing tests that find this link
        // by accessible name (`getByRole("link", { name: "Open chat" })`)
        // keep passing — see `apps/metis-web/app/__tests__/home-page.test.tsx`.
        ariaLabel: "Open chat",
        offset: { x: -56, y: -56 },
      },
      {
        key: "filters",
        label: "Filters",
        ariaLabel: "Toggle catalogue filters",
        offset: { x: 0, y: -80 },
      },
    ];
    if (showSearchSatellite) {
      list.push({
        key: "search",
        label: "Search",
        ariaLabel: "Toggle threads search",
        offset: { x: -80, y: 0 },
      });
    }
    return list;
  }, [showSearchSatellite]);

  // Outside-click closes the FAB.
  useEffect(() => {
    if (!open) return;
    const onDocClick = (event: MouseEvent) => {
      const root = containerRef.current;
      if (!root) return;
      if (event.target instanceof Node && !root.contains(event.target)) {
        onOpenChange(false);
      }
    };
    // Defer registration to the next tick so the click that opened the
    // FAB doesn't immediately close it.
    const id = window.setTimeout(() => {
      document.addEventListener("mousedown", onDocClick);
    }, 0);
    return () => {
      window.clearTimeout(id);
      document.removeEventListener("mousedown", onDocClick);
    };
  }, [open, onOpenChange]);

  // Escape closes the FAB.
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onOpenChange(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onOpenChange]);

  // GSAP stagger: when `open` flips, animate the satellites in/out.
  useEffect(() => {
    const nodes = satellites
      .map((sat) => satelliteRefs.current.get(sat.key))
      .filter((node): node is HTMLElement => Boolean(node));
    if (nodes.length === 0) return;

    if (reducedMotion) {
      // Snap — no transition flash.
      gsap.set(nodes, {
        x: (i) => (open ? satellites[i].offset.x : 0),
        y: (i) => (open ? satellites[i].offset.y : 0),
        opacity: open ? 1 : 0,
        scale: open ? 1 : 0.4,
        pointerEvents: open ? "auto" : "none",
      });
      return;
    }

    if (open) {
      gsap.killTweensOf(nodes);
      gsap.fromTo(
        nodes,
        {
          x: 0,
          y: 0,
          opacity: 0,
          scale: 0.4,
          pointerEvents: "none",
        },
        {
          x: (i) => satellites[i].offset.x,
          y: (i) => satellites[i].offset.y,
          opacity: 1,
          scale: 1,
          pointerEvents: "auto",
          duration: 0.18,
          ease: "back.out(1.6)",
          stagger: 0.04,
        },
      );
    } else if (triggerHovered) {
      // Hover peek — satellites slide partway out (~30% of full
      // distance) at reduced opacity so the user can tell there's a
      // menu without clicking. Pointer events stay off so the peek
      // can't be clicked accidentally; that requires a real open.
      gsap.killTweensOf(nodes);
      gsap.to(nodes, {
        x: (i) => satellites[i].offset.x * 0.32,
        y: (i) => satellites[i].offset.y * 0.32,
        opacity: 0.55,
        scale: 0.7,
        pointerEvents: "none",
        duration: 0.22,
        ease: "power2.out",
        stagger: 0.02,
      });
    } else {
      gsap.killTweensOf(nodes);
      gsap.to(nodes, {
        x: 0,
        y: 0,
        opacity: 0,
        scale: 0.4,
        pointerEvents: "none",
        duration: 0.16,
        ease: "power2.in",
        stagger: { each: 0.03, from: "end" },
      });
    }
  }, [open, reducedMotion, satellites, triggerHovered]);

  const handleSatelliteActivate = (key: string) => {
    if (key === "filters") {
      onFiltersOpenChange(!filtersOpen);
      onOpenChange(false);
    } else if (key === "search") {
      onSearchOpenChange(!searchOpen);
      onOpenChange(false);
    }
    // "chat" is a <Link> — Next.js handles navigation; we still close.
    if (key === "chat") onOpenChange(false);
  };

  const renderSatelliteIcon = (key: string) => {
    if (key === "chat") return <MessageSquare size={18} aria-hidden />;
    if (key === "filters") return <SlidersHorizontal size={18} aria-hidden />;
    return <Search size={18} aria-hidden />;
  };

  return (
    <div
      ref={containerRef}
      className="metis-home-fab-root"
      data-testid="home-action-fab"
    >
      {satellites.map((sat) => {
        const setNode = (node: HTMLElement | null) => {
          if (node) satelliteRefs.current.set(sat.key, node);
          else satelliteRefs.current.delete(sat.key);
        };
        const commonProps = {
          className: "metis-home-fab-satellite",
          "aria-label": sat.ariaLabel,
          "data-key": sat.key,
          // Keep satellites in the accessibility tree so existing tests
          // querying by accessible name continue to pass; tab order is
          // gated on open state, and pointer-events: none in CSS prevents
          // accidental clicks while collapsed.
          tabIndex: open ? 0 : -1,
        } as const;
        if (sat.key === "chat") {
          return (
            <Link
              key={sat.key}
              ref={setNode as (node: HTMLAnchorElement | null) => void}
              href="/chat"
              onClick={() => handleSatelliteActivate("chat")}
              {...commonProps}
            >
              {renderSatelliteIcon(sat.key)}
            </Link>
          );
        }
        return (
          <button
            key={sat.key}
            ref={setNode as (node: HTMLButtonElement | null) => void}
            type="button"
            onClick={() => handleSatelliteActivate(sat.key)}
            {...commonProps}
          >
            {renderSatelliteIcon(sat.key)}
          </button>
        );
      })}

      {/* The FAB itself — gold bubble matching the previous chat-bubble.
          Click toggles the radial menu; hover triggers a satellite
          peek-preview so first-time users see there's a menu. */}
      <button
        type="button"
        className={`metis-chat-bubble metis-home-fab-trigger${open ? " is-open" : ""}`}
        aria-label={open ? "Close actions" : "Open actions"}
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={() => onOpenChange(!open)}
        onMouseEnter={() => setTriggerHovered(true)}
        onMouseLeave={() => setTriggerHovered(false)}
        onFocus={() => setTriggerHovered(true)}
        onBlur={() => setTriggerHovered(false)}
      >
        <svg
          className="metis-celestial-star-svg"
          viewBox="0 0 44 44"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          aria-hidden
        >
          <defs>
            <radialGradient id="metisFabStarGlow" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#fff5dc" stopOpacity={0.95} />
              <stop offset="35%" stopColor="#e8c882" stopOpacity={0.6} />
              <stop offset="100%" stopColor="#c4953a" stopOpacity={0} />
            </radialGradient>
            <radialGradient id="metisFabOuterHalo" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#c4953a" stopOpacity={0.12} />
              <stop offset="100%" stopColor="#c4953a" stopOpacity={0} />
            </radialGradient>
          </defs>
          <circle cx="22" cy="22" r="20" fill="url(#metisFabOuterHalo)" />
          <polygon
            points="22,2 23.5,18 42,22 23.5,26 22,42 20.5,26 2,22 20.5,18"
            fill="url(#metisFabStarGlow)"
            opacity={0.55}
          />
          <polygon
            points="22,8 24,18.5 36,10 25.5,20 36,34 24,25.5 22,36 20,25.5 8,34 18.5,20 8,10 20,18.5"
            fill="url(#metisFabStarGlow)"
            opacity={0.3}
          />
          <circle cx="22" cy="22" r="3" fill="#fff5dc" opacity={0.9} />
          <circle cx="22" cy="22" r="1.5" fill="#ffffff" opacity={0.95} />
          <circle cx="22" cy="10" r="0.7" fill="#d4c3a0" opacity={0.45} />
          <circle cx="32" cy="28" r="0.5" fill="#d4c3a0" opacity={0.35} />
          <circle cx="13" cy="30" r="0.6" fill="#d4c3a0" opacity={0.4} />
        </svg>
      </button>
    </div>
  );
}
