"use client";

import { useEffect, useRef } from "react";
import * as THREE from "three";
import type { MutableRefObject } from "react";
import { getStarVisualArchetypeId } from "@/lib/landing-stars/star-visual-archetype";
import type { LandingWebglStar, LandingStarfieldFrame, LandingStarRenderTier } from "./landing-starfield-webgl.types";

export type { LandingWebglStar, LandingStarfieldFrame } from "./landing-starfield-webgl.types";

interface LandingStarfieldWebglProps {
  className?: string;
  frameRef: MutableRefObject<LandingStarfieldFrame>;
}

const vertexShader = `
attribute vec4 aColorA;
attribute vec4 aColorB;
attribute vec4 aColorC;
attribute vec4 aShape;
attribute vec2 aTwinkle;
attribute float aArchetype;

uniform float uDpr;
uniform float uTime;
uniform float uZoomScale;
uniform vec2 uFocusCenter;
uniform float uFocusStrength;
uniform float uFocusRadius;
uniform float uFocusFalloff;

varying float vAddable;
varying float vBloom;
varying float vBrightness;
varying float vCoreRadius;
varying float vDiffraction;
varying float vTier;
varying float vTwinkle;
varying float vFocusDim;
varying float vFocusBlur;
varying float vArchetype;
varying float vArchetypePulse;
varying vec3 vAccentColor;
varying vec3 vCoreColor;
varying vec3 vHaloColor;

void main() {
  vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
  gl_Position = projectionMatrix * mvPosition;

  float twinkle = 0.92 + sin(uTime * aTwinkle.y + aTwinkle.x) * 0.08;
  float tierBoost = aShape.w > 1.5 ? 1.45 : (aShape.w > 0.5 ? 1.18 : 1.0);
  float heroGlow = aShape.w > 1.5 ? 1.0 + aColorC.w * 0.32 : 1.0;
  float zoomSizeScale = mix(0.15, 1.0, smoothstep(0.0, 0.4, uZoomScale));

  // Depth-of-field-like falloff from the dive focus centre. The focused star
  // (closeup tier, aShape.w > 2.5) keeps its full size; ambient stars dim and
  // bloom outward as the viewer settles on the target.
  float focusDist = distance(position.xy, uFocusCenter);
  float outsideFocus = smoothstep(uFocusRadius, uFocusRadius + max(1.0, uFocusFalloff), focusDist);
  float isFocused = step(2.5, aShape.w);
  float falloff = outsideFocus * uFocusStrength * (1.0 - isFocused);
  // Ambient stars: dim up to 85%, broaden halo (blur) by up to 1.6x.
  float dim = 1.0 - falloff * 0.85;
  float blur = 1.0 + falloff * 0.6;

  // Archetype branches only fire for the closeup (focused) star. Other
  // tiers ignore archetype so point / sprite / hero rendering stays
  // untouched. Archetype ids come from STAR_VISUAL_ARCHETYPE_IDS and are
  // the ABI between this shader and the CPU attribute packer.
  float archetypePulse = 1.0;
  float archetypeSizeScale = 1.0;
  if (isFocused > 0.5) {
    // Pulsar (id 1): ~3 Hz size pulsation on top of twinkle.
    if (aArchetype > 0.5 && aArchetype < 1.5) {
      archetypePulse = 1.0 + sin(uTime * 18.85) * 0.18;
    }
    // Quasar (id 2): steady bright, modest size so the jets in the
    // fragment stage have a visible host disc.
    else if (aArchetype > 1.5 && aArchetype < 2.5) {
      archetypeSizeScale = 1.22;
      archetypePulse = 1.0 + sin(uTime * 8.0) * 0.06;
    }
    // Brown dwarf (id 3): dim and small so the rendered disc feels
    // intrinsically weak.
    else if (aArchetype > 2.5 && aArchetype < 3.5) {
      archetypeSizeScale = 0.75;
    }
    // Red giant (id 4): slow ~0.5 Hz swell, mild point-size bloat so the
    // warm bloom reads as physically large.
    else if (aArchetype > 3.5 && aArchetype < 4.5) {
      archetypePulse = 1.0 + sin(uTime * 3.14) * 0.06;
      archetypeSizeScale = 1.12;
    }
    // Binary (id 5): give the sprite enough canvas for a companion blob
    // alongside the primary.
    else if (aArchetype > 4.5 && aArchetype < 5.5) {
      archetypeSizeScale = 1.18;
    }
    // Nebula (id 6): no sharp core at all — give the sprite more canvas
    // so the diffuse cloud effect in the fragment stage can spread.
    else if (aArchetype > 5.5 && aArchetype < 6.5) {
      archetypeSizeScale = 1.18;
    }
    // Comet (id 8): tail extends across the sprite; needs more canvas.
    // Starter implementation renders the tail inside a single point
    // sprite via UV space (ADR 0006 suggests sprite strip or per-frame
    // offset buffer as a follow-up for true motion trails).
    else if (aArchetype > 7.5 && aArchetype < 8.5) {
      archetypeSizeScale = 1.35;
    }
    // Constellation (id 9): multi-point pattern needs canvas too.
    else if (aArchetype > 8.5 && aArchetype < 9.5) {
      archetypeSizeScale = 1.32;
    }
    // Variable (id 10): irregular brightness. Two overlapping sines with
    // incommensurate periods give a non-repeating feel within the
    // demo-length dive.
    else if (aArchetype > 9.5 && aArchetype < 10.5) {
      archetypePulse = 1.0
        + sin(uTime * 4.2) * 0.09
        + sin(uTime * 1.7 + 1.1) * 0.05;
    }
    // Wolf-Rayet (id 11): energetic, slightly larger, rapid flare beat.
    else if (aArchetype > 10.5 && aArchetype < 11.5) {
      archetypeSizeScale = 1.08;
      archetypePulse = 1.0 + sin(uTime * 11.0) * 0.1;
    }
  }

  gl_PointSize = max(1.0, aShape.z * uDpr * tierBoost * heroGlow * twinkle * zoomSizeScale * blur * archetypePulse * archetypeSizeScale);

  vAddable = aColorA.w;
  vBloom = aColorC.w;
  vBrightness = aColorB.w;
  vCoreRadius = aShape.x;
  vDiffraction = aShape.y;
  vTier = aShape.w;
  vTwinkle = twinkle;
  vFocusDim = dim;
  vFocusBlur = falloff;
  vArchetype = aArchetype;
  vArchetypePulse = archetypePulse;
  vAccentColor = aColorA.rgb;
  vCoreColor = aColorB.rgb;
  vHaloColor = aColorC.rgb;
}
`;

