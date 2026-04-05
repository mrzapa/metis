// ═══════════════════════════════════════════════════════════════════════════════
// PHASE 4: Galaxy Integration — The galaxy IS the stars
// ═══════════════════════════════════════════════════════════════════════════════
//
// Replace the painted galaxy canvas overlay with the actual catalogue stars.
// At extreme zoom-out, star point sizes compress so thousands of stars
// naturally form the spiral arm structure.

// ──────────────────────────────────────────────────────────────────────────────
// STEP 4.1: Modify the WebGL vertex shader to scale stars with zoom
// ──────────────────────────────────────────────────────────────────────────────

// In landing-starfield-webgl.tsx, ADD a new uniform `uZoomScale` to the vertex shader.
// This lets stars shrink at low zoom (galaxy view) and grow at high zoom (close view).

export const UPDATED_VERTEX_SHADER = `
attribute vec4 aColorA;
attribute vec4 aColorB;
attribute vec4 aColorC;
attribute vec4 aShape;
attribute vec2 aTwinkle;

uniform float uDpr;
uniform float uTime;
uniform float uZoomScale;  // NEW: 0.0 = galaxy view, 1.0 = normal view

varying float vAddable;
varying float vBloom;
varying float vBrightness;
varying float vCoreRadius;
varying float vDiffraction;
varying float vTier;
varying float vTwinkle;
varying vec3 vAccentColor;
varying vec3 vCoreColor;
varying vec3 vHaloColor;

void main() {
  vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
  gl_Position = projectionMatrix * mvPosition;

  float twinkle = 0.92 + sin(uTime * aTwinkle.y + aTwinkle.x) * 0.08;
  float tierBoost = aShape.w > 1.5 ? 1.45 : (aShape.w > 0.5 ? 1.18 : 1.0);
  float heroGlow = aShape.w > 1.5 ? 1.0 + aColorC.w * 0.32 : 1.0;

  // Galaxy zoom scaling: at extreme zoom-out, compress all stars to tiny points
  // so they form the galaxy structure visually
  float zoomSizeScale = mix(0.15, 1.0, smoothstep(0.0, 0.4, uZoomScale));

  gl_PointSize = max(0.5, aShape.z * uDpr * tierBoost * heroGlow * twinkle * zoomSizeScale);

  vAddable = aColorA.w;
  vBloom = aColorC.w;
  vBrightness = aColorB.w;
  vCoreRadius = aShape.x;
  vDiffraction = aShape.y;
  vTier = aShape.w;
  vTwinkle = twinkle;
  vAccentColor = aColorA.rgb;
  vCoreColor = aColorB.rgb;
  vHaloColor = aColorC.rgb;
}
`;

// ──────────────────────────────────────────────────────────────────────────────
// STEP 4.2: Update the LandingStarfieldWebgl component to accept zoomScale
// ──────────────────────────────────────────────────────────────────────────────

// MODIFY the LandingStarfieldFrame interface in landing-starfield-webgl.types.ts:
/*
export interface LandingStarfieldFrame {
  height: number;
  revision: number;
  stars: LandingWebglStar[];
  width: number;
  zoomScale: number;  // NEW: normalized 0→1 representing zoom level
}
*/

// MODIFY the render function in landing-starfield-webgl.tsx:
/*
// Add the uniform:
uniforms: {
  uDpr: { value: 1 },
  uTime: { value: 0 },
  uZoomScale: { value: 1.0 },  // NEW
},

// In the render loop, update it:
const zoomScale = Math.min(1, Math.max(0, frame.zoomScale ?? 1.0));
material.uniforms.uZoomScale.value = zoomScale;
*/

// ──────────────────────────────────────────────────────────────────────────────
// STEP 4.3: Feed zoomScale from page.tsx
// ──────────────────────────────────────────────────────────────────────────────

// MODIFY the frame ref update in page.tsx (around line 2730):
/*
// Normalize zoom factor to 0→1 range for the shader
// 0.002 (galaxy) → 0.0, 1.0 (default) → 0.5, 2000 (star dive) → 1.0
const zoomNorm = Math.min(1, Math.max(0,
  (Math.log(backgroundCamera.zoomFactor) - Math.log(0.002)) /
  (Math.log(2000) - Math.log(0.002))
));

landingStarfieldFrameRef.current = {
  height: H,
  revision: landingStarfieldFrameRef.current.revision + 1,
  stars: nextWebglStars,
  width: W,
  zoomScale: zoomNorm,  // NEW
};
*/

// ──────────────────────────────────────────────────────────────────────────────
// STEP 4.4: Remove the painted galaxy overlay
// ──────────────────────────────────────────────────────────────────────────────

// REMOVE or COMMENT OUT:
// 1. The `galaxyCanvas` creation and its 3-layer painting code
//    (the off-screen canvas that draws the radial core glow, fBm cloud arms, star field)
// 2. The `drawGalaxy()` function (lines 2213-2221)
// 3. The `drawGalaxy()` call in the render loop (line 3866)
//
// KEEP: A subtle CSS vignette or radial gradient on the background for atmosphere.

// ──────────────────────────────────────────────────────────────────────────────
// STEP 4.5: Add a soft nebula glow behind dense star regions (optional polish)
// ──────────────────────────────────────────────────────────────────────────────

// For atmosphere, add a subtle background radial gradient that simulates
// the galactic core glow. This goes on the 2D canvas layer:
/*
function drawGalacticCoreGlow(backgroundCamera: BackgroundCameraState) {
  const zoomFactor = backgroundCamera.zoomFactor;
  // Only show at galaxy-view zoom levels
  const glowAlpha = 1 - smoothstep(0.002, 0.15, zoomFactor);
  if (glowAlpha <= 0) return;

  const scale = getBackgroundCameraScale(zoomFactor);
  // Galaxy centre is at world (0, 0) — project to screen
  const cx = (0 - backgroundCamera.x) * scale + W / 2;
  const cy = (0 - backgroundCamera.y) * scale + H / 2;
  const radius = Math.max(W, H) * 0.4 * scale;

  ctx!.save();
  ctx!.globalAlpha = glowAlpha * 0.18;
  const glow = ctx!.createRadialGradient(cx, cy, 0, cx, cy, radius);
  glow.addColorStop(0, "rgba(200, 170, 120, 0.3)");
  glow.addColorStop(0.3, "rgba(140, 150, 180, 0.12)");
  glow.addColorStop(1, "rgba(0, 0, 0, 0)");
  ctx!.fillStyle = glow;
  ctx!.fillRect(0, 0, W, H);
  ctx!.restore();
}
*/

export {};
