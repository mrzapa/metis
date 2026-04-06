// Shared WebGL2 procedural star shader.
// Used by: star-observatory-dialog.tsx, star-dive-overlay.tsx

export const STAR_VERT = `#version 300 es
precision highp float;
in vec2 a_pos;
out vec2 v_uv;
void main(){
  v_uv = a_pos * 0.5 + 0.5;
  gl_Position = vec4(a_pos, 0.0, 1.0);
}` as const;

export const STAR_FRAG = `#version 300 es
precision highp float;

in vec2 v_uv;
out vec4 fragColor;

uniform float u_time;
uniform float u_seed;
uniform vec3  u_color;
uniform vec3  u_color2;
uniform vec3  u_color3;
uniform float u_hasColor2;
uniform float u_hasColor3;
uniform float u_hasDiffraction;
uniform float u_stage;        // 0 seed, 1 growing, 2 integrated
uniform vec2  u_res;          // physical pixel resolution

/* ── hash ───────────────────────────────────────────────────────────── */
float hash(vec2 p){
  vec3 p3 = fract(vec3(p.xyx) * vec3(0.1031, 0.1030, 0.0973));
  p3 += dot(p3, p3.yzx + 33.33);
  return fract((p3.x + p3.y) * p3.z);
}
vec2 hash2(vec2 p){
  return vec2(hash(p), hash(p + 127.1));
}
vec3 hash3(vec2 p){
  return vec3(hash(p), hash(p + 127.1), hash(p + 269.5));
}

/* ── value noise (quintic interp for smoothness) ────────────────────── */
float vnoise(vec2 p){
  vec2 i = floor(p), f = fract(p);
  vec2 u = f*f*f*(f*(f*6.0-15.0)+10.0);   // quintic Hermite
  float a = hash(i);
  float b = hash(i + vec2(1,0));
  float c = hash(i + vec2(0,1));
  float d = hash(i + vec2(1,1));
  return mix(mix(a,b,u.x), mix(c,d,u.x), u.y);
}

/* ── fbm — up to 8 octaves for HD detail ─────────────────────────── */
float fbm(vec2 p, int oct){
  float v = 0.0, a = 0.5, tot = 0.0;
  mat2 rot = mat2(0.8,-0.6,0.6,0.8);
  for(int i=0; i<8; i++){
    if(i >= oct) break;
    v += a * vnoise(p);
    tot += a;
    p = rot * p * 2.03;
    a *= 0.49;
  }
  return v / tot;
}

/* ── domain-warped FBM for turbulent plasma ─────────────────────────── */
float warpedFbm(vec2 p, float t, int oct){
  // Two-pass domain warping for organic turbulent flow
  vec2 q = vec2(fbm(p + vec2(0.0, 0.0) + t * 0.03, oct),
                fbm(p + vec2(5.2, 1.3) - t * 0.02, oct));
  vec2 r = vec2(fbm(p + 4.0 * q + vec2(1.7, 9.2) + t * 0.015, oct),
                fbm(p + 4.0 * q + vec2(8.3, 2.8) - t * 0.01, oct));
  return fbm(p + 3.5 * r, oct);
}

/* ── Worley (F1) with animated jitter ───────────────────────────────── */
float worley(vec2 p, float jitter){
  vec2 i = floor(p), f = fract(p);
  float md = 1.0;
  for(int y=-1; y<=1; y++){
    for(int x=-1; x<=1; x++){
      vec2 nb = vec2(float(x), float(y));
      vec2 pt = hash2(i + nb + u_seed * 13.7) * jitter;
      float d = length(nb + pt - f);
      md = min(md, d);
    }
  }
  return md;
}

/* ── Worley F1-F2 for cell walls ────────────────────────────────────── */
vec2 worley2(vec2 p, float jitter){
  vec2 i = floor(p), f = fract(p);
  float f1 = 1.0, f2 = 1.0;
  for(int y=-1; y<=1; y++){
    for(int x=-1; x<=1; x++){
      vec2 nb = vec2(float(x), float(y));
      vec2 pt = hash2(i + nb + u_seed * 13.7) * jitter;
      float d = length(nb + pt - f);
      if(d < f1){ f2 = f1; f1 = d; }
      else if(d < f2){ f2 = d; }
    }
  }
  return vec2(f1, f2);
}

/* ── HD granulation with cell walls ─────────────────────────────────── */
float granulation(vec2 p, float t){
  // Large convection cells (supergranulation)
  vec2 w0 = worley2(p * 8.0 + t * 0.02, 0.94);
  float superGran = smoothstep(0.0, 0.12, w0.y - w0.x);  // cell wall darkening

  // Main granulation cells
  vec2 w1 = worley2(p * 22.0 + t * 0.06, 0.92);
  float gran1 = w1.x;                                      // bright cell centres
  float walls1 = smoothstep(0.0, 0.08, w1.y - w1.x);     // intergranular lanes

  // Fine sub-granulation
  vec2 w2 = worley2(p * 48.0 + t * 0.04, 0.88);
  float gran2 = w2.x;
  float walls2 = smoothstep(0.0, 0.06, w2.y - w2.x);

  // Ultra-fine texture
  float w3 = worley(p * 96.0 - t * 0.02, 0.85);

  // Combine: bright granule centres with clearly dark lanes
  float cellBrightness = gran1 * 0.45 + gran2 * 0.35 + w3 * 0.2;
  float lanesDark = walls1 * 0.6 + walls2 * 0.25 + (1.0 - superGran) * 0.15;

  return cellBrightness * (0.55 + lanesDark * 0.45);
}

/* ── plasma turbulence overlay ──────────────────────────────────────── */
float plasmaTurbulence(vec2 p, float t){
  float turb = warpedFbm(p * 5.0 + vec2(u_seed * 7.3, u_seed * 3.1), t, 7);
  float flow = warpedFbm(p * 3.0 + vec2(u_seed * 11.0, u_seed * 5.7) + t * 0.05, t, 6);
  return turb * 0.6 + flow * 0.4;
}

/* ── dither to kill banding ─────────────────────────────────────────── */
float dither(vec2 fragCoord){
  return (hash(fragCoord + fract(u_time)) - 0.5) / 255.0;
}

void main(){
  vec2 uv = v_uv * 2.0 - 1.0;
  float dist = length(uv);
  float angle = atan(uv.y, uv.x);

  vec2 starOff = vec2(u_seed * 11.3, u_seed * 7.7);
  float t = u_time * 0.9;  // fast enough to see granulation drift

  vec3 fc   = u_color / 255.0;
  vec3 hot  = vec3(1.0, 0.97, 0.92);
  vec3 warm = vec3(1.0, 0.82, 0.48);  // yellow-orange mid tone

  /* ===================================================================
     PHOTOSPHERE  (dist < ~0.44)
     High-detail realistic star surface with visible convection
     ================================================================ */

  float sphereR = 0.46;
  float rNorm   = dist / sphereR;
  float mu      = sqrt(max(0.0, 1.0 - rNorm * rNorm));

  // Steeper limb darkening for stronger 3D sphere appearance
  // Blended power law: combines slow core falloff with sharp edge
  float limb = pow(mu, 0.55) * 0.7 + pow(mu, 2.5) * 0.3;

  // ── TRUE 3D SPHERE UV WITH Y-AXIS ROTATION ──────────────────────────
  // Reconstruct normalised 3D position on the front hemisphere.
  // nz > 0 for the entire visible disc (back hemisphere is culled by bodyMask).
  float nx = uv.x / sphereR;
  float ny = uv.y / sphereR;
  float nz = sqrt(max(0.0, 1.0 - nx*nx - ny*ny));

  // Rotate around Y axis over time — slow, clearly visible spin.
  float rotAngle = u_time * 0.08 + u_seed * 6.28318;
  float cosR = cos(rotAngle);
  float sinR = sin(rotAngle);
  float rx = cosR * nx + sinR * nz;
  float rz = -sinR * nx + cosR * nz;

  // Seamless surface UV from the 3D rotated position.
  // XZ-plane projection — no atan() seam, rotation is fully smooth.
  // Pole pinch is invisible because limb darkening blacks out the poles.
  vec2 sphereUV = vec2(rx, rz) * 2.0 + starOff;

  // === GRANULATION — highly detailed convective cells ===
  float gran = granulation(sphereUV, t);

  // Modulate: bright granule centres vs dark intergranular lanes
  // Much higher contrast than before
  float granMod = 0.72 + gran * 0.56;            // range ~0.72–1.28

  // === PLASMA TURBULENCE — organic flow patterns overlaid ===
  float plasma = plasmaTurbulence(sphereUV * 0.7, t);
  // Subtle large-scale brightness variation across the surface
  float plasmaMod = 0.85 + plasma * 0.3;

  // === COLOUR GRADIENT — multi-band temperature mapping ===
  // Hot white core → warm yellow → faculty colour → dark limb
  float coreT = smoothstep(0.0, 0.7, rNorm);
  vec3 innerCol = mix(hot, warm, coreT * 0.5);
  vec3 outerCol = mix(warm, fc * 1.15, smoothstep(0.3, 0.95, rNorm));
  vec3 surfCol  = mix(innerCol, outerCol, coreT * coreT);

  // Mid-tone warm band — wider and stronger
  float midBand = exp(-pow((rNorm - 0.5) * 3.0, 2.0));
  vec3 midWarm  = mix(warm, fc, 0.35);
  surfCol = mix(surfCol, midWarm, midBand * 0.35);

  // Chromatic granulation: hot granule centres, cooler lanes
  vec3 granHot  = mix(surfCol * 1.15, hot, 0.15);
  vec3 granCool = mix(surfCol * 0.7, fc * 0.6, 0.3);
  float granBlend = smoothstep(0.3, 0.7, gran);
  vec3 granColored = mix(granCool, granHot, granBlend);

  vec3 photosphere = granColored * granMod * limb * plasmaMod;

  // === SUNSPOTS (growing + integrated) — more dramatic ===
  if(u_stage >= 1.0){
    float spotBase = warpedFbm(sphereUV * 1.5 + t * 0.01, t * 0.5, 6);
    float spotMask = smoothstep(0.58, 0.66, spotBase) * smoothstep(0.85, 0.15, rNorm);
    // Dark umbra
    photosphere *= 1.0 - spotMask * 0.65;
    // Penumbra ring — fibrous structure
    float penumbra = smoothstep(0.54, 0.58, spotBase) * smoothstep(0.66, 0.60, spotBase);
    float penFiber = fbm(vec2(angle * 12.0 + u_seed, rNorm * 20.0), 5);
    photosphere = mix(photosphere, fc * 0.35 * (0.7 + penFiber * 0.6),
                      penumbra * 0.45 * smoothstep(0.85, 0.15, rNorm));
  }

  // === FACULAE — bright patches near limb (integrated) ===
  if(u_stage >= 2.0){
    float fac = warpedFbm(sphereUV * 2.0 + t * 0.008, t * 0.3, 5);
    float facMask = smoothstep(0.52, 0.62, fac)
                  * smoothstep(0.25, 0.85, rNorm)
                  * smoothstep(1.0, 0.8, rNorm);
    photosphere += hot * facMask * 0.22;
    // Plage (bright active regions)
    float plage = fbm(sphereUV * 3.5 + t * 0.015, 6);
    float plageMask = smoothstep(0.56, 0.64, plage) * smoothstep(0.9, 0.4, rNorm);
    photosphere += mix(hot, warm, 0.3) * plageMask * 0.12;
  }

  // Sharp photosphere edge with sub-pixel anti-aliasing
  float edgeSoft = 1.0 / u_res.x * 2.0;
  float bodyMask = smoothstep(sphereR + edgeSoft, sphereR - edgeSoft, dist);

  /* ===================================================================
     CHROMOSPHERE  (thin bright ring with spicule forests)
     ================================================================ */
  float chromoDist = abs(dist - sphereR);
  float chromo = exp(-chromoDist * chromoDist * 4000.0) * 0.75;

  // Spicule forest texture — finer and more varied
  float spiculeCoarse = fbm(vec2(angle * 12.0 + u_seed * 3.0, dist * 40.0 - t * 0.6), 6);
  float spiculeFine = fbm(vec2(angle * 24.0 + u_seed * 5.0, dist * 60.0 - t * 0.4), 5);
  float spiculeNoise = spiculeCoarse * 0.6 + spiculeFine * 0.4;
  chromo *= 0.5 + spiculeNoise * 1.0;

  // Bright macrospicules at random angles
  float macroSpicule = 0.0;
  for(int i = 0; i < 8; i++){
    float spAngle = hash(vec2(u_seed, float(i) * 1.7)) * 6.283;
    float angDist = abs(mod(angle - spAngle + 3.14159, 6.28318) - 3.14159);
    float spHeight = 0.02 + hash(vec2(float(i), u_seed * 2.3)) * 0.03;
    float sp = exp(-angDist * angDist * 400.0)
             * smoothstep(sphereR + spHeight, sphereR, dist)
             * smoothstep(sphereR - 0.01, sphereR, dist);
    macroSpicule += sp * 0.3;
  }
  chromo += macroSpicule;

  vec3 chromoCol = mix(fc * 1.2, hot, 0.45) * chromo;

  /* ===================================================================
     CORONA  (HD filamentary streamers with fine structure)
     ================================================================ */
  float coronaDist = max(0.0, dist - sphereR);
  float coronaFade = exp(-coronaDist * 3.0);

  // Asymmetric streamer rays with domain-warped turbulence
  float nRays = 6.0 + u_seed * 6.0;              // 6–12 rays
  float warpedAngle = angle + warpedFbm(vec2(angle * 0.3 + u_seed * 9.0, coronaDist * 3.0), t * 0.5, 4) * 1.2;
  float rays = pow(abs(cos(warpedAngle * nRays * 0.5)), 6.0);

  // Multi-scale filament structure
  float fil1 = fbm(vec2(angle * 8.0 + u_seed, coronaDist * 25.0 - t * 0.3), 7);
  float fil2 = fbm(vec2(angle * 16.0 - u_seed * 2.0, coronaDist * 50.0 + t * 0.2), 6);
  float fil3 = fbm(vec2(angle * 32.0 + u_seed * 4.0, coronaDist * 80.0 - t * 0.15), 5);
  float detail = fil1 * 0.5 + fil2 * 0.3 + fil3 * 0.2;

  // Coronal loops and arcs
  float loops = 0.0;
  for(int k = 0; k < 4; k++){
    float loopAngle = u_seed * 6.28 * (float(k) + 1.0) * 0.414;
    float la = abs(mod(angle - loopAngle + 3.14159, 6.28318) - 3.14159);
    float loopR = 0.05 + hash(vec2(u_seed * 2.0, float(k))) * 0.06;
    float loopArc = exp(-la * la * 120.0)
                  * exp(-pow(coronaDist - loopR, 2.0) * 800.0);
    loops += loopArc * 0.25;
  }

  float corona = coronaFade * (rays * 0.55 + 0.2) * (0.35 + detail * 0.95) + loops;
  corona *= smoothstep(0.0, 0.035, coronaDist);

  // Corona colour with secondary domain blending
  vec3 coronaColor = mix(fc, hot, 0.4);
  if(u_hasColor2 > 0.5){
    vec3 c2 = u_color2 / 255.0;
    float side1 = smoothstep(-0.3, 0.5, sin(angle + u_seed * 2.0));
    coronaColor = mix(coronaColor, c2, side1 * 0.4);
  }
  if(u_hasColor3 > 0.5){
    vec3 c3 = u_color3 / 255.0;
    float side2 = smoothstep(-0.3, 0.5, sin(angle + u_seed * 4.0 + 2.1));
    coronaColor = mix(coronaColor, c3, side2 * 0.35);
  }

  /* ===================================================================
     PROMINENCES  (dramatic plasma arcs at the limb)
     ================================================================ */
  float prom = 0.0;
  if(u_stage >= 1.0){
    int nProm = u_stage >= 2.0 ? 4 : 2;
    for(int k=0; k<4; k++){
      if(k >= nProm) break;
      float pa = u_seed * 6.28 * float(k+1) * 0.618;
      float angDiff = abs(mod(angle - pa + 3.14159, 6.28318) - 3.14159);
      float arcWidth = 0.12 + hash(vec2(u_seed, float(k))) * 0.12;
      float arcH = 0.05 + hash(vec2(float(k), u_seed * 3.0)) * 0.10;
      float radialPeak = sphereR + arcH;
      // Turbulent arc shape
      float turbArc = fbm(vec2(angDiff * 10.0 + u_seed * float(k+1), dist * 15.0 + t * 0.1), 4);
      float arcShape = exp(-angDiff * angDiff / (arcWidth * arcWidth))
                      * exp(-pow(dist - radialPeak - turbArc * 0.015, 2.0) * 180.0);
      prom += arcShape * 0.55;
    }
  }

  /* ===================================================================
     DIFFRACTION SPIKES  (6-point, tapered, with secondary set)
     ================================================================ */
  float spikes = 0.0;
  if(u_hasDiffraction > 0.5){
    // Fixed aperture angle — determined by seed, not rotating with time.
    // Real telescope diffraction spikes are stationary relative to the optic.
    float sa = u_seed * 0.7854;  // 0..π/4 offset per star
    for(int k=0; k<4; k++){
      float target = sa + float(k) * 1.5708;
      float diff = abs(mod(angle - target + 3.14159, 6.28318) - 3.14159);
      float spike = exp(-diff * diff * 1100.0);
      spike *= exp(-coronaDist * 3.2) * 0.55 + exp(-coronaDist * 1.1) * 0.28;
      spikes += spike;
    }
    for(int k=0; k<4; k++){
      float target = sa + 0.7854 + float(k) * 1.5708;
      float diff = abs(mod(angle - target + 3.14159, 6.28318) - 3.14159);
      float spike = exp(-diff * diff * 2800.0);
      spike *= exp(-coronaDist * 5.5) * 0.18;
      spikes += spike;
    }
    spikes *= smoothstep(0.0, 0.02, coronaDist);
  }

  /* ===================================================================
     COMPOSE — HDR-style tonemapping for realistic star appearance
     ================================================================ */
  float twinkle = 0.93 + sin(t * 0.7 + u_seed * 6.0) * 0.05
                       + cos(t * 0.5) * 0.02;

  // Photosphere body
  vec3 col = photosphere * bodyMask;

  // Chromosphere ring
  col += chromoCol;

  // Corona
  col += coronaColor * corona * 0.85;

  // Prominences
  col += mix(fc * 1.1, hot, 0.55) * prom;

  // Diffraction spikes
  col += coronaColor * spikes * 0.65;

  // Core bloom — tight, intense, HDR-hot
  float bloom = exp(-dist * dist / 0.009);
  col += hot * bloom * 0.55;

  // Second bloom — medium halo
  float bloom2 = exp(-dist * dist / 0.04);
  col += mix(hot, fc, 0.25) * bloom2 * 0.18;

  // Third bloom — wider atmospheric glow
  float bloom3 = exp(-dist * dist / 0.12);
  col += mix(hot, fc, 0.5) * bloom3 * 0.06;

  col *= twinkle;

  // Soft HDR tonemapping — preserve highlights while keeping darks rich
  col = col / (1.0 + col * 0.15);
  col = pow(col, vec3(0.97));  // very slight gamma lift for richness

  // Alpha: body is solid, corona/halo fall off
  float alpha = bodyMask;
  float glowAlpha = corona * 0.85 + chromo + spikes * 0.5 + prom + bloom2 * 0.35 + bloom3 * 0.15;
  alpha = max(alpha, clamp(glowAlpha * twinkle, 0.0, 1.0));
  alpha *= smoothstep(1.02, 0.92, dist);

  // Dither
  vec2 fc2 = gl_FragCoord.xy;
  col += dither(fc2);

  fragColor = vec4(clamp(col, 0.0, 1.0), clamp(alpha, 0.0, 1.0));
}` as const;

export function compileShader(gl: WebGL2RenderingContext, type: number, src: string): WebGLShader | null {
  const s = gl.createShader(type);
  if (!s) return null;
  gl.shaderSource(s, src);
  gl.compileShader(s);
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
    console.error("Shader compile error:", gl.getShaderInfoLog(s));
    gl.deleteShader(s);
    return null;
  }
  return s;
}

export function createStarProgram(gl: WebGL2RenderingContext): WebGLProgram | null {
  const vs = compileShader(gl, gl.VERTEX_SHADER, STAR_VERT);
  const fs = compileShader(gl, gl.FRAGMENT_SHADER, STAR_FRAG);
  if (!vs || !fs) return null;
  const prog = gl.createProgram()!;
  gl.attachShader(prog, vs);
  gl.attachShader(prog, fs);
  gl.linkProgram(prog);
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
    console.error("Program link error:", gl.getProgramInfoLog(prog));
    return null;
  }
  gl.deleteShader(vs);
  gl.deleteShader(fs);
  return prog;
}
