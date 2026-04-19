import React from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { IndexSummary } from "@/lib/api";
import type { LearningRoute, UserStar } from "@/lib/constellation-types";

vi.mock("@/components/ui/dialog", () => ({
  Dialog: ({
    open,
    onOpenChange,
    children,
  }: React.PropsWithChildren<{ open: boolean; onOpenChange?: (open: boolean) => void }>) => (
    open ? (
      <div data-testid="dialog-root">
        <button type="button" onClick={() => onOpenChange?.(false)}>
          Close panel
        </button>
        {children}
      </div>
    ) : null
  ),
  DialogContent: (
    props: React.PropsWithChildren<{
      className?: string;
      showCloseButton?: boolean;
      showOverlay?: boolean;
    }>,
  ) => {
    const { children, ...rest } = props;
    const contentProps = { ...rest };
    delete contentProps.showCloseButton;
    delete contentProps.showOverlay;
    return <div {...contentProps}>{children}</div>;
  },
  DialogDescription: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogHeader: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogTitle: ({ children }: React.PropsWithChildren) => <h1>{children}</h1>,
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    buildIndexStream: vi.fn(),
    fetchSettings: vi.fn(),
    suggestStarArchetypes: vi.fn(),
    uploadFiles: vi.fn(),
  };
});

const { buildIndexStream, fetchSettings, suggestStarArchetypes } = await import("@/lib/api");
const { StarDetailsPanel } = await import("../star-observatory-dialog");

function makeIndex(overrides: Partial<IndexSummary> = {}): IndexSummary {
  return {
    index_id: "Atlas A",
    manifest_path: "/indexes/atlas-a.json",
    document_count: 4,
    chunk_count: 16,
    backend: "faiss",
    created_at: "2026-03-26T12:00:00.000Z",
    embedding_signature: "embed-a",
    ...overrides,
  };
}

function makeStar(overrides: Partial<UserStar> = {}): UserStar {
  return {
    id: "star-1",
    x: 0.2,
    y: 0.3,
    size: 0.95,
    createdAt: 1,
    ...overrides,
  };
}

function renderPanel({
  star = makeStar(),
  entryMode = "existing",
  availableIndexes = [] as IndexSummary[],
  indexesLoading = false,
  onOpenChange = vi.fn(),
  onIndexBuilt = vi.fn(),
  onUpdateStar = vi.fn().mockResolvedValue(true),
  onRemoveStar = vi.fn().mockResolvedValue(undefined),
  onOpenChat = vi.fn(),
  learningRoutePreview = null,
  learningRouteLoading = false,
  learningRouteError = null,
  onStartCourse = vi.fn(),
  onSaveLearningRoutePreview = vi.fn(),
  onDiscardLearningRoutePreview = vi.fn(),
  onRegenerateLearningRoute = vi.fn(),
  onLaunchLearningRouteStep = vi.fn(),
  onSetLearningRouteStepStatus = vi.fn(),
}: Partial<React.ComponentProps<typeof StarDetailsPanel>> & { star?: UserStar } = {}) {
  render(
    <StarDetailsPanel
      open
      onOpenChange={onOpenChange}
      star={star}
      entryMode={entryMode}
      closeLockedUntil={0}
      availableIndexes={availableIndexes}
      indexesLoading={indexesLoading}
      onIndexBuilt={onIndexBuilt}
      onUpdateStar={onUpdateStar}
      onRemoveStar={onRemoveStar}
      onOpenChat={onOpenChat}
      learningRoutePreview={learningRoutePreview}
      learningRouteLoading={learningRouteLoading}
      learningRouteError={learningRouteError}
      onStartCourse={onStartCourse}
      onSaveLearningRoutePreview={onSaveLearningRoutePreview}
      onDiscardLearningRoutePreview={onDiscardLearningRoutePreview}
      onRegenerateLearningRoute={onRegenerateLearningRoute}
      onLaunchLearningRouteStep={onLaunchLearningRouteStep}
      onSetLearningRouteStepStatus={onSetLearningRouteStepStatus}
    />,
  );

  return {
    onOpenChange,
    onIndexBuilt,
    onUpdateStar,
    onRemoveStar,
    onOpenChat,
    onStartCourse,
    onSaveLearningRoutePreview,
    onDiscardLearningRoutePreview,
    onRegenerateLearningRoute,
    onLaunchLearningRouteStep,
    onSetLearningRouteStepStatus,
  };
}