const fragmentShader = `
uniform float uTime;

varying float vAddable;
varying float vBloom;
varying float vBrightness;
varying float vCoreRadius;
varying float vDiffraction;
varying float vTier;
varying float vTwinkle;
varying float vFocusDim;
varying float vFocusBlur;
varying float vArchetype;
varying float vArchetypePulse;
varying vec3 vAccentColor;
varying vec3 vCoreColor;
varying vec3 vHaloColor;

float safeSmoothstep(float edge0, float edge1, float x) {
  if (edge0 == edge1) {
    return x < edge0 ? 0.0 : 1.0;
  }
  return smoothstep(edge0, edge1, x);
}

void main() {
  vec2 uv = gl_PointCoord * 2.0 - 1.0;
  float dist = length(uv);
  if (dist > 1.0) {
    discard;
  }

  // Archetype flags. Only fire on closeup tier. Ids come from
  // STAR_VISUAL_ARCHETYPE_IDS — see
  // apps/metis-web/lib/landing-stars/star-visual-archetype.ts.
  bool isCloseup = vTier > 2.5;
  bool isPulsar = isCloseup && vArchetype > 0.5 && vArchetype < 1.5;
  bool isQuasar = isCloseup && vArchetype > 1.5 && vArchetype < 2.5;
  bool isBrownDwarf = isCloseup && vArchetype > 2.5 && vArchetype < 3.5;
  bool isRedGiant = isCloseup && vArchetype > 3.5 && vArchetype < 4.5;
  bool isBinary = isCloseup && vArchetype > 4.5 && vArchetype < 5.5;
  bool isNebula = isCloseup && vArchetype > 5.5 && vArchetype < 6.5;
  bool isBlackHole = isCloseup && vArchetype > 6.5 && vArchetype < 7.5;
  bool isComet = isCloseup && vArchetype > 7.5 && vArchetype < 8.5;
  bool isConstellation = isCloseup && vArchetype > 8.5 && vArchetype < 9.5;
  bool isVariable = isCloseup && vArchetype > 9.5 && vArchetype < 10.5;
  bool isWolfRayet = isCloseup && vArchetype > 10.5 && vArchetype < 11.5;

  // Several archetypes repaint the sprite from scratch and should skip
  // the default halo/core/rim stack. Consolidate the flag so later
  // branches stay readable.
  bool suppressDefaultDisc = isNebula || isBlackHole || isComet || isConstellation;

  float tierBlend = vTier > 1.5 ? 1.0 : (vTier > 0.5 ? 0.6 : 0.0);
  float haloMask = safeSmoothstep(1.0, max(0.0, 0.16 + (1.0 - tierBlend) * 0.22), dist);
  float surfaceMask = safeSmoothstep(0.84, max(0.06, vCoreRadius * 1.95), dist);
  float coreMask = safeSmoothstep(max(0.72, vCoreRadius * 1.12), max(0.0, vCoreRadius * 0.18), dist);
  float rimMask = safeSmoothstep(0.98, 0.58, dist) * (1.0 - coreMask);

  vec3 surfaceColor = mix(vHaloColor, vCoreColor, 0.42);
  vec3 color = mix(vHaloColor, surfaceColor, surfaceMask);
  color = mix(color, vCoreColor, coreMask);
  color += vAccentColor * rimMask * (0.08 + tierBlend * 0.12);

  if (vTier > 1.5) {
    float swirl = sin(atan(uv.y, uv.x) * 3.0 + dist * 10.0);
    float accent = safeSmoothstep(0.88, 0.18, dist) * (0.08 + max(0.0, swirl) * 0.08) * vBloom;
    color += vAccentColor * accent;
  }

  // Red giant (id 4): warm-shift the base colour mix and widen the halo
  // so the disc reads as large and cool.
  if (isRedGiant) {
    vec3 warmTint = mix(vCoreColor, vec3(1.0, 0.56, 0.28), 0.42);
    color = mix(color, warmTint, 0.35);
  }

  // Brown dwarf (id 3): dim rust palette. Keep the star shape but mute
  // colour + bias toward a rust/accent blend. No pulsation.
  if (isBrownDwarf) {
    vec3 rust = vec3(0.6, 0.3, 0.15);
    color = mix(color, rust, 0.55);
  }

  // Wolf-Rayet (id 11): energetic hot-star spectrum with radial wind
  // bands. Tint toward blue/violet and overlay a high-frequency band
  // pattern that animates outward to read as stellar wind.
  if (isWolfRayet) {
    vec3 hotTint = vec3(0.6, 0.78, 1.0);
    color = mix(color, hotTint, 0.38);
    float windBand = 0.5 + 0.5 * sin(dist * 26.0 - uTime * 8.0);
    color += mix(vHaloColor, vAccentColor, 0.5) * windBand * (1.0 - dist) * 0.2;
  }

  // Nebula (id 6): replace the sharp star look with a diffuse, noise-
  // modulated cloud. Angular + radial sines break the smooth circle into a
  // patchy glow; the accent channel carries wisps. No hard core survives.
  if (isNebula) {
    float ang = atan(uv.y, uv.x);
    float cloud = 0.5
      + 0.25 * sin(ang * 3.0 + dist * 6.0)
      + 0.15 * sin(ang * 7.0 - dist * 11.0 + vTwinkle * 3.0);
    cloud = clamp(cloud, 0.0, 1.0);
    vec3 cloudColor = mix(vHaloColor, vAccentColor, 0.55);
    color = mix(color, cloudColor * (0.55 + cloud * 0.55), 0.82);
  }

  // Black hole (id 7): crush the inner disc to near-black; draw a
  // luminous accretion ring at ~0.55..0.72 radius; keep a faint bent-light
  // halo just outside it. The halo/accent colours drive the ring hue.
  if (isBlackHole) {
    float ringMask = safeSmoothstep(0.53, 0.6, dist) * (1.0 - safeSmoothstep(0.72, 0.82, dist));
    vec3 ringColor = mix(vHaloColor, vAccentColor, 0.4) * 1.6;
    float darken = 1.0 - safeSmoothstep(0.5, 0.0, dist);
    color = mix(vec3(0.0), color, darken);
    color += ringColor * ringMask;
  }

  // Quasar (id 2): host disc + two opposing polar jets along the y axis.
  // Jet mask widens radially so the lobes feel energetic at the poles.
  if (isQuasar) {
    float jetWidth = exp(-abs(uv.x) * 8.0);
    float jetExtent = smoothstep(0.25, 1.0, abs(uv.y));
    float jet = jetWidth * jetExtent * (0.7 + 0.3 * sin(uTime * 6.0 + abs(uv.y) * 10.0));
    vec3 jetColor = mix(vAccentColor, vec3(0.85, 0.95, 1.0), 0.35);
    color += jetColor * jet * 0.9;
  }

  // Binary (id 5): primary at centre + companion blob orbiting at ~0.6
  // radius. Companion position rotates slowly around the primary so the
  // pair reads as a bound system.
  if (isBinary) {
    float phase = uTime * 1.6;
    vec2 companion = vec2(cos(phase), sin(phase)) * 0.6;
    float companionDist = length(uv - companion);
    float companionCore = safeSmoothstep(0.22, 0.04, companionDist);
    color += mix(vCoreColor, vAccentColor, 0.35) * companionCore * 0.9;
  }

  // Comet (id 8): head biased to the right, tail streaming left with
  // an exponential alpha/intensity falloff. Starter implementation —
  // ADR 0006 notes a sprite strip / per-frame offset buffer as the
  // richer long-term option.
  if (isComet) {
    vec2 headPos = vec2(0.45, 0.0);
    float headDist = length(uv - headPos);
    float head = safeSmoothstep(0.26, 0.0, headDist);
    float tailX = clamp((headPos.x - uv.x) / 1.5, 0.0, 1.0);
    float tailFalloff = exp(-tailX * 2.4);
    float tailSpread = exp(-pow(uv.y * 4.0, 2.0));
    float tail = tailFalloff * tailSpread * 0.75;
    vec3 headColor = mix(vCoreColor, vec3(1.0, 0.95, 0.8), 0.35);
    vec3 tailColor = mix(vHaloColor, vAccentColor, 0.55);
    color = mix(vec3(0.0), headColor, head) + tailColor * tail;
  }

  // Constellation (id 9): five anchors plus thin connecting links so the
  // closeup reads as a composite group. Fixed positions; the small
  // motion in uTime gives a gentle collective shimmer.
  if (isConstellation) {
    vec2 nodes[5];
    nodes[0] = vec2(0.0, -0.55);
    nodes[1] = vec2(-0.5, -0.1);
    nodes[2] = vec2(0.55, 0.05);
    nodes[3] = vec2(-0.15, 0.55);
    nodes[4] = vec2(0.3, 0.35);
    float pattern = 0.0;
    for (int i = 0; i < 5; i++) {
      pattern += safeSmoothstep(0.14, 0.0, length(uv - nodes[i]));
    }
    // Thin links between pairs 0→2, 2→4, 4→3, 3→1, 1→0.
    vec2 links[5];
    links[0] = nodes[2] - nodes[0];
    links[1] = nodes[4] - nodes[2];
    links[2] = nodes[3] - nodes[4];
    links[3] = nodes[1] - nodes[3];
    links[4] = nodes[0] - nodes[1];
    vec2 origins[5];
    origins[0] = nodes[0];
    origins[1] = nodes[2];
    origins[2] = nodes[4];
    origins[3] = nodes[3];
    origins[4] = nodes[1];
    float lineAcc = 0.0;
    for (int i = 0; i < 5; i++) {
      vec2 d = uv - origins[i];
      float t = clamp(dot(d, links[i]) / max(dot(links[i], links[i]), 0.0001), 0.0, 1.0);
      float perp = length(d - links[i] * t);
      lineAcc += safeSmoothstep(0.03, 0.0, perp);
    }
    vec3 nodeColor = mix(vCoreColor, vAccentColor, 0.4);
    vec3 linkColor = mix(vHaloColor, vAccentColor, 0.6) * 0.65;
    color = nodeColor * pattern + linkColor * lineAcc;
  }

  // Variable (id 10): oscillating brightness, no structural change. The
  // irregular dual-sine beat on vArchetypePulse flows through pulseAlpha
  // below; here we warm-shift the core mildly so the oscillation reads
  // as a living star rather than a flicker.
  if (isVariable) {
    vec3 warmPulse = mix(vCoreColor, vec3(1.0, 0.78, 0.45), 0.25 + 0.25 * (vArchetypePulse - 1.0));
    color = mix(color, warmPulse, 0.28);
  }

  // Pulsar (id 1): sharpened diffraction rays (×1.9 boost, steeper exp
  // falloff). Baseline + most archetypes keep the standard strength;
  // archetypes that repaint the sprite (nebula, black hole, comet,
  // constellation) or use opposing jets (quasar) or a companion blob
  // (binary) would read as visually wrong with the default cross, so we
  // suppress the diffraction stage for them.
  float diffractionBoost = isPulsar ? 1.9 : 1.0;
  float diffractionFalloff = isPulsar ? 19.0 : 13.0;
  bool skipDiffraction = suppressDefaultDisc || isQuasar || isBinary;

  if (vDiffraction > 0.02 && !skipDiffraction) {
    float crossX = exp(-abs(uv.x) * diffractionFalloff);
    float crossY = exp(-abs(uv.y) * diffractionFalloff);
    float diffraction = max(crossX, crossY) * (1.0 - dist) * vDiffraction * (0.18 + tierBlend * 0.2) * diffractionBoost;
    color += vAccentColor * diffraction;
  }

  if (vAddable > 0.5) {
    color = mix(color, vec3(0.95, 0.82, 0.55), 0.12);
  }

  // Archetype alpha adjustments. Each archetype tunes halo/core/rim alpha
  // and an overall pulse term independently.
  float haloScale = 1.0;
  float coreScale = 1.0;
  float rimScale = 1.0;
  float pulseAlpha = 1.0;
  if (isPulsar) {
    haloScale = 0.72;
    coreScale = 1.35;
    pulseAlpha = 0.85 + vArchetypePulse * 0.3;
  } else if (isQuasar) {
    haloScale = 0.65;
    coreScale = 1.2;
    pulseAlpha = 0.95 + vArchetypePulse * 0.08;
  } else if (isBrownDwarf) {
    haloScale = 0.55;
    coreScale = 0.75;
    rimScale = 0.6;
  } else if (isRedGiant) {
    haloScale = 1.18;
    coreScale = 0.92;
    pulseAlpha = 0.94 + vArchetypePulse * 0.12;
  } else if (isBinary) {
    // Primary disc a touch smaller so the companion blob reads.
    haloScale = 0.85;
    coreScale = 1.1;
  } else if (isVariable) {
    pulseAlpha = 0.7 + vArchetypePulse * 0.45;
  } else if (isWolfRayet) {
    haloScale = 1.05;
    coreScale = 1.15;
    pulseAlpha = 0.9 + vArchetypePulse * 0.18;
  } else if (suppressDefaultDisc) {
    // Nebula, black hole, comet, constellation all paint their own
    // silhouette; the default halo/core/rim stack would muddy the
    // intended look.
    haloScale = 0.0;
    coreScale = 0.0;
    rimScale = 0.0;
  }
  // Nebula still wants a soft ambient glow outside the cloud sines so
  // the star feels present — dial the halo back in partially.
  if (isNebula) {
    haloScale = 1.55;
    coreScale = 0.2;
    rimScale = 0.4;
  }

  float alphaBase = (0.18 + vBrightness * 0.46) * vTwinkle;
  float alpha = haloMask * alphaBase * haloScale + coreMask * 0.28 * coreScale + rimMask * 0.08 * rimScale;
  if (isBlackHole) {
    // Ring has its own mask; read it back so the pixel is visible even
    // though halo/core/rim scales are 0.
    float ringMask = safeSmoothstep(0.53, 0.6, dist) * (1.0 - safeSmoothstep(0.72, 0.82, dist));
    alpha = ringMask * (0.6 + vBrightness * 0.35);
  } else if (isComet) {
    // Comet owns its alpha from the head/tail masks. Recompute here so
    // the default alpha stack (zeroed via suppressDefaultDisc) doesn't
    // contribute.
    vec2 headPos = vec2(0.45, 0.0);
    float headDist = length(uv - headPos);
    float head = safeSmoothstep(0.26, 0.0, headDist);
    float tailX = clamp((headPos.x - uv.x) / 1.5, 0.0, 1.0);
    float tail = exp(-tailX * 2.4) * exp(-pow(uv.y * 4.0, 2.0));
    alpha = clamp(head * (0.7 + vBrightness * 0.3) + tail * 0.55, 0.0, 1.0);
  } else if (isConstellation) {
    // Constellation owns its alpha too — anchors + links each contribute.
    vec2 nodes[5];
    nodes[0] = vec2(0.0, -0.55);
    nodes[1] = vec2(-0.5, -0.1);
    nodes[2] = vec2(0.55, 0.05);
    nodes[3] = vec2(-0.15, 0.55);
    nodes[4] = vec2(0.3, 0.35);
    float nodeAlpha = 0.0;
    for (int i = 0; i < 5; i++) {
      nodeAlpha += safeSmoothstep(0.14, 0.0, length(uv - nodes[i]));
    }
    alpha = clamp(nodeAlpha * 0.9 + 0.08 * (1.0 - dist), 0.0, 1.0);
  }
  alpha = clamp(alpha * (0.9 + vBloom * 0.12) * pulseAlpha, 0.0, 1.0);

  // Depth-of-field: ambient stars dim and soften outside the focus radius.
  // vFocusBlur ∈ [0,1]; larger values shift alpha away from the core toward the halo.
  if (vFocusBlur > 0.001) {
    float softened = mix(alpha, alpha * 0.55 + haloMask * 0.1, vFocusBlur);
    alpha = softened;
  }
  alpha *= vFocusDim;

  gl_FragColor = vec4(color * (0.86 + vBrightness * 0.34) * vFocusDim, alpha);
}
`;

