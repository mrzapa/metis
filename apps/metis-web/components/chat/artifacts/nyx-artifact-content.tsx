import Link from "next/link";

import {
  getNyxComponentPreviewHref,
} from "@/components/library/nyx-shared";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import type { NormalizedArrowArtifact } from "@/lib/artifacts/extract-arrow-artifacts";
import { cn } from "@/lib/utils";

const PANEL_CLASS_NAME = "rounded-xl border border-white/10 bg-black/10 px-3 py-3";
const SUBPANEL_CLASS_NAME = "rounded-lg border border-white/10 bg-background/30 px-3 py-2";
const LABEL_CLASS_NAME = "text-[10px] font-medium uppercase tracking-[0.18em] text-primary/80";
const ACTION_LINK_CLASS_NAME = cn(buttonVariants({ size: "xs", variant: "outline" }), "h-auto py-1");

type NyxDependencyGroupKey = "required" | "runtime" | "dev" | "registry";

interface NyxSelectedComponent {
  component_name: string;
  title: string;
  description: string;
  curated_description: string;
  component_type: string;
  install_target: string;
  registry_url: string;
  source_repo: string;
  match_score: number;
  match_reason: string;
  match_reasons: string[];
  preview_targets: string[];
  targets: string[];
  file_count: number;
  required_dependencies: string[];
  dependencies: string[];
  dev_dependencies: string[];
  registry_dependencies: string[];
}

interface NyxComponentSelectionPayload {
  query: string;
  intent_type: string;
  confidence: number;
  matched_signals: string[];
  selection_reason: string;
  selected_components: NyxSelectedComponent[];
}

interface NyxInstallPlanStep {
  step_type: string;
  label: string;
  command: string;
}

interface NyxInstallPlanComponent {
  component_name: string;
  title: string;
  install_target: string;
  registry_url: string;
  targets: string[];
  file_count: number;
  dependency_packages: string[];
  steps: NyxInstallPlanStep[];
}

interface NyxInstallPlanPayload {
  query: string;
  intent_type: string;
  package_manager_note: string;
  components: NyxInstallPlanComponent[];
}

interface NyxDependencyEntry {
  package_name: string;
  dependency_type: string;
  required_by: string[];
  install_targets: string[];
  registry_urls: string[];
}

interface NyxDependencyReportPayload {
  query: string;
  component_count: number;
  packages: NyxDependencyEntry[];
  groups: Record<NyxDependencyGroupKey, NyxDependencyEntry[]>;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object";
}

