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
uniform vec3  u_color;       // palette.core (0-255 range — divide by 255 in shader)
uniform vec3  u_color2;      // palette.halo
uniform vec3  u_color3;      // palette.accent
uniform float u_hasColor2;
uniform float u_hasColor3;
uniform float u_hasDiffraction;
uniform float u_stage;
uniform vec2  u_res;          // physical canvas size (full screen × DPR)
uniform vec2  u_starPos;      // star centre in physical pixels
uniform float u_focusStrength; // 0→1

/* ── helpers ──────────────────────────────────────────────────────────── */
float hash(vec2 p){
  vec3 p3 = fract(vec3(p.xyx) * vec3(0.1031, 0.1030, 0.0973));
  p3 += dot(p3, p3.yzx + 33.33);
  return fract((p3.x + p3.y) * p3.z);
}
vec2 hash2(vec2 p){ return vec2(hash(p), hash(p + 127.1)); }

float vnoise(vec2 p){
  vec2 i = floor(p), f = fract(p);
  vec2 u = f*f*f*(f*(f*6.0-15.0)+10.0);
  return mix(mix(hash(i),hash(i+vec2(1,0)),u.x),
             mix(hash(i+vec2(0,1)),hash(i+vec2(1,1)),u.x), u.y);
}

float fbm(vec2 p, int oct){
  float v=0.0, a=0.5, tot=0.0;
  mat2 rot=mat2(0.8,-0.6,0.6,0.8);
  for(int i=0;i<8;i++){
    if(i>=oct) break;
    v+=a*vnoise(p); tot+=a;
    p=rot*p*2.03; a*=0.49;
  }
  return v/tot;
}

float dither(vec2 fc){ return (hash(fc+fract(u_time))-0.5)/255.0; }

