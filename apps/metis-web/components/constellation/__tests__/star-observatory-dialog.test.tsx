import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { IndexSummary } from "@/lib/api";
import type { UserStar } from "@/lib/constellation-types";

vi.mock("@/components/ui/dialog", () => ({
  Dialog: ({
    open,
    children,
  }: React.PropsWithChildren<{ open: boolean; onOpenChange?: (open: boolean) => void }>) => (
    open ? <div data-testid="dialog-root">{children}</div> : null
  ),
  DialogContent: ({ children }: React.PropsWithChildren<{ className?: string; showCloseButton?: boolean }>) => (
    <div>{children}</div>
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
const { StarObservatoryDialog } = await import("../star-observatory-dialog");

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

function renderDialog({
  star = makeStar(),
  entryMode = "existing" as const,
  availableIndexes = [] as IndexSummary[],
  indexesLoading = false,
  onIndexBuilt = vi.fn(),
  onUpdateStar = vi.fn().mockResolvedValue(true),
  onRemoveStar = vi.fn().mockResolvedValue(undefined),
  onOpenChat = vi.fn(),
} = {}) {
  render(
    <StarObservatoryDialog
      open
      onOpenChange={vi.fn()}
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

  return { onIndexBuilt, onUpdateStar, onRemoveStar, onOpenChat };
}

describe("StarObservatoryDialog", () => {
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
    };
    vi.mocked(buildIndexStream).mockImplementation(async (_paths, _settings, onEvent) => {
      onEvent({ type: "status", text: "embedding" });
      return builtIndex;
    });

    const { onIndexBuilt, onUpdateStar } = renderDialog({
      star: makeStar({ label: undefined, stage: "seed" }),
      entryMode: "new",
    });

    fireEvent.click(screen.getByRole("button", { name: "Local paths" }));
    fireEvent.click(screen.getByRole("checkbox", { name: /I understand these paths/i }));
    fireEvent.change(screen.getByPlaceholderText(/report\.pdf/), {
      target: { value: "/docs/field-notes.md\n/docs/summary.pdf" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Build and attach" }));

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
          linkedManifestPaths: ["/tmp/orbit-dossier.json"],
          activeManifestPath: "/tmp/orbit-dossier.json",
          linkedManifestPath: "/tmp/orbit-dossier.json",
        }),
      );
    });

    const payload = vi.mocked(onUpdateStar).mock.calls[0]?.[1];
    expect(payload?.stage).toBeUndefined();
    expect(await screen.findByText(/Built Orbit dossier and attached it/i)).toBeInTheDocument();
  });

  it("saves meaning, switches the active index, and opens chat from the active orbit", async () => {
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

    const { onOpenChat, onUpdateStar } = renderDialog({
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

    fireEvent.click(screen.getByRole("button", { name: "Open active chat" }));

    expect(onOpenChat).toHaveBeenCalledWith(atlasB.manifest_path, "Pattern Atlas");
    expect(screen.getByText(/Star details updated/i)).toBeInTheDocument();
    expect(screen.getAllByText("Atlas C").length).toBeGreaterThan(0);
  });

  it("detaches an attached index and keeps the remaining orbit active", async () => {
    const atlasA = makeIndex();
    const atlasB = makeIndex({
      index_id: "Atlas B",
      manifest_path: "/indexes/atlas-b.json",
      document_count: 6,
      chunk_count: 22,
      embedding_signature: "embed-b",
    });

    const { onUpdateStar } = renderDialog({
      star: makeStar({
        label: "Orbit map",
        linkedManifestPaths: [atlasA.manifest_path, atlasB.manifest_path],
        activeManifestPath: atlasA.manifest_path,
        linkedManifestPath: atlasA.manifest_path,
      }),
      availableIndexes: [atlasA, atlasB],
    });

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
});
