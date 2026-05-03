import { describe, it, expect, vi, beforeEach } from "vitest";

const { fetchStarClusters, recommendStarsForContent } = await import("../api");

function mockJsonResponse<T>(data: T) {
  return {
    ok: true,
    json: () => Promise.resolve(data),
  };
}

describe("stars API helpers", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("fetchStarClusters calls GET /v1/stars/clusters and returns the parsed list", async () => {
    const assignments = [
      {
        star_id: "star-1",
        cluster_id: 0,
        x: 0.12,
        y: -0.34,
        cluster_label: "python performance",
      },
      {
        star_id: "star-2",
        cluster_id: 1,
        x: -0.55,
        y: 0.41,
        cluster_label: "graph theory",
      },
    ];

    const fetchMock = vi.fn().mockResolvedValue(mockJsonResponse(assignments));
    vi.stubGlobal("fetch", fetchMock);

    await expect(fetchStarClusters()).resolves.toEqual(assignments);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/v1/stars/clusters",
      {},
    );
  });

  it("recommendStarsForContent posts content to /v1/stars/recommend and returns the parsed response", async () => {
    const response = {
      recommendations: [
        {
          star_id: "star-9",
          similarity: 0.83,
          label: "Distributed systems",
          archetype: "tome",
        },
      ],
      create_new_suggested: false,
    };

    const fetchMock = vi.fn().mockResolvedValue(mockJsonResponse(response));
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      recommendStarsForContent("Notes on Raft consensus.", "note"),
    ).resolves.toEqual(response);

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/v1/stars/recommend",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          content: "Notes on Raft consensus.",
          content_type: "note",
        }),
      }),
    );
  });

  it("recommendStarsForContent defaults content_type to empty string when omitted", async () => {
    const response = { recommendations: [], create_new_suggested: true };
    const fetchMock = vi.fn().mockResolvedValue(mockJsonResponse(response));
    vi.stubGlobal("fetch", fetchMock);

    await expect(recommendStarsForContent("hello")).resolves.toEqual(response);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/v1/stars/recommend",
      expect.objectContaining({
        body: JSON.stringify({ content: "hello", content_type: "" }),
      }),
    );
  });
});
