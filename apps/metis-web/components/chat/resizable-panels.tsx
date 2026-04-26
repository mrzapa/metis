"use client";

import {
  useRef,
  useState,
  useCallback,
  useEffect,
  type ReactNode,
  type PointerEvent,
} from "react";
import { cn } from "@/lib/utils";

interface PanelConfig {
  /** Default width in fr-like units (proportional) */
  default: number;
  /** Minimum width in pixels */
  min: number;
  children: ReactNode;
  /**
   * Accessible tab label used when the layout collapses to single-panel
   * mode on narrow viewports. Defaults if omitted, but call sites should
   * provide one for clarity.
   */
  label?: string;
}

interface ResizablePanelsProps {
  panels: [PanelConfig, PanelConfig, PanelConfig];
  className?: string;
  resetToken?: number;
  /**
   * Optional localStorage key for persisting panel sizes across sessions.
   * New users (no stored preference) always see the default open layout.
   * When resetToken changes the stored preference is overwritten with the new defaults.
   */
  storageKey?: string;
  /**
   * Which panel is shown by default in narrow-mode (single-panel tab
   * layout). 0/1/2 indexes into `panels`. Defaults to the middle panel
   * (chat surface), which is the chat page's primary content.
   */
  narrowDefaultIndex?: 0 | 1 | 2;
}

function loadSizes(
  storageKey: string | undefined,
  defaults: [number, number, number],
): [number, number, number] {
  if (!storageKey || typeof window === "undefined") return defaults;
  try {
    const raw = window.localStorage.getItem(storageKey);
    if (!raw) return defaults;
    const parsed = JSON.parse(raw) as unknown;
    if (
      Array.isArray(parsed) &&
      parsed.length === 3 &&
      parsed.every((n) => typeof n === "number" && n > 0 && n < 50)
    ) {
      return parsed as [number, number, number];
    }
  } catch {
    // Ignore malformed entries.
  }
  return defaults;
}

function saveSizes(
  storageKey: string | undefined,
  sizes: [number, number, number],
): void {
  if (!storageKey || typeof window === "undefined") return;
  try {
    window.localStorage.setItem(storageKey, JSON.stringify(sizes));
  } catch {
    // Ignore storage errors (e.g., quota exceeded in private browsing).
  }
}

/**
 * Three-panel resizable layout using CSS grid + pointer-drag dividers.
 *
 * On narrow viewports (container width < sum of panel min-widths + dividers)
 * the layout collapses to a single-panel tab strip so the chat surface
 * doesn't get squeezed into an unreadable sliver. The tab strip uses the
 * `label` field on each PanelConfig.
 */
