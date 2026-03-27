import type { ComponentProps, ReactNode } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { IndexBuildResult, IndexSummary } from "@/lib/api";
import type { UserStar } from "@/lib/constellation-types";

vi.mock("lucide-react", async (importOriginal) => {
  const actual = await importOriginal<typeof import("lucide-react")>();
  const Icon = () => null;
  return {
    ...actual,
    Circle: Icon,
    Orbit: Icon,
    Sparkles: Icon,
  };
});

vi.mock("@/components/ui/dialog", () => ({
  Dialog: ({
    open,
    children,
  }: {
    open: boolean;
    children: ReactNode;
  }) => (open ? <div>{children}</div> : null),
  DialogContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  DialogDescription: ({ children }: { children: ReactNode }) => <p>{children}</p>,
  DialogHeader: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: ReactNode }) => <h2>{children}</h2>,
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

import { buildIndexStream, fetchSettings } from "@/lib/api";
import { StarObservatoryDialog } from "../star-observatory-dialog";

const baseStar: UserStar = {
  id: "star-1",
  x: 0.3,
  y: 0.4,
  size: 1.2,
  createdAt: 1710000000000,
};

const linkedIndex: IndexSummary = {
  index_id: "Atlas notes",
  manifest_path: "/indexes/atlas.json",
  document_count: 8,
  chunk_count: 64,
  backend: "faiss",
  created_at: "2026-03-26T12:00:00.000Z",
  embedding_signature: "embed-a",
};

const alternateIndex: IndexSummary = {
  index_id: "Observatory log",
  manifest_path: "/indexes/observatory.json",
  document_count: 5,
  chunk_count: 21,
  backend: "faiss",
  created_at: "2026-03-25T12:00:00.000Z",
  embedding_signature: "embed-b",
};

function renderDialog(
  overrides: Partial<ComponentProps<typeof StarObservatoryDialog>> = {},
) {
  const onOpenChange = vi.fn();
  const onIndexBuilt = vi.fn();
  const onUpdateStar = vi.fn().mockResolvedValue(true);
  const onRemoveStar = vi.fn().mockResolvedValue(undefined);
  const onOpenChat = vi.fn();

  render(
    <StarObservatoryDialog
      open
      onOpenChange={onOpenChange}
      star={baseStar}
      entryMode="new"
      availableIndexes={[linkedIndex, alternateIndex]}
      indexesLoading={false}
      onIndexBuilt={onIndexBuilt}
      onUpdateStar={onUpdateStar}
      onRemoveStar={onRemoveStar}
      onOpenChat={onOpenChat}
      {...overrides}
    />,
  );

  return {
    onOpenChange,
    onIndexBuilt,
    onUpdateStar,
    onRemoveStar,
    onOpenChat,
  };
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("StarObservatoryDialog", () => {
  it("starts new stars in build mode and builds then links a new index", async () => {
    const buildResult: IndexBuildResult = {
      index_id: "Northern archive",
      manifest_path: "/indexes/northern-archive.json",
      document_count: 4,
      chunk_count: 18,
      embedding_signature: "embed-build",
      vector_backend: "faiss",
    };

    vi.mocked(fetchSettings).mockResolvedValue({});
    vi.mocked(buildIndexStream).mockImplementation(async (_paths, _settings, onEvent) => {
      onEvent({ type: "status", text: "embedding documents" });
      return buildResult;
    });

    const { onIndexBuilt, onUpdateStar } = renderDialog();

    expect(screen.getByText("New star selected")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Feed this star" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Build and link" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Local paths" }));
    fireEvent.click(
      screen.getByRole("checkbox", {
        name: "I understand these paths must be accessible to the local API.",
      }),
    );
    fireEvent.change(
      screen.getByPlaceholderText(/\/home\/user\/docs\/report\.pdf/),
      { target: { value: "/docs/a.md\n/docs/b.md" } },
    );

    fireEvent.click(screen.getByRole("button", { name: "Build and link" }));

    await waitFor(() => {
      expect(buildIndexStream).toHaveBeenCalledWith(
        ["/docs/a.md", "/docs/b.md"],
        {},
        expect.any(Function),
      );
    });

    await waitFor(() => {
      expect(onIndexBuilt).toHaveBeenCalledWith(buildResult);
      expect(onUpdateStar).toHaveBeenCalledWith(baseStar.id, {
        label: "Northern archive",
        linkedManifestPath: "/indexes/northern-archive.json",
      });
      expect(screen.getByText("Built Northern archive and linked it to this star.")).toBeInTheDocument();
      expect(screen.getByText("Latest build")).toBeInTheDocument();
      expect(screen.getByDisplayValue("Northern archive")).toBeInTheDocument();
    });
  });

  it("starts linked existing stars in overview mode and saves metadata changes", async () => {
    const star: UserStar = {
      ...baseStar,
      label: "Atlas star",
      linkedManifestPath: linkedIndex.manifest_path,
    };
    const { onOpenChat, onUpdateStar } = renderDialog({
      star,
      entryMode: "existing",
    });

    expect(screen.getByText("Existing star selected")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Star observatory" }),
    ).toBeInTheDocument();
    expect(screen.getByDisplayValue("Atlas star")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Atlas notes" })).toBeInTheDocument();
    expect(screen.getAllByText("8").length).toBeGreaterThan(0);
    expect(screen.getAllByText("64").length).toBeGreaterThan(0);

    fireEvent.change(screen.getByLabelText("Star label"), {
      target: { value: "Atlas revised" },
    });
    fireEvent.change(screen.getByLabelText("Linked index"), {
      target: { value: alternateIndex.manifest_path },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save star" }));

    await waitFor(() => {
      expect(onUpdateStar).toHaveBeenCalledWith(baseStar.id, {
        label: "Atlas revised",
        linkedManifestPath: alternateIndex.manifest_path,
      });
      expect(screen.getByText("Star details updated.")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Open linked chat" }));

    expect(onOpenChat).toHaveBeenCalledWith(
      alternateIndex.manifest_path,
      "Atlas revised",
    );
  });
});
