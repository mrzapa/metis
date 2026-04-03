"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Circle,
  Database,
  FolderOpen,
  Loader2,
  Orbit,
  Sparkles,
  Trash2,
  UploadCloud,
  X,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { LearningRoutePanel } from "@/components/constellation/learning-route-panel";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { buildIndexStream, fetchSettings, uploadFiles } from "@/lib/api";
import type { IndexBuildResult, IndexSummary } from "@/lib/api";
import {
  buildBrainPlacementIntent,
  buildFacultyAnchoredPlacement,
  getConstellationPlacementDecision,
} from "@/lib/constellation-brain";
import { CONSTELLATION_FACULTIES, getAutoStarFaculty, getFacultyColor, isAutonomousStar } from "@/lib/constellation-home";
import type {
  LearningRoute,
  LearningRouteStep,
  LearningRouteStepStatus,
  UserStar,
  UserStarStage,
} from "@/lib/constellation-types";
import { cn } from "@/lib/utils";

type BuildStep = "idle" | "active" | "done";
type EntryMode = "new" | "existing";
type StarDialogView = "build" | "overview";
type DialogTone = "default" | "error";

type DetailStar = UserStar & {
  primaryDomainId?: string;
  relatedDomainIds?: string[];
  stage?: UserStarStage;
  intent?: string;
  notes?: string;
  linkedManifestPaths?: string[];
  activeManifestPath?: string;
};

type StarUpdatePayload = Partial<
  Pick<
    UserStar,
    | "label"
    | "primaryDomainId"
    | "relatedDomainIds"
    | "stage"
    | "intent"
    | "notes"
    | "linkedManifestPaths"
    | "activeManifestPath"
    | "linkedManifestPath"
    | "x"
    | "y"
  >
>;

type AttachedIndexSummary = {
  manifest_path: string;
  index_id: string;
  document_count: number;
  chunk_count: number;
  backend: string;
  created_at?: string;
  embedding_signature?: string;
  source: "available" | "build" | "unresolved";
};

interface ProgressState {
  reading: BuildStep;
  embedding: BuildStep;
  saved: BuildStep;
}

const INITIAL_PROGRESS: ProgressState = {
  reading: "idle",
  embedding: "idle",
  saved: "idle",
};

const STAGE_OPTIONS: Array<{ value: UserStarStage; label: string; description: string }> = [
  {
    value: "seed",
    label: "Seed",
    description: "A new possibility that is just entering the constellation.",
  },
  {
    value: "growing",
    label: "Growing",
    description: "Actively collecting sources, notes, or applied meaning.",
  },
  {
    value: "integrated",
    label: "Integrated",
    description: "A mature star drawing on multiple attached sources.",
  },
];

interface StarDetailsPanelProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  star: UserStar | null;
  entryMode: EntryMode;
  closeLockedUntil?: number;
  availableIndexes: IndexSummary[];
  indexesLoading: boolean;
  onIndexBuilt: (result: IndexBuildResult) => void;
  onUpdateStar: (starId: string, updates: StarUpdatePayload) => Promise<boolean>;
  onRemoveStar: (payload: { starId: string; manifestPaths: string[] }) => Promise<void>;
  onOpenChat: (payload: {
    manifestPath: string;
    label: string;
    selectedMode?: string;
    draft?: string;
  }) => void;
  learningRoutePreview: LearningRoute | null;
  learningRouteLoading: boolean;
  learningRouteError: string | null;
  onStartCourse: () => void;
  onSaveLearningRoutePreview: () => void;
  onDiscardLearningRoutePreview: () => void;
  onRegenerateLearningRoute: () => void;
  onLaunchLearningRouteStep: (step: LearningRouteStep) => void;
  onSetLearningRouteStepStatus: (stepId: string, status: LearningRouteStepStatus) => void;
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  } catch {
    return iso;
  }
}

function uniqueStrings(values: Array<string | undefined | null>): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  values.forEach((value) => {
    const trimmed = value?.trim();
    if (!trimmed || seen.has(trimmed)) {
      return;
    }
    seen.add(trimmed);
    result.push(trimmed);
  });
  return result;
}

function resolveDefaultStage(
  linkedManifestPaths: string[],
  notes: string | undefined,
): UserStarStage {
  if (linkedManifestPaths.length >= 2) {
    return "integrated";
  }
  if (linkedManifestPaths.length === 1 || notes?.trim()) {
    return "growing";
  }
  return "seed";
}

/* ── WebGL2 procedural star shader ──────────────────────────────────── */

const STAR_VERT = `#version 300 es
precision highp float;
in vec2 a_pos;
out vec2 v_uv;
void main(){
  v_uv = a_pos * 0.5 + 0.5;
  gl_Position = vec4(a_pos, 0.0, 1.0);
}` as const;