void main(){
  // Work in physical pixels relative to star centre
  vec2 px     = gl_FragCoord.xy - u_starPos;
  float dist  = length(px);
  float angle = atan(px.y, px.x);

  // Disc radius grows with focus: pinpoint at first glow → full NMS disc at focusStrength=1.
  // This ensures the NMS overlay starts as a tiny glow that matches the background WebGL star,
  // then expands seamlessly — no hard mode-switch.
  float vmin    = min(u_res.x, u_res.y);
  float discR   = vmin * mix(0.006, 0.28, smoothstep(0.0, 0.7, u_focusStrength));

  float rNorm     = dist / discR;
  float coronaDist = max(0.0, dist - discR);

  vec3  fc_col = u_color  / 255.0;
  vec3  fc_col2= u_color2 / 255.0;
  vec3  fc_col3= u_color3 / 255.0;
  vec3  hot    = vec3(1.0, 0.97, 0.92);
  vec3  warm   = vec3(1.0, 0.85, 0.55);

  float t = u_time * 0.6;

  /* ── DISC (smooth limb-darkened sphere, no hard edge) ──────────────── */
  // Soft edge: smoothstep gives a painterly fade, no mathematical clip
  float discMask = smoothstep(1.18, 0.65, rNorm);

  // Limb darkening — classic stellar mu law
  float mu   = sqrt(max(0.0, 1.0 - min(rNorm, 1.0)*min(rNorm, 1.0)));
  float limb = pow(mu, 0.45) * 0.65 + pow(mu, 2.2) * 0.35;

  // Colour: blinding white core → warm → star colour at limb
  float coreT  = smoothstep(0.0, 0.9, rNorm);
  vec3  discCol = mix(hot, mix(warm, fc_col, coreT * 0.7), coreT);

  // Subtle slow surface shimmer (replaces granulation — just a slow noise roll)
  float shimmer = 0.92 + fbm(vec2(angle*3.0+u_seed, rNorm*4.0+t*0.05), 3) * 0.16;

  vec3 disc = discCol * limb * shimmer * discMask;

  /* ── PROMINENCES ───────────────────────────────────────────────────── */
  float prom = 0.0;
  if(u_stage >= 1.0){
    int nProm = u_stage >= 2.0 ? 4 : 2;
    for(int k=0; k<4; k++){
      if(k >= nProm) break;
      float pa      = u_seed * 6.28318 * float(k+1) * 0.618;
      float angDiff = abs(mod(angle - pa + 3.14159, 6.28318) - 3.14159);
      float arcW    = 0.12 + hash(vec2(u_seed, float(k))) * 0.12;
      float arcH    = discR * (0.12 + hash(vec2(float(k), u_seed*3.0)) * 0.18);
      float radPeak = discR + arcH;
      float turbArc = fbm(vec2(angDiff*10.0+u_seed*float(k+1), dist*0.015+t*0.1), 4);
      float arcShape = exp(-angDiff*angDiff/(arcW*arcW))
                     * exp(-pow(dist - radPeak - turbArc*discR*0.03, 2.0) / (discR*discR*0.04));
      prom += arcShape * 0.6;
    }
  }

  /* ── CORONA ────────────────────────────────────────────────────────── */
  // Extended — fades over ~3× disc radius
  float coronaFade = exp(-coronaDist / (discR * 0.9));

  // Asymmetric rays (domain-warped)
  float nRays      = 5.0 + u_seed * 5.0;
  float warpedAngle = angle + fbm(vec2(angle*0.3+u_seed*9.0, coronaDist/discR*3.0), 4) * 1.1;
  float rays        = pow(abs(cos(warpedAngle * nRays * 0.5)), 5.0);

  // Filament detail
  float fil1 = fbm(vec2(angle*8.0+u_seed,      coronaDist/discR*12.0 - t*0.3), 6);
  float fil2 = fbm(vec2(angle*16.0-u_seed*2.0, coronaDist/discR*24.0 + t*0.2), 5);
  float detail = fil1 * 0.6 + fil2 * 0.4;

  float corona = coronaFade * (rays * 0.5 + 0.25) * (0.4 + detail * 0.85);
  corona *= smoothstep(0.0, discR * 0.06, coronaDist);

  // Corona colour blended from palette
  vec3 coronaCol = mix(fc_col, hot, 0.35);
  if(u_hasColor2 > 0.5) coronaCol = mix(coronaCol, fc_col2, smoothstep(-0.3, 0.5, sin(angle+u_seed*2.0)) * 0.4);
  if(u_hasColor3 > 0.5) coronaCol = mix(coronaCol, fc_col3, smoothstep(-0.3, 0.5, sin(angle+u_seed*4.0+2.1)) * 0.35);

  /* ── WIDE AMBIENT TINT ─────────────────────────────────────────────── */
  // Bleeds star colour across the entire viewport — the NMS "space tinted by the star" look
  float ambient = exp(-(dist*dist) / (vmin * vmin * 0.55)) * 0.18;
  vec3  ambientCol = mix(fc_col, fc_col2 * u_hasColor2 + fc_col * (1.0 - u_hasColor2), 0.35);

  /* ── DIFFRACTION SPIKES ─────────────────────────────────────────────── */
  float spikes = 0.0;
  if(u_hasDiffraction > 0.5){
    float sa = u_seed * 0.7854;
    for(int k=0; k<4; k++){
      float target = sa + float(k) * 1.5708;
      float diff   = abs(mod(angle - target + 3.14159, 6.28318) - 3.14159);
      float spike  = exp(-diff*diff * 1100.0);
      spike *= exp(-coronaDist/(discR*1.6)) * 0.55 + exp(-coronaDist/(discR*4.0)) * 0.28;
      spikes += spike;
    }
    for(int k=0; k<4; k++){
      float target = sa + 0.7854 + float(k) * 1.5708;
      float diff   = abs(mod(angle - target + 3.14159, 6.28318) - 3.14159);
      float spike  = exp(-diff*diff * 2800.0) * exp(-coronaDist/(discR*0.9)) * 0.18;
      spikes += spike;
    }
    spikes *= smoothstep(0.0, discR*0.04, coronaDist);
  }

  /* ── CORE BLOOM ────────────────────────────────────────────────────── */
  float bloom1 = exp(-(dist*dist) / (discR * discR * 0.018));  // tight white-hot
  float bloom2 = exp(-(dist*dist) / (discR * discR * 0.12));   // medium halo

  /* ── COMPOSE ───────────────────────────────────────────────────────── */
  float twinkle = 0.94 + sin(t*0.7+u_seed*6.0)*0.04 + cos(t*0.5)*0.02;

  vec3 col = vec3(0.0);
  col += disc;
  col += mix(fc_col*1.1, hot, 0.5) * prom;
  col += coronaCol * corona * 0.9;
  col += coronaCol * spikes * 0.7;
  col += hot * bloom1 * 0.7;
  col += mix(hot, fc_col, 0.3) * bloom2 * 0.22;
  col += ambientCol * ambient;
  col *= twinkle;

  // Scale entire output by focus strength — glow builds as you zoom in.
  // Low threshold (0.15) means the ambient tint is visible early in the dive,
  // cross-fading smoothly with the background WebGL point sprite.
  float intensity = smoothstep(0.0, 0.15, u_focusStrength);
  col *= intensity;

  // Reinhard tonemap
  col = col / (1.0 + col * 0.18);
  col = pow(col, vec3(0.97));

  // Alpha: disc is solid, everything else additive-soft
  float alpha = discMask * limb;
  float glowA  = corona * 0.9 + prom + spikes * 0.55 + bloom2 * 0.4 + ambient * 0.6;
  alpha = max(alpha, clamp(glowA * twinkle, 0.0, 1.0));
  alpha *= intensity;

  col += dither(gl_FragCoord.xy);

  fragColor = vec4(clamp(col, 0.0, 1.0), clamp(alpha, 0.0, 1.0));
}` as const;

// ── Three.js-compatible variants ──────────────────────────────────────────
// Used by landing-starfield-webgl.tsx to render the NMS disc inside the
// existing Three.js canvas (avoids a separate WebGL2 rendering context).
// Differences from STAR_VERT / STAR_FRAG:
//   • No #version or precision header (Three.js injects these)
//   • Vertex shader uses the built-in `position` attribute to fill NDC
//   • `gl_FragColor` instead of `out vec4 fragColor`

export const STAR_VERT_THREEJS = `
void main() {
  // Full-screen NDC quad — bypasses camera/model transforms entirely.
  // PlaneGeometry(2,2) vertex positions are already in [-1,1] NDC space.
  gl_Position = vec4(position.xy, 0.0, 1.0);
}` as const;

export const STAR_FRAG_THREEJS = `
uniform float u_time;
uniform float u_seed;
uniform vec3  u_color;
uniform vec3  u_color2;
uniform vec3  u_color3;
uniform float u_hasColor2;
uniform float u_hasColor3;
uniform float u_hasDiffraction;
uniform float u_stage;
uniform vec2  u_res;
uniform vec2  u_starPos;
uniform float u_focusStrength;