function normalizeRgb([red, green, blue]: readonly [number, number, number]) {
  return [red / 255, green / 255, blue / 255] as const;
}

function getTierValue(renderTier: LandingStarRenderTier): number {
  switch (renderTier) {
    case "closeup":
      return 3;
    case "hero":
      return 2;
    case "sprite":
      return 1;
    default:
      return 0;
  }
}

function getPointSize(star: LandingWebglStar) {
  const { visual } = star.profile;
  const tierScale =
    star.renderTier === "closeup"
      ? 12 + visual.haloRadiusFactor * 1.2
      : star.renderTier === "hero"
        ? 5.2 + visual.haloRadiusFactor * 0.42
        : star.renderTier === "sprite"
          ? 2.9 + visual.haloRadiusFactor * 0.16
          : 1.5;

  return Math.max(1.4, star.apparentSize * tierScale);
}

function canUseWebGl(): boolean {
  if (typeof document === "undefined") {
    return false;
  }

  try {
    const canvas = document.createElement("canvas");
    return Boolean(
      canvas.getContext("webgl2")
      || canvas.getContext("webgl")
      || canvas.getContext("experimental-webgl"),
    );
  } catch {
    return false;
  }
}

function fillStarAttributes(frame: LandingStarfieldFrame) {
  const stars = frame.stars;
  const starCount = stars.length;
  const positions = new Float32Array(starCount * 3);
  const colorA = new Float32Array(starCount * 4);
  const colorB = new Float32Array(starCount * 4);
  const colorC = new Float32Array(starCount * 4);
  const shape = new Float32Array(starCount * 4);
  const twinkle = new Float32Array(starCount * 2);
  const archetype = new Float32Array(starCount);

  for (let index = 0; index < starCount; index += 1) {
    const star = stars[index];
    const { palette, stellarType, visual, visualArchetype } = star.profile;
    const pointSize = getPointSize(star);
    const normalizedAccent = normalizeRgb(palette.accent);
    const normalizedCore = normalizeRgb(palette.core);
    const normalizedHalo = normalizeRgb(palette.halo);
    const attributeIndex = index * 3;
    const packedIndex = index * 4;
    const twinkleIndex = index * 2;
    const isDarkObject = stellarType === "BLACK_HOLE";

    positions[attributeIndex] = star.x;
    positions[attributeIndex + 1] = star.y;
    positions[attributeIndex + 2] = 0;
    colorA[packedIndex] = normalizedAccent[0];
    colorA[packedIndex + 1] = normalizedAccent[1];
    colorA[packedIndex + 2] = normalizedAccent[2];
    colorA[packedIndex + 3] = star.addable ? 1 : 0;
    colorB[packedIndex] = normalizedCore[0];
    colorB[packedIndex + 1] = normalizedCore[1];
    colorB[packedIndex + 2] = normalizedCore[2];
    colorB[packedIndex + 3] = star.brightness;
    colorC[packedIndex] = isDarkObject ? 0.12 : normalizedHalo[0];
    colorC[packedIndex + 1] = isDarkObject ? 0.16 : normalizedHalo[1];
    colorC[packedIndex + 2] = isDarkObject ? 0.22 : normalizedHalo[2];
    colorC[packedIndex + 3] = visual.bloomFactor;
    shape[packedIndex] = visual.coreRadiusFactor;
    shape[packedIndex + 1] = visual.diffractionStrength;
    shape[packedIndex + 2] = pointSize;
    shape[packedIndex + 3] = getTierValue(star.renderTier);
    twinkle[twinkleIndex] = visual.twinklePhase;
    twinkle[twinkleIndex + 1] = visual.twinkleSpeed * 500;
    archetype[index] = getStarVisualArchetypeId(visualArchetype);
  }

  return {
    archetype,
    colorA,
    colorB,
    colorC,
    positions,
    shape,
    twinkle,
  };
}