function toStringValue(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function toNumberValue(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function toStringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.map((item) => toStringValue(item)).filter(Boolean)
    : [];
}

function uniqueStrings(values: string[]): string[] {
  return Array.from(new Set(values.filter(Boolean)));
}

function formatIntentLabel(intentType: string): string {
  return intentType.replaceAll("_", " ");
}

function getComponentSummary(component: NyxSelectedComponent): string {
  return component.curated_description || component.description || "No description available.";
}

function asNyxSelectedComponent(value: unknown): NyxSelectedComponent | null {
  if (!isRecord(value)) {
    return null;
  }

  const componentName = toStringValue(value.component_name);
  const installTarget = toStringValue(value.install_target);
  if (!componentName || !installTarget) {
    return null;
  }

  return {
    component_name: componentName,
    title: toStringValue(value.title),
    description: toStringValue(value.description),
    curated_description: toStringValue(value.curated_description),
    component_type: toStringValue(value.component_type),
    install_target: installTarget,
    registry_url: toStringValue(value.registry_url),
    source_repo: toStringValue(value.source_repo),
    match_score: toNumberValue(value.match_score),
    match_reason: toStringValue(value.match_reason),
    match_reasons: toStringArray(value.match_reasons),
    preview_targets: toStringArray(value.preview_targets),
    targets: toStringArray(value.targets),
    file_count: toNumberValue(value.file_count),
    required_dependencies: toStringArray(value.required_dependencies),
    dependencies: toStringArray(value.dependencies),
    dev_dependencies: toStringArray(value.dev_dependencies),
    registry_dependencies: toStringArray(value.registry_dependencies),
  };
}

function asNyxComponentSelectionPayload(payload: unknown): NyxComponentSelectionPayload | null {
  if (!isRecord(payload)) {
    return null;
  }

  const selectedComponents = Array.isArray(payload.selected_components)
    ? payload.selected_components
        .map((item) => asNyxSelectedComponent(item))
        .filter((item): item is NyxSelectedComponent => Boolean(item))
    : [];

  if (selectedComponents.length === 0) {
    return null;
  }

  return {
    query: toStringValue(payload.query),
    intent_type: toStringValue(payload.intent_type),
    confidence: toNumberValue(payload.confidence),
    matched_signals: toStringArray(payload.matched_signals),
    selection_reason: toStringValue(payload.selection_reason),
    selected_components: selectedComponents,
  };
}

function asNyxInstallPlanStep(value: unknown): NyxInstallPlanStep | null {
  if (!isRecord(value)) {
    return null;
  }

  const label = toStringValue(value.label);
  const command = toStringValue(value.command);
  if (!label && !command) {
    return null;
  }

  return {
    step_type: toStringValue(value.step_type),
    label,
    command,
  };
}

function asNyxInstallPlanComponent(value: unknown): NyxInstallPlanComponent | null {
  if (!isRecord(value)) {
    return null;
  }

  const componentName = toStringValue(value.component_name);
  const installTarget = toStringValue(value.install_target);
  if (!componentName || !installTarget) {
    return null;
  }

  const steps = Array.isArray(value.steps)
    ? value.steps
        .map((step) => asNyxInstallPlanStep(step))
        .filter((step): step is NyxInstallPlanStep => Boolean(step))
    : [];

  if (steps.length === 0) {
    return null;
  }

  return {
    component_name: componentName,
    title: toStringValue(value.title),
    install_target: installTarget,
    registry_url: toStringValue(value.registry_url),
    targets: toStringArray(value.targets),
    file_count: toNumberValue(value.file_count),
    dependency_packages: toStringArray(value.dependency_packages),
    steps,
  };
}

function asNyxInstallPlanPayload(payload: unknown): NyxInstallPlanPayload | null {
  if (!isRecord(payload)) {
    return null;
  }

  const components = Array.isArray(payload.components)
    ? payload.components
        .map((item) => asNyxInstallPlanComponent(item))
        .filter((item): item is NyxInstallPlanComponent => Boolean(item))
    : [];

  if (components.length === 0) {
    return null;
  }

  return {
    query: toStringValue(payload.query),
    intent_type: toStringValue(payload.intent_type),
    package_manager_note: toStringValue(payload.package_manager_note),
    components,
  };
}

function asNyxDependencyEntry(value: unknown): NyxDependencyEntry | null {
  if (!isRecord(value)) {
    return null;
  }

  const packageName = toStringValue(value.package_name);
  const dependencyType = toStringValue(value.dependency_type);
  if (!packageName || !dependencyType) {
    return null;
  }

  return {
    package_name: packageName,
    dependency_type: dependencyType,
    required_by: toStringArray(value.required_by),
    install_targets: toStringArray(value.install_targets),
    registry_urls: toStringArray(value.registry_urls),
  };
}

function asNyxDependencyGroup(value: unknown): NyxDependencyEntry[] {
  return Array.isArray(value)
    ? value.map((entry) => asNyxDependencyEntry(entry)).filter((entry): entry is NyxDependencyEntry => Boolean(entry))
    : [];
}

function asNyxDependencyReportPayload(payload: unknown): NyxDependencyReportPayload | null {
  if (!isRecord(payload) || !isRecord(payload.groups)) {
    return null;
  }

  const groups = {
    required: asNyxDependencyGroup(payload.groups.required),
    runtime: asNyxDependencyGroup(payload.groups.runtime),
    dev: asNyxDependencyGroup(payload.groups.dev),
    registry: asNyxDependencyGroup(payload.groups.registry),
  };

  return {
    query: toStringValue(payload.query),
    component_count: toNumberValue(payload.component_count),
    packages: asNyxDependencyGroup(payload.packages),
    groups,
  };
}

function EmptyArtifactState({ message }: { message: string }) {
  return <p className="text-sm leading-relaxed text-muted-foreground">{message}</p>;
}

function StringBadgeList({
  emptyLabel,
  items,
}: {
  emptyLabel: string;
  items: string[];
}) {
  if (items.length === 0) {
    return <p className="text-xs text-muted-foreground">{emptyLabel}</p>;
  }

  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((item) => (
        <Badge key={item} variant="outline">
          {item}
        </Badge>
      ))}
    </div>
  );
}

