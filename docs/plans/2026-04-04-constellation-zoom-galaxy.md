# Constellation: Zoom Direction, Star Dive Targeting, Faculty Lines, Galaxy Background

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Four coordinated enhancements to the constellation landing page: correct scroll-to-zoom direction, restrict star dive to user stars, draw faculty connection lines, and render a procedural Milky Way background at low zoom.

**Architecture:** All changes land in `apps/metis-web/app/page.tsx`. The galaxy is an offscreen canvas rendered once on init and composited as the very first draw call. Faculty lines are added inside the existing `drawUserStarEdges` closure. Star dive targeting swaps `visibleStarsRef.current` for a derived list built from `projectedUserStarRenderState`. Scroll direction is a one-line fix.

**Tech Stack:** TypeScript, React, HTML Canvas 2D API, `ImageData` for pixel-level galaxy rendering, `fBm` noise computed inline (no library needed).

**Design doc:** `docs/plans/2026-04-04-constellation-zoom-galaxy-design.md`

---

### Task 1: Revert scroll direction

**Files:**
- Modify: `apps/metis-web/app/page.tsx:4060`

**Context:** `zoomMultiplier = Math.exp(-e.deltaY * 0.0014)` — the negation inverts the scroll: scroll-down zooms OUT. The correct behaviour is scroll-down → positive deltaY → multiplier > 1 → zoomFactor increases toward 2000× (star dive). Remove the minus sign.

**Step 1: Make the change**

In `page.tsx` at line 4060, change:
```ts
const zoomMultiplier = Math.exp(-e.deltaY * 0.0014);
```
to:
```ts
const zoomMultiplier = Math.exp(e.deltaY * 0.0014);
```

**Step 2: Verify manually**

Run the dev server (`pnpm --filter metis-web dev`) and open the constellation page. Scroll down — the view should zoom in (stars grow, zoomFactor increases toward 2000). Scroll up — view zooms out (0.75×). Confirm `getStarDiveFocusStrength` activates on deep scroll-in (not scroll-out).

**Step 3: Commit**

```bash
git add apps/metis-web/app/page.tsx
git commit -m "fix: revert scroll direction — scroll-down zooms in toward 2000x"
```

---

### Task 2: Star dive targets user stars only

**Files:**
- Modify: `apps/metis-web/app/page.tsx:3298`

**Context:** `findStarDiveFocusTarget` is generic: `<T extends {id, screenX, screenY, brightness}>`. Currently called with `visibleStarsRef.current` (background field stars). We replace this with a list derived from `userStarsRef.current` × `projectedUserStarRenderState` (the per-frame Map of user star screen positions). If no user stars are near centre, `findStarDiveFocusTarget` returns `null` and star dive stays dormant.

`projectedUserStarRenderState` has type `Map<string, ProjectedUserStarRenderState>` where each entry has:
- `.target.x`, `.target.y` — screen-space position (CSS pixels)
- `star.size` — radius proxy used as brightness

**Step 1: Replace the target call**

Find the block at ~line 3297–3298:
```ts
if (!starDiveFocusedStarIdRef.current) {
  const target = findStarDiveFocusTarget(visibleStarsRef.current, W, H);
```

Replace with:
```ts
if (!starDiveFocusedStarIdRef.current) {
  const userStarTargets = userStarsRef.current.flatMap((star) => {
    const proj = projectedUserStarRenderState.get(star.id);
    if (!proj) return [];
    return [{ id: star.id, screenX: proj.target.x, screenY: proj.target.y, brightness: star.size ?? 1 }];
  });
  const target = findStarDiveFocusTarget(userStarTargets, W, H);
```

**Step 2: TypeScript check**

```bash
pnpm --filter metis-web tsc --noEmit
```
Expected: no new errors.

**Step 3: Verify manually**

With a constellation that has ≥1 user star: scroll in past 200× — star dive should lock onto a user star, not a random background point. With zero user stars: scroll in — no star dive auto-lock occurs.

**Step 4: Commit**

```bash
git add apps/metis-web/app/page.tsx
git commit -m "feat: star dive targets user constellation stars only"
```

---

### Task 3: Faculty connection lines

**Files:**
- Modify: `apps/metis-web/app/page.tsx` (inside `drawUserStarEdges`, after line 2653)

