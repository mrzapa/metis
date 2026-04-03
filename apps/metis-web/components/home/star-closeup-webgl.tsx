"use client";

import { useEffect, useRef } from "react";
import * as THREE from "three";
import type { StellarProfile } from "@/lib/landing-stars";

/* -------------------------------------------------------------------------- */
/*  Procedural Sun Shader — vertex                                            */
/* -------------------------------------------------------------------------- */

const vertexShader = /* glsl */ `
  varying vec2 vUv;
  void main() {
    vUv = uv;
    gl_Position = vec4(position, 1.0);
  }
`;

/* -------------------------------------------------------------------------- */
/*  Procedural Sun Shader — fragment                                          */
/*                                                                            */
/*  Features:                                                                 */
/*    - Limb darkening (cos(θ)^0.4)                                          */
/*    - Surface convection granulation (2-octave fBm simplex noise)           */
/*    - Sunspots (low-frequency noise threshold)                              */
/*    - Solar prominences (noise arcs from the limb)                          */
/*    - Corona / extended radial glow                                         */
/*    - Chromatic aberration at the disk edge                                 */
/* -------------------------------------------------------------------------- */

const fragmentShader = /* glsl */ `
  precision highp float;

  uniform float uTime;
  uniform float uFocusStrength;
  uniform float uTemperature;
  uniform float uCoronaIntensity;
  uniform float uBloom;
  uniform float uSeed;
  uniform vec3 uCoreColor;
  uniform vec3 uSurfaceColor;
  uniform vec3 uRimColor;
  uniform vec3 uHaloColor;
  uniform vec3 uAccentColor;

  varying vec2 vUv;

  /* ---- Simplex 2D noise (Ashima Arts / Ian McEwan) ---- */
  vec3 mod289(vec3 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
  vec2 mod289(vec2 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
  vec3 permute(vec3 x) { return mod289(((x * 34.0) + 1.0) * x); }

  float snoise(vec2 v) {
    const vec4 C = vec4(
      0.211324865405187,   // (3.0 - sqrt(3.0)) / 6.0
      0.366025403784439,   // 0.5 * (sqrt(3.0) - 1.0)
     -0.577350269189626,   // -1.0 + 2.0 * C.x
      0.024390243902439    // 1.0 / 41.0
    );
    vec2 i = floor(v + dot(v, C.yy));
    vec2 x0 = v - i + dot(i, C.xx);
    vec2 i1 = (x0.x > x0.y) ? vec2(1.0, 0.0) : vec2(0.0, 1.0);
    vec4 x12 = x0.xyxy + C.xxzz;
    x12.xy -= i1;
    i = mod289(i);
    vec3 p = permute(permute(i.y + vec3(0.0, i1.y, 1.0)) + i.x + vec3(0.0, i1.x, 1.0));
    vec3 m = max(0.5 - vec3(dot(x0, x0), dot(x12.xy, x12.xy), dot(x12.zw, x12.zw)), 0.0);
    m = m * m;
    m = m * m;
    vec3 x_ = 2.0 * fract(p * C.www) - 1.0;
    vec3 h = abs(x_) - 0.5;
    vec3 ox = floor(x_ + 0.5);
    vec3 a0 = x_ - ox;
    m *= 1.79284291400159 - 0.85373472095314 * (a0 * a0 + h * h);
    vec3 g;
    g.x = a0.x * x0.x + h.x * x0.y;
    g.yz = a0.yz * x12.xz + h.yz * x12.yw;
    return 130.0 * dot(m, g);
  }

  /* ---- fBm (2-octave) ---- */
  float fbm2(vec2 p) {
    float f = 0.0;
    f += 0.5 * snoise(p);
    f += 0.25 * snoise(p * 2.04 + vec2(1.7, 3.2));
    return f;
  }

  /* ---- fBm (3-octave, for corona) ---- */
  float fbm3(vec2 p) {
    float f = 0.0;
    f += 0.5 * snoise(p);
    f += 0.25 * snoise(p * 2.04 + vec2(1.7, 3.2));
    f += 0.125 * snoise(p * 4.01 + vec2(5.1, 0.9));
    return f;
  }

  void main() {
    vec2 uv = vUv * 2.0 - 1.0;   // -1..1 centred
    float aspect = 1.0;            // fullscreen quad is square in UV

    float dist = length(uv);
    float diskRadius = 0.38 * uFocusStrength;

    /* ---- Corona (outer glow, always visible once focus starts) ---- */
    float coronaDist = dist / max(diskRadius, 0.001);
    float coronaNoise = fbm3(uv * 2.5 + vec2(uSeed * 0.37, uTime * 0.08));
    float coronaRaw = 1.0 / (1.0 + pow(coronaDist, 2.2 - uCoronaIntensity * 0.3));
    float corona = coronaRaw * (0.7 + coronaNoise * 0.3) * uBloom;
    corona *= smoothstep(0.0, 0.3, uFocusStrength);
    vec3 coronaColor = uHaloColor * corona * 0.6;

    /* ---- Prominences (noise arcs from the limb) ---- */
    float angle = atan(uv.y, uv.x);
    float prominenceNoise = snoise(vec2(angle * 1.5 + uSeed, uTime * 0.12)) * 0.5 + 0.5;
    float prominenceArch = smoothstep(diskRadius, diskRadius + 0.12 * uFocusStrength, dist)
                         * smoothstep(diskRadius + 0.25 * uFocusStrength, diskRadius + 0.06 * uFocusStrength, dist);
    float prominence = prominenceArch * prominenceNoise * uCoronaIntensity * 0.8;
    prominence *= smoothstep(0.0, 0.5, uFocusStrength);
    vec3 prominenceColor = uAccentColor * prominence;

    /* ---- Disk surface ---- */
    if (dist < diskRadius && diskRadius > 0.001) {
      float r = dist / diskRadius;             // 0..1 from center to limb

      /* Limb darkening */
      float cosTheta = sqrt(max(0.0, 1.0 - r * r));
      float limbDarkening = pow(cosTheta, 0.4);

      /* Convection granulation */
      float convectionScale = 6.0 + uSeed * 0.3;
      float convection = fbm2(uv * convectionScale + vec2(uTime * 0.06, uTime * 0.04 + uSeed));
      convection = convection * 0.5 + 0.5;     // 0..1

      /* Sunspots (low-frequency threshold) */
      float spotNoise = snoise(uv * 3.0 + vec2(uSeed * 2.1, uTime * 0.02));
      float spots = smoothstep(0.42 + uCoronaIntensity * 0.1, 0.55 + uCoronaIntensity * 0.1, spotNoise);
      spots *= smoothstep(0.0, 0.3, r);        // no spots at dead center
      spots *= smoothstep(1.0, 0.7, r);        // no spots near limb

      /* Color mixing: core → surface → rim by radial position */
      vec3 baseColor = mix(uCoreColor, uSurfaceColor, smoothstep(0.0, 0.55, r));
      baseColor = mix(baseColor, uRimColor, smoothstep(0.55, 0.95, r));

      /* Apply convection variation */
      baseColor = mix(baseColor, baseColor * 0.82, (1.0 - convection) * 0.35);

      /* Apply spots */
      baseColor = mix(baseColor, baseColor * 0.25, spots * 0.7);

      /* Apply limb darkening */
      baseColor *= limbDarkening;

      /* Chromatic aberration at disk edge */
      float chromaStrength = smoothstep(0.7, 1.0, r) * 0.15 * uFocusStrength;
      baseColor.r *= 1.0 + chromaStrength;
      baseColor.b *= 1.0 - chromaStrength * 0.5;

      /* Soft edge anti-alias */
      float edgeAlpha = smoothstep(diskRadius, diskRadius - 0.008, dist);

      gl_FragColor = vec4(
        baseColor * edgeAlpha + coronaColor + prominenceColor,
        edgeAlpha * uFocusStrength + corona * 0.5 + prominence * 0.4
      );
    } else {
      /* Outside disk: corona + prominences only */
      float totalAlpha = corona * 0.5 + prominence * 0.4;
      gl_FragColor = vec4(coronaColor + prominenceColor, totalAlpha);
    }
  }
`;