function makeLearningRoute(overrides: Partial<LearningRoute> = {}): LearningRoute {
  return {
    id: "route-1",
    title: "Route Through the Stars: Pattern Atlas",
    originStarId: "star-1",
    createdAt: "2026-03-31T10:00:00+00:00",
    updatedAt: "2026-03-31T10:00:00+00:00",
    steps: [
      {
        id: "step-1",
        kind: "orient",
        title: "Orient Around Pattern Atlas",
        objective: "Get the lay of the land.",
        rationale: "Start broad before specializing.",
        manifestPath: "/indexes/atlas-a.json",
        tutorPrompt: "Tutor me through the overview.",
        estimatedMinutes: 12,
        status: "todo",
      },
      {
        id: "step-2",
        kind: "foundations",
        title: "Lay the Foundations",
        objective: "Build the core concepts.",
        rationale: "Anchor the route.",
        manifestPath: "/indexes/atlas-b.json",
        tutorPrompt: "Tutor me through the foundations.",
        estimatedMinutes: 18,
        status: "done",
        completedAt: "2026-03-31T10:20:00+00:00",
      },
    ],
    ...overrides,
  };
}

describe("StarDetailsPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchSettings).mockResolvedValue({});
    vi.mocked(suggestStarArchetypes).mockResolvedValue([
      {
        id: "scroll",
        name: "Scroll",
        description: "Long-form prose, reports, and academic papers",
        icon_hint: "BookOpen",
        why: "Detected as a document-heavy upload.",
        settings_overrides: {},
        score: 0.9,
      },
    ]);
  });

  it("builds a new index and attaches it to a new star", async () => {
    const builtIndex = {
      index_id: "Orbit dossier",
      manifest_path: "/tmp/orbit-dossier.json",
      document_count: 3,
      chunk_count: 12,
      embedding_signature: "embed-orbit",
      vector_backend: "faiss",
      brain_pass: {
        provider: "fallback",
        placement: {
          faculty_id: "reasoning",
          confidence: 0.68,
          rationale: "Filed near Reasoning because the upload emphasized argument and evidence.",
          provenance: "fallback-heuristic",
          secondary_faculty_id: "knowledge",
        },
      },
    };

    vi.mocked(buildIndexStream).mockImplementation(async (_paths, _settings, onEvent) => {
      onEvent({ type: "status", text: "embedding" });
      return builtIndex;
    });

    const { onIndexBuilt, onUpdateStar } = renderPanel({
      star: makeStar({ label: undefined, stage: "seed" }),
      entryMode: "new",
    });

    fireEvent.click(screen.getByRole("button", { name: "Local paths" }));
    fireEvent.click(screen.getByRole("checkbox", { name: /I understand these paths/i }));
    fireEvent.change(screen.getByPlaceholderText(/report\.pdf/), {
      target: { value: "/docs/field-notes.md\n/docs/summary.pdf" },
    });

    // Wait for the archetype picker to complete its async suggestion fetch
    // and auto-select an archetype (which enables the build button).
    await waitFor(() => {
      expect(
        screen.getAllByRole("button", { name: "Add and build" }).at(-1),
      ).not.toBeDisabled();
    });
    fireEvent.click(screen.getAllByRole("button", { name: "Add and build" }).at(-1) as HTMLButtonElement);

    await waitFor(() => {
      expect(buildIndexStream).toHaveBeenCalledWith(
        ["/docs/field-notes.md", "/docs/summary.pdf"],
        {},
        expect.any(Function),
      );
    });

    expect(onIndexBuilt).toHaveBeenCalledWith(builtIndex);

    await waitFor(() => {
      expect(onUpdateStar).toHaveBeenCalledWith(
        "star-1",
        expect.objectContaining({
          label: "Orbit dossier",
          primaryDomainId: "reasoning",
          relatedDomainIds: ["knowledge"],
          intent: "Filed by METIS brain pass",
          notes: "Filed near Reasoning because the upload emphasized argument and evidence.",
          linkedManifestPaths: ["/tmp/orbit-dossier.json"],
          activeManifestPath: "/tmp/orbit-dossier.json",
          linkedManifestPath: "/tmp/orbit-dossier.json",
          x: expect.any(Number),
          y: expect.any(Number),
        }),
      );
    });

    expect(await screen.findByText(/Built Orbit dossier and filed it near Reasoning/i)).toBeInTheDocument();
  });

  it("updates star details, switches the active index, and opens chat", async () => {
    const atlasA = makeIndex();
    const atlasB = makeIndex({
      index_id: "Atlas B",
      manifest_path: "/indexes/atlas-b.json",
      document_count: 6,
      chunk_count: 22,
      embedding_signature: "embed-b",
    });
    const atlasC = makeIndex({
      index_id: "Atlas C",
      manifest_path: "/indexes/atlas-c.json",
      document_count: 2,
      chunk_count: 8,
      embedding_signature: "embed-c",
    });

    const { onOpenChat, onUpdateStar } = renderPanel({
      star: makeStar({
        label: "Pattern Atlas",
        primaryDomainId: "knowledge",
        relatedDomainIds: ["memory"],
        stage: "growing",
        intent: "Compare signals",
        notes: "Initial pass",
        linkedManifestPaths: [atlasA.manifest_path, atlasB.manifest_path],
        activeManifestPath: atlasA.manifest_path,
        linkedManifestPath: atlasA.manifest_path,
      }),
      availableIndexes: [atlasA, atlasB, atlasC],
    });

    fireEvent.click(screen.getByRole("button", { name: "Attached sources" }));
    fireEvent.click(screen.getByRole("button", { name: "Set active" }));
    fireEvent.change(screen.getByPlaceholderText("knowledge"), {
      target: { value: "synthesis" },
    });
    fireEvent.change(screen.getByPlaceholderText("memory, strategy"), {
      target: { value: "reasoning, memory" },
    });
    const stageSelect = screen
      .getAllByRole("combobox")
      .find((element) => element.tagName === "SELECT");
    expect(stageSelect).toBeTruthy();
    fireEvent.change(stageSelect as HTMLSelectElement, {
      target: { value: "seed" },
    });
    fireEvent.change(screen.getByLabelText("What is this star for?"), {
      target: { value: "Connect research patterns across active sources." },
    });
    fireEvent.change(screen.getByLabelText("Supporting notes"), {
      target: { value: "Use the active atlas for the next chat launch." },
    });

    fireEvent.click(screen.getByRole("button", { name: "Save meaning" }));

    await waitFor(() => {
      expect(onUpdateStar).toHaveBeenCalledWith(
        "star-1",
        expect.objectContaining({
          label: "Pattern Atlas",
          primaryDomainId: "synthesis",
          relatedDomainIds: ["reasoning", "memory"],
          stage: "seed",
          intent: "Connect research patterns across active sources.",
          notes: "Use the active atlas for the next chat launch.",
          linkedManifestPaths: [atlasA.manifest_path, atlasB.manifest_path],
          activeManifestPath: atlasB.manifest_path,
          linkedManifestPath: atlasB.manifest_path,
        }),
      );
    });

    fireEvent.click(screen.getAllByRole("button", { name: "Open chat" })[0]);

    expect(onOpenChat).toHaveBeenCalledWith({
      manifestPath: atlasB.manifest_path,
      label: "Pattern Atlas",
    });
    expect(screen.getByText(/Star details updated/i)).toBeInTheDocument();
    expect(screen.getAllByText("Atlas C").length).toBeGreaterThan(0);
  });

  it("detaches an attached index and keeps the remaining source active", async () => {
    const atlasA = makeIndex();
    const atlasB = makeIndex({
      index_id: "Atlas B",
      manifest_path: "/indexes/atlas-b.json",
      document_count: 6,
      chunk_count: 22,
      embedding_signature: "embed-b",
    });

    const { onUpdateStar } = renderPanel({
      star: makeStar({
        label: "Orbit map",
        linkedManifestPaths: [atlasA.manifest_path, atlasB.manifest_path],
        activeManifestPath: atlasA.manifest_path,
        linkedManifestPath: atlasA.manifest_path,
      }),
      availableIndexes: [atlasA, atlasB],
    });

    fireEvent.click(screen.getByRole("button", { name: "Attached sources" }));
    fireEvent.click(screen.getAllByRole("button", { name: "Detach" })[0]);

    await waitFor(() => {
      expect(onUpdateStar).toHaveBeenCalledWith(
        "star-1",
        expect.objectContaining({
          linkedManifestPaths: [atlasB.manifest_path],
          activeManifestPath: atlasB.manifest_path,
          linkedManifestPath: atlasB.manifest_path,
        }),
      );
    });

    expect(screen.getByText(/Atlas A detached/i)).toBeInTheDocument();
  });

  it("prevents closing while a build is in progress", async () => {
    vi.mocked(buildIndexStream).mockImplementation(
      () => new Promise(() => undefined),
    );

    const { onOpenChange } = renderPanel({
      star: makeStar({ stage: "seed" }),
      entryMode: "new",
    });

    fireEvent.click(screen.getByRole("button", { name: "Local paths" }));
    fireEvent.click(screen.getByRole("checkbox", { name: /I understand these paths/i }));
    fireEvent.change(screen.getByPlaceholderText(/report\.pdf/), {
      target: { value: "/docs/field-notes.md" },
    });

    // Wait for archetype picker async fetch to complete and enable the button.
    await waitFor(() => {
      expect(
        screen.getAllByRole("button", { name: "Add and build" }).at(-1),
      ).not.toBeDisabled();
    });
    fireEvent.click(screen.getAllByRole("button", { name: "Add and build" }).at(-1) as HTMLButtonElement);

    await waitFor(() => {
      expect(buildIndexStream).toHaveBeenCalled();
    });

    fireEvent.click(screen.getByRole("button", { name: "Close panel" }));

    expect(onOpenChange).not.toHaveBeenCalled();
  });

  it("keeps the existing-star footer actions visible and exposes cascade delete", () => {
    renderPanel({
      star: makeStar({
        label: "Mapped star",
        linkedManifestPaths: ["/indexes/atlas-a.json"],
        activeManifestPath: "/indexes/atlas-a.json",
        linkedManifestPath: "/indexes/atlas-a.json",
      }),
    });

    const actions = screen.getByTestId("star-details-actions");
    expect(within(actions).getByRole("button", { name: "Save meaning" })).toBeInTheDocument();
    expect(within(actions).getByRole("button", { name: "Open chat" })).toBeInTheDocument();
    expect(within(actions).getByRole("button", { name: "Add another source" })).toBeInTheDocument();
    expect(within(actions).getByRole("button", { name: "Delete star and sources" })).toBeInTheDocument();
  });

  it("shows Start course only when the selected star has an attached source", () => {
    const { rerender } = render(
      <StarDetailsPanel
        open
        onOpenChange={vi.fn()}
        star={makeStar({
          label: "Mapped star",
          linkedManifestPaths: ["/indexes/atlas-a.json"],
          activeManifestPath: "/indexes/atlas-a.json",
          linkedManifestPath: "/indexes/atlas-a.json",
        })}
        entryMode="existing"
        closeLockedUntil={0}
        availableIndexes={[makeIndex()]}
        indexesLoading={false}
        onIndexBuilt={vi.fn()}
        onUpdateStar={vi.fn().mockResolvedValue(true)}
        onRemoveStar={vi.fn().mockResolvedValue(undefined)}
        onOpenChat={vi.fn()}
        learningRoutePreview={null}
        learningRouteLoading={false}
        learningRouteError={null}
        onStartCourse={vi.fn()}
        onSaveLearningRoutePreview={vi.fn()}
        onDiscardLearningRoutePreview={vi.fn()}
        onRegenerateLearningRoute={vi.fn()}
        onLaunchLearningRouteStep={vi.fn()}
        onSetLearningRouteStepStatus={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: "Start course" })).toBeInTheDocument();

    rerender(
      <StarDetailsPanel
        open
        onOpenChange={vi.fn()}
        star={makeStar({ label: "Unbound star" })}
        entryMode="existing"
        closeLockedUntil={0}
        availableIndexes={[]}
        indexesLoading={false}
        onIndexBuilt={vi.fn()}
        onUpdateStar={vi.fn().mockResolvedValue(true)}
        onRemoveStar={vi.fn().mockResolvedValue(undefined)}
        onOpenChat={vi.fn()}
        learningRoutePreview={null}
        learningRouteLoading={false}
        learningRouteError={null}
        onStartCourse={vi.fn()}
        onSaveLearningRoutePreview={vi.fn()}
        onDiscardLearningRoutePreview={vi.fn()}
        onRegenerateLearningRoute={vi.fn()}
        onLaunchLearningRouteStep={vi.fn()}
        onSetLearningRouteStepStatus={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: "Start course" })).toBeDisabled();
  });

  it("renders saved routes and lets the user launch Tutor or toggle completion", async () => {
    const route = makeLearningRoute();
    const { onLaunchLearningRouteStep, onSetLearningRouteStepStatus } = renderPanel({
      star: makeStar({
        label: "Pattern Atlas",
        linkedManifestPaths: ["/indexes/atlas-a.json", "/indexes/atlas-b.json"],
        activeManifestPath: "/indexes/atlas-a.json",
        linkedManifestPath: "/indexes/atlas-a.json",
        learningRoute: route,
      }),
      availableIndexes: [
        makeIndex({ manifest_path: "/indexes/atlas-a.json" }),
        makeIndex({ manifest_path: "/indexes/atlas-b.json", index_id: "Atlas B" }),
      ],
    });

    expect(screen.getByText("Route Through the Stars: Pattern Atlas")).toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("button", { name: "Open in Tutor" })[0]);
    expect(onLaunchLearningRouteStep).toHaveBeenCalledWith(
      expect.objectContaining({ id: "step-1", tutorPrompt: "Tutor me through the overview." }),
    );

    fireEvent.click(screen.getByRole("button", { name: "Mark complete" }));
    expect(onSetLearningRouteStepStatus).toHaveBeenCalledWith("step-1", "done");

    fireEvent.click(screen.getByRole("button", { name: "Reopen step" }));
    expect(onSetLearningRouteStepStatus).toHaveBeenCalledWith("step-2", "todo");
  });

  it("renders preview actions and wires save or discard callbacks", () => {
    const preview = makeLearningRoute({
      id: "preview-route-1",
      title: "Route Through the Stars: Preview",
      steps: [
        {
          id: "preview-step-1",
          kind: "orient",
          title: "Orient Around Preview",
          objective: "Preview the path.",
          rationale: "Get the feel of the course.",
          manifestPath: "/indexes/atlas-a.json",
          tutorPrompt: "Tutor me through the preview.",
          estimatedMinutes: 10,
          status: "todo",
        },
      ],
    });
    const { onSaveLearningRoutePreview, onDiscardLearningRoutePreview } = renderPanel({
      star: makeStar({
        label: "Pattern Atlas",
        linkedManifestPaths: ["/indexes/atlas-a.json"],
        activeManifestPath: "/indexes/atlas-a.json",
        linkedManifestPath: "/indexes/atlas-a.json",
      }),
      availableIndexes: [makeIndex()],
      learningRoutePreview: preview,
    });

    fireEvent.click(screen.getByRole("button", { name: "Save route" }));
    expect(onSaveLearningRoutePreview).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "Discard" }));
    expect(onDiscardLearningRoutePreview).toHaveBeenCalledTimes(1);
  });

  it("opens a delete confirmation and cancels without removing the star", async () => {
    const { onRemoveStar } = renderPanel({
      star: makeStar({
        label: "Mapped star",
        linkedManifestPaths: ["/indexes/atlas-a.json"],
        activeManifestPath: "/indexes/atlas-a.json",
        linkedManifestPath: "/indexes/atlas-a.json",
      }),
    });

    fireEvent.click(screen.getByRole("button", { name: "Delete star and sources" }));

    expect(screen.getByTestId("star-delete-confirmation")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    await waitFor(() => {
      expect(screen.queryByTestId("star-delete-confirmation")).not.toBeInTheDocument();
    });
    expect(onRemoveStar).not.toHaveBeenCalled();
  });

  it("confirms cascade delete with the star id and attached manifest paths", async () => {
    const atlasA = makeIndex({ manifest_path: "/indexes/atlas-a.json" });
    const atlasB = makeIndex({
      index_id: "Atlas B",
      manifest_path: "/indexes/atlas-b.json",
      embedding_signature: "embed-b",
    });
    const { onRemoveStar } = renderPanel({
      star: makeStar({
        id: "star-delete",
        label: "Mapped star",
        linkedManifestPaths: [atlasA.manifest_path, atlasB.manifest_path],
        activeManifestPath: atlasB.manifest_path,
        linkedManifestPath: atlasB.manifest_path,
      }),
      availableIndexes: [atlasA, atlasB],
    });

    fireEvent.click(screen.getByRole("button", { name: "Delete star and sources" }));
    fireEvent.click(screen.getAllByRole("button", { name: "Delete star and sources" }).at(-1) as HTMLButtonElement);

    await waitFor(() => {
      expect(onRemoveStar).toHaveBeenCalledWith({
        starId: "star-delete",
        manifestPaths: [atlasA.manifest_path, atlasB.manifest_path],
      });
    });
  });

  describe("Stellar identity panel (M02 Phase 7.1)", () => {
    it("renders the procedural character sheet with spectral class, temperature, luminosity, archetype, and palette", () => {
      renderPanel({ star: makeStar({ id: "identity-panel-star" }) });

      const panel = screen.getByTestId("star-identity-panel");
      expect(panel).toBeTruthy();
      expect(within(panel).getByText("Stellar identity")).toBeTruthy();

      // Each numeric field is populated (value is derived from the seed so
      // we only assert the field exists and is non-empty).
      const spectralClass = within(panel).getByText((_, node) =>
        node?.getAttribute("data-field") === "spectral-class",
      );
      expect(spectralClass.textContent?.trim().length).toBeGreaterThan(0);

      const temperature = within(panel).getByText((_, node) =>
        node?.getAttribute("data-field") === "temperature",
      );
      expect(temperature.textContent).toMatch(/K$/);

      const luminosity = within(panel).getByText((_, node) =>
        node?.getAttribute("data-field") === "luminosity",
      );
      expect(luminosity.textContent).toMatch(/L☉$/);

      const archetype = within(panel).getByText((_, node) =>
        node?.getAttribute("data-field") === "archetype",
      );
      expect(archetype.textContent?.trim().length).toBeGreaterThan(0);

      const palette = within(panel).getByLabelText("Stellar palette");
      const swatchKeys = Array.from(palette.querySelectorAll("[data-palette-key]")).map(
        (node) => node.getAttribute("data-palette-key"),
      );
      expect(swatchKeys).toEqual(["core", "halo", "accent", "rim", "surface"]);
    });

    it("derives a deterministic identity from the star id so two renders of the same star agree", () => {
      const first = renderWithReturn({ star: makeStar({ id: "identity-determinism" }) });
      const firstSpectral = within(first.panel).getByText((_, node) =>
        node?.getAttribute("data-field") === "spectral-class",
      ).textContent;
      const firstTemp = within(first.panel).getByText((_, node) =>
        node?.getAttribute("data-field") === "temperature",
      ).textContent;
      first.unmount();

      const second = renderWithReturn({ star: makeStar({ id: "identity-determinism" }) });
      const secondSpectral = within(second.panel).getByText((_, node) =>
        node?.getAttribute("data-field") === "spectral-class",
      ).textContent;
      const secondTemp = within(second.panel).getByText((_, node) =>
        node?.getAttribute("data-field") === "temperature",
      ).textContent;
      expect(secondSpectral).toBe(firstSpectral);
      expect(secondTemp).toBe(firstTemp);
      second.unmount();
    });
  });
});