const STAR_FRAG = `#version 300 es
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

  float sphereR = 0.44;
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
    float sa = t * 0.04;
    for(int k=0; k<4; k++){
      float target = sa + float(k) * 1.5708;
      float diff = abs(mod(angle - target + 3.14159, 6.28318) - 3.14159);
      float spike = exp(-diff * diff * 900.0);
      spike *= exp(-coronaDist * 3.5) * 0.5 + exp(-coronaDist * 1.2) * 0.3;
      spikes += spike;
    }
    for(int k=0; k<4; k++){
      float target = sa + 0.7854 + float(k) * 1.5708;
      float diff = abs(mod(angle - target + 3.14159, 6.28318) - 3.14159);
      float spike = exp(-diff * diff * 2200.0);
      spike *= exp(-coronaDist * 5.0) * 0.2;
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

function compileShader(gl: WebGL2RenderingContext, type: number, src: string): WebGLShader | null {
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

function createStarProgram(gl: WebGL2RenderingContext): WebGLProgram | null {
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

function domainSeed(id?: string, id2?: string): number {
  const combined = (id ?? "") + "\x00" + (id2 ?? "");
  if (!combined.replace(/\x00/g, "")) return 0.42;
  let h = 0;
  for (let i = 0; i < combined.length; i++) {
    h = ((h << 5) - h + combined.charCodeAt(i)) | 0;
  }
  return (((h >>> 0) % 10000) / 10000);
}

function StarMiniPreview({
  primaryDomainId,
  relatedDomainIds,
  stage,
  size,
  starId,
}: {
  primaryDomainId?: string;
  relatedDomainIds?: string[];
  stage?: UserStarStage;
  size?: number;
  starId?: string;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rafRef = useRef<number>(0);
  const glRef = useRef<{ gl: WebGL2RenderingContext; prog: WebGLProgram } | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const DPR = Math.min(typeof window !== "undefined" ? (window.devicePixelRatio ?? 1) : 1, 3);
    const PX = 320;
    canvas.width = PX * DPR;
    canvas.height = PX * DPR;
    canvas.style.width = `${PX}px`;
    canvas.style.height = `${PX}px`;

    /* ── init WebGL2 ────────────────────────────────────────────────── */
    let cached = glRef.current;
    if (!cached) {
      const gl = canvas.getContext("webgl2", { alpha: true, premultipliedAlpha: false, antialias: true });
      if (!gl) return;                // fallback: just show dark circle
      const prog = createStarProgram(gl);
      if (!prog) return;

      /* fullscreen quad */
      const buf = gl.createBuffer()!;
      gl.bindBuffer(gl.ARRAY_BUFFER, buf);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1, 1,-1, -1,1, 1,1]), gl.STATIC_DRAW);
      const loc = gl.getAttribLocation(prog, "a_pos");
      gl.enableVertexAttribArray(loc);
      gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);

      cached = { gl, prog };
      glRef.current = cached;
    }

    const { gl, prog } = cached;
    gl.useProgram(prog);
    gl.viewport(0, 0, canvas.width, canvas.height);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
    gl.clearColor(8 / 255, 11 / 255, 20 / 255, 1);

    /* ── uniforms ───────────────────────────────────────────────────── */
    const uTime  = gl.getUniformLocation(prog, "u_time");
    const uSeed  = gl.getUniformLocation(prog, "u_seed");
    const uColor = gl.getUniformLocation(prog, "u_color");
    const uColor2 = gl.getUniformLocation(prog, "u_color2");
    const uColor3 = gl.getUniformLocation(prog, "u_color3");
    const uHasC2 = gl.getUniformLocation(prog, "u_hasColor2");
    const uHasC3 = gl.getUniformLocation(prog, "u_hasColor3");
    const uDiffraction = gl.getUniformLocation(prog, "u_hasDiffraction");
    const uStage = gl.getUniformLocation(prog, "u_stage");
    const uRes = gl.getUniformLocation(prog, "u_res");

    const [r, g, b] = getFacultyColor(primaryDomainId);
    const related = (relatedDomainIds ?? []).slice(0, 2).map((id) => getFacultyColor(id));
    const hasDiffraction = stage === "integrated" || stage === "growing";
    const stageVal = stage === "integrated" ? 2 : stage === "growing" ? 1 : 0;
    const seed = domainSeed(primaryDomainId, starId);

    gl.uniform3f(uColor, r, g, b);
    gl.uniform3f(uColor2, ...(related[0] ?? [208, 216, 232]) as [number, number, number]);
    gl.uniform3f(uColor3, ...(related[1] ?? [208, 216, 232]) as [number, number, number]);
    gl.uniform1f(uHasC2, related.length >= 1 ? 1 : 0);
    gl.uniform1f(uHasC3, related.length >= 2 ? 1 : 0);
    gl.uniform1f(uDiffraction, hasDiffraction ? 1 : 0);
    gl.uniform1f(uStage, stageVal);
    gl.uniform1f(uSeed, seed);
    gl.uniform2f(uRes, canvas.width, canvas.height);

    let startTime: number | null = null;

    function draw(ts: number) {
      if (!startTime) startTime = ts;
      const elapsed = (ts - startTime) / 1000;    // seconds
      gl.uniform1f(uTime, elapsed);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
      rafRef.current = requestAnimationFrame(draw);
    }

    rafRef.current = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(rafRef.current);
      glRef.current = null;
    };
  }, [primaryDomainId, relatedDomainIds, stage, size, starId]);

  return <canvas ref={canvasRef} style={{ display: "block", borderRadius: "50%" }} />;
}

export function StarDetailsPanel({
  open,
  onOpenChange,
  star,
  entryMode,
  closeLockedUntil = 0,
  availableIndexes,
  indexesLoading,
  onIndexBuilt,
  onUpdateStar,
  onRemoveStar,
  onOpenChat,
  learningRoutePreview,
  learningRouteLoading,
  learningRouteError,
  onStartCourse,
  onSaveLearningRoutePreview,
  onDiscardLearningRoutePreview,
  onRegenerateLearningRoute,
  onLaunchLearningRouteStep,
  onSetLearningRouteStepStatus,
}: StarDetailsPanelProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDesktop, setIsDesktop] = useState(false);
  const [tab, setTab] = useState<"upload" | "paths" | "desktop">("upload");
  const [pathsConsent, setPathsConsent] = useState(false);

  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [uploadedPaths, setUploadedPaths] = useState<string[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const [rawPaths, setRawPaths] = useState("");
  const [desktopPaths, setDesktopPaths] = useState<string[]>([]);
  const [pickError, setPickError] = useState<string | null>(null);

  const [building, setBuilding] = useState(false);
  const [buildError, setBuildError] = useState<string | null>(null);
  const [progress, setProgress] = useState<ProgressState>(INITIAL_PROGRESS);
  const [buildResult, setBuildResult] = useState<IndexBuildResult | null>(null);

  const [labelDraft, setLabelDraft] = useState("");
  const [primaryDomainIdDraft, setPrimaryDomainIdDraft] = useState("");
  const [relatedDomainIdsDraft, setRelatedDomainIdsDraft] = useState("");
  const [manualStageOverride, setManualStageOverride] = useState<UserStarStage | "">("");
  const [intentDraft, setIntentDraft] = useState("");
  const [notesDraft, setNotesDraft] = useState("");
  const [attachedManifestPaths, setAttachedManifestPaths] = useState<string[]>([]);
  const [activeManifestPath, setActiveManifestPath] = useState("");
  const [view, setView] = useState<StarDialogView>("build");
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [statusTone, setStatusTone] = useState<DialogTone>("default");
  const [savingMeta, setSavingMeta] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);

  useEffect(() => {
    if (typeof window !== "undefined" && "__TAURI_INTERNALS__" in window) {
      setIsDesktop(true);
      setTab("desktop");
    }
  }, []);

  useEffect(() => {
    if (!open || !star) {
      return;
    }

    const activeStar = star as DetailStar;
    const nextAttachedManifestPaths = uniqueStrings([
      ...(activeStar.linkedManifestPaths ?? []),
      activeStar.activeManifestPath,
      activeStar.linkedManifestPath,
    ]);

    setLabelDraft(activeStar.label ?? "");
    setPrimaryDomainIdDraft(activeStar.primaryDomainId ?? "");
    setRelatedDomainIdsDraft((activeStar.relatedDomainIds ?? []).join(", "));
    const derivedStage = resolveDefaultStage(nextAttachedManifestPaths, activeStar.notes);
    setManualStageOverride(
      activeStar.stage && activeStar.stage !== derivedStage ? activeStar.stage : "",
    );
    setIntentDraft(activeStar.intent ?? "");
    setNotesDraft(activeStar.notes ?? "");
    setAttachedManifestPaths(nextAttachedManifestPaths);
    setActiveManifestPath(
      activeStar.activeManifestPath
        || nextAttachedManifestPaths[nextAttachedManifestPaths.length - 1]
        || activeStar.linkedManifestPath
        || "",
    );
    setStatusMessage(null);
    setStatusTone("default");
    setBuildError(null);
    setBuildResult(null);
    setProgress(INITIAL_PROGRESS);
    setSelectedFiles([]);
    setUploadedPaths([]);
    setRawPaths("");
    setDesktopPaths([]);
    setUploadError(null);
    setPickError(null);
    setPathsConsent(false);
    setDeleteConfirmOpen(false);
    setView(entryMode === "new" || nextAttachedManifestPaths.length === 0 ? "build" : "overview");
  }, [entryMode, open, star]);

  const readyPaths = useMemo(
    () => (
      tab === "upload"
        ? uploadedPaths
        : tab === "desktop"
          ? desktopPaths
          : rawPaths
              .split("\n")
              .map((path) => path.trim())
              .filter(Boolean)
    ),
    [desktopPaths, rawPaths, tab, uploadedPaths],
  );

  const activeManifestPathForChat = activeManifestPath
    || attachedManifestPaths[attachedManifestPaths.length - 1]
    || buildResult?.manifest_path
    || "";
  const derivedStage = resolveDefaultStage(attachedManifestPaths, notesDraft);
  const effectiveStage = manualStageOverride || derivedStage;
  const availableIndexByManifestPath = useMemo(
    () => new Map(
      availableIndexes.map((index) => [
        index.manifest_path,
        { ...index, source: "available" as const },
      ]),
    ),
    [availableIndexes],
  );
  const buildResultSummary = useMemo<AttachedIndexSummary | null>(() => {
    if (!buildResult) {
      return null;
    }

    return {
      manifest_path: buildResult.manifest_path,
      index_id: buildResult.index_id,
      document_count: buildResult.document_count,
      chunk_count: buildResult.chunk_count,
      backend: buildResult.vector_backend,
      created_at: undefined,
      embedding_signature: buildResult.embedding_signature,
      source: "build",
    };
  }, [buildResult]);

  const resolveAttachedIndex = useCallback((manifestPath: string): AttachedIndexSummary => {
    const foundIndex = availableIndexByManifestPath.get(manifestPath);
    if (foundIndex) {
      return foundIndex;
    }

    if (buildResultSummary?.manifest_path === manifestPath) {
      return buildResultSummary;
    }

    return {
      manifest_path: manifestPath,
      index_id: manifestPath,
      document_count: 0,
      chunk_count: 0,
      backend: "unknown",
      source: "unresolved",
    };
  }, [availableIndexByManifestPath, buildResultSummary]);

  const activeIndex = activeManifestPathForChat ? resolveAttachedIndex(activeManifestPathForChat) : null;
  const attachedIndexes = useMemo(
    () => attachedManifestPaths.map((manifestPath) => resolveAttachedIndex(manifestPath)),
    [attachedManifestPaths, resolveAttachedIndex],
  );
  const attachedManifestPathSet = useMemo(
    () => new Set(attachedManifestPaths),
    [attachedManifestPaths],
  );
  const suggestedIndexes = useMemo(
    () => availableIndexes
      .filter((index) => !attachedManifestPathSet.has(index.manifest_path))
      .slice(0, 5),
    [attachedManifestPathSet, availableIndexes],
  );

  const handleOpenChange = useCallback((nextOpen: boolean) => {
    if (!nextOpen && (building || uploading || removing)) {
      return;
    }
    if (!nextOpen && Date.now() < closeLockedUntil) {
      return;
    }
    onOpenChange(nextOpen);
  }, [building, closeLockedUntil, onOpenChange, removing, uploading]);

  // Close on Space key when panel is open and not busy
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === " " && !building && !uploading && !removing) {
        e.preventDefault();
        handleOpenChange(false);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, building, uploading, removing, handleOpenChange]);

  if (!star) {
    return null;
  }

  const activeStar = star as DetailStar;
  const savedLearningRoute = activeStar.learningRoute ?? null;
  const displayedLearningRoute = learningRoutePreview ?? savedLearningRoute;
  const hasCourseSource = Boolean(activeManifestPathForChat) || attachedManifestPaths.length > 0;
  const unavailableManifestPaths = new Set(
    (displayedLearningRoute?.steps ?? [])
      .map((step) => step.manifestPath)
      .filter((manifestPath) => resolveAttachedIndex(manifestPath).source === "unresolved"),
  );

  function buildStarUpdate(
    nextAttachedManifestPaths = attachedManifestPaths,
    nextActiveManifestPath = activeManifestPath,
    labelOverride?: string,
    extraUpdates?: Partial<StarUpdatePayload>,
  ): StarUpdatePayload {
    const label = extraUpdates?.label ?? ((labelOverride ?? labelDraft.trim()) || activeStar.label || undefined);
    const notes = extraUpdates?.notes ?? (notesDraft.trim() || undefined);
    const relatedDomainIds = extraUpdates?.relatedDomainIds
      ? uniqueStrings(extraUpdates.relatedDomainIds)
      : uniqueStrings(relatedDomainIdsDraft.split(/[\n,]/g));
    const linkedManifestPaths = uniqueStrings([
      ...nextAttachedManifestPaths,
      nextActiveManifestPath,
    ]);
    const activePath = extraUpdates?.activeManifestPath ?? (nextActiveManifestPath || linkedManifestPaths[linkedManifestPaths.length - 1] || undefined);

    return {
      label,
      primaryDomainId: extraUpdates?.primaryDomainId ?? (primaryDomainIdDraft.trim() || undefined),
      relatedDomainIds: relatedDomainIds.length > 0 ? relatedDomainIds : undefined,
      stage: extraUpdates?.stage ?? (manualStageOverride || undefined),
      intent: extraUpdates?.intent ?? (intentDraft.trim() || undefined),
      notes,
      linkedManifestPaths: linkedManifestPaths.length > 0 ? linkedManifestPaths : undefined,
      activeManifestPath: activePath,
      linkedManifestPath: extraUpdates?.linkedManifestPath ?? activePath,
      x: extraUpdates?.x,
      y: extraUpdates?.y,
    };
  }

  async function commitStarUpdate({
    nextAttachedManifestPaths = attachedManifestPaths,
    nextActiveManifestPath = activeManifestPath,
    labelOverride,
    extraUpdates,
    successMessage = "Star details updated.",
    showSavingState = true,
  }: {
    nextAttachedManifestPaths?: string[];
    nextActiveManifestPath?: string;
    labelOverride?: string;
    extraUpdates?: Partial<StarUpdatePayload>;
    successMessage?: string;
    showSavingState?: boolean;
  } = {}) {
    if (showSavingState) {
      setSavingMeta(true);
    }

    try {
      const payload = buildStarUpdate(
        nextAttachedManifestPaths,
        nextActiveManifestPath,
        labelOverride,
        extraUpdates,
      );
      const updated = await onUpdateStar(activeStar.id, payload as Parameters<typeof onUpdateStar>[1]);
      if (!updated) {
        throw new Error("This star is no longer available.");
      }

      setLabelDraft(payload.label ?? "");
      setPrimaryDomainIdDraft(payload.primaryDomainId ?? "");
      setRelatedDomainIdsDraft((payload.relatedDomainIds ?? []).join(", "));
      setIntentDraft(payload.intent ?? "");
      setNotesDraft(payload.notes ?? "");
      setAttachedManifestPaths(payload.linkedManifestPaths ?? []);
      setActiveManifestPath(payload.activeManifestPath ?? "");
      const nextDerivedStage = resolveDefaultStage(payload.linkedManifestPaths ?? [], payload.notes);
      setManualStageOverride(
        payload.stage && payload.stage !== nextDerivedStage ? payload.stage : "",
      );
      setStatusTone("default");
      setStatusMessage(successMessage);
      return true;
    } catch (error) {
      setStatusTone("error");
      setStatusMessage(error instanceof Error ? error.message : "Unable to save star details.");
      return false;
    } finally {
      if (showSavingState) {
        setSavingMeta(false);
      }
    }
  }

  function handleSetActiveManifestPath(manifestPath: string) {
    setActiveManifestPath(manifestPath);
    const summary = resolveAttachedIndex(manifestPath);
    setStatusTone("default");
    setStatusMessage(`Active chat index staged to ${summary.index_id}. Save to keep it.`);
  }

  async function handlePickFiles() {
    setPickError(null);
    try {
      const { open: openPicker } = await import("@tauri-apps/plugin-dialog");
      const selected = await openPicker({ multiple: true });
      if (selected === null) {
        return;
      }
      const paths = Array.isArray(selected) ? selected : [selected];
      setDesktopPaths(paths);
    } catch (error) {
      setPickError(error instanceof Error ? error.message : "File picker failed");
    }
  }

  async function handleUpload() {
    if (selectedFiles.length === 0) {
      return;
    }
    setUploading(true);
    setUploadError(null);
    try {
      const { paths } = await uploadFiles(selectedFiles);
      setUploadedPaths(paths);
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  async function handleSaveMeta() {
    await commitStarUpdate();
  }

  async function handleLinkExistingIndex(index: IndexSummary) {
    const nextLabel = labelDraft.trim() || activeStar.label || index.index_id;
    const nextAttachedManifestPaths = uniqueStrings([
      ...attachedManifestPaths.filter((manifestPath) => manifestPath !== index.manifest_path),
      index.manifest_path,
    ]);
    const updated = await commitStarUpdate({
      nextAttachedManifestPaths,
      nextActiveManifestPath: index.manifest_path,
      labelOverride: nextLabel,
      successMessage: `${index.index_id} is now attached and active.`,
      showSavingState: false,
    });

    if (updated) {
      setView("overview");
    }
  }

  async function handleDetachIndex(manifestPath: string) {
    const nextAttachedManifestPaths = attachedManifestPaths.filter(
      (attachedManifestPath) => attachedManifestPath !== manifestPath,
    );
    const nextActiveManifestPath = manifestPath === activeManifestPathForChat
      ? (nextAttachedManifestPaths[nextAttachedManifestPaths.length - 1] ?? "")
      : activeManifestPathForChat;
    const detachedIndex = resolveAttachedIndex(manifestPath);
    const updated = await commitStarUpdate({
      nextAttachedManifestPaths,
      nextActiveManifestPath,
      successMessage:
        nextAttachedManifestPaths.length > 0
          ? `${detachedIndex.index_id} detached. Remaining sources stay in orbit.`
          : `${detachedIndex.index_id} detached. This star is ready for new material.`,
      showSavingState: false,
    });

    if (updated && nextAttachedManifestPaths.length === 0) {
      setView("build");
    }
  }

  async function handleBuild() {
    if (readyPaths.length === 0) {
      return;
    }

    setBuilding(true);
    setBuildError(null);
    setBuildResult(null);
    setStatusMessage(null);
    setProgress({ reading: "active", embedding: "idle", saved: "idle" });

    try {
      const settings = await fetchSettings();
      const result = await buildIndexStream(readyPaths, settings, (event) => {
        const type = String(event.type ?? "");
        if (type === "status") {
          const text = String(event.text ?? "").toLowerCase();
          if (text.includes("embedding")) {
            setProgress({ reading: "done", embedding: "active", saved: "idle" });
          }
        }
      });

      setProgress({ reading: "done", embedding: "done", saved: "active" });
      setBuildResult(result);
      onIndexBuilt(result);

      const nextLabel = labelDraft.trim() || activeStar.label || result.index_id;
      const nextAttachedManifestPaths = uniqueStrings([
        ...attachedManifestPaths.filter((manifestPath) => manifestPath !== result.manifest_path),
        result.manifest_path,
      ]);
      const placement = getConstellationPlacementDecision(result);
      const facultyLabel = CONSTELLATION_FACULTIES.find(
        (faculty) => faculty.id === placement.facultyId,
      )?.label ?? placement.facultyId;
      const placementSeed = Math.abs(Math.trunc(activeStar.createdAt % 24));
      const { x, y } = buildFacultyAnchoredPlacement(placement.facultyId, placementSeed);
      const nextRelatedDomainIds = uniqueStrings([
        ...relatedDomainIdsDraft.split(/[\n,]/g),
        ...placement.secondaryFacultyIds,
      ]);
      const updated = await commitStarUpdate({
        nextAttachedManifestPaths,
        nextActiveManifestPath: result.manifest_path,
        labelOverride: nextLabel,
        extraUpdates: {
          primaryDomainId: placement.facultyId,
          relatedDomainIds: nextRelatedDomainIds.length > 0 ? nextRelatedDomainIds : undefined,
          intent: intentDraft.trim() || buildBrainPlacementIntent(placement.provider),
          notes: notesDraft.trim() || placement.rationale || undefined,
          x,
          y,
        },
        successMessage: `Built ${result.index_id} and filed it near ${facultyLabel}.`,
        showSavingState: false,
      });
      if (!updated) {
        throw new Error("Index built, but the star could not be linked.");
      }

      setProgress({ reading: "done", embedding: "done", saved: "done" });
      setView("overview");
    } catch (error) {
      setBuildError(error instanceof Error ? error.message : "Build failed");
      setProgress((current) =>
        current.saved === "active"
          ? { reading: "done", embedding: "done", saved: "idle" }
          : current,
      );
      setStatusTone("error");
      setStatusMessage(null);
    } finally {
      setBuilding(false);
    }
  }

  async function handleRemoveStar() {
    setRemoving(true);
    try {
      await onRemoveStar({
        starId: activeStar.id,
        manifestPaths: uniqueStrings([
          ...attachedManifestPaths,
          activeManifestPathForChat,
        ]),
      });
      setDeleteConfirmOpen(false);
    } catch (error) {
      setStatusTone("error");
      setStatusMessage(error instanceof Error ? error.message : "Unable to delete this star right now.");
    } finally {
      setRemoving(false);
    }
  }

  const dialogTitle = view === "build"
    ? (entryMode === "new" ? "Add to this star" : "Attach sources")
    : "Star details";
  const dialogDescription = view === "build"
    ? "Upload files, add local paths, or attach an existing index to deepen this star's memory."
    : "Edit the star's meaning, switch the active chat index, or bring in more attached indexes.";

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent
        className="left-1/2 top-auto bottom-3 flex h-[calc(100vh-1.5rem)] max-h-[calc(100vh-1.5rem)] w-[calc(100%-1.5rem)] max-w-[calc(100%-1.5rem)] -translate-x-1/2 translate-y-0 flex-col gap-0 overflow-hidden rounded-[1.75rem] border-white/12 bg-[linear-gradient(180deg,rgba(14,20,34,0.98),rgba(8,11,20,0.96))] p-0 sm:left-auto sm:right-4 sm:top-4 sm:bottom-4 sm:h-[calc(100vh-2rem)] sm:max-h-[calc(100vh-2rem)] sm:w-[min(460px,calc(100vw-2rem))] sm:max-w-[460px] sm:translate-x-0 sm:translate-y-0"
        data-testid="star-details-panel"
        showCloseButton={true}
        showOverlay={false}
      >
        <div className="border-b border-white/10 bg-[linear-gradient(180deg,rgba(14,20,34,0.98),rgba(10,13,23,0.92))] px-5 py-5 sm:px-6">
          <DialogHeader className="gap-3">
            <div className="flex items-start justify-between gap-4 pr-10">
              <div className="space-y-2">
                <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.32em] text-[#d6b361]">
                  <Sparkles className="size-3.5" />
                  {entryMode === "new" ? "New star selected" : "Existing star selected"}
                </div>
                <DialogTitle className="font-display text-3xl font-semibold tracking-[-0.05em] text-white">
                  {dialogTitle}
                </DialogTitle>
                <DialogDescription className="max-w-2xl text-sm leading-7 text-slate-300">
                  {dialogDescription}
                </DialogDescription>
                {isAutonomousStar(activeIndex?.index_id) && (
                  <div className="flex items-center gap-1.5 text-[11px] text-violet-300/80">
                    <span>✦</span>
                    <span>
                      Added autonomously by METIS
                      {getAutoStarFaculty(activeIndex?.index_id)
                        ? ` · ${getAutoStarFaculty(activeIndex?.index_id)}`
                        : ""}
                    </span>
                  </div>
                )}
              </div>

              <div className="shrink-0 overflow-hidden rounded-full border border-[#d6b361]/30 ring-1 ring-white/5">
                <StarMiniPreview
                  primaryDomainId={primaryDomainIdDraft || activeStar.primaryDomainId}
                  relatedDomainIds={
                    relatedDomainIdsDraft
                      ? relatedDomainIdsDraft.split(",").map((s) => s.trim()).filter(Boolean)
                      : activeStar.relatedDomainIds
                  }
                  stage={effectiveStage}
                  size={activeStar.size}
                  starId={activeStar.id}
                />
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => setView("build")}
                className={cn(
                  "rounded-full px-4 py-2 text-sm transition-all",
                  view === "build"
                    ? "bg-primary/18 text-primary"
                    : "bg-white/6 text-slate-300 hover:bg-white/10 hover:text-white",
                )}
              >
                Add and build
              </button>
              <button
                type="button"
                onClick={() => setView("overview")}
                className={cn(
                  "rounded-full px-4 py-2 text-sm transition-all",
                  view === "overview"
                    ? "bg-primary/18 text-primary"
                    : "bg-white/6 text-slate-300 hover:bg-white/10 hover:text-white",
                )}
              >
                Attached sources
              </button>
            </div>
          </DialogHeader>
        </div>

        <div className="flex min-h-0 flex-1 flex-col">
          <div className="min-h-0 flex-1 overflow-y-auto">
            <div className="px-5 py-5 sm:px-6 sm:py-6">
            {view === "build" ? (
              <div className="space-y-6">
                <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start">
                  <div>
                    <h3 className="font-display text-2xl font-semibold tracking-[-0.04em] text-white">
                      Bring in source material
                    </h3>
                    <p className="mt-2 text-sm leading-7 text-slate-300">
                      Pick a few files, add server-readable paths, or attach a ready-made index to this star.
                    </p>
                  </div>
                  <div className="rounded-full border border-white/10 bg-white/6 px-4 py-2 text-sm text-slate-200">
                    {readyPaths.length} ready
                  </div>
                </div>

                <div className="flex flex-wrap gap-2">
                  {isDesktop ? (
                    <button
                      type="button"
                      onClick={() => setTab("desktop")}
                      className={cn(
                        "rounded-full px-4 py-2 text-sm transition-all",
                        tab === "desktop"
                          ? "bg-primary/18 text-primary"
                          : "bg-white/6 text-slate-300 hover:bg-white/10 hover:text-white",
                      )}
                    >
                      Choose files
                    </button>
                  ) : null}
                  <button
                    type="button"
                    onClick={() => setTab("upload")}
                    className={cn(
                      "rounded-full px-4 py-2 text-sm transition-all",
                      tab === "upload"
                        ? "bg-primary/18 text-primary"
                        : "bg-white/6 text-slate-300 hover:bg-white/10 hover:text-white",
                    )}
                  >
                    Upload files
                  </button>
                  <button
                    type="button"
                    onClick={() => setTab("paths")}
                    className={cn(
                      "rounded-full px-4 py-2 text-sm transition-all",
                      tab === "paths"
                        ? "bg-primary/18 text-primary"
                        : "bg-white/6 text-slate-300 hover:bg-white/10 hover:text-white",
                    )}
                  >
                    Local paths
                  </button>
                </div>

                <div className="rounded-[1.6rem] border border-white/10 bg-black/18 p-4 sm:p-5">
                  {tab === "desktop" ? (
                    <div className="space-y-4">
                      <Button variant="outline" onClick={handlePickFiles} className="gap-2">
                        <FolderOpen className="size-4" />
                        Choose files
                      </Button>

                      {desktopPaths.length > 0 ? (
                        <div className="space-y-2">
                          {desktopPaths.map((path, index) => (
                            <div
                              key={`${path}-${index}`}
                              className="flex items-center justify-between gap-3 rounded-2xl border border-white/8 bg-white/4 px-4 py-3 text-sm"
                            >
                              <span className="truncate font-mono text-xs text-slate-300">{path}</span>
                              <button
                                type="button"
                                onClick={() => setDesktopPaths((current) => current.filter((_, itemIndex) => itemIndex !== index))}
                                className="text-slate-400 transition-colors hover:text-white"
                              >
                                <X className="size-4" />
                              </button>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="text-sm text-slate-300">
                          Use the native picker to bring PDFs, Markdown, notes, or research folders into orbit.
                        </p>
                      )}

                      {pickError ? (
                        <p className="flex items-center gap-2 text-sm text-rose-300">
                          <AlertCircle className="size-4" />
                          {pickError}
                        </p>
                      ) : null}
                    </div>
                  ) : null}

                  {tab === "upload" ? (
                    <div className="space-y-4">
                      <button
                        type="button"
                        onClick={() => fileInputRef.current?.click()}
                        className="flex w-full flex-col items-center justify-center rounded-[1.5rem] border border-dashed border-primary/28 bg-primary/6 px-6 py-12 text-center transition-all duration-200 hover:border-primary/46 hover:bg-primary/10"
                      >
                        <UploadCloud className="size-11 text-primary" />
                        <p className="mt-4 font-medium text-white">Drop or select files to index</p>
                        <p className="mt-2 text-sm text-slate-300">
                          Great for PDFs, Markdown, docs, transcripts, and mixed research sets.
                        </p>
                      </button>
                      <input
                        ref={fileInputRef}
                        type="file"
                        multiple
                        className="hidden"
                        onChange={(event) => {
                          setSelectedFiles(Array.from(event.target.files ?? []));
                          setUploadedPaths([]);
                          setUploadError(null);
                        }}
                      />

                      {selectedFiles.length > 0 ? (
                        <div className="space-y-2">
                          {selectedFiles.map((file, index) => (
                            <div
                              key={`${file.name}-${index}`}
                              className="flex items-center justify-between gap-3 rounded-2xl border border-white/8 bg-white/4 px-4 py-3 text-sm"
                            >
                              <span className="truncate text-slate-100">{file.name}</span>
                              <button
                                type="button"
                                onClick={() => {
                                  setSelectedFiles((current) => current.filter((_, itemIndex) => itemIndex !== index));
                                  setUploadedPaths([]);
                                }}
                                className="text-slate-400 transition-colors hover:text-white"
                              >
                                <X className="size-4" />
                              </button>
                            </div>
                          ))}
                        </div>
                      ) : null}

                      {uploadError ? (
                        <p className="flex items-center gap-2 text-sm text-rose-300">
                          <AlertCircle className="size-4" />
                          {uploadError}
                        </p>
                      ) : null}

                      {uploadedPaths.length > 0 ? (
                        <p className="flex items-center gap-2 text-sm text-emerald-300">
                          <CheckCircle2 className="size-4" />
                          {uploadedPaths.length} file{uploadedPaths.length === 1 ? "" : "s"} uploaded and ready.
                        </p>
                      ) : null}

                      {selectedFiles.length > 0 && uploadedPaths.length === 0 ? (
                        <Button onClick={handleUpload} disabled={uploading} className="gap-2">
                          {uploading ? <Loader2 className="size-4 animate-spin" /> : <UploadCloud className="size-4" />}
                          {uploading ? "Uploading..." : "Upload files"}
                        </Button>
                      ) : null}
                    </div>
                  ) : null}

                  {tab === "paths" ? (
                    <div className="space-y-4">
                      <div className="rounded-[1.35rem] border border-[#d6b361]/20 bg-[#d6b361]/8 px-4 py-3 text-sm leading-7 text-[#ebd7a3]">
                        Use this when the METIS API can already read the filesystem paths directly, such as a desktop sidecar or self-hosted workspace.
                      </div>

                      <label className="flex items-center gap-3 text-sm text-slate-300">
                        <input
                          type="checkbox"
                          checked={pathsConsent}
                          onChange={(event) => setPathsConsent(event.target.checked)}
                          className="size-4 rounded accent-primary"
                        />
                        I understand these paths must be accessible to the local API.
                      </label>

                      {pathsConsent ? (
                        <Textarea
                          placeholder={"/home/user/docs/report.pdf\n/home/user/docs/notes.md"}
                          value={rawPaths}
                          onChange={(event) => setRawPaths(event.target.value)}
                          rows={6}
                          className="font-mono text-xs"
                        />
                      ) : null}
                    </div>
                  ) : null}
                </div>

                <div className="rounded-[1.6rem] border border-white/10 bg-black/18 p-4 sm:p-5">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <h4 className="font-display text-xl font-semibold tracking-[-0.04em] text-white">
                        Build index
                      </h4>
                      <p className="mt-2 text-sm leading-7 text-slate-300">
                        Turn the selected material into a searchable index and attach it to this star.
                      </p>
                    </div>
                    <Badge variant="outline" className="border-white/12 bg-white/6 text-slate-200">
                      {building ? "Building" : readyPaths.length > 0 ? "Ready" : "Waiting on docs"}
                    </Badge>
                  </div>

                  <div className="mt-5 flex flex-wrap gap-3">
                    <Button onClick={handleBuild} disabled={building || readyPaths.length === 0} className="gap-2">
                      {building ? <Loader2 className="size-4 animate-spin" /> : <Database className="size-4" />}
                      {building ? "Building..." : "Add and build"}
                    </Button>
                    {buildResult ? (
                      <Button
                        variant="outline"
                        onClick={() => {
                          const nextLabel = labelDraft.trim() || activeStar.label || buildResult.index_id;
                          onOpenChat({
                            manifestPath: activeManifestPathForChat || buildResult.manifest_path,
                            label: nextLabel,
                          });
                        }}
                      >
                        Open chat
                      </Button>
                    ) : null}
                  </div>

                  {building || progress.reading !== "idle" ? (
                    <div className="mt-5 space-y-3">
                      {(
                        [
                          ["reading", "Reading documents"],
                          ["embedding", "Computing embeddings"],
                          ["saved", "Linking the star"],
                        ] as const
                      ).map(([key, label]) => (
                        <div key={key} className="flex items-center gap-3 text-sm">
                          {progress[key] === "done" ? (
                            <CheckCircle2 className="size-4 text-emerald-300" />
                          ) : progress[key] === "active" ? (
                            <Loader2 className="size-4 animate-spin text-primary" />
                          ) : (
                            <Circle className="size-4 text-slate-500" />
                          )}
                          <span className={progress[key] === "active" ? "text-white" : "text-slate-300"}>
                            {label}
                          </span>
                        </div>
                      ))}
                    </div>
                  ) : null}

                  {buildError ? (
                    <p className="mt-4 flex items-center gap-2 text-sm text-rose-300">
                      <AlertCircle className="size-4" />
                      {buildError}
                    </p>
                  ) : null}
                </div>
              </div>
            ) : (
              <div className="space-y-6">
                {attachedIndexes.length > 0 ? (
                  <div className="space-y-6">
                    <div className="rounded-[1.6rem] border border-white/10 bg-black/18 p-5">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div>
                          <div className="text-[11px] uppercase tracking-[0.28em] text-slate-400">Active chat index</div>
                          <h3 className="mt-2 font-display text-2xl font-semibold tracking-[-0.04em] text-white">
                            {activeIndex?.index_id || activeManifestPathForChat || "No active index"}
                          </h3>
                        </div>
                        {activeIndex ? (
                          <Badge variant="outline" className="border-white/12 bg-white/6 text-slate-200">
                            Active
                          </Badge>
                        ) : null}
                      </div>

                      {activeIndex ? (
                        <div className="mt-5 grid gap-3 sm:grid-cols-3">
                          <div className="rounded-2xl border border-white/8 bg-white/4 px-4 py-3">
                            <div className="text-[11px] uppercase tracking-[0.24em] text-slate-400">Documents</div>
                            <div className="mt-2 text-2xl font-semibold text-white">{activeIndex.document_count}</div>
                          </div>
                          <div className="rounded-2xl border border-white/8 bg-white/4 px-4 py-3">
                            <div className="text-[11px] uppercase tracking-[0.24em] text-slate-400">Chunks</div>
                            <div className="mt-2 text-2xl font-semibold text-white">{activeIndex.chunk_count}</div>
                          </div>
                          <div className="rounded-2xl border border-white/8 bg-white/4 px-4 py-3">
                            <div className="text-[11px] uppercase tracking-[0.24em] text-slate-400">Backend</div>
                            <div className="mt-2 text-base font-medium text-white">{activeIndex.backend}</div>
                          </div>
                        </div>
                      ) : (
                        <div className="mt-5 rounded-2xl border border-dashed border-white/12 bg-black/10 px-4 py-4 text-sm leading-7 text-slate-300">
                          No active index is selected yet. Pick one from the attached rail to launch grounded chat.
                        </div>
                      )}

                      <p className="mt-5 text-sm leading-7 text-slate-300">
                        This star routes chat through one active index at a time, while keeping every attached source in orbit.
                      </p>
                    </div>

                    <div className="rounded-[1.6rem] border border-white/10 bg-black/18 p-5">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div>
                          <div className="text-[11px] uppercase tracking-[0.28em] text-slate-400">Attached indexes</div>
                          <div className="mt-2 text-sm text-slate-300">
                            {attachedIndexes.length} source{attachedIndexes.length === 1 ? "" : "s"} are attached to this star.
                          </div>
                        </div>
                        <Badge variant="outline" className="border-white/12 bg-white/6 text-slate-200">
                          {attachedIndexes.length}
                        </Badge>
                      </div>

                      <div className="mt-4 space-y-2">
                        {attachedIndexes.map((index) => {
                          const isActive = index.manifest_path === activeManifestPathForChat;
                          return (
                            <div
                              key={index.manifest_path}
                              className={cn(
                                "flex items-start justify-between gap-3 rounded-2xl border px-4 py-3 transition-colors",
                                isActive
                                  ? "border-[#d6b361]/30 bg-[#d6b361]/8"
                                  : "border-white/8 bg-white/4 hover:border-primary/30 hover:bg-primary/8",
                              )}
                            >
                              <div className="min-w-0">
                                <div className="truncate font-medium text-white">{index.index_id}</div>
                                <div className="mt-1 flex flex-wrap gap-3 text-xs text-slate-400">
                                  <span>{index.document_count} docs</span>
                                  <span>{index.chunk_count} chunks</span>
                                  {index.created_at ? <span>{formatDate(index.created_at)}</span> : null}
                                </div>
                              </div>
                              <div className="flex flex-wrap items-center justify-end gap-2">
                                <button
                                  type="button"
                                  onClick={() => handleSetActiveManifestPath(index.manifest_path)}
                                  className={cn(
                                    "rounded-full px-3 py-1.5 text-xs transition-all",
                                    isActive
                                      ? "bg-[#d6b361]/18 text-[#f5d899]"
                                      : "bg-white/8 text-slate-200 hover:bg-white/12",
                                  )}
                                >
                                  {isActive ? "Active" : "Set active"}
                                </button>
                                <button
                                  type="button"
                                  onClick={() => void handleDetachIndex(index.manifest_path)}
                                  className="rounded-full bg-white/8 px-3 py-1.5 text-xs text-slate-200 transition-all hover:bg-white/12 hover:text-white"
                                >
                                  Detach
                                </button>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>

                    {suggestedIndexes.length > 0 ? (
                      <div className="rounded-[1.6rem] border border-white/10 bg-black/18 p-5">
                        <div className="flex flex-wrap items-center justify-between gap-3">
                          <div>
                            <div className="text-[11px] uppercase tracking-[0.28em] text-slate-400">More to attach</div>
                            <div className="mt-2 text-sm text-slate-300">
                              Add one of these indexes to the star without replacing anything already attached.
                            </div>
                          </div>
                          <Badge variant="outline" className="border-white/12 bg-white/6 text-slate-200">
                            {suggestedIndexes.length}
                          </Badge>
                        </div>

                        <div className="mt-4 space-y-2">
                          {suggestedIndexes.map((index) => (
                            <button
                              key={index.manifest_path}
                              type="button"
                              onClick={() => void handleLinkExistingIndex(index)}
                              className="flex w-full items-start justify-between gap-3 rounded-2xl border border-white/8 bg-black/18 px-4 py-3 text-left transition-colors hover:border-primary/30 hover:bg-primary/8"
                            >
                              <div className="min-w-0">
                                <div className="truncate font-medium text-white">{index.index_id}</div>
                                <div className="mt-1 flex flex-wrap gap-3 text-xs text-slate-400">
                                  <span>{index.document_count} docs</span>
                                  <span>{index.chunk_count} chunks</span>
                                </div>
                              </div>
                              <span className="text-xs text-primary">Attach</span>
                            </button>
                          ))}
                        </div>
                      </div>
                    ) : null}
                  </div>
                ) : (
                  <div className="rounded-[1.6rem] border border-dashed border-white/12 bg-black/18 p-5">
                    <div className="flex items-center gap-3 text-white">
                      <Orbit className="size-5 text-[#d6b361]" />
                      <span className="font-medium">This star is not attached to an index yet.</span>
                    </div>
                    <p className="mt-3 text-sm leading-7 text-slate-300">
                      Build a new index or attach one of the indexed sources from the source rail.
                    </p>
                  </div>
                )}
              </div>
            )}
          </div>

          <aside className="border-t border-white/10 bg-[linear-gradient(180deg,rgba(12,16,28,0.98),rgba(8,11,20,0.96))] px-5 py-5 sm:px-6 sm:py-6">
            <div className="space-y-5">
              <div className="rounded-[1.5rem] border border-white/10 bg-white/4 p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="text-[11px] uppercase tracking-[0.28em] text-slate-400">Star meaning</div>
                    <div className="mt-2 text-sm text-slate-300">
                      Label the star, give it a domain, and describe the kind of thinking it should hold.
                    </div>
                  </div>
                  <Badge variant="outline" className="border-white/12 bg-white/6 text-slate-200">
                    {activeManifestPathForChat ? "Grounded" : "Unbound"}
                  </Badge>
                </div>

                <div className="mt-4 space-y-4">
                  <label className="space-y-2">
                    <span className="text-[11px] uppercase tracking-[0.26em] text-slate-400">Star label</span>
                    <Input
                      value={labelDraft}
                      onChange={(event) => setLabelDraft(event.target.value)}
                      placeholder="Name this star"
                    />
                  </label>

                  <div className="grid gap-4 sm:grid-cols-2">
                    <label className="space-y-2">
                      <span className="text-[11px] uppercase tracking-[0.26em] text-slate-400">What part of METIS does this strengthen?</span>
                      <Input
                        value={primaryDomainIdDraft}
                        onChange={(event) => setPrimaryDomainIdDraft(event.target.value)}
                        placeholder="knowledge"
                        list="constellation-faculties"
                      />
                    </label>

                    <label className="space-y-2">
                      <span className="text-[11px] uppercase tracking-[0.26em] text-slate-400">Growth stage</span>
                      <select
                        value={effectiveStage}
                        onChange={(event) => {
                          const nextStage = event.target.value as UserStarStage;
                          setManualStageOverride(nextStage === derivedStage ? "" : nextStage);
                        }}
                        className="flex h-10 w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm text-white shadow-xs outline-none transition-[color,box-shadow] focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
                      >
                        {STAGE_OPTIONS.map((option) => (
                          <option key={option.value} value={option.value} className="bg-slate-950 text-white">
                            {option.label}
                          </option>
                        ))}
                      </select>
                      <p className="text-xs leading-6 text-slate-400">
                        {STAGE_OPTIONS.find((option) => option.value === effectiveStage)?.description}
                      </p>
                    </label>
                  </div>

                  <label className="space-y-2">
                    <span className="text-[11px] uppercase tracking-[0.26em] text-slate-400">Bridge faculties</span>
                    <Input
                      value={relatedDomainIdsDraft}
                      onChange={(event) => setRelatedDomainIdsDraft(event.target.value)}
                      placeholder="memory, strategy"
                      list="constellation-faculties"
                    />
                    <p className="text-xs leading-6 text-slate-400">
                      Optional bridge faculties, comma-separated. Use one when a star should sit between domains.
                    </p>
                  </label>

                  <label className="space-y-2">
                    <span className="text-[11px] uppercase tracking-[0.26em] text-slate-400">What is this star for?</span>
                    <Textarea
                      value={intentDraft}
                      onChange={(event) => setIntentDraft(event.target.value)}
                      rows={3}
                      placeholder="What should this star help you decide, remember, or compare?"
                    />
                  </label>

                  <label className="space-y-2">
                    <span className="text-[11px] uppercase tracking-[0.26em] text-slate-400">Supporting notes</span>
                    <Textarea
                      value={notesDraft}
                      onChange={(event) => setNotesDraft(event.target.value)}
                      rows={4}
                      placeholder="Extra reminders, caveats, or context that keeps the star grounded."
                    />
                  </label>
                </div>

                <div className="mt-4 flex flex-wrap gap-2">
                  <Badge variant="outline" className="border-white/12 bg-white/6 text-slate-200">
                    {attachedManifestPaths.length} attached
                  </Badge>
                  <Badge variant="outline" className="border-white/12 bg-white/6 text-slate-200">
                    {activeManifestPathForChat ? "Active chat selected" : "No active chat"}
                  </Badge>
                </div>

                <datalist id="constellation-faculties">
                  {CONSTELLATION_FACULTIES.map((faculty) => (
                    <option key={faculty.id} value={faculty.id}>
                      {faculty.label}
                    </option>
                  ))}
                </datalist>
              </div>

              <div className="rounded-[1.5rem] border border-white/10 bg-white/4 p-4">
                <div className="text-[11px] uppercase tracking-[0.28em] text-slate-400">Source rail</div>
                <div className="mt-3 flex items-center gap-3">
                  <div className="size-3 rounded-full bg-[#d6b361] shadow-[0_0_24px_rgba(214,179,97,0.7)]" />
                  <div>
                    <div className="text-sm font-medium text-white">
                      {labelDraft.trim() || star.label || "Untitled star"}
                    </div>
                    <div className="text-sm text-slate-300">
                      {activeIndex ? "Linked and chat-ready" : "Awaiting an index"}
                    </div>
                  </div>
                </div>
              </div>

              <LearningRoutePanel
                route={displayedLearningRoute}
                previewActive={learningRoutePreview !== null}
                eligible={hasCourseSource}
                loading={learningRouteLoading}
                error={learningRouteError}
                unavailableManifestPaths={unavailableManifestPaths}
                onStartCourse={onStartCourse}
                onSaveRoute={onSaveLearningRoutePreview}
                onDiscardPreview={onDiscardLearningRoutePreview}
                onRegenerateRoute={onRegenerateLearningRoute}
                onLaunchStep={onLaunchLearningRouteStep}
                onSetStepStatus={onSetLearningRouteStepStatus}
              />

              {statusMessage ? (
                <div
                  className={cn(
                    "rounded-[1.4rem] border px-4 py-3 text-sm",
                    statusTone === "error"
                      ? "border-rose-400/20 bg-rose-400/10 text-rose-200"
                      : "border-emerald-400/20 bg-emerald-400/10 text-emerald-100",
                  )}
                >
                  {statusMessage}
                </div>
              ) : null}

              {buildResult ? (
                <div className="rounded-[1.5rem] border border-emerald-400/20 bg-emerald-400/10 p-4">
                  <div className="text-[11px] uppercase tracking-[0.28em] text-emerald-200">Latest build</div>
                  <div className="mt-2 text-lg font-semibold text-white">{buildResult.index_id}</div>
                  <div className="mt-3 flex flex-wrap gap-3 text-sm text-emerald-100/90">
                    <span>{buildResult.document_count} docs</span>
                    <span>{buildResult.chunk_count} chunks</span>
                  </div>
                  <div className="mt-4 text-sm leading-7 text-emerald-100/85">
                    This build is attached to the star and set active until you choose another orbit.
                  </div>
                </div>
              ) : null}

              <div className="rounded-[1.5rem] border border-white/10 bg-white/4 p-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="text-[11px] uppercase tracking-[0.28em] text-slate-400">Indexed sources</div>
                    <div className="mt-2 text-sm text-slate-300">
                      {indexesLoading ? "Refreshing orbit…" : `${availableIndexes.length} ready to attach`}
                    </div>
                  </div>
                  <Badge variant="outline" className="border-white/12 bg-white/6 text-slate-200">
                    {availableIndexes.length}
                  </Badge>
                </div>

                {suggestedIndexes.length > 0 ? (
                  <div className="mt-4 space-y-2">
                    {suggestedIndexes.map((index) => (
                      <button
                        key={index.manifest_path}
                        type="button"
                        onClick={() => void handleLinkExistingIndex(index)}
                        className="flex w-full items-start justify-between gap-3 rounded-2xl border border-white/8 bg-black/18 px-4 py-3 text-left transition-colors hover:border-primary/30 hover:bg-primary/8"
                      >
                        <div className="min-w-0">
                          <div className="truncate font-medium text-white">{index.index_id}</div>
                          <div className="mt-1 flex flex-wrap gap-3 text-xs text-slate-400">
                            <span>{index.document_count} docs</span>
                            <span>{index.chunk_count} chunks</span>
                          </div>
                        </div>
                        <span className="text-xs text-primary">Attach</span>
                      </button>
                    ))}
                  </div>
                ) : (
                  <p className="mt-4 text-sm leading-7 text-slate-300">
                    {indexesLoading
                      ? "Loading indexed sources."
                      : "No other indexed sources are available yet. Build one here to give the star grounded memory."}
                  </p>
                )}
              </div>

            </div>
          </aside>
          </div>

          <div
            className="border-t border-white/10 bg-[linear-gradient(180deg,rgba(12,16,28,0.98),rgba(8,11,20,0.98))] px-5 py-4 sm:px-6"
            data-testid="star-details-actions"
          >
            <div className="flex flex-wrap gap-3">
              <Button onClick={() => void handleSaveMeta()} disabled={savingMeta || removing} className="gap-2">
                {savingMeta ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
                Save meaning
              </Button>
              <Button
                variant="outline"
                onClick={() => {
                  if (!activeManifestPathForChat) {
                    return;
                  }
                  const linkedLabel = labelDraft.trim() || activeStar.label || activeIndex?.index_id || "Mapped star";
                  onOpenChat({
                    manifestPath: activeManifestPathForChat,
                    label: linkedLabel,
                  });
                }}
                disabled={!activeManifestPathForChat || removing}
              >
                Open chat
              </Button>
              <Button variant="outline" onClick={() => setView("build")} disabled={removing}>
                Add another source
              </Button>
              {entryMode === "existing" ? (
                <Button
                  variant="destructive"
                  onClick={() => setDeleteConfirmOpen(true)}
                  disabled={removing}
                  className="gap-2"
                >
                  <Trash2 className="size-4" />
                  Delete star and sources
                </Button>
              ) : null}
            </div>
          </div>
        </div>
      </DialogContent>

      <Dialog open={deleteConfirmOpen} onOpenChange={setDeleteConfirmOpen}>
        <DialogContent className="max-w-md" data-testid="star-delete-confirmation">
          <DialogHeader className="gap-3">
            <DialogTitle className="font-display text-2xl tracking-[-0.04em] text-white">
              Delete this star and its sources?
            </DialogTitle>
            <DialogDescription className="text-sm leading-7 text-slate-300">
              This will delete the star and purge every METIS-managed index attached to it. Your original local files will remain on disk, but the indexed sources and chat-ready artifacts will be removed permanently.
            </DialogDescription>
          </DialogHeader>

          <div className="rounded-[1.3rem] border border-rose-400/20 bg-rose-400/10 px-4 py-3 text-sm leading-7 text-rose-100">
            This action cannot be undone.
          </div>

          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <Button variant="outline" onClick={() => setDeleteConfirmOpen(false)} disabled={removing}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => void handleRemoveStar()}
              disabled={removing}
              className="gap-2"
            >
              {removing ? <Loader2 className="size-4 animate-spin" /> : <Trash2 className="size-4" />}
              {removing ? "Deleting..." : "Delete star and sources"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </Dialog>
  );
}

/* ─────────────────── Faculty concept panel ─────────────────────────── */

interface FacultyConceptPanelProps {
  open: boolean;
  onClose: () => void;
  concept: { label: string; title: string; desc: string } | null;
}

export function FacultyConceptPanel({ open, onClose, concept }: FacultyConceptPanelProps) {
  if (!concept) return null;
  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent
        className="left-1/2 top-auto bottom-3 flex h-[calc(100vh-1.5rem)] max-h-[calc(100vh-1.5rem)] w-[calc(100%-1.5rem)] max-w-[calc(100%-1.5rem)] -translate-x-1/2 translate-y-0 flex-col gap-0 overflow-hidden rounded-[1.75rem] border-white/12 bg-[linear-gradient(180deg,rgba(14,20,34,0.98),rgba(8,11,20,0.96))] p-0 sm:left-auto sm:right-4 sm:top-4 sm:bottom-4 sm:h-[calc(100vh-2rem)] sm:max-h-[calc(100vh-2rem)] sm:w-[min(460px,calc(100vw-2rem))] sm:max-w-[460px] sm:translate-x-0 sm:translate-y-0"
        showOverlay={false}
      >
        <div className="border-b border-white/10 bg-[linear-gradient(180deg,rgba(14,20,34,0.98),rgba(10,13,23,0.92))] px-5 py-5 sm:px-6">
          <DialogHeader className="gap-3 pr-10">
            <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.32em] text-[#d6b361]">
              <Orbit className="size-3.5" />
              {concept.label}
            </div>
            <DialogTitle className="font-display text-3xl font-semibold tracking-[-0.05em] text-white">
              {concept.title}
            </DialogTitle>
            <DialogDescription className="text-sm leading-7 text-slate-300">
              {concept.desc}
            </DialogDescription>
          </DialogHeader>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-5 sm:px-6">
          <p className="text-sm leading-relaxed text-slate-400">
            Faculty nodes are the gravitational poles of the constellation. Drag your stars toward{" "}
            <span className="text-slate-200">{concept.title}</span> to align them with this domain, or add a new star near this node to begin building knowledge here.
          </p>
        </div>
      </DialogContent>
    </Dialog>
  );
}
