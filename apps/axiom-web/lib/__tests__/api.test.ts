import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock the Tauri detection so getApiBase() falls back to env/default
vi.stubGlobal("window", { ...globalThis.window });

// Dynamically import after mocks are in place
const { fetchSessions, fetchSettings, fetchApiVersion } = await import(
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
