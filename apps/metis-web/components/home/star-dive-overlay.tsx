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

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const DPR = Math.min(window.devicePixelRatio ?? 1, 3);

    /* ── init WebGL2 ─────────────────────────────────────────────── */
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

    /* ── uniform locations ───────────────────────────────────────── */
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
      raf = requestAnimationFrame(draw);
      const view = viewRef.current;

      if (!view || view.focusStrength < 0.01) {
        canvas!.style.opacity = "0";
        return;
      }

      if (!startTime) startTime = ts;
      const elapsed = reducedMotion ? 0 : (ts - startTime) / 1000;

      /* Position and size the canvas over the focused star */
      const radius = view.focusStrength * 0.30 * window.innerHeight;
      const diameter = Math.round(radius * 2);
      const physSize = Math.round(diameter * DPR);

      if (canvas!.width !== physSize || canvas!.height !== physSize) {
        canvas!.width  = physSize;
        canvas!.height = physSize;
        canvas!.style.width  = `${diameter}px`;
        canvas!.style.height = `${diameter}px`;
        gl.viewport(0, 0, physSize, physSize);
      }

      canvas!.style.left    = `${Math.round(view.screenX - radius)}px`;
      canvas!.style.top     = `${Math.round(view.screenY - radius)}px`;
      canvas!.style.opacity = String(view.focusStrength);

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
        gl.uniform1f(uDiffraction, 1.0);  // always show diffraction for close-up
        gl.uniform1f(uStage, 2.0);        // always full detail
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
      gl.deleteBuffer(buf);
      gl.deleteProgram(prog);
    };
  }, [viewRef, reducedMotion]);

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: "fixed",
        left: 0,
        top: 0,
        pointerEvents: "none",
        borderRadius: "50%",
        opacity: 0,
        transition: "opacity 0.1s",
        zIndex: 2,
      }}
      aria-hidden="true"
    />
  );
}
