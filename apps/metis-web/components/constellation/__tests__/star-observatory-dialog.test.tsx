import React from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { IndexSummary } from "@/lib/api";
import type { UserStar } from "@/lib/constellation-types";

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
  DialogContent: ({
    className: _className,
    showCloseButton: _showCloseButton,
    showOverlay: _showOverlay,
    children,
    ...rest
  }: React.PropsWithChildren<{ className?: string; showCloseButton?: boolean; showOverlay?: boolean }>) => (
    <div {...rest}>{children}</div>
  ),
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
    uploadFiles: vi.fn(),
  };
});

const { buildIndexStream, fetchSettings } = await import("@/lib/api");
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
    />,
  );

  return { onOpenChange, onIndexBuilt, onUpdateStar, onRemoveStar, onOpenChat };
}

describe("StarDetailsPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchSettings).mockResolvedValue({});
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

    expect(onOpenChat).toHaveBeenCalledWith(atlasB.manifest_path, "Pattern Atlas");
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
});
