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
 *   - If the underlying fetcher never settles (network stall, server
 *     hang) within `STALL_TIMEOUT_MS`, the in-flight promise is
 *     rejected with a timeout error so the slot clears. Without
 *     this, a single hung HTTP request would deadlock every later
 *     caller of the same key for the tab's lifetime.
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
 *   - It does not abort the underlying network request when the
 *     stall timeout fires. The in-flight Promise rejects (so waiters
 *     unblock and the slot clears for the next caller); the original
 *     `fetch` may still complete on the wire and is harmlessly
 *     ignored. Long-poll endpoints (e.g. `/v1/comets/events`) MUST
 *     NOT use this helper — they'd reject before the poll naturally
 *     completes.
 */

/**
 * Stall timeout for in-flight requests, in ms. Generous enough to
 * cover any reasonable status-fetch / list-fetch / config-fetch on a
 * slow connection, tight enough that a hung request doesn't deadlock
 * the dedup slot for the tab's lifetime.
 */
const STALL_TIMEOUT_MS = 30_000;

const inFlight = new Map<string, Promise<unknown>>();

export function dedupedFetch<T>(key: string, fetcher: () => Promise<T>): Promise<T> {
  const existing = inFlight.get(key) as Promise<T> | undefined;
  if (existing) return existing;
  let timeoutHandle: ReturnType<typeof setTimeout> | null = null;
  const stallGuard = new Promise<never>((_, reject) => {
    timeoutHandle = setTimeout(() => {
      reject(new Error(`dedupedFetch: ${key} timed out after ${STALL_TIMEOUT_MS}ms`));
    }, STALL_TIMEOUT_MS);
  });
  const p = Promise.race([fetcher(), stallGuard]).finally(() => {
    if (timeoutHandle !== null) clearTimeout(timeoutHandle);
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
