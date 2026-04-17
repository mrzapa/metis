import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useConstellationStars } from "@/hooks/use-constellation-stars";
import { fetchSettings, postNourishmentEvent, updateSettings } from "@/lib/api";
import { normalizeUserStar, type UserStar } from "@/lib/constellation-types";

vi.mock("@/lib/api", () => ({
  fetchSettings: vi.fn(),
  updateSettings: vi.fn(),
  postNourishmentEvent: vi.fn(),
}));

const STORAGE_KEY = "metis_constellation_user_stars";
const SETTINGS_KEY = "landing_constellation_user_stars";

function seedLocalStars(stars: UserStar[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(stars));
}

describe("useConstellationStars", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    vi.mocked(fetchSettings).mockResolvedValue({} as Record<string, unknown>);
    vi.mocked(updateSettings).mockResolvedValue({});
    vi.mocked(postNourishmentEvent).mockResolvedValue(undefined as never);
  });

  it("removeUserStarById uses current stars and prunes inbound connections", async () => {
    seedLocalStars([
      { id: "a", x: 0.1, y: 0.2, size: 1, createdAt: 1 },
      { id: "b", x: 0.2, y: 0.3, size: 1, createdAt: 2 },
    ]);

    const { result } = renderHook(() => useConstellationStars());
    const staleRemoveUserStarById = result.current.removeUserStarById;

    await act(async () => {
      const added = await result.current.addUserStars([
        {
          x: 0.3,
          y: 0.4,
          size: 1,
          label: "new-link",
          connectedUserStarIds: ["b"],
        },
      ]);
      expect(added).toBe(1);
    });

    await act(async () => {
      await staleRemoveUserStarById("b");
    });

    expect(result.current.userStars.map((star) => star.id)).not.toContain("b");
    expect(result.current.userStars).toHaveLength(2);

    const addedStar = result.current.userStars.find((star) => star.label === "new-link");
    expect(addedStar).toBeDefined();
    expect(addedStar?.connectedUserStarIds).toBeUndefined();

    expect(vi.mocked(fetchSettings)).not.toHaveBeenCalled();
    expect(vi.mocked(updateSettings)).toHaveBeenCalledWith({ [SETTINGS_KEY]: expect.any(Array) });
  });

  it("removeLastUserStar uses current stars when called from a stale callback", async () => {
    seedLocalStars([
      { id: "a", x: 0.1, y: 0.2, size: 1, createdAt: 1 },
      { id: "b", x: 0.2, y: 0.3, size: 1, createdAt: 2 },
    ]);

    const { result } = renderHook(() => useConstellationStars());
    const staleRemoveLastUserStar = result.current.removeLastUserStar;

    await act(async () => {
      const added = await result.current.addUserStars([
        {
          x: 0.4,
          y: 0.5,
          size: 1,
          label: "tail",
        },
      ]);
      expect(added).toBe(1);
    });

    await act(async () => {
      await staleRemoveLastUserStar();
    });

    expect(result.current.userStars).toHaveLength(2);
    expect(result.current.userStars.map((star) => star.id)).toEqual(["a", "b"]);
  });

  it("replaceUserStars restores an exact saved snapshot including user-star links", async () => {
    const originalSnapshot: UserStar[] = [
      {
        id: "a",
        createdAt: 1,
        x: 0.1,
        y: 0.2,
        size: 1,
        label: "Alpha",
        connectedUserStarIds: ["b"],
        linkedManifestPaths: ["/tmp/alpha.json"],
        relatedDomainIds: ["memory"],
      },
      {
        id: "b",
        createdAt: 2,
        x: 0.2,
        y: 0.3,
        size: 1.1,
        label: "Beta",
        connectedUserStarIds: ["a"],
      },
    ];
    const normalizedSnapshot = originalSnapshot.map((star) => normalizeUserStar(star));
    seedLocalStars(originalSnapshot);

    const { result } = renderHook(() => useConstellationStars());

    await act(async () => {
      await result.current.removeUserStarById("a");
    });

    expect(result.current.userStars.map((star) => star.id)).toEqual(["b"]);
    expect(result.current.userStars[0]?.connectedUserStarIds).toBeUndefined();

    await act(async () => {
      await result.current.replaceUserStars(originalSnapshot);
    });

    expect(result.current.userStars).toEqual(normalizedSnapshot);
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]")).toEqual(normalizedSnapshot);
    expect(vi.mocked(updateSettings)).toHaveBeenLastCalledWith({ [SETTINGS_KEY]: normalizedSnapshot });
  });

  it("loads settings-seeded stars as stable editable records", async () => {
    const settingsSeed = {
      label: "Settings seed",
      x: 0.25,
      y: 0.3,
      primaryDomainId: "knowledge",
      linkedManifestPath: "/indexes/settings-seed.json",
    };
    vi.mocked(fetchSettings).mockResolvedValue({
      [SETTINGS_KEY]: [settingsSeed],
    } as Record<string, unknown>);

    const firstRender = renderHook(() => useConstellationStars());

    await waitFor(() => {
      expect(firstRender.result.current.userStars).toHaveLength(1);
    });

    const loadedStar = firstRender.result.current.userStars[0];
    expect(loadedStar).toEqual(
      expect.objectContaining({
        id: expect.stringMatching(/^default-star-/),
        label: "Settings seed",
        linkedManifestPath: "/indexes/settings-seed.json",
        linkedManifestPaths: ["/indexes/settings-seed.json"],
        primaryDomainId: "knowledge",
        size: 1,
        stage: "growing",
      }),
    );
    expect(loadedStar.createdAt).toBeGreaterThan(0);
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]")).toEqual([loadedStar]);

    await act(async () => {
      const updated = await firstRender.result.current.updateUserStarById(loadedStar.id, {
        label: "Edited settings seed",
        notes: "Now editable like any other star.",
      });
      expect(updated).toBe(true);
    });

    expect(firstRender.result.current.userStars[0]).toEqual(
      expect.objectContaining({
        id: loadedStar.id,
        label: "Edited settings seed",
        notes: "Now editable like any other star.",
      }),
    );
    expect(vi.mocked(updateSettings)).toHaveBeenLastCalledWith({
      [SETTINGS_KEY]: [
        expect.objectContaining({
          id: loadedStar.id,
          label: "Edited settings seed",
          notes: "Now editable like any other star.",
        }),
      ],
    });

    firstRender.unmount();
    localStorage.clear();
    vi.clearAllMocks();
    vi.mocked(fetchSettings).mockResolvedValue({
      [SETTINGS_KEY]: [settingsSeed],
    } as Record<string, unknown>);
    vi.mocked(updateSettings).mockResolvedValue({});

    const secondRender = renderHook(() => useConstellationStars());

    await waitFor(() => {
      expect(secondRender.result.current.userStars).toHaveLength(1);
    });

    expect(secondRender.result.current.userStars[0]).toEqual(
      expect.objectContaining({
        id: loadedStar.id,
        createdAt: loadedStar.createdAt,
        label: "Settings seed",
      }),
    );
  });

  it("keeps fully populated settings stars unchanged", async () => {
    const fullyPopulatedStar = normalizeUserStar({
      id: "full-settings-star",
      createdAt: 42,
      x: 0.4,
      y: 0.6,
      size: 1.2,
      label: "Already normalized",
      primaryDomainId: "memory",
      relatedDomainIds: ["knowledge"],
      linkedManifestPaths: ["/indexes/already-normalized.json"],
      activeManifestPath: "/indexes/already-normalized.json",
      linkedManifestPath: "/indexes/already-normalized.json",
      notes: "Persisted payload",
    });
    vi.mocked(fetchSettings).mockResolvedValue({
      [SETTINGS_KEY]: [fullyPopulatedStar],
    } as Record<string, unknown>);

    const { result } = renderHook(() => useConstellationStars());

    await waitFor(() => {
      expect(result.current.userStars).toEqual([fullyPopulatedStar]);
    });
  });

  it("persists saved learning routes through star updates and settings sync", async () => {
    seedLocalStars([
      {
        id: "star-1",
        x: 0.2,
        y: 0.3,
        size: 1,
        createdAt: 1,
        label: "Route star",
      },
    ]);

    const { result } = renderHook(() => useConstellationStars());

    await act(async () => {
      const updated = await result.current.updateUserStarById("star-1", {
        learningRoute: {
          id: "route-1",
          title: "Route Through the Stars: Route star",
          originStarId: "star-1",
          createdAt: "2026-03-31T10:00:00+00:00",
          updatedAt: "2026-03-31T10:00:00+00:00",
          steps: [
            {
              id: "step-1",
              kind: "orient",
              title: "Orient Around Route star",
              objective: "Map the route.",
              rationale: "Start broad.",
              manifestPath: "/indexes/atlas-a.json",
              tutorPrompt: "Tutor me through the route.",
              estimatedMinutes: 12,
              status: "todo",
            },
          ],
        },
      });
      expect(updated).toBe(true);
    });

    expect(result.current.userStars[0]?.learningRoute).toEqual(
      expect.objectContaining({
        id: "route-1",
        steps: [expect.objectContaining({ id: "step-1", status: "todo" })],
      }),
    );
    expect(vi.mocked(updateSettings)).toHaveBeenLastCalledWith({
      [SETTINGS_KEY]: [
        expect.objectContaining({
          id: "star-1",
          learningRoute: expect.objectContaining({
            id: "route-1",
            steps: [expect.objectContaining({ id: "step-1" })],
          }),
        }),
      ],
    });
  });
});
