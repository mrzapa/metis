"use client";

import { ForecastArtifactContent } from "@/components/chat/artifacts/forecast-artifact-content";
import { NyxArtifactContent } from "@/components/chat/artifacts/nyx-artifact-content";
import type { NormalizedArrowArtifact } from "@/lib/artifacts/extract-arrow-artifacts";

function EmptyArtifactState({ message }: { message: string }) {
  return <p className="text-sm leading-relaxed text-muted-foreground">{message}</p>;
}

export function StructuredArtifactContent({ artifact }: { artifact: NormalizedArrowArtifact }) {
  if (artifact.type === "forecast_report") {
    return <ForecastArtifactContent artifact={artifact} />;
  }

  if (
    artifact.type === "nyx_component_selection"
    || artifact.type === "nyx_install_plan"
    || artifact.type === "nyx_dependency_report"
  ) {
    return <NyxArtifactContent artifact={artifact} />;
  }

  return <EmptyArtifactState message="Unsupported structured artifact." />;
}

