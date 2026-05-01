import { describe, it, expect, vi, afterEach } from "vitest";

import { _resetRequestDedupForTests, dedupedFetch } from "../request-dedup";

afterEach(() => {
  vi.useRealTimers();
});

describe("dedupedFetch", () => {
  it("merges concurrent calls with the same key into one fetcher invocation", async () => {
    _resetRequestDedupForTests();
    const fetcher = vi.fn(async () => {
      await new Promise((r) => setTimeout(r, 5));
      return { ok: true } as const;
    });

    // Three concurrent callers; all pass the same key.
    const [a, b, c] = await Promise.all([
      dedupedFetch("GET /v1/settings", fetcher),
      dedupedFetch("GET /v1/settings", fetcher),
      dedupedFetch("GET /v1/settings", fetcher),
    ]);

    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(a).toEqual({ ok: true });
    expect(b).toEqual({ ok: true });
    expect(c).toEqual({ ok: true });
  });

  it("re-invokes the fetcher for a sequential call after the first settles", async () => {
    _resetRequestDedupForTests();
    const fetcher = vi.fn(async () => ({ ok: true }) as const);
    await dedupedFetch("GET /v1/settings", fetcher);
    await dedupedFetch("GET /v1/settings", fetcher);
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("treats different keys as separate in-flight slots", async () => {
    _resetRequestDedupForTests();
    const fetcherA = vi.fn(async () => "A");
    const fetcherB = vi.fn(async () => "B");
    const [a, b] = await Promise.all([
      dedupedFetch("GET /v1/settings", fetcherA),
      dedupedFetch("GET /v1/forge/techniques", fetcherB),
    ]);
    expect(a).toBe("A");
    expect(b).toBe("B");
    expect(fetcherA).toHaveBeenCalledTimes(1);
    expect(fetcherB).toHaveBeenCalledTimes(1);
  });

  it("propagates rejections to all concurrent callers from the same fetch", async () => {
    _resetRequestDedupForTests();
    const fetcher = vi.fn(async () => {
      throw new Error("boom");
    });
    const promises = [
      dedupedFetch("GET /v1/settings", fetcher).catch((e: Error) => e.message),
      dedupedFetch("GET /v1/settings", fetcher).catch((e: Error) => e.message),
    ];
    const results = await Promise.all(promises);
    expect(results).toEqual(["boom", "boom"]);
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("clears the in-flight slot after rejection so the next call can retry", async () => {
    _resetRequestDedupForTests();
    let attempt = 0;
    const fetcher = vi.fn(async () => {
      attempt += 1;
      if (attempt === 1) throw new Error("first");
      return "ok";
    });

    await dedupedFetch("GET /v1/settings", fetcher).catch(() => {});
    const result = await dedupedFetch("GET /v1/settings", fetcher);
    expect(result).toBe("ok");
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("rejects the in-flight promise if the fetcher never settles within the stall window", async () => {
    // Regression test: without a timeout, a hung HTTP request
    // (network stall, server hang, etc.) leaves the dedup slot
    // occupied for the tab's lifetime — every later caller waits
    // forever. The timeout must reject the in-flight promise so
    // the slot clears and the next call gets a fresh fetch.
    _resetRequestDedupForTests();
    vi.useFakeTimers();
    // Fetcher returns a promise that never settles.
    const neverSettles = vi.fn(() => new Promise<unknown>(() => {}));

    const stuck = dedupedFetch("GET /v1/settings", neverSettles).catch(
      (e: Error) => e.message,
    );
    // Advance past the stall window — the timeout should fire and
    // reject. (Use 30_001 to be safely past the 30_000ms threshold
    // regardless of the implementation's strict-vs-non-strict
    // comparison.)
    await vi.advanceTimersByTimeAsync(30_001);
    const message = await stuck;
    expect(message).toMatch(/timed out|stall/i);
    expect(neverSettles).toHaveBeenCalledTimes(1);
  });

  it("allows a retry on a fresh call after the stall-timeout fires", async () => {
    _resetRequestDedupForTests();
    vi.useFakeTimers();
    const stuckFetcher = vi.fn(() => new Promise<unknown>(() => {}));
    const okFetcher = vi.fn(async () => "ok");

    const stuck = dedupedFetch("GET /v1/settings", stuckFetcher).catch(() => null);
    await vi.advanceTimersByTimeAsync(30_001);
    await stuck;

    // Slot should be clear; next call uses a fresh fetcher.
    vi.useRealTimers();
    const result = await dedupedFetch("GET /v1/settings", okFetcher);
    expect(result).toBe("ok");
    expect(okFetcher).toHaveBeenCalledTimes(1);
  });
});