**Context:** `drawUserStarEdges` iterates `currentUserStars.forEach((star) => { ... })`. Each iteration has access to:
- `from` = `projectedUserStarRenderState.get(star.id)` — already fetched at line 2614
- `star.primaryDomainId` — faculty id (matches `node.concept.faculty.id`)
- `nodes[]` — array of `NodeData`, in scope (defined at line 2105 in the same closure). After `applyNodeLayout` runs each frame, `node.x` / `node.y` hold screen-space coords.
- `getFacultyColor(facultyId)` → `[r, g, b]` 0–255

The faculty line is drawn **per star, not per edge pair**, so no dedup set is needed. Line style: dashed `[4, 6]`, 0.7px, alpha 0.22 at star end → 0.09 at hub.

**Step 1: Locate the insertion point**

The `currentUserStars.forEach` callback ends at line 2652 (`});`). The guard at line 2615 is:
```ts
if (!from || !star.connectedUserStarIds || star.connectedUserStarIds.length === 0) {
  return;
}
```

This early-return skips stars with no connections — but we want faculty lines drawn even for disconnected stars. The faculty line block must go **before** this early-return, or the early-return guard must be adjusted so it only skips the inter-star edge loop.

**Step 2: Restructure the guard and add faculty lines**

Replace the existing `forEach` callback body (lines 2613–2651) with:

```ts
currentUserStars.forEach((star) => {
  const from = projectedUserStarRenderState.get(star.id);

  // --- Faculty connection line (drawn even for stars with no inter-star edges) ---
  if (from && star.primaryDomainId) {
    const facultyNode = nodes.find((n) => n.concept.faculty.id === star.primaryDomainId);
    if (facultyNode) {
      const [fr, fg, fb] = getFacultyColor(star.primaryDomainId);
      const alpha = 0.22 * Math.min(1, from.fadeIn);
      const grad = ctx!.createLinearGradient(from.target.x, from.target.y, facultyNode.x, facultyNode.y);
      grad.addColorStop(0, `rgba(${fr},${fg},${fb},${alpha})`);
      grad.addColorStop(1, `rgba(${fr},${fg},${fb},${alpha * 0.4})`);
      ctx!.strokeStyle = grad;
      ctx!.lineWidth = 0.7;
      ctx!.setLineDash([4, 6]);
      ctx!.beginPath();
      ctx!.moveTo(from.target.x, from.target.y);
      ctx!.lineTo(facultyNode.x, facultyNode.y);
      ctx!.stroke();
      ctx!.setLineDash([]);
    }
  }

  // --- Inter-star edges (existing logic, unchanged) ---
  if (!from || !star.connectedUserStarIds || star.connectedUserStarIds.length === 0) {
    return;
  }

  star.connectedUserStarIds.forEach((linkedStarId) => {
    const to = projectedUserStarRenderState.get(linkedStarId);
    if (!to) {
      return;
    }

    const edgeKey = star.id < linkedStarId
      ? `${star.id}:${linkedStarId}`
      : `${linkedStarId}:${star.id}`;
    if (renderedLinks.has(edgeKey)) {
      return;
    }
    renderedLinks.add(edgeKey);

    const alphaMultiplier = Math.max(0, Math.min(1, Math.min(from.fadeIn, to.fadeIn) * edgeBreath));
    const ragHighlighted = ragPulseStrength > 0
      && (ragPulseState?.starIds.has(star.id) || ragPulseState?.starIds.has(linkedStarId));
    const selectedEdge = selectedStarId !== null
      && (star.id === selectedStarId || linkedStarId === selectedStarId);
    const ragBoost = ragHighlighted ? ragPulseStrength : 0;
    const edgeAlpha = selectedEdge ? 0.32 : ragHighlighted ? 0.21 : 0.13;
    const gradient = ctx!.createLinearGradient(from.target.x, from.target.y, to.target.x, to.target.y);
    gradient.addColorStop(0, `rgba(${from.mixed[0]},${from.mixed[1]},${from.mixed[2]},${(edgeAlpha + ragBoost * 0.34) * alphaMultiplier})`);
    gradient.addColorStop(1, `rgba(${to.mixed[0]},${to.mixed[1]},${to.mixed[2]},${(edgeAlpha + ragBoost * 0.34) * alphaMultiplier})`);
    ctx!.strokeStyle = gradient;
    ctx!.lineWidth = 0.95 + ragBoost * 1.35;
    ctx!.beginPath();
    ctx!.moveTo(from.target.x, from.target.y);
    ctx!.lineTo(to.target.x, to.target.y);
    ctx!.stroke();
  });
});
```

