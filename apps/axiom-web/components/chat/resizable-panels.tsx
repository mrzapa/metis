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
}

interface ResizablePanelsProps {
  panels: [PanelConfig, PanelConfig, PanelConfig];
  className?: string;
}

/**
 * Three-panel resizable layout using CSS grid + pointer-drag dividers.
 * Falls back gracefully — panels can be collapsed below min width on small screens.
 */
export function ResizablePanels({ panels, className }: ResizablePanelsProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [sizes, setSizes] = useState<[number, number, number]>([
    panels[0].default,
    panels[1].default,
    panels[2].default,
  ]);

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
    draggingRef.current = null;
  }, []);

  useEffect(() => {
    document.addEventListener("pointermove", handlePointerMove);
    document.addEventListener("pointerup", handlePointerUp);
    return () => {
      document.removeEventListener("pointermove", handlePointerMove);
      document.removeEventListener("pointerup", handlePointerUp);
    };
  }, [handlePointerMove, handlePointerUp]);

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
      <div className="overflow-hidden">{panels[0].children}</div>

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
            setSizes((prev) => [
              Math.max(1, prev[0] + delta),
              Math.max(1, prev[1] - delta),
              prev[2],
            ]);
          }
        }}
        className="cursor-col-resize bg-border transition-colors hover:bg-ring focus-visible:bg-ring focus-visible:outline-none"
      />

      {/* Centre panel */}
      <div className="overflow-hidden">{panels[1].children}</div>

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
            setSizes((prev) => [
              prev[0],
              Math.max(1, prev[1] + delta),
              Math.max(1, prev[2] - delta),
            ]);
          }
        }}
        className="cursor-col-resize bg-border transition-colors hover:bg-ring focus-visible:bg-ring focus-visible:outline-none"
      />

      {/* Right panel */}
      <div className="overflow-hidden">{panels[2].children}</div>
    </div>
  );
}