/* -------------------------------------------------------------------------- */
/*  Component                                                                 */
/* -------------------------------------------------------------------------- */

interface StarCloseupWebglProps {
  className?: string;
  focusStrength: number;
  profile: StellarProfile | null;
  reducedMotion?: boolean;
}

export function StarCloseupWebgl({
  className,
  focusStrength,
  profile,
  reducedMotion = false,
}: StarCloseupWebglProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const materialRef = useRef<THREE.ShaderMaterial | null>(null);
  const rafRef = useRef(0);
  const startTimeRef = useRef(0);
  const reducedMotionRef = useRef(reducedMotion);
  reducedMotionRef.current = reducedMotion;

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    // Create renderer
    const renderer = new THREE.WebGLRenderer({
      alpha: true,
      antialias: false,
      premultipliedAlpha: false,
    });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(container.clientWidth, container.clientHeight);
    container.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    // Scene + fullscreen quad
    const scene = new THREE.Scene();
    const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
    const geometry = new THREE.PlaneGeometry(2, 2);
    const material = new THREE.ShaderMaterial({
      vertexShader,
      fragmentShader,
      transparent: true,
      depthWrite: false,
      uniforms: {
        uTime: { value: 0 },
        uFocusStrength: { value: 0 },
        uTemperature: { value: 5778 },
        uCoronaIntensity: { value: 0.5 },
        uBloom: { value: 1.0 },
        uSeed: { value: 0 },
        uCoreColor: { value: new THREE.Vector3(1, 0.95, 0.8) },
        uSurfaceColor: { value: new THREE.Vector3(1, 0.85, 0.5) },
        uRimColor: { value: new THREE.Vector3(1, 0.55, 0.2) },
        uHaloColor: { value: new THREE.Vector3(0.6, 0.7, 1.0) },
        uAccentColor: { value: new THREE.Vector3(1, 0.4, 0.2) },
      },
    });
    materialRef.current = material;
    const mesh = new THREE.Mesh(geometry, material);
    scene.add(mesh);

    startTimeRef.current = performance.now();

    function animate() {
      const elapsed = reducedMotionRef.current
        ? 0
        : (performance.now() - startTimeRef.current) / 1000;
      material.uniforms.uTime.value = elapsed;
      renderer.render(scene, camera);
      rafRef.current = requestAnimationFrame(animate);
    }
    rafRef.current = requestAnimationFrame(animate);

    function onResize() {
      if (!container) return;
      const w = container.clientWidth;
      const h = container.clientHeight;
      renderer.setSize(w, h);
    }
    window.addEventListener("resize", onResize);

    return () => {
      cancelAnimationFrame(rafRef.current);
      window.removeEventListener("resize", onResize);
      renderer.dispose();
      geometry.dispose();
      material.dispose();
      if (container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement);
      }
      rendererRef.current = null;
      materialRef.current = null;
    };
  }, []);

  // Sync uniforms on prop changes
  useEffect(() => {
    const mat = materialRef.current;
    if (!mat) return;

    mat.uniforms.uFocusStrength.value = focusStrength;

    if (profile) {
      const toVec3 = (rgb: readonly [number, number, number]) =>
        new THREE.Vector3(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255);

      mat.uniforms.uTemperature.value = profile.temperatureK;
      mat.uniforms.uCoronaIntensity.value = profile.visual.coronaIntensity;
      mat.uniforms.uBloom.value = profile.visual.bloomFactor;
      mat.uniforms.uSeed.value = (profile.seedHash % 1000) / 1000;
      mat.uniforms.uCoreColor.value = toVec3(profile.palette.core);
      mat.uniforms.uSurfaceColor.value = toVec3(profile.palette.surface);
      mat.uniforms.uRimColor.value = toVec3(profile.palette.rim);
      mat.uniforms.uHaloColor.value = toVec3(profile.palette.halo);
      mat.uniforms.uAccentColor.value = toVec3(profile.palette.accent);
    }
  }, [focusStrength, profile]);

  const visible = focusStrength > 0.01;

  return (
    <div
      ref={containerRef}
      className={className}
      style={{
        position: "absolute",
        inset: 0,
        pointerEvents: "none",
        opacity: visible ? 1 : 0,
        transition: "opacity 0.3s",
        zIndex: 1,
      }}
      aria-hidden="true"
    />
  );
}