**Step 3: TypeScript check**

```bash
pnpm --filter metis-web tsc --noEmit
```
Expected: no new errors.

**Step 4: Verify manually**

Add a star to your constellation with a faculty domain set. At normal zoom (1–2×), a thin dashed line in the faculty colour should run from the user star toward its faculty hub node. The line should fade in with `fadeIn` (not pop in). Inter-star solid edges are unchanged.

**Step 5: Commit**

```bash
git add apps/metis-web/app/page.tsx
git commit -m "feat: draw dashed faculty connection lines from user stars to hub nodes"
```

---

### Task 4: Procedural galaxy background

**Files:**
- Modify: `apps/metis-web/app/page.tsx` (two insertion points)

**Context:** A `smoothstep` helper and an offscreen canvas (`galaxyCanvas`) are created once during canvas init (alongside the `nebulae` array at line 2025). Each render frame, if `galaxyAlpha > 0`, the offscreen canvas is `drawImage`-composited as the very first draw call (before `drawNebulae`).

The galaxy does not move with the camera — it fills the canvas in screen space.

**`smoothstep` helper** (standard GLSL-style):
```ts
function smoothstep(edge0: number, edge1: number, x: number): number {
  const t = Math.max(0, Math.min(1, (x - edge0) / (edge1 - edge0)));
  return t * t * (3 - 2 * t);
}
```

**fBm 4-octave noise** (value noise, no external library):
```ts
function hash2(ix: number, iy: number): number {
  const n = ix * 127 + iy * 311;
  return (Math.sin(n) * 43758.5453) % 1;
}

function valueNoise(x: number, y: number): number {
  const ix = Math.floor(x), iy = Math.floor(y);
  const fx = x - ix, fy = y - iy;
  const ux = fx * fx * (3 - 2 * fx), uy = fy * fy * (3 - 2 * fy);
  const a = Math.abs(hash2(ix, iy));
  const b = Math.abs(hash2(ix + 1, iy));
  const c = Math.abs(hash2(ix, iy + 1));
  const d = Math.abs(hash2(ix + 1, iy + 1));
  return a + (b - a) * ux + (c - a) * uy + (d - a + a - b - c + b + c - d) * ux * uy;
}

function fbm4(x: number, y: number): number {
  return (
    valueNoise(x,       y      ) * 0.5   +
    valueNoise(x * 2,   y * 2  ) * 0.25  +
    valueNoise(x * 4,   y * 4  ) * 0.125 +
    valueNoise(x * 8,   y * 8  ) * 0.0625
  );
}
```

**Galaxy render function:**
```ts
function renderGalaxyToCanvas(offscreen: HTMLCanvasElement, W: number, H: number) {
  const gc = offscreen.getContext('2d')!;
  const dpr = window.devicePixelRatio || 1;
  const pw = Math.round(W * dpr);
  const ph = Math.round(H * dpr);
  offscreen.width  = pw;
  offscreen.height = ph;

  const imageData = gc.createImageData(pw, ph);
  const data = imageData.data;

  const cos25 = Math.cos(25 * Math.PI / 180);
  const sin25 = Math.sin(25 * Math.PI / 180);
  const stride = 3; // sample every 3rd pixel for performance

  for (let py = 0; py < ph; py += stride) {
    for (let px = 0; px < pw; px += stride) {
      const nx = (px / pw - 0.5) * 4;
      const ny = (py / ph - 0.5) * 4;

      // Rotate into tilted band space (25° tilt)
      const by = -nx * sin25 + ny * cos25;

      // Band density — Gaussian falloff perpendicular to band axis
      const band = Math.exp(-(by * by) / 0.18);

      // 4-octave fBm cloud texture
      const noise = fbm4(nx * 3, ny * 3);

      const density = band * (0.4 + noise * 0.6);

      // Colour: deep blue-indigo → dark violet, scaled by density
      const rBase = 8  + (18 - 8)  * noise;
      const gBase = 10 + (12 - 10) * noise;
      const bBase = 28 + (42 - 28) * noise;

      const r = Math.round(rBase * density);
      const g = Math.round(gBase * density);
      const b = Math.round(bBase * density);
      const a = Math.round(density * 200); // max alpha ~200/255

      // Fill a stride×stride block
      for (let dy = 0; dy < stride && py + dy < ph; dy++) {
        for (let dx = 0; dx < stride && px + dx < pw; dx++) {
          const idx = ((py + dy) * pw + (px + dx)) * 4;
          data[idx    ] = r;
          data[idx + 1] = g;
          data[idx + 2] = b;
          data[idx + 3] = a;
        }
      }
    }
  }

  gc.putImageData(imageData, 0, 0);

  // Pass 2: light blur for smooth density gradients
  gc.filter = 'blur(4px)';
  gc.drawImage(offscreen, 0, 0);
  gc.filter = 'none';

  // Pass 3: scattered point stars
  const seed = 0.618;
  for (let py = 0; py < ph; py += 2) {
    for (let px = 0; px < pw; px += 2) {
      const nx = (px / pw - 0.5) * 4;
      const ny = (py / ph - 0.5) * 4;
      const by = -nx * sin25 + ny * cos25;
      const band = Math.exp(-(by * by) / 0.18);
      const noise = fbm4(nx * 3 + seed, ny * 3 + seed);
      const density = band * (0.4 + noise * 0.6);
      const h = Math.abs(hash2(px, py));
      if (h < density * 0.06) {
        gc.fillStyle = `rgba(200,210,255,${density * 0.85})`;
        gc.fillRect(px / dpr, py / dpr, 1 / dpr, 1 / dpr);
      }
    }
  }
}
```

