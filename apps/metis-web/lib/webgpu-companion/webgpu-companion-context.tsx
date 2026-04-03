"use client";

import { createContext, useContext, type ReactNode } from "react";
import { useWebGPUCompanion, type UseWebGPUCompanion } from "./use-webgpu-companion";

const WebGPUCompanionContext = createContext<UseWebGPUCompanion | null>(null);

export function WebGPUCompanionProvider({ children }: { children: ReactNode }) {
  const companion = useWebGPUCompanion();
  return (
    <WebGPUCompanionContext.Provider value={companion}>
      {children}
    </WebGPUCompanionContext.Provider>
  );
}

export function useWebGPUCompanionContext(): UseWebGPUCompanion {
  const ctx = useContext(WebGPUCompanionContext);
  if (!ctx) {
    throw new Error(
      "useWebGPUCompanionContext must be used within <WebGPUCompanionProvider>",
    );
  }
  return ctx;
}
