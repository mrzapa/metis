/**
 * constellation-comets.ts — Comet rendering logic for the landing page canvas.
 *
 * Extracted from page.tsx to keep the render loop manageable.
 * All coordinates are screen-space pixels (like dust particles).
 */

import type { CometData, CometEvent, CometPhase } from "@/lib/comet-types";

const TAIL_MAX_LENGTH = 20;
const ENTER_DURATION_MS = 1200;
const DRIFT_SPEED = 0.35;
const APPROACH_SPEED = 1.8;
const ABSORB_DURATION_MS = 800;
const FADE_DURATION_MS = 600;
const COMET_HEAD_RADIUS = 3.5;

/**
 * Convert a CometEvent from the server into a CometData for canvas rendering.
 */
export function makeCometData(
  event: CometEvent,
  canvasW: number,
  canvasH: number,
  facultyColor: [number, number, number],
  targetX: number,
  targetY: number,
): CometData {
  // Spawn from a random edge of the canvas
  const edge = Math.random();
  let x: number, y: number, vx: number, vy: number;
  if (edge < 0.25) {
    // top
    x = Math.random() * canvasW;
    y = -20;
    vx = (Math.random() - 0.5) * DRIFT_SPEED;
    vy = DRIFT_SPEED;
  } else if (edge < 0.5) {
    // right
    x = canvasW + 20;
    y = Math.random() * canvasH;
    vx = -DRIFT_SPEED;
    vy = (Math.random() - 0.5) * DRIFT_SPEED;
  } else if (edge < 0.75) {
    // bottom
    x = Math.random() * canvasW;
    y = canvasH + 20;
    vx = (Math.random() - 0.5) * DRIFT_SPEED;
    vy = -DRIFT_SPEED;
  } else {
    // left
    x = -20;
    y = Math.random() * canvasH;
    vx = DRIFT_SPEED;
    vy = (Math.random() - 0.5) * DRIFT_SPEED;
  }

  return {
    comet_id: event.comet_id,
    x,
    y,
    vx,
    vy,
    tailHistory: [],
    color: facultyColor,
    facultyId: event.faculty_id,
    targetX,
    targetY,
    phase: "entering",
    phaseStartedAt: performance.now(),
    size: COMET_HEAD_RADIUS,
    opacity: 0,
    title: event.news_item.title,
    summary: event.news_item.summary,
    url: event.news_item.url,
    decision: event.decision,
    relevanceScore: event.relevance_score,
  };
}

/**
 * Advance one comet by one frame. Mutates in place and returns true if it
 * should be removed (phase = absorbed or fully faded).
 */
export function tickComet(comet: CometData, ts: number): boolean {
  const elapsed = ts - comet.phaseStartedAt;

  // Record tail
  comet.tailHistory.push({ x: comet.x, y: comet.y });
  if (comet.tailHistory.length > TAIL_MAX_LENGTH) {
    comet.tailHistory.shift();
  }

  switch (comet.phase) {
    case "entering": {
      // Fade in while drifting in from edge
      const t = Math.min(1, elapsed / ENTER_DURATION_MS);
      comet.opacity = t;
      comet.x += comet.vx;
      comet.y += comet.vy;
      if (t >= 1) {
        transitionPhase(comet, comet.decision === "drift" ? "drifting" : "approaching", ts);
      }
      break;
    }

    case "drifting": {
      comet.opacity = Math.max(0.3, comet.opacity - 0.0003);
      comet.x += comet.vx;
      comet.y += comet.vy;
      // Fade out after 30 seconds of drifting
      if (elapsed > 30_000) {
        transitionPhase(comet, "fading", ts);
      }
      break;
    }

    case "approaching": {
      // Move toward target faculty position
      const dx = comet.targetX - comet.x;
      const dy = comet.targetY - comet.y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist > 5) {
        const speed = Math.min(APPROACH_SPEED, dist * 0.02);
        comet.vx = (dx / dist) * speed;
        comet.vy = (dy / dist) * speed;
        comet.x += comet.vx;
        comet.y += comet.vy;
      } else if (comet.decision === "absorb") {
        transitionPhase(comet, "absorbing", ts);
      } else {
        // Approach-only: orbit near the faculty briefly then fade
        comet.vx = -dy * 0.003;
        comet.vy = dx * 0.003;
        comet.x += comet.vx;
        comet.y += comet.vy;
        if (elapsed > 12_000) {
          transitionPhase(comet, "fading", ts);
        }
      }
      comet.opacity = Math.min(1, comet.opacity + 0.01);
      break;
    }

    case "absorbing": {
      // Lerp to exact target and shrink
      const t = Math.min(1, elapsed / ABSORB_DURATION_MS);
      const eased = 1 - Math.pow(1 - t, 3); // ease-out cubic
      comet.x = comet.x + (comet.targetX - comet.x) * eased * 0.15;
      comet.y = comet.y + (comet.targetY - comet.y) * eased * 0.15;
      comet.size = COMET_HEAD_RADIUS * (1 - eased * 0.5);
      comet.opacity = 1;
      if (t >= 1) {
        transitionPhase(comet, "absorbed", ts);
      }
      break;
    }

    case "fading": {
      const t = Math.min(1, elapsed / FADE_DURATION_MS);
      comet.opacity = Math.max(0, 1 - t);
      comet.x += comet.vx * 0.5;
      comet.y += comet.vy * 0.5;
      if (t >= 1) return true; // remove
      break;
    }

    case "absorbed":
      return true; // remove

    case "dismissed": {
      transitionPhase(comet, "fading", ts);
      break;
    }
  }

  return false;
}