function NyxActionLinks({
  componentName,
  registryUrl,
  sourceRepo,
}: {
  componentName: string;
  registryUrl: string;
  sourceRepo?: string;
}) {
  const previewHref = getNyxComponentPreviewHref(componentName);

  return (
    <div className="flex flex-wrap gap-2">
      {previewHref ? (
        <Link href={previewHref} className={ACTION_LINK_CLASS_NAME}>
          Open detail
        </Link>
      ) : null}
      {registryUrl ? (
        <a
          href={registryUrl}
          target="_blank"
          rel="noreferrer"
          className={ACTION_LINK_CLASS_NAME}
        >
          Registry JSON
        </a>
      ) : null}
      {sourceRepo ? (
        <a
          href={sourceRepo}
          target="_blank"
          rel="noreferrer"
          className={ACTION_LINK_CLASS_NAME}
        >
          Source repo
        </a>
      ) : null}
    </div>
  );
}

function NyxComponentSelectionArtifact({ artifact }: { artifact: NormalizedArrowArtifact }) {
  const payload = asNyxComponentSelectionPayload(artifact.payload);
  if (!payload) {
    return <EmptyArtifactState message="Nyx component selection details were unavailable." />;
  }

  return (
    <div className="space-y-3" data-testid="nyx-component-selection-artifact">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="space-y-1">
          <p className="text-sm leading-relaxed text-foreground/95">
            {payload.selection_reason || artifact.summary || "Nyx matched components for this prompt."}
          </p>
          {payload.query ? (
            <p className="text-xs text-muted-foreground">Prompt: {payload.query}</p>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-1.5">
          {payload.intent_type ? (
            <Badge variant="outline">{formatIntentLabel(payload.intent_type)}</Badge>
          ) : null}
          {payload.confidence > 0 ? (
            <Badge variant="outline">{Math.round(payload.confidence * 100)}% confidence</Badge>
          ) : null}
        </div>
      </div>

      {payload.matched_signals.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {payload.matched_signals.map((signal) => (
            <Badge key={signal} variant="secondary">
              {signal}
            </Badge>
          ))}
        </div>
      ) : null}

      <div className="grid gap-3">
        {payload.selected_components.map((component) => {
          const dependencyPackages = uniqueStrings([
            ...component.required_dependencies,
            ...component.dependencies,
          ]);
          const previewTargets = uniqueStrings([
            ...component.preview_targets,
            ...component.targets,
          ]);

          return (
            <section
              key={`${component.component_name}:${component.install_target}`}
              className={PANEL_CLASS_NAME}
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <p className="text-sm font-semibold text-foreground">
                    {component.title || component.component_name}
                  </p>
                  <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                    {getComponentSummary(component)}
                  </p>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  <Badge variant="outline">{component.install_target}</Badge>
                  {component.component_type ? (
                    <Badge variant="outline">{component.component_type}</Badge>
                  ) : null}
                  {component.match_score > 0 ? (
                    <Badge variant="outline">Score {component.match_score}</Badge>
                  ) : null}
                  {component.file_count > 0 ? (
                    <Badge variant="outline">{component.file_count} file{component.file_count === 1 ? "" : "s"}</Badge>
                  ) : null}
                </div>
              </div>

              {component.match_reason ? (
                <p className="mt-2 text-xs text-muted-foreground">
                  Why this matched: {component.match_reason}
                </p>
              ) : null}

              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <div className={SUBPANEL_CLASS_NAME}>
                  <p className={LABEL_CLASS_NAME}>File targets</p>
                  <div className="mt-2">
                    <StringBadgeList
                      emptyLabel="No target files were included."
                      items={previewTargets}
                    />
                  </div>
                </div>
                <div className={SUBPANEL_CLASS_NAME}>
                  <p className={LABEL_CLASS_NAME}>Dependencies</p>
                  <div className="mt-2">
                    <StringBadgeList
                      emptyLabel="No dependency packages were included."
                      items={dependencyPackages}
                    />
                  </div>
                </div>
              </div>

              <div className="mt-3">
                <NyxActionLinks
                  componentName={component.component_name}
                  registryUrl={component.registry_url}
                  sourceRepo={component.source_repo}
                />
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}

function NyxInstallPlanArtifact({ artifact }: { artifact: NormalizedArrowArtifact }) {
  const payload = asNyxInstallPlanPayload(artifact.payload);
  if (!payload) {
    return <EmptyArtifactState message="Nyx install plan details were unavailable." />;
  }

  return (
    <div className="space-y-3" data-testid="nyx-install-plan-artifact">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="space-y-1">
          <p className="text-sm leading-relaxed text-foreground/95">
            {artifact.summary || "Nyx install plan ready."}
          </p>
          {payload.package_manager_note ? (
            <p className="text-xs text-muted-foreground">{payload.package_manager_note}</p>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-1.5">
          {payload.intent_type ? (
            <Badge variant="outline">{formatIntentLabel(payload.intent_type)}</Badge>
          ) : null}
          <Badge variant="outline">{payload.components.length} component{payload.components.length === 1 ? "" : "s"}</Badge>
        </div>
      </div>

      {payload.query ? (
        <p className="text-xs text-muted-foreground">Prompt: {payload.query}</p>
      ) : null}

      <div className="grid gap-3">
        {payload.components.map((component) => (
          <section key={`${component.component_name}:${component.install_target}`} className={PANEL_CLASS_NAME}>
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <p className="text-sm font-semibold text-foreground">
                  {component.title || component.component_name}
                </p>
                <p className="mt-1 break-all font-mono text-xs text-muted-foreground">
                  {component.install_target}
                </p>
              </div>
              {component.file_count > 0 ? (
                <Badge variant="outline">{component.file_count} target file{component.file_count === 1 ? "" : "s"}</Badge>
              ) : null}
            </div>

            <div className="mt-3 grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,0.8fr)]">
              <div className={SUBPANEL_CLASS_NAME}>
                <p className={LABEL_CLASS_NAME}>Install steps</p>
                <ol className="mt-2 space-y-2">
                  {component.steps.map((step, index) => (
                    <li key={`${component.component_name}:${step.label}:${index}`} className="space-y-1">
                      <p className="text-xs text-foreground/90">{step.label || step.step_type || `Step ${index + 1}`}</p>
                      {step.command ? (
                        <code className="block overflow-x-auto rounded-md border border-white/10 bg-background/40 px-2 py-2 font-mono text-[11px] text-foreground">
                          {step.command}
                        </code>
                      ) : null}
                    </li>
                  ))}
                </ol>
              </div>

              <div className="space-y-3">
                <div className={SUBPANEL_CLASS_NAME}>
                  <p className={LABEL_CLASS_NAME}>Dependency packages</p>
                  <div className="mt-2">
                    <StringBadgeList
                      emptyLabel="No dependency packages were included."
                      items={component.dependency_packages}
                    />
                  </div>
                </div>

                <div className={SUBPANEL_CLASS_NAME}>
                  <p className={LABEL_CLASS_NAME}>File targets</p>
                  <div className="mt-2">
                    <StringBadgeList
                      emptyLabel="No file targets were included."
                      items={component.targets}
                    />
                  </div>
                </div>
              </div>
            </div>

            <div className="mt-3">
              <NyxActionLinks
                componentName={component.component_name}
                registryUrl={component.registry_url}
              />
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}

const DEPENDENCY_GROUP_LABELS: Record<NyxDependencyGroupKey, string> = {
  required: "Required in Metis",
  runtime: "Runtime",
  dev: "Dev",
  registry: "Registry dependencies",
};

function NyxDependencyReportArtifact({ artifact }: { artifact: NormalizedArrowArtifact }) {
  const payload = asNyxDependencyReportPayload(artifact.payload);
  if (!payload) {
    return <EmptyArtifactState message="Nyx dependency details were unavailable." />;
  }

  return (
    <div className="space-y-3" data-testid="nyx-dependency-report-artifact">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="space-y-1">
          <p className="text-sm leading-relaxed text-foreground/95">
            {artifact.summary || "Nyx dependency rollup ready."}
          </p>
          {payload.query ? (
            <p className="text-xs text-muted-foreground">Prompt: {payload.query}</p>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-1.5">
          {payload.component_count > 0 ? (
            <Badge variant="outline">{payload.component_count} component{payload.component_count === 1 ? "" : "s"}</Badge>
          ) : null}
          {payload.packages.length > 0 ? (
            <Badge variant="outline">{payload.packages.length} package{payload.packages.length === 1 ? "" : "s"}</Badge>
          ) : null}
        </div>
      </div>

      <div className="grid gap-3">
        {(Object.keys(DEPENDENCY_GROUP_LABELS) as NyxDependencyGroupKey[]).map((groupKey) => {
          const entries = payload.groups[groupKey] ?? [];
          if (entries.length === 0) {
            return null;
          }

          return (
            <section key={groupKey} className={PANEL_CLASS_NAME}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className={LABEL_CLASS_NAME}>{DEPENDENCY_GROUP_LABELS[groupKey]}</p>
                <Badge variant="outline">{entries.length} package{entries.length === 1 ? "" : "s"}</Badge>
              </div>

              <div className="mt-3 space-y-2">
                {entries.map((entry) => (
                  <div key={`${groupKey}:${entry.package_name}`} className={SUBPANEL_CLASS_NAME}>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="font-mono text-xs text-foreground">{entry.package_name}</p>
                      <Badge variant="outline">{entry.dependency_type}</Badge>
                    </div>

                    {entry.required_by.length > 0 ? (
                      <div className="mt-2 space-y-1">
                        <p className={LABEL_CLASS_NAME}>Used by</p>
                        <div className="flex flex-wrap gap-1.5">
                          {entry.required_by.map((componentName) => {
                            const previewHref = getNyxComponentPreviewHref(componentName);

                            return (
                              <Badge key={`${entry.package_name}:${componentName}`} variant="outline">
                                {previewHref ? (
                                  <Link href={previewHref}>{componentName}</Link>
                                ) : (
                                  componentName
                                )}
                              </Badge>
                            );
                          })}
                        </div>
                      </div>
                    ) : null}

                    {entry.install_targets.length > 0 ? (
                      <div className="mt-2 space-y-1">
                        <p className={LABEL_CLASS_NAME}>Install targets</p>
                        <StringBadgeList emptyLabel="" items={entry.install_targets} />
                      </div>
                    ) : null}

                    {entry.registry_urls.length > 0 ? (
                      <div className="mt-2 flex flex-wrap gap-2">
                        {entry.registry_urls.map((registryUrl) => (
                          <a
                            key={`${entry.package_name}:${registryUrl}`}
                            href={registryUrl}
                            target="_blank"
                            rel="noreferrer"
                            className={ACTION_LINK_CLASS_NAME}
                          >
                            Registry JSON
                          </a>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ))}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}

export function NyxArtifactContent({ artifact }: { artifact: NormalizedArrowArtifact }) {
  if (artifact.type === "nyx_component_selection") {
    return <NyxComponentSelectionArtifact artifact={artifact} />;
  }

  if (artifact.type === "nyx_install_plan") {
    return <NyxInstallPlanArtifact artifact={artifact} />;
  }

  if (artifact.type === "nyx_dependency_report") {
    return <NyxDependencyReportArtifact artifact={artifact} />;
  }

  return <EmptyArtifactState message="Unsupported Nyx artifact." />;
}