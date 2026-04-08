"use client";

/**
 * Star-dive HUD labels — the text overlay that appears during the NMS dive.
 * Pure HTML/CSS, no WebGL. The WebGL disc rendering lives in
 * landing-starfield-webgl.tsx (same Three.js canvas as the starfield).
 */

import { useEffect, useRef } from "react";
import type { StellarProfile } from "@/lib/landing-stars/types";

export interface StarDiveLabelsView {
  screenX: number;   // star centre in CSS pixels from viewport left
  screenY: number;   // star centre in CSS pixels from viewport top
  focusStrength: number; // 0→1
  profile: StellarProfile;
  starName?: string;
}

interface StarDiveLabelsProps {
  viewRef: React.MutableRefObject<StarDiveLabelsView | null>;
}

export function StarDiveLabels({ viewRef }: StarDiveLabelsProps) {
  const labelContainerRef = useRef<HTMLDivElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const nameRef = useRef<HTMLDivElement>(null);
  const subRef = useRef<HTMLDivElement>(null);
  const statsRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let raf = 0;

    function tick() {
      raf = requestAnimationFrame(tick);
      const view = viewRef.current;
      const wrapper = wrapperRef.current;

      if (!view || view.focusStrength < 0.01) {
        if (wrapper) wrapper.style.opacity = "0";
        return;
      }

      if (wrapper) wrapper.style.opacity = "1";

      if (labelContainerRef.current) {
        const discCssPx = Math.min(window.innerWidth, window.innerHeight) * 0.28;
        labelContainerRef.current.style.left = `${Math.round(view.screenX)}px`;
        labelContainerRef.current.style.top  = `${Math.round(view.screenY + discCssPx + 24)}px`;
      }

      if (nameRef.current && view.starName) {
        nameRef.current.textContent = view.starName;
      }
      if (subRef.current) {
        const p = view.profile;
        subRef.current.textContent = `${p.spectralClass}  ·  ${p.stellarType.replace(/_/g, " ")}`;
      }
      if (statsRef.current) {
        const p = view.profile;
        statsRef.current.textContent =
          `${Math.round(p.temperatureK).toLocaleString()} K  ·  ${p.luminositySolar.toFixed(1)} L☉  ·  ${p.radiusSolar.toFixed(2)} R☉`;
      }

      const labelAlpha = Math.min(1, Math.max(0, (view.focusStrength - 0.55) / 0.3));
      if (nameRef.current)  nameRef.current.style.opacity  = String(labelAlpha);
      if (subRef.current)   subRef.current.style.opacity   = String(labelAlpha * 0.7);
      if (statsRef.current) statsRef.current.style.opacity = String(labelAlpha * 0.45);
    }

    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [viewRef]);

  return (
    <div
      ref={wrapperRef}
      style={{
        position: "fixed",
        inset: 0,
        pointerEvents: "none",
        zIndex: 3,
        opacity: 0,
        willChange: "opacity",
      }}
      aria-hidden="true"
    >
      <div
        ref={labelContainerRef}
        style={{
          position: "absolute",
          transform: "translate(-50%, 0)",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 5,
          fontFamily: '"Space Grotesk", sans-serif',
          textShadow: "0 1px 10px rgba(0,0,0,0.8)",
          textAlign: "center",
        }}
      >
        <div
          ref={nameRef}
          style={{
            fontSize: 18,
            fontWeight: 600,
            color: "rgba(255,255,255,0.95)",
            letterSpacing: "0.04em",
            opacity: 0,
          }}
        />
        <div
          ref={subRef}
          style={{
            fontSize: 12,
            color: "rgba(200,210,255,0.82)",
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            opacity: 0,
          }}
        />
        <div
          ref={statsRef}
          style={{
            fontSize: 11,
            color: "rgba(160,180,220,0.7)",
            letterSpacing: "0.05em",
            opacity: 0,
          }}
        />
      </div>
    </div>
  );
}