function transitionPhase(comet: CometData, phase: CometPhase, ts: number): void {
  comet.phase = phase;
  comet.phaseStartedAt = ts;
}

/**
 * Draw all comets onto the 2D canvas context.
 */
export function drawComets(
  ctx: CanvasRenderingContext2D,
  comets: CometData[],
  ts: number,
): void {
  for (const comet of comets) {
    if (comet.opacity <= 0) continue;

    const [r, g, b] = comet.color;
    const alpha = comet.opacity;

    // --- Tail ---
    if (comet.tailHistory.length > 1) {
      const tail = comet.tailHistory;
      ctx.beginPath();
      ctx.moveTo(tail[0].x, tail[0].y);
      for (let i = 1; i < tail.length; i++) {
        ctx.lineTo(tail[i].x, tail[i].y);
      }
      ctx.lineTo(comet.x, comet.y);

      const tailGrad = ctx.createLinearGradient(
        tail[0].x,
        tail[0].y,
        comet.x,
        comet.y,
      );
      tailGrad.addColorStop(0, `rgba(${r},${g},${b},0)`);
      tailGrad.addColorStop(1, `rgba(${r},${g},${b},${alpha * 0.6})`);
      ctx.strokeStyle = tailGrad;
      ctx.lineWidth = comet.size * 0.8;
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      ctx.stroke();
    }

    // --- Glow ---
    const glowRadius = comet.size * 4;
    const glow = ctx.createRadialGradient(comet.x, comet.y, 0, comet.x, comet.y, glowRadius);
    glow.addColorStop(0, `rgba(${r},${g},${b},${alpha * 0.35})`);
    glow.addColorStop(0.5, `rgba(${r},${g},${b},${alpha * 0.1})`);
    glow.addColorStop(1, `rgba(${r},${g},${b},0)`);
    ctx.beginPath();
    ctx.arc(comet.x, comet.y, glowRadius, 0, Math.PI * 2);
    ctx.fillStyle = glow;
    ctx.fill();

    // --- Head ---
    ctx.beginPath();
    ctx.arc(comet.x, comet.y, comet.size, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(${r},${g},${b},${alpha})`;
    ctx.fill();

    // White core
    ctx.beginPath();
    ctx.arc(comet.x, comet.y, comet.size * 0.4, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(255,255,255,${alpha * 0.9})`;
    ctx.fill();
  }
}

/**
 * Draw a "tendril" line from Polaris core to an approaching/absorbing comet.
 */
export function drawPolarisTendril(
  ctx: CanvasRenderingContext2D,
  polarisX: number,
  polarisY: number,
  comet: CometData,
  ts: number,
): void {
  if (comet.phase !== "approaching" && comet.phase !== "absorbing") return;
  if (comet.opacity <= 0) return;

  const elapsed = ts - comet.phaseStartedAt;
  const [r, g, b] = comet.color;

  // Trace animation: line extends over 600ms
  const traceT = Math.min(1, elapsed / 600);
  const alpha = comet.opacity * 0.4 * traceT;

  // Bezier control point (perpendicular offset for curve)
  const mx = (polarisX + comet.x) / 2;
  const my = (polarisY + comet.y) / 2;
  const dx = comet.x - polarisX;
  const dy = comet.y - polarisY;
  const cpx = mx - dy * 0.15;
  const cpy = my + dx * 0.15;

  // Animated endpoint
  const endX = polarisX + (comet.x - polarisX) * traceT;
  const endY = polarisY + (comet.y - polarisY) * traceT;

  ctx.beginPath();
  ctx.moveTo(polarisX, polarisY);
  ctx.quadraticCurveTo(cpx, cpy, endX, endY);
  ctx.strokeStyle = `rgba(${r},${g},${b},${alpha})`;
  ctx.lineWidth = 1.2;
  ctx.setLineDash([4, 6]);
  ctx.stroke();
  ctx.setLineDash([]);
}

/**
 * Flash burst effect when a comet is absorbed at the faculty position.
 */
export function drawAbsorptionBurst(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  color: [number, number, number],
  progress: number, // 0 to 1
): void {
  if (progress >= 1) return;
  const [r, g, b] = color;
  const radius = 8 + progress * 30;
  const alpha = (1 - progress) * 0.5;

  const grad = ctx.createRadialGradient(x, y, 0, x, y, radius);
  grad.addColorStop(0, `rgba(255,255,255,${alpha})`);
  grad.addColorStop(0.3, `rgba(${r},${g},${b},${alpha * 0.7})`);
  grad.addColorStop(1, `rgba(${r},${g},${b},0)`);

  ctx.beginPath();
  ctx.arc(x, y, radius, 0, Math.PI * 2);
  ctx.fillStyle = grad;
  ctx.fill();
}
