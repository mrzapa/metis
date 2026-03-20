"use client";

import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";

interface GraphPoint {
  x?: number;
  y?: number;
  z?: number;
}

export interface BrainModelOverlayHandle {
  root: THREE.Group;
  lightRig: THREE.Group;
  fitToGraph: (nodes: readonly GraphPoint[]) => void;
  dispose: () => void;
}

function disposeMaterial(material: THREE.Material): void {
  if ("map" in material && (material as THREE.MeshBasicMaterial).map) {
    (material as THREE.MeshBasicMaterial).map?.dispose();
  }
  material.dispose();
}

function disposeObject3D(object: THREE.Object3D): void {
  object.traverse((child) => {
    if (child instanceof THREE.Mesh) {
      child.geometry?.dispose();
      if (Array.isArray(child.material)) {
        child.material.forEach(disposeMaterial);
      } else if (child.material) {
        disposeMaterial(child.material);
      }
    }
  });
}

function normalizeModel(model: THREE.Object3D): void {
  const bounds = new THREE.Box3().setFromObject(model);
  const center = new THREE.Vector3();
  const size = new THREE.Vector3();
  bounds.getCenter(center);
  bounds.getSize(size);

  const maxDimension = Math.max(size.x, size.y, size.z) || 1;
  const scale = 1 / maxDimension;

  model.position.sub(center);
  model.scale.setScalar(scale);
  model.rotation.y = Math.PI * 0.08;
  model.updateMatrixWorld(true);
}

function stylizeModel(model: THREE.Object3D): void {
  model.traverse((child) => {
    if (!(child instanceof THREE.Mesh)) return;

    const baseMaterial = Array.isArray(child.material) ? child.material[0] : child.material;
    const baseColor =
      baseMaterial && "color" in baseMaterial && baseMaterial.color instanceof THREE.Color
        ? baseMaterial.color.clone()
        : new THREE.Color("#e8c3b7");

    child.material = new THREE.MeshPhysicalMaterial({
      color: baseColor.lerp(new THREE.Color("#f4d4c8"), 0.4),
      transparent: true,
      opacity: 0.18,
      roughness: 0.35,
      metalness: 0.02,
      transmission: 0.05,
      clearcoat: 0.2,
      side: THREE.DoubleSide,
      depthWrite: false,
    });
    child.castShadow = false;
    child.receiveShadow = false;
    child.renderOrder = -5;
  });
}

function computeBounds(nodes: readonly GraphPoint[]): {
  center: THREE.Vector3;
  maxDimension: number;
} | null {
  const points = nodes.filter(
    (node) =>
      Number.isFinite(node.x) &&
      Number.isFinite(node.y) &&
      Number.isFinite(node.z),
  );

  if (points.length === 0) return null;

  let minX = Number.POSITIVE_INFINITY;
  let minY = Number.POSITIVE_INFINITY;
  let minZ = Number.POSITIVE_INFINITY;
  let maxX = Number.NEGATIVE_INFINITY;
  let maxY = Number.NEGATIVE_INFINITY;
  let maxZ = Number.NEGATIVE_INFINITY;

  for (const point of points) {
    minX = Math.min(minX, point.x ?? 0);
    minY = Math.min(minY, point.y ?? 0);
    minZ = Math.min(minZ, point.z ?? 0);
    maxX = Math.max(maxX, point.x ?? 0);
    maxY = Math.max(maxY, point.y ?? 0);
    maxZ = Math.max(maxZ, point.z ?? 0);
  }

  return {
    center: new THREE.Vector3(
      (minX + maxX) / 2,
      (minY + maxY) / 2,
      (minZ + maxZ) / 2,
    ),
    maxDimension: Math.max(maxX - minX, maxY - minY, maxZ - minZ),
  };
}

function buildLightRig(): {
  rig: THREE.Group;
  keyLight: THREE.DirectionalLight;
  rimLight: THREE.DirectionalLight;
} {
  const rig = new THREE.Group();
  rig.name = "brain-model-light-rig";

  const ambient = new THREE.AmbientLight(0xffffff, 0.45);
  const hemisphere = new THREE.HemisphereLight(0xf4c2b3, 0x0a1220, 0.6);
  const keyLight = new THREE.DirectionalLight(0xfff3e8, 1.1);
  const rimLight = new THREE.DirectionalLight(0xc2dbff, 0.65);

  rig.add(ambient);
  rig.add(hemisphere);
  rig.add(keyLight);
  rig.add(rimLight);

  return { rig, keyLight, rimLight };
}

export async function loadBrainModelOverlay(
  modelUrl = "/brain/brain-model.glb",
): Promise<BrainModelOverlayHandle> {
  const loader = new GLTFLoader();
  const gltf = await loader.loadAsync(modelUrl);
  const model = gltf.scene;
  normalizeModel(model);
  stylizeModel(model);

  const root = new THREE.Group();
  root.name = "brain-model-overlay";
  root.add(model);

  const { rig: lightRig, keyLight, rimLight } = buildLightRig();

  const fitToGraph = (nodes: readonly GraphPoint[]) => {
    const bounds = computeBounds(nodes);
    const center = bounds?.center ?? new THREE.Vector3(0, 0, 0);
    const maxDimension = Math.max(bounds?.maxDimension ?? 160, 120);
    const targetScale = maxDimension * 0.65;

    root.position.copy(center);
    root.scale.setScalar(targetScale);

    lightRig.position.copy(center);
    keyLight.position.set(center.x + maxDimension * 0.6, center.y + maxDimension * 0.45, center.z + maxDimension * 0.75);
    rimLight.position.set(center.x - maxDimension * 0.5, center.y + maxDimension * 0.2, center.z - maxDimension * 0.65);
  };

  const dispose = () => {
    disposeObject3D(root);
  };

  return { root, lightRig, fitToGraph, dispose };
}
