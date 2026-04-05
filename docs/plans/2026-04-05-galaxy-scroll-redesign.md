# Galaxy Redesign + Scroll Direction Fix

**Date:** 2026-04-05
**Status:** Approved

## Overview

Two coordinated changes:

1. Fix scroll direction — positive `deltaY` (scroll-down on natural scroll) zooms in toward stars
2. Replace the procedural galaxy background with a dramatic three-layer composited galaxy where the constellation nucleus sits at the brightest centre

---

## 1. Scroll Direction Fix

**File:** `apps/metis-web/app/page.tsx`

The current code uses `Math.exp(-e.deltaY * 0.0014)`. On the user's device, scroll-down produces positive `deltaY`. We want scroll-down = zoom in toward stars. So positive deltaY must produce multiplier > 1, which means no negation:

```ts
// CORRECT — scroll-down (positive deltaY) zooms in
const zoomMultiplier = Math.exp(e.deltaY * 0.0014);
```

This is the form WITHOUT the minus sign.

---

## 2. Galaxy Redesign

**File:** `apps/metis-web/app/page.tsx` — replace `renderGalaxyToCanvas` entirely.

**Fade range:** `galaxyAlpha = 1 - smoothstep(0.75, 2.5, zoomFactor)` — extended upper bound from 1.5× to 2.5× so the galaxy lingers as you dive into the nucleus.

**Three-pass render (all into the same offscreen canvas, rendered once at init + resize):**

### Pass 1 — Radial core glow

Draw a `radialGradient` centred at canvas midpoint (physical pixels):

```
centre:     rgba(200, 180, 255, 0.6)
at 20% r:   rgba(80,  40,  180, 0.25)
at 50% r:   rgba(20,  10,   60, 0.1)
at 100% r:  rgba(0,    0,    0, 0)
```

Radius = `min(pw, ph) * 0.55`. Use `gc.fillRect` over full canvas after setting fillStyle to the gradient.

### Pass 2 — fBm cloud arms (ImageData pixel pass)

Stride-2 pixel sampling. Two-lobe density field: instead of a single tilted band, compute density as the sum of two Gaussian lobes offset from centre in opposite directions (120° apart), each with its own fBm modulation:

```
For each pixel (px, py):
  nx = (px/pw - 0.5) * 3   // normalised ±1.5
  ny = (py/ph - 0.5) * 3

  // Radial falloff from centre (nucleus always bright)
  r = sqrt(nx² + ny²)
  coreDensity = exp(-r² / 0.15)

  // Two spiral arm lobes
  angle = atan2(ny, nx)
  lobe1 = exp(-((angle - 0.4)² + r²*0.3) / 0.4)
  lobe2 = exp(-((angle - 0.4 - π)² + r²*0.3) / 0.4)
  armDensity = (lobe1 + lobe2) * 0.6

  noise = fbm4(nx*2.5, ny*2.5)
  density = clamp(coreDensity + armDensity) * (0.35 + noise * 0.65)

  // Colour: deep violet → lavender, driven by noise + proximity to core
  r_col = 15 + 75 * noise + 110 * coreDensity
  g_col = 8  + 52 * noise +  70 * coreDensity
  b_col = 45 + 135 * noise + 100 * coreDensity

  alpha = density * 180   // max ~180/255
```

Apply `blur(6px)` after `putImageData` (using a temp canvas, not self-compositing).

### Pass 3 — Three-tier procedural star field

Sample every other pixel from the density map. For each sample, draw into `gc` based on thresholds derived from `density` and a `hash2(px,py)` value:

| Tier | Size | Colour | Threshold |
|------|------|--------|-----------|
| Large bright | 1.5px radius filled circle | `rgba(230,220,255, density*0.95)` | `h < density * 0.003` |
| Medium | 1px square | `rgba(180,160,255, density*0.85)` | `h < density * 0.025` |
| Tiny dim | 1px square | `rgba(140,120,220, density*0.55)` | `h < density * 0.10` |

All coordinates in physical pixels (`gc.fillRect(px, py, 1, 1)` / `gc.arc(px, py, 1.5, 0, Math.PI*2)`).

---

## Fade Behaviour

```
zoomFactor  galaxyAlpha
0.75×       1.0   (full galaxy, constellation is tiny nucleus)
1.5×        0.5   (fading, constellation expanding)
2.5×        0.0   (constellation fills view, galaxy gone)
```

---

## Files Changed

| File | Change |
|------|--------|
| `apps/metis-web/app/page.tsx` | Scroll direction (1 line), replace `renderGalaxyToCanvas`, update `smoothstep` fade range |