export function LandingStarfieldWebgl({ className, frameRef }: LandingStarfieldWebglProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || !canUseWebGl()) {
      return;
    }

    const scene = new THREE.Scene();
    const camera = new THREE.OrthographicCamera(0, 1, 0, 1, -1, 1);
    camera.position.z = 1;

    const geometry = new THREE.BufferGeometry();
    const material = new THREE.ShaderMaterial({
      blending: THREE.NormalBlending,
      depthTest: false,
      depthWrite: false,
      fragmentShader,
      transparent: true,
      uniforms: {
        uDpr: { value: 1 },
        uTime: { value: 0 },
        uZoomScale: { value: 1 },
        uFocusCenter: { value: new THREE.Vector2(0, 0) },
        uFocusStrength: { value: 0 },
        uFocusRadius: { value: 200 },
        uFocusFalloff: { value: 400 },
      },
      vertexShader,
    });
    const points = new THREE.Points(geometry, material);
    scene.add(points);

    const renderer = new THREE.WebGLRenderer({
      alpha: true,
      antialias: false,
      powerPreference: "high-performance",
    });
    renderer.sortObjects = false;
    renderer.setClearColor(0x06080e, 1);
    renderer.domElement.style.width = "100%";
    renderer.domElement.style.height = "100%";
    renderer.domElement.style.display = "block";
    container.appendChild(renderer.domElement);

    let frameHandle = 0;
    let lastRevision = -1;
    let lastWidth = 0;
    let lastHeight = 0;
    let lastPaintTime = 0;

    const updateRendererSize = (width: number, height: number) => {
      const safeWidth = Math.max(1, Math.round(width));
      const safeHeight = Math.max(1, Math.round(height));
      const dpr = Math.min(window.devicePixelRatio || 1, 1.8);

      if (safeWidth === lastWidth && safeHeight === lastHeight) {
        material.uniforms.uDpr.value = dpr;
        return;
      }

      lastWidth = safeWidth;
      lastHeight = safeHeight;
      renderer.setPixelRatio(dpr);
      renderer.setSize(safeWidth, safeHeight, false);
      material.uniforms.uDpr.value = dpr;
      camera.left = 0;
      camera.right = safeWidth;
      camera.top = 0;
      camera.bottom = safeHeight;
      camera.updateProjectionMatrix();
    };

    const updateGeometry = (frame: LandingStarfieldFrame) => {
      const attributes = fillStarAttributes(frame);

      geometry.setAttribute("position", new THREE.BufferAttribute(attributes.positions, 3));
      geometry.setAttribute("aColorA", new THREE.BufferAttribute(attributes.colorA, 4));
      geometry.setAttribute("aColorB", new THREE.BufferAttribute(attributes.colorB, 4));
      geometry.setAttribute("aColorC", new THREE.BufferAttribute(attributes.colorC, 4));
      geometry.setAttribute("aShape", new THREE.BufferAttribute(attributes.shape, 4));
      geometry.setAttribute("aTwinkle", new THREE.BufferAttribute(attributes.twinkle, 2));
      geometry.setAttribute("aArchetype", new THREE.BufferAttribute(attributes.archetype, 1));
      geometry.computeBoundingSphere();
    };

    const render = (timestampMs: number) => {
      frameHandle = window.requestAnimationFrame(render);
      const frame = frameRef.current;
      if (document.visibilityState === "hidden") {
        return;
      }

      const minimumFrameDeltaMs = 16;
      if (timestampMs - lastPaintTime < minimumFrameDeltaMs) {
        return;
      }
      lastPaintTime = timestampMs;

      updateRendererSize(frame.width, frame.height);
      if (frame.revision !== lastRevision) {
        updateGeometry(frame);
        lastRevision = frame.revision;
      }

      material.uniforms.uTime.value = timestampMs * 0.001;
      material.uniforms.uZoomScale.value = frame.zoomScale ?? 1;
      const focusCenter = material.uniforms.uFocusCenter.value as THREE.Vector2;
      focusCenter.set(frame.focusCenterX ?? 0, frame.focusCenterY ?? 0);
      material.uniforms.uFocusStrength.value = frame.focusStrength ?? 0;
      material.uniforms.uFocusRadius.value = frame.focusRadius ?? 200;
      material.uniforms.uFocusFalloff.value = frame.focusFalloff ?? 400;
      renderer.render(scene, camera);
    };

    frameHandle = window.requestAnimationFrame(render);

    return () => {
      window.cancelAnimationFrame(frameHandle);
      geometry.dispose();
      material.dispose();
      renderer.dispose();
      points.removeFromParent();
      if (renderer.domElement.parentElement === container) {
        container.removeChild(renderer.domElement);
      }
    };
  }, [frameRef]);

  return <div className={className} ref={containerRef} aria-hidden="true" />;
}
