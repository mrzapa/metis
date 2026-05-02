/**
 * Dot-matrix inline semantic loaders.
 *
 * 5×5 grid · single CSS @keyframes · per-dot animation-delay map.
 * Technique inspired by https://icons.icantcode.fyi/ (used with permission).
 * See `./dot-matrix/README.md` for the full vocabulary and authorship notes.
 */
"use client";

import { BreathLoader } from "./dot-matrix/breath";
import { CompileLoader } from "./dot-matrix/compile";
import { HaltLoader } from "./dot-matrix/halt";
import { StreamLoader } from "./dot-matrix/stream";
import { ThinkingLoader } from "./dot-matrix/thinking";
import { VerifyLoader } from "./dot-matrix/verify";

export type DotMatrixLoaderName =
  | "thinking"
  | "stream"
  | "compile"
  | "verify"
  | "halt"
  | "breath";

export interface DotMatrixLoaderProps {
  name: DotMatrixLoaderName;
  size?: number;
  "aria-label"?: string;
  className?: string;
}

const DEFAULT_ARIA: Record<DotMatrixLoaderName, string> = {
  thinking: "Thinking",
  stream: "Streaming",
  compile: "Working",
  verify: "Verified",
  halt: "Halted",
  breath: "Loading",
};

export function DotMatrixLoader({
  name,
  size = 20,
  className,
  "aria-label": ariaLabel,
}: DotMatrixLoaderProps) {
  const label = ariaLabel ?? DEFAULT_ARIA[name];
  switch (name) {
    case "breath":
      return <BreathLoader size={size} className={className} ariaLabel={label} />;
    case "thinking":
      return <ThinkingLoader size={size} className={className} ariaLabel={label} />;
    case "stream":
      return <StreamLoader size={size} className={className} ariaLabel={label} />;
    case "compile":
      return <CompileLoader size={size} className={className} ariaLabel={label} />;
    case "verify":
      return <VerifyLoader size={size} className={className} ariaLabel={label} />;
    case "halt":
      return <HaltLoader size={size} className={className} ariaLabel={label} />;
    // Other arms added in Tasks 4–13.
    default:
      // Fallback while authoring; replaced with exhaustive switch in Task 14.
      return <BreathLoader size={size} className={className} ariaLabel={label} />;
  }
}
