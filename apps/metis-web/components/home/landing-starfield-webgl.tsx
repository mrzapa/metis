"use client";

import { useEffect, useRef } from "react";
import * as THREE from "three";
import type { MutableRefObject } from "react";
import type { LandingWebglStar, LandingStarfieldFrame, LandingStarRenderTier } from "./landing-starfield-webgl.types";
import { STAR_FRAG_THREEJS, STAR_VERT_THREEJS } from "@/lib/landing-stars/star-surface-shader";

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

uniform float uDpr;
uniform float uTime;
uniform float uZoomScale;

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
  float zoomSizeScale = mix(0.15, 1.0, smoothstep(0.0, 0.4, uZoomScale));
  gl_PointSize = max(1.0, aShape.z * uDpr * tierBoost * heroGlow * twinkle * zoomSizeScale);

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

const fragmentShader = `
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

  if (vDiffraction > 0.02) {
    float crossX = exp(-abs(uv.x) * 13.0);
    float crossY = exp(-abs(uv.y) * 13.0);
    float diffraction = max(crossX, crossY) * (1.0 - dist) * vDiffraction * (0.18 + tierBlend * 0.2);
    color += vAccentColor * diffraction;
  }

  if (vAddable > 0.5) {
    color = mix(color, vec3(0.95, 0.82, 0.55), 0.12);
  }

  float alphaBase = (0.18 + vBrightness * 0.46) * vTwinkle;
  float alpha = haloMask * alphaBase + coreMask * 0.28 + rimMask * 0.08;
  alpha = clamp(alpha * (0.9 + vBloom * 0.12), 0.0, 1.0);

  gl_FragColor = vec4(color * (0.86 + vBrightness * 0.34), alpha);
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
      ? 5.2 + visual.haloRadiusFactor * 0.42  // same as hero — NMS overlay provides the growing-star visual
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

  for (let index = 0; index < starCount; index += 1) {
    const star = stars[index];
    const { palette, stellarType, visual } = star.profile;
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
  }

  return {
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
      },
      vertexShader,
    });
    const points = new THREE.Points(geometry, material);
    scene.add(points);

    // ── NMS star-disc quad ────────────────────────────────────────────────────
    // A 2×2 PlaneGeometry in NDC space. The vertex shader bypasses the camera
    // so it always covers the full viewport. The fragment shader uses gl_FragCoord
    // (physical pixels) to compute the disc/corona centred on u_starPos.
    const nmsQuadGeo = new THREE.PlaneGeometry(2, 2);
    const nmsMaterial = new THREE.ShaderMaterial({
      blending: THREE.AdditiveBlending,
      depthTest: false,
      depthWrite: false,
      transparent: true,
      vertexShader: STAR_VERT_THREEJS,
      fragmentShader: STAR_FRAG_THREEJS,
      uniforms: {
        u_time: { value: 0 },
        u_seed: { value: 0 },
        u_color: { value: new THREE.Vector3() },
        u_color2: { value: new THREE.Vector3() },
        u_color3: { value: new THREE.Vector3() },
        u_hasColor2: { value: 0 },
        u_hasColor3: { value: 0 },
        u_hasDiffraction: { value: 0 },
        u_stage: { value: 0 },
        u_res: { value: new THREE.Vector2() },
        u_starPos: { value: new THREE.Vector2() },
        u_focusStrength: { value: 0 },
      },
    });
    const nmsQuad = new THREE.Mesh(nmsQuadGeo, nmsMaterial);
    nmsQuad.visible = false;
    nmsQuad.renderOrder = 1;
    scene.add(nmsQuad);
    // Last profile id seen — profile-level uniforms only update when star changes
    let lastNmsProfileId = "";

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

      // ── NMS disc ────────────────────────────────────────────────────────────
      const focused = frame.focusedStar;
      if (focused && focused.focusStrength > 0) {
        nmsQuad.visible = true;
        const dpr = Math.min(window.devicePixelRatio || 1, 1.8);
        const physW = frame.width * dpr;
        const physH = frame.height * dpr;
        nmsMaterial.uniforms.u_time.value = timestampMs * 0.001;
        nmsMaterial.uniforms.u_res.value.set(physW, physH);
        // u_starPos: physical pixels from bottom-left (WebGL convention).
        // screenY is CSS pixels from top → flip to bottom: (frame.height - screenY) * dpr.
        // The disc effect is radially symmetric so Y-direction is irrelevant for dist/angle,
        // but we flip for correctness with any future asymmetric additions.
        nmsMaterial.uniforms.u_starPos.value.set(
          focused.screenX * dpr,
          (frame.height - focused.screenY) * dpr,
        );
        nmsMaterial.uniforms.u_focusStrength.value = focused.focusStrength;

        const pid = `${focused.profile.seedHash}`;
        if (pid !== lastNmsProfileId) {
          lastNmsProfileId = pid;
          const { palette, visual } = focused.profile;
          nmsMaterial.uniforms.u_seed.value = (focused.profile.seedHash % 1000) / 1000;
          nmsMaterial.uniforms.u_color.value.set(palette.core[0], palette.core[1], palette.core[2]);
          nmsMaterial.uniforms.u_color2.value.set(palette.halo[0], palette.halo[1], palette.halo[2]);
          nmsMaterial.uniforms.u_color3.value.set(palette.accent[0], palette.accent[1], palette.accent[2]);
          nmsMaterial.uniforms.u_hasColor2.value = 1;
          nmsMaterial.uniforms.u_hasColor3.value = 1;
          nmsMaterial.uniforms.u_hasDiffraction.value = visual.diffractionStrength > 0.02 ? 1 : 0;
          nmsMaterial.uniforms.u_stage.value = 2.0;
        }
      } else {
        nmsQuad.visible = false;
        lastNmsProfileId = "";
      }

      renderer.render(scene, camera);
    };

    frameHandle = window.requestAnimationFrame(render);

    return () => {
      window.cancelAnimationFrame(frameHandle);
      geometry.dispose();
      material.dispose();
      nmsQuadGeo.dispose();
      nmsMaterial.dispose();
      renderer.dispose();
      points.removeFromParent();
      nmsQuad.removeFromParent();
      if (renderer.domElement.parentElement === container) {
        container.removeChild(renderer.domElement);
      }
    };
  }, [frameRef]);

  return <div className={className} ref={containerRef} aria-hidden="true" />;
}