float hash(vec2 p){
  vec3 p3 = fract(vec3(p.xyx) * vec3(0.1031, 0.1030, 0.0973));
  p3 += dot(p3, p3.yzx + 33.33);
  return fract((p3.x + p3.y) * p3.z);
}
vec2 hash2(vec2 p){ return vec2(hash(p), hash(p + 127.1)); }

float vnoise(vec2 p){
  vec2 i = floor(p), f = fract(p);
  vec2 u = f*f*f*(f*(f*6.0-15.0)+10.0);
  return mix(mix(hash(i),hash(i+vec2(1,0)),u.x),
             mix(hash(i+vec2(0,1)),hash(i+vec2(1,1)),u.x), u.y);
}

float fbm(vec2 p, int oct){
  float v=0.0, a=0.5, tot=0.0;
  mat2 rot=mat2(0.8,-0.6,0.6,0.8);
  for(int i=0;i<8;i++){
    if(i>=oct) break;
    v+=a*vnoise(p); tot+=a;
    p=rot*p*2.03; a*=0.49;
  }
  return v/tot;
}

float dither(vec2 fc){ return (hash(fc+fract(u_time))-0.5)/255.0; }

void main(){
  vec2 px     = gl_FragCoord.xy - u_starPos;
  float dist  = length(px);
  float angle = atan(px.y, px.x);

  float vmin    = min(u_res.x, u_res.y);
  float discR   = vmin * mix(0.006, 0.28, smoothstep(0.0, 0.7, u_focusStrength));

  float rNorm     = dist / discR;
  float coronaDist = max(0.0, dist - discR);

  vec3  fc_col = u_color  / 255.0;
  vec3  fc_col2= u_color2 / 255.0;
  vec3  fc_col3= u_color3 / 255.0;
  vec3  hot    = vec3(1.0, 0.97, 0.92);
  vec3  warm   = vec3(1.0, 0.85, 0.55);

  float t = u_time * 0.6;

  float discMask = smoothstep(1.18, 0.65, rNorm);

  float mu   = sqrt(max(0.0, 1.0 - min(rNorm, 1.0)*min(rNorm, 1.0)));
  float limb = pow(mu, 0.45) * 0.65 + pow(mu, 2.2) * 0.35;

  float coreT  = smoothstep(0.0, 0.9, rNorm);
  vec3  discCol = mix(hot, mix(warm, fc_col, coreT * 0.7), coreT);

  float shimmer = 0.92 + fbm(vec2(angle*3.0+u_seed, rNorm*4.0+t*0.05), 3) * 0.16;

  vec3 disc = discCol * limb * shimmer * discMask;

  float prom = 0.0;
  if(u_stage >= 1.0){
    int nProm = u_stage >= 2.0 ? 4 : 2;
    for(int k=0; k<4; k++){
      if(k >= nProm) break;
      float pa      = u_seed * 6.28318 * float(k+1) * 0.618;
      float angDiff = abs(mod(angle - pa + 3.14159, 6.28318) - 3.14159);
      float arcW    = 0.12 + hash(vec2(u_seed, float(k))) * 0.12;
      float arcH    = discR * (0.12 + hash(vec2(float(k), u_seed*3.0)) * 0.18);
      float radPeak = discR + arcH;
      float turbArc = fbm(vec2(angDiff*10.0+u_seed*float(k+1), dist*0.015+t*0.1), 4);
      float arcShape = exp(-angDiff*angDiff/(arcW*arcW))
                     * exp(-pow(dist - radPeak - turbArc*discR*0.03, 2.0) / (discR*discR*0.04));
      prom += arcShape * 0.6;
    }
  }

  float coronaFade = exp(-coronaDist / (discR * 0.9));

  float nRays      = 5.0 + u_seed * 5.0;
  float warpedAngle = angle + fbm(vec2(angle*0.3+u_seed*9.0, coronaDist/discR*3.0), 4) * 1.1;
  float rays        = pow(abs(cos(warpedAngle * nRays * 0.5)), 5.0);

  float fil1 = fbm(vec2(angle*8.0+u_seed,      coronaDist/discR*12.0 - t*0.3), 6);
  float fil2 = fbm(vec2(angle*16.0-u_seed*2.0, coronaDist/discR*24.0 + t*0.2), 5);
  float detail = fil1 * 0.6 + fil2 * 0.4;

  float corona = coronaFade * (rays * 0.5 + 0.25) * (0.4 + detail * 0.85);
  corona *= smoothstep(0.0, discR * 0.06, coronaDist);

  vec3 coronaCol = mix(fc_col, hot, 0.35);
  if(u_hasColor2 > 0.5) coronaCol = mix(coronaCol, fc_col2, smoothstep(-0.3, 0.5, sin(angle+u_seed*2.0)) * 0.4);
  if(u_hasColor3 > 0.5) coronaCol = mix(coronaCol, fc_col3, smoothstep(-0.3, 0.5, sin(angle+u_seed*4.0+2.1)) * 0.35);

  float ambient = exp(-(dist*dist) / (vmin * vmin * 0.55)) * 0.18;
  vec3  ambientCol = mix(fc_col, fc_col2 * u_hasColor2 + fc_col * (1.0 - u_hasColor2), 0.35);

  float spikes = 0.0;
  if(u_hasDiffraction > 0.5){
    float sa = u_seed * 0.7854;
    for(int k=0; k<4; k++){
      float target = sa + float(k) * 1.5708;
      float diff   = abs(mod(angle - target + 3.14159, 6.28318) - 3.14159);
      float spike  = exp(-diff*diff * 1100.0);
      spike *= exp(-coronaDist/(discR*1.6)) * 0.55 + exp(-coronaDist/(discR*4.0)) * 0.28;
      spikes += spike;
    }
    for(int k=0; k<4; k++){
      float target = sa + 0.7854 + float(k) * 1.5708;
      float diff   = abs(mod(angle - target + 3.14159, 6.28318) - 3.14159);
      float spike  = exp(-diff*diff * 2800.0) * exp(-coronaDist/(discR*0.9)) * 0.18;
      spikes += spike;
    }
    spikes *= smoothstep(0.0, discR*0.04, coronaDist);
  }

  float bloom1 = exp(-(dist*dist) / (discR * discR * 0.018));
  float bloom2 = exp(-(dist*dist) / (discR * discR * 0.12));

  float twinkle = 0.94 + sin(t*0.7+u_seed*6.0)*0.04 + cos(t*0.5)*0.02;

  vec3 col = vec3(0.0);
  col += disc;
  col += mix(fc_col*1.1, hot, 0.5) * prom;
  col += coronaCol * corona * 0.9;
  col += coronaCol * spikes * 0.7;
  col += hot * bloom1 * 0.7;
  col += mix(hot, fc_col, 0.3) * bloom2 * 0.22;
  col += ambientCol * ambient;
  col *= twinkle;

  float intensity = smoothstep(0.0, 0.15, u_focusStrength);
  col *= intensity;

  col = col / (1.0 + col * 0.18);
  col = pow(col, vec3(0.97));

  float alpha = discMask * limb;
  float glowA  = corona * 0.9 + prom + spikes * 0.55 + bloom2 * 0.4 + ambient * 0.6;
  alpha = max(alpha, clamp(glowA * twinkle, 0.0, 1.0));
  alpha *= intensity;

  col += dither(gl_FragCoord.xy);

  gl_FragColor = vec4(clamp(col, 0.0, 1.0), clamp(alpha, 0.0, 1.0));
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