export function ResizablePanels({
  panels,
  className,
  resetToken,
  storageKey,
  narrowDefaultIndex = 1,
}: ResizablePanelsProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState<number>(0);
  const [activeNarrowIndex, setActiveNarrowIndex] =
    useState<0 | 1 | 2>(narrowDefaultIndex);

  const [sizes, setSizes] = useState<[number, number, number]>(() =>
    loadSizes(storageKey, [panels[0].default, panels[1].default, panels[2].default]),
  );

  // Observe container width so we can fall back to the single-panel tab
  // layout when there isn't enough room for all three panels at their
  // minimum widths.
  useEffect(() => {
    const node = containerRef.current;
    if (!node) return;
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      setContainerWidth(entry.contentRect.width);
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  // 8px = 2 dividers × 4px. Add a small slack buffer so we don't oscillate.
  const minTotal = panels[0].min + panels[1].min + panels[2].min + 8 + 24;
  const isNarrow = containerWidth > 0 && containerWidth < minTotal;

  // Keep a ref that always reflects the latest sizes so we can read it
  // inside event callbacks without capturing stale closures.
  const sizesRef = useRef(sizes);
  useEffect(() => {
    sizesRef.current = sizes;
  }, [sizes]);

  const isFirstResetRender = useRef(true);
  useEffect(() => {
    if (isFirstResetRender.current) {
      isFirstResetRender.current = false;
      return;
    }
    const next: [number, number, number] = [
      panels[0].default,
      panels[1].default,
      panels[2].default,
    ];
    setSizes(next);
    // Persist the reset so the new posture survives the next page load.
    saveSizes(storageKey, next);
    // `panels` and `storageKey` are intentionally excluded: `panels` changes
    // every render (array literal), and `storageKey` is treated as a stable
    // prop (like an id). The effect should only fire on explicit posture resets.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resetToken]);

  // Which divider is being dragged: 0 = left|center, 1 = center|right
  const draggingRef = useRef<number | null>(null);
  const startXRef = useRef(0);
  const startSizesRef = useRef<[number, number, number]>([...sizes]);

  const total = sizes[0] + sizes[1] + sizes[2];

  const handlePointerDown = useCallback(
    (dividerIndex: number) => (e: PointerEvent) => {
      e.preventDefault();
      draggingRef.current = dividerIndex;
      startXRef.current = e.clientX;
      startSizesRef.current = [...sizes] as [number, number, number];
      (e.target as HTMLElement).setPointerCapture(e.pointerId);
    },
    [sizes],
  );

  const handlePointerMove = useCallback(
    (e: globalThis.PointerEvent) => {
      if (draggingRef.current === null || !containerRef.current) return;

      const containerWidth = containerRef.current.offsetWidth;
      const dx = e.clientX - startXRef.current;
      const dFraction = (dx / containerWidth) * total;
      const idx = draggingRef.current;
      const ss = startSizesRef.current;
      const minFr = (panel: PanelConfig) => (panel.min / containerWidth) * total;

      const newSizes: [number, number, number] = [...ss];
      newSizes[idx] = Math.max(minFr(panels[idx]), ss[idx] + dFraction);
      newSizes[idx + 1] = Math.max(
        minFr(panels[idx + 1]),
        ss[idx + 1] - dFraction,
      );

      setSizes(newSizes);
    },
    [panels, total],
  );

  const handlePointerUp = useCallback(() => {
    if (draggingRef.current !== null) {
      // Persist the final layout after a drag completes.
      saveSizes(storageKey, sizesRef.current);
    }
    draggingRef.current = null;
  }, [storageKey]);

  useEffect(() => {
    document.addEventListener("pointermove", handlePointerMove);
    document.addEventListener("pointerup", handlePointerUp);
    return () => {
      document.removeEventListener("pointermove", handlePointerMove);
      document.removeEventListener("pointerup", handlePointerUp);
    };
  }, [handlePointerMove, handlePointerUp]);

  if (isNarrow) {
    const labels: [string, string, string] = [
      panels[0].label ?? "Panel 1",
      panels[1].label ?? "Panel 2",
      panels[2].label ?? "Panel 3",
    ];
    return (
      <div
        ref={containerRef}
        className={cn("flex h-full min-h-0 flex-col", className)}
      >
        <div
          role="tablist"
          aria-label="Panels"
          className="flex shrink-0 gap-1 px-1.5 pb-1.5"
        >
          {labels.map((label, i) => {
            const active = i === activeNarrowIndex;
            return (
              <button
                key={label}
                role="tab"
                type="button"
                aria-selected={active}
                aria-controls={`narrow-panel-${i}`}
                onClick={() => setActiveNarrowIndex(i as 0 | 1 | 2)}
                className={cn(
                  "flex-1 rounded-full px-3 py-1.5 text-xs font-medium transition-colors",
                  active
                    ? "bg-primary/15 text-foreground"
                    : "text-muted-foreground hover:bg-white/5 hover:text-foreground",
                )}
              >
                {label}
              </button>
            );
          })}
        </div>
        {panels.map((panel, i) => (
          <div
            key={i}
            id={`narrow-panel-${i}`}
            role="tabpanel"
            aria-labelledby={`narrow-tab-${i}`}
            hidden={i !== activeNarrowIndex}
            className={cn(
              "min-h-0 flex-1 overflow-hidden",
              i !== activeNarrowIndex && "hidden",
            )}
          >
            {panel.children}
          </div>
        ))}
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className={cn("flex h-full", className)}
      style={{
        display: "grid",
        gridTemplateColumns: `${sizes[0]}fr 4px ${sizes[1]}fr 4px ${sizes[2]}fr`,
      }}
    >
      {/* Left panel */}
      <div className="min-h-0 overflow-hidden">{panels[0].children}</div>

      {/* Divider 0 */}
      <div
        role="separator"
        aria-orientation="vertical"
        tabIndex={0}
        onPointerDown={handlePointerDown(0)}
        onKeyDown={(e) => {
          if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
            e.preventDefault();
            const delta = e.key === "ArrowLeft" ? -0.5 : 0.5;
            setSizes((prev) => {
              const next: [number, number, number] = [
                Math.max(1, prev[0] + delta),
                Math.max(1, prev[1] - delta),
                prev[2],
              ];
              saveSizes(storageKey, next);
              return next;
            });
          }
        }}
        className="chat-pane-divider mx-1.5 my-3 cursor-col-resize rounded-full focus-visible:outline-none"
      />

      {/* Centre panel */}
      <div className="min-h-0 overflow-hidden">{panels[1].children}</div>

      {/* Divider 1 */}
      <div
        role="separator"
        aria-orientation="vertical"
        tabIndex={0}
        onPointerDown={handlePointerDown(1)}
        onKeyDown={(e) => {
          if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
            e.preventDefault();
            const delta = e.key === "ArrowLeft" ? -0.5 : 0.5;
            setSizes((prev) => {
              const next: [number, number, number] = [
                prev[0],
                Math.max(1, prev[1] + delta),
                Math.max(1, prev[2] - delta),
              ];
              saveSizes(storageKey, next);
              return next;
            });
          }
        }}
        className="chat-pane-divider mx-1.5 my-3 cursor-col-resize rounded-full focus-visible:outline-none"
      />

      {/* Right panel */}
      <div className="min-h-0 overflow-hidden">{panels[2].children}</div>
    </div>
  );
}
