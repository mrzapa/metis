/**
 * In-flight request dedup — collapse concurrent calls for the same
 * `key` (typically `"GET /v1/settings"`-style) into a single fetcher
 * invocation. Solves M21 #6: a fresh page load was firing
 * `/v1/settings` 30+ times due to React Strict double-mount + four to
 * six components calling `fetchSettings` independently per render.
 *
 * **Contract:**
 *   - While a fetcher is in flight, every call with the same `key`
 *     returns the same Promise. The fetcher is invoked exactly once
 *     for that batch.
 *   - When the in-flight Promise settles (resolved OR rejected), the
 *     slot is cleared. The next call with that key starts a fresh
 *     fetch — this is dedup, NOT caching.
 *   - On rejection, all concurrent waiters see the same rejection.
 *     Subsequent callers can retry with a new fetch.
 *
 * **What this does NOT do:**
 *   - It does not cache responses. A long stream of distinct-time
 *     calls to the same key results in N fetches when nothing else
 *     is concurrent.
 *   - It does not coalesce different keys. `"GET /v1/settings"` and
 *     `"GET /v1/settings?lang=en"` are two slots.
 *   - It does not throttle. If a component is genuinely calling the
 *     same key in a tight loop, that pattern is the bug; this helper
 *     just prevents N React-Strict double-mounts from compounding it.
 */

const inFlight = new Map<string, Promise<unknown>>();

export function dedupedFetch<T>(key: string, fetcher: () => Promise<T>): Promise<T> {
  const existing = inFlight.get(key) as Promise<T> | undefined;
  if (existing) return existing;
  const p = fetcher().finally(() => {
    // Only clear if WE'RE still the in-flight entry. A subsequent
    // call could have already replaced us, though under the current
    // logic that can't happen (we only set in this function and a
    // new call only sets when nothing's in-flight). Defensive.
    if (inFlight.get(key) === p) inFlight.delete(key);
  });
  inFlight.set(key, p);
  return p;
}

/**
 * Test-only escape hatch. The dedup map is process-global; tests need
 * a clean slate between runs to avoid bleed-through. Production code
 * MUST NOT call this — it would invalidate any in-flight callers.
 */
export function _resetRequestDedupForTests(): void {
  inFlight.clear();
}