**Step 1: Add helpers and galaxy init after the `nebulae` array**

After line 2030 (`};`), insert the `smoothstep`, `hash2`, `valueNoise`, `fbm4`, and `renderGalaxyToCanvas` functions, then create and render the offscreen canvas:

```ts
// Galaxy offscreen canvas (rendered once, re-rendered on resize)
const galaxyCanvas = document.createElement('canvas');
renderGalaxyToCanvas(galaxyCanvas, W, H);
```

**Step 2: Add `drawGalaxy` function**

After `renderGalaxyToCanvas` and the galaxy canvas creation, add:

```ts
function drawGalaxy() {
  const zoomFactor = backgroundZoomRef.current;
  // Fade: fully visible at 0.75×, zero at 1.5×
  const galaxyAlpha = 1 - smoothstep(0.75, 1.5, zoomFactor);
  if (galaxyAlpha <= 0) return;
  ctx!.save();
  ctx!.globalAlpha = galaxyAlpha;
  ctx!.drawImage(galaxyCanvas, 0, 0, W, H);
  ctx!.restore();
}
```

**Step 3: Call `drawGalaxy()` first in the render loop**

In the render loop (around line 3415), currently:
```ts
drawNebulae();
drawDust();
```

Change to:
```ts
drawGalaxy();
drawNebulae();
drawDust();
```

**Step 4: Re-render galaxy on canvas resize**

Find where the canvas is resized when window dimensions change (search for `canvas.width = ` or the resize handler). After updating `W` and `H`, add:
```ts
renderGalaxyToCanvas(galaxyCanvas, W, H);
```

To find the resize location:
```bash
grep -n "canvas.width\s*=" apps/metis-web/app/page.tsx | head -5
```

**Step 5: TypeScript check**

```bash
pnpm --filter metis-web tsc --noEmit
```
Expected: no new errors.

**Step 6: Verify manually**

Zoom out to minimum (0.75×). A dark blue-indigo Milky Way band should be visible, filling the canvas, tilted ~25°, with faint cloud texture and scattered point stars. Zoom in past 1.5× — the galaxy should fade cleanly to invisible. The nebulae and constellation nodes render on top.

**Step 7: Commit**

```bash
git add apps/metis-web/app/page.tsx
git commit -m "feat: procedural galaxy background fades in at low zoom"
```

---

## Data Flow Summary

```
scroll wheel → zoomFactor (0.75–2000)
  ↓ < 1.5×       → drawGalaxy() fades in (galaxy background visible)
  ↓ > 200×       → starDiveFocusStrength ramps 0→1
                    → findStarDiveFocusTarget(userStarTargets)  [not background stars]
                    → StarDiveOverlay renders focused user star

drawUserStarEdges:
  primaryDomainId       → dashed faculty line to hub node (new, drawn first)
  connectedUserStarIds  → solid gradient inter-star edges (existing, unchanged)
```

## Files Changed

| File | Tasks |
|------|-------|
| `apps/metis-web/app/page.tsx` | All 4 tasks |