// Minimal helper for the identity-panel determinism test — mirrors renderPanel
// but returns the cleanup hook so two renders can share the same id and assert
// on both panels in sequence.
function renderWithReturn(
  props: Partial<React.ComponentProps<typeof StarDetailsPanel>> & { star?: UserStar } = {},
) {
  const result = render(
    <StarDetailsPanel
      open
      onOpenChange={vi.fn()}
      star={props.star ?? { id: "star-1", x: 0.2, y: 0.3, size: 0.95, createdAt: 1 }}
      entryMode={props.entryMode ?? "existing"}
      closeLockedUntil={0}
      availableIndexes={props.availableIndexes ?? []}
      indexesLoading={props.indexesLoading ?? false}
      onIndexBuilt={props.onIndexBuilt ?? vi.fn()}
      onUpdateStar={props.onUpdateStar ?? vi.fn().mockResolvedValue(true)}
      onRemoveStar={props.onRemoveStar ?? vi.fn().mockResolvedValue(undefined)}
      onOpenChat={props.onOpenChat ?? vi.fn()}
      learningRoutePreview={props.learningRoutePreview ?? null}
      learningRouteLoading={props.learningRouteLoading ?? false}
      learningRouteError={props.learningRouteError ?? null}
      onStartCourse={props.onStartCourse ?? vi.fn()}
      onSaveLearningRoutePreview={props.onSaveLearningRoutePreview ?? vi.fn()}
      onDiscardLearningRoutePreview={props.onDiscardLearningRoutePreview ?? vi.fn()}
      onRegenerateLearningRoute={props.onRegenerateLearningRoute ?? vi.fn()}
      onLaunchLearningRouteStep={props.onLaunchLearningRouteStep ?? vi.fn()}
      onSetLearningRouteStepStatus={props.onSetLearningRouteStepStatus ?? vi.fn()}
    />,
  );
  return { panel: screen.getByTestId("star-identity-panel"), unmount: result.unmount };
}
