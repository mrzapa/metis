"use client";

import { useEffect, useRef } from "react";

// ── canvas helpers ────────────────────────────────────────────────────────────
// Draws the plasma orb at (cx, cy) with radius R. Caller handles clearRect.
export function drawOrbAt(
  ctx: CanvasRenderingContext2D,
  cx: number,
  cy: number,
  R: number,
  t: number,
  logoImg?: HTMLImageElement | null
): void {
  // Butterfly constellation node positions (normalized to R, center = 0,0)
  const NODES: [number, number][] = [
    [-0.55, -0.65], // 0 top-left
    [ 0.55, -0.65], // 1 top-right
    [-0.30, -0.10], // 2 mid-left
    [ 0.00, -0.18], // 3 mid-center
    [ 0.30, -0.10], // 4 mid-right
    [-0.62,  0.65], // 5 bottom-left
    [ 0.62,  0.65], // 6 bottom-right
  ];
  const pts = NODES.map(([nx, ny]) => [cx + nx * R, cy + ny * R] as [number, number]);

  // Ordered edge list for the traveling light path
  const EDGES: [number, number][] = [
    [0,2],[2,3],[3,4],[4,1],[1,4],[4,6],[6,3],[3,5],[5,2],[2,0],
  ];

  // Fixed background star field (normalized coords, near edges) with twinkle phase
  const STARS: [number, number, number][] = [
    [-0.80,-0.50,0.3],[ 0.82,-0.42,0.7],[-0.75, 0.30,1.1],[ 0.70, 0.55,0.5],
    [-0.40,-0.85,0.9],[ 0.50,-0.80,0.2],[-0.88, 0.10,1.5],[ 0.85, 0.05,0.8],
    [ 0.10, 0.88,1.2],[-0.15,-0.88,0.4],
  ];

  // ── 0. Soft outer corona (integrates with page) ──────────────────────────────
  const corona = ctx.createRadialGradient(cx, cy, R * 0.70, cx, cy, R * 1.55);
  corona.addColorStop(0,   "rgba(30,90,220,0.35)");
  corona.addColorStop(0.5, "rgba(15,55,180,0.12)");
  corona.addColorStop(1,   "rgba(0,20,120,0)");
  ctx.fillStyle = corona;
  ctx.fillRect(cx - R * 2, cy - R * 2, R * 4, R * 4);

  // ── 1. Dark deep-blue sphere base ────────────────────────────────────────────
  const base = ctx.createRadialGradient(cx, cy, 0, cx, cy, R);
  base.addColorStop(0,   "rgba(8,20,60,0.92)");
  base.addColorStop(0.6, "rgba(5,12,40,0.96)");
  base.addColorStop(1,   "rgba(2,6,22,0.99)");
  ctx.beginPath();
  ctx.arc(cx, cy, R, 0, Math.PI * 2);
  ctx.fillStyle = base;
  ctx.fill();

  // ── 2. Pulsing breathing radial glow behind logo ─────────────────────────────
  const pulse = 0.5 + 0.5 * Math.sin(t * 1.2);
  const ba    = 0.18 + 0.14 * pulse;
  ctx.save();
  ctx.beginPath();
  ctx.arc(cx, cy, R, 0, Math.PI * 2);
  ctx.clip();
  const breathe = ctx.createRadialGradient(cx, cy, 0, cx, cy, R * (0.55 + 0.15 * pulse));
  breathe.addColorStop(0,    `rgba(60,140,255,${ba.toFixed(3)})`);
  breathe.addColorStop(0.55, `rgba(30,80,220,${(ba * 0.4).toFixed(3)})`);
  breathe.addColorStop(1,    "rgba(10,40,160,0)");
  ctx.fillStyle = breathe;
  ctx.fillRect(cx - R, cy - R, R * 2, R * 2);
  ctx.restore();

  // ── 3. Background star field ─────────────────────────────────────────────────
  for (const [nx, ny, ph] of STARS) {
    const sx = cx + nx * R, sy = cy + ny * R;
    const tw = 0.3 + 0.7 * Math.abs(Math.sin(t * 1.8 + ph));
    const sg = ctx.createRadialGradient(sx, sy, 0, sx, sy, R * 0.018);
    sg.addColorStop(0, `rgba(200,230,255,${tw.toFixed(3)})`);
    sg.addColorStop(1, "rgba(100,160,255,0)");
    ctx.fillStyle = sg;
    ctx.beginPath();
    ctx.arc(sx, sy, R * 0.018, 0, Math.PI * 2);
    ctx.fill();
  }

  // ── 4. Logo — white bg → invisible; constellation lines → bright blue-white ──
  if (logoImg?.complete && logoImg.naturalWidth > 0) {
    ctx.save();
    ctx.beginPath();
    ctx.arc(cx, cy, R * 0.92, 0, Math.PI * 2);
    ctx.clip();
    ctx.filter = "invert(1) brightness(5) contrast(2)";
    ctx.globalAlpha = 0.92;
    const s = R * 1.85;
    ctx.drawImage(logoImg, cx - s / 2, cy - s / 2, s, s);
    ctx.filter = "none";
    ctx.globalAlpha = 1;
    ctx.restore();
  }

  // ── 5. Node sparkles — independently twinkling at each constellation node ────
  const SPD = [2.1, 1.7, 2.5, 1.9, 2.3, 1.5, 2.7];
  const PHS = [0.0, 1.2, 2.4, 3.6, 0.8, 2.0, 3.2];
  for (let i = 0; i < pts.length; i++) {
    const [px, py] = pts[i];
    const glow = 0.4 + 0.6 * Math.abs(Math.sin(t * SPD[i] + PHS[i]));
    // Outer halo
    const hR = R * (0.055 + 0.035 * glow);
    const hg = ctx.createRadialGradient(px, py, 0, px, py, hR);
    hg.addColorStop(0,   `rgba(160,220,255,${(glow * 0.55).toFixed(3)})`);
    hg.addColorStop(0.5, `rgba(80,160,255,${(glow * 0.20).toFixed(3)})`);
    hg.addColorStop(1,   "rgba(40,100,255,0)");
    ctx.fillStyle = hg;
    ctx.beginPath();
    ctx.arc(px, py, hR, 0, Math.PI * 2);
    ctx.fill();
    // Bright center point
    const cg = ctx.createRadialGradient(px, py, 0, px, py, R * 0.022);
    cg.addColorStop(0, `rgba(255,255,255,${(glow * 0.95).toFixed(3)})`);
    cg.addColorStop(1, "rgba(120,190,255,0)");
    ctx.fillStyle = cg;
    ctx.beginPath();
    ctx.arc(px, py, R * 0.022, 0, Math.PI * 2);
    ctx.fill();
    // Cross sparkle arms when bright enough
    if (glow > 0.65) {
      const arm = R * 0.045 * glow;
      ctx.strokeStyle = `rgba(220,245,255,${(glow * 0.5).toFixed(3)})`;
      ctx.lineWidth = 0.8;
      ctx.beginPath(); ctx.moveTo(px - arm, py); ctx.lineTo(px + arm, py); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(px, py - arm); ctx.lineTo(px, py + arm); ctx.stroke();
    }
  }

  // ── 6. Traveling light — shooting-star dot flowing along the edge path ────────
  const lens  = EDGES.map(([a, b]) => {
    const dx = pts[b][0] - pts[a][0], dy = pts[b][1] - pts[a][1];
    return Math.sqrt(dx * dx + dy * dy);
  });
  const total = lens.reduce((s, l) => s + l, 0);
  let   pos   = (t * total / 8) % total, walked = 0;
  for (let i = 0; i < EDGES.length; i++) {
    if (pos <= walked + lens[i]) {
      const f  = (pos - walked) / lens[i];
      const [a, b] = EDGES[i];
      const lx = pts[a][0] + (pts[b][0] - pts[a][0]) * f;
      const ly = pts[a][1] + (pts[b][1] - pts[a][1]) * f;
      // Trailing glow halo
      const tg = ctx.createRadialGradient(lx, ly, 0, lx, ly, R * 0.065);
      tg.addColorStop(0,   "rgba(180,235,255,0.75)");
      tg.addColorStop(0.4, "rgba(80,180,255,0.30)");
      tg.addColorStop(1,   "rgba(30,100,200,0)");
      ctx.fillStyle = tg;
      ctx.beginPath(); ctx.arc(lx, ly, R * 0.065, 0, Math.PI * 2); ctx.fill();
      // Bright leading dot
      const dg = ctx.createRadialGradient(lx, ly, 0, lx, ly, R * 0.025);
      dg.addColorStop(0, "rgba(255,255,255,0.95)");
      dg.addColorStop(1, "rgba(100,200,255,0)");
      ctx.fillStyle = dg;
      ctx.beginPath(); ctx.arc(lx, ly, R * 0.025, 0, Math.PI * 2); ctx.fill();
      break;
    }
    walked += lens[i];
  }
}

// ── component ─────────────────────────────────────────────────────────────────

export default function MetisOrb() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rafRef = useRef<number>(0);
  const startRef = useRef<number>(0);
  const logoImgRef = useRef<HTMLImageElement | null>(null);

  useEffect(() => {
    const img = new Image();
    img.src = "/metis-logo.png";
    img.onload = () => { logoImgRef.current = img; };
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const size = 72;
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    canvas.style.width = `${size}px`;
    canvas.style.height = `${size}px`;
    ctx.scale(dpr, dpr);

    const animate = (ts: number) => {
      if (!startRef.current) startRef.current = ts;
      const t = (ts - startRef.current) / 1000;
      ctx.clearRect(0, 0, size, size);
      drawOrbAt(ctx, size / 2, size / 2, size * 0.455, t, logoImgRef.current);
      rafRef.current = requestAnimationFrame(animate);
    };

    rafRef.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(rafRef.current);
  }, []);

  return (
    <canvas
      ref={canvasRef}
      style={{ display: "block", borderRadius: "50%" }}
      aria-hidden="true"
    />
  );
}
