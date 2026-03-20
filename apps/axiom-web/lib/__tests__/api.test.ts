import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock the Tauri detection so getApiBase() falls back to env/default
vi.stubGlobal("window", { ...globalThis.window });

// Dynamically import after mocks are in place
const { fetchSessions, fetchSettings, fetchApiVersion, queryKnowledgeSearch } = await import(
  "../api"
);

describe("fetchSessions", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("returns parsed session list on success", async () => {
    const mockSessions = [
      { session_id: "abc", title: "Test", created_at: "2026-01-01T00:00:00Z" },
    ];
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockSessions),
      })
    );

    const result = await fetchSessions();
    expect(result).toEqual(mockSessions);
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("throws on non-ok response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        text: () => Promise.resolve("Internal Server Error"),
      })
    );

    await expect(fetchSessions()).rejects.toThrow();
  });
});

describe("fetchSettings", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("returns parsed settings object", async () => {
    const mockSettings = { llm_provider: "anthropic", chunk_size: 1000 };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockSettings),
      })
    );

    const result = await fetchSettings();
    expect(result).toEqual(mockSettings);
  });
});

describe("fetchApiVersion", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("returns version string", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ version: "1.0.0" }),
      })
    );

    const result = await fetchApiVersion();
    expect(result).toBe("1.0.0");
  });
});

describe("queryKnowledgeSearch", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("posts to the knowledge search endpoint with run and session ids", async () => {
    const mockResult = {
      run_id: "run-1",
      summary_text: "Found 2 relevant passages.",
      sources: [{ sid: "S1", source: "doc", snippet: "evidence" }],
      context_block: "context",
      top_score: 0.92,
      selected_mode: "Knowledge Search",
      retrieval_plan: { stages: [] },
      fallback: { triggered: false, strategy: "synthesize_anyway" },
    };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(mockResult),
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await queryKnowledgeSearch(
      "/tmp/index.json",
      "What does this say?",
      { selected_mode: "Knowledge Search" },
      { runId: "run-1", sessionId: "session-1" },
    );

    expect(result).toEqual(mockResult);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0]?.[0]).toContain("/v1/search/knowledge");
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({
      manifest_path: "/tmp/index.json",
      question: "What does this say?",
      settings: { selected_mode: "Knowledge Search" },
      run_id: "run-1",
      session_id: "session-1",
    });
  });
});
