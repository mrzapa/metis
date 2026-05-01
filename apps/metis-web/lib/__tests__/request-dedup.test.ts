import { describe, it, expect, vi } from "vitest";

import { _resetRequestDedupForTests, dedupedFetch } from "../request-dedup";

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
});
