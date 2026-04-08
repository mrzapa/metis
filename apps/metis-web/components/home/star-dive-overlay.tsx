"use client";

import { useEffect, useRef } from "react";
import {
  createStarProgram,
} from "@/lib/landing-stars/star-surface-shader";
import type { StellarProfile } from "@/lib/landing-stars/types";

export interface StarDiveOverlayView {
  screenX: number;   // star centre in CSS pixels from viewport left
  screenY: number;   // star centre in CSS pixels from viewport top
  focusStrength: number; // 0→1
  profile: StellarProfile;
  starName?: string;
}

interface StarDiveOverlayProps {
  viewRef: React.MutableRefObject<StarDiveOverlayView | null>;
  reducedMotion?: boolean;
}

export function StarDiveOverlay({
  viewRef,
  reducedMotion = false,
}: StarDiveOverlayProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const nameRef = useRef<HTMLDivElement>(null);
  const subRef = useRef<HTMLDivElement>(null);
  const statsRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const DPR = Math.min(window.devicePixelRatio ?? 1, 3);

    const gl = canvas.getContext("webgl2", {
      alpha: true,
      premultipliedAlpha: false,
      antialias: true,
    });
    if (!gl) return;

    const prog = createStarProgram(gl);
    if (!prog) return;

    const buf = gl.createBuffer()!;
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(
      gl.ARRAY_BUFFER,
      new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]),
      gl.STATIC_DRAW,
    );
    const loc = gl.getAttribLocation(prog, "a_pos");
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);

    gl.useProgram(prog);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);

    const uTime        = gl.getUniformLocation(prog, "u_time");
    const uSeed        = gl.getUniformLocation(prog, "u_seed");
    const uColor       = gl.getUniformLocation(prog, "u_color");
    const uColor2      = gl.getUniformLocation(prog, "u_color2");
    const uColor3      = gl.getUniformLocation(prog, "u_color3");
    const uHasC2       = gl.getUniformLocation(prog, "u_hasColor2");
    const uHasC3       = gl.getUniformLocation(prog, "u_hasColor3");
    const uDiffraction = gl.getUniformLocation(prog, "u_hasDiffraction");
    const uStage       = gl.getUniformLocation(prog, "u_stage");
    const uRes         = gl.getUniformLocation(prog, "u_res");

    let startTime: number | null = null;
    let lastProfileId = "";
    let raf = 0;

    function draw(ts: number) {
      if (!gl) return;
      raf = requestAnimationFrame(draw);
      const view = viewRef.current;
      const wrapper = wrapperRef.current;

      if (!view || view.focusStrength < 0.01) {
        if (wrapper) {
          wrapper.style.opacity = "0";
          wrapper.style.transform = "translate(-50%, -50%) scale(0.82)";
        }
        startTime = null;
        return;
      }

      if (!startTime) startTime = ts;
      const elapsed = reducedMotion ? 0 : (ts - startTime) / 1000;

      // Size: sphere fills ~52% of the shortest viewport dimension at full focus
      const vmin = Math.min(window.innerWidth, window.innerHeight);
      const radius = view.focusStrength * 0.52 * vmin * 0.5;
      const diameter = Math.round(radius * 2);
      const physSize = Math.round(diameter * DPR);

      if (physSize < 1) return;

      if (canvas!.width !== physSize || canvas!.height !== physSize) {
        canvas!.width  = physSize;
        canvas!.height = physSize;
        canvas!.style.width  = `${diameter}px`;
        canvas!.style.height = `${diameter}px`;
        gl.viewport(0, 0, physSize, physSize);
      }

      // Position wrapper centred on the star
      if (wrapper) {
        wrapper.style.left = `${Math.round(view.screenX)}px`;
        wrapper.style.top  = `${Math.round(view.screenY)}px`;

        const scale = 0.82 + view.focusStrength * 0.18;
        wrapper.style.opacity   = String(Math.min(1, view.focusStrength * 1.8));
        wrapper.style.transform = `translate(-50%, -50%) scale(${scale.toFixed(3)})`;
      }

      // HUD labels
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

      /* Update uniforms when profile changes */
      const pid = view.profile.seedHash + "";
      if (pid !== lastProfileId) {
        lastProfileId = pid;
        const p = view.profile;
        const seed = (p.seedHash % 1000) / 1000;
        const [cr, cg, cb] = p.palette.core;
        const [h2r, h2g, h2b] = p.palette.halo;
        const [h3r, h3g, h3b] = p.palette.accent;
        gl.uniform1f(uSeed, seed);
        gl.uniform3f(uColor,  cr,  cg,  cb);
        gl.uniform3f(uColor2, h2r, h2g, h2b);
        gl.uniform3f(uColor3, h3r, h3g, h3b);
        gl.uniform1f(uHasC2, 1.0);
        gl.uniform1f(uHasC3, 1.0);
        gl.uniform1f(uDiffraction, 1.0);
        gl.uniform1f(uStage, 2.0);
      }

      gl.uniform1f(uTime, elapsed);
      gl.uniform2f(uRes, canvas!.width, canvas!.height);
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    }

    raf = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(raf);
      gl?.deleteBuffer(buf);
      gl?.deleteProgram(prog);
    };
  }, [viewRef, reducedMotion]);

  return (
    <div
      ref={wrapperRef}
      style={{
        position: "fixed",
        left: 0,
        top: 0,
        pointerEvents: "none",
        zIndex: 2,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        opacity: 0,
        transform: "translate(-50%, -50%) scale(0.82)",
        transition: reducedMotion
          ? "opacity 0.15s"
          : "opacity 0.55s ease, transform 0.55s cubic-bezier(0.23, 1, 0.32, 1)",
        willChange: "transform, opacity",
      }}
      aria-hidden="true"
    >
      <canvas
        ref={canvasRef}
        style={{
          display: "block",
          borderRadius: "50%",
          boxShadow: "0 0 80px 20px rgba(0,0,0,0.55)",
        }}
        aria-hidden="true"
      />

      {/* Label block — centred below sphere */}
      <div style={{
        marginTop: 18,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 5,
        fontFamily: '"Space Grotesk", sans-serif',
        textShadow: "0 1px 10px rgba(0,0,0,0.8)",
        textAlign: "center",
      }}>
        <div
          ref={nameRef}
          style={{
            fontSize: 18,
            fontWeight: 600,
            letterSpacing: "0.06em",
            color: "rgba(235,230,220,0.95)",
            opacity: 0,
            transition: "opacity 0.4s",
          }}
        />
        <div
          ref={subRef}
          style={{
            fontSize: 12,
            fontWeight: 400,
            letterSpacing: "0.12em",
            textTransform: "uppercase",
            color: "rgba(200,210,235,0.85)",
            opacity: 0,
            transition: "opacity 0.4s",
          }}
        />
        <div
          ref={statsRef}
          style={{
            fontSize: 11,
            fontWeight: 400,
            letterSpacing: "0.06em",
            color: "rgba(170,185,210,0.7)",
            opacity: 0,
            transition: "opacity 0.4s",
          }}
        />
      </div>
    </div>
  );
}
