# 0011 - Network audit retention and privacy

- **Status:** Accepted (proposed with this PR)
- **Date:** 2026-04-19

## Context

M17 Phase 1 (ADR 0010) chose the interception strategy — an explicit
`audited_urlopen` wrapper at call sites plus SDK-invocation-layer
events for LangChain vendor SDKs. Phase 2 answers the next question:
*what is persisted for each outbound call, for how long, and in what
form?*

The product constraint is a *truth surface*, not a firewall. The panel
must be credible to a privacy-focused user who will, reasonably, read
the on-disk schema and ask "what exactly are you keeping about me?".
That constraint drives three decisions:

1. **Never persist the full URL.** Query strings routinely carry API
   keys, user-generated prompts (think: a DuckDuckGo search query
   containing a personal medical question), and other
   personally-identifying text. Path components beyond the first
   segment (e.g. a Reddit subreddit name) can also be identifying.
2. **Bound the log.** Keeping every call forever turns an audit log
   into a behavioural dossier on the user. A rolling window is
   honest: we keep enough to show what happened recently, not
   enough to profile you.
3. **Store it locally, in a format the user can read.** SQLite
   because it is single-file, zero-dependency, and amenable to the
   per-provider aggregation queries the Phase 5 panel needs. No
   upload. Ever.

ADR 0010 named the open question as *"how long? what fields? hashed
URL paths vs. prefix-only vs. full?"*. This ADR locks the answer
after the Phase 2 implementation pass.

## Decision

### 1. On-disk shape — a SQLite database beside `skill_candidates.db`

The store is a single SQLite file at
`<repo_root>/network_audit.db`, matching the convention established by
`metis_app/services/skill_repository.py::_DEFAULT_CANDIDATES_DB_PATH`
for local-first per-feature databases.

Schema (v0 — see *Migration posture* below):

```sql
CREATE TABLE network_audit_events (
    id               TEXT PRIMARY KEY,      -- 26-char Crockford ULID
    timestamp_ms     INTEGER NOT NULL,       -- UNIX epoch milliseconds
    method           TEXT NOT NULL,          -- "GET" / "POST" / ...
    url_host         TEXT NOT NULL,          -- hostname only, lowercased
    url_path_prefix  TEXT NOT NULL,          -- first path segment, e.g. "/v1"
    provider_key     TEXT NOT NULL,          -- KNOWN_PROVIDERS key, or "unclassified"
    trigger_feature  TEXT NOT NULL,          -- caller-declared feature tag
    size_bytes_in    INTEGER,                -- response body bytes; NULL if blocked / unknown
    size_bytes_out   INTEGER,                -- request body bytes; NULL for plain GETs
    latency_ms       INTEGER,                -- wall-clock; NULL if blocked pre-dispatch
    status_code      INTEGER,                -- HTTP status; NULL if blocked / connection failed
    user_initiated   INTEGER NOT NULL,       -- 0/1
    blocked          INTEGER NOT NULL        -- 0/1; true iff kill switch intercepted
);
CREATE INDEX idx_audit_timestamp ON network_audit_events (timestamp_ms);
CREATE INDEX idx_audit_provider ON network_audit_events (provider_key, timestamp_ms);
```

There is **no** `url_query` column, no `url_path_suffix` column, no
headers column, no request-body column, no response-body column. Those
omissions are load-bearing — see *URL privacy invariants* below.

WAL journal mode (`PRAGMA journal_mode=WAL`) is enabled on connect so
the Phase 5 API routes can read concurrently with the writer. All
writes go through a single `threading.Lock` because stdlib `sqlite3`
is not asyncio-friendly, and because an in-process audit trail does
not need the throughput of a sharded logger.

### 2. Rolling bounded retention — 30 days OR 50,000 events

Whichever limit is hit first evicts the oldest rows. The policy is
enforced in two places:

- **Opportunistically on append**, every ~100 inserts (constant
  amortised overhead).
- **Unconditionally on `vacuum()`**, intended to be called on app
  startup before the API routes begin serving.

The 30-day window is long enough to be useful for "was that DuckDuckGo
call last Thursday from me or from autonomous research?" and short
enough that it is not a behavioural archive. The 50,000-event cap is
the secondary safety valve — a runaway worker cannot bloat the DB
past a few megabytes before the oldest events roll out.

Both limits are constructor arguments on `NetworkAuditStore`
(`max_rows`, `max_age_seconds`) so tests can exercise eviction with
small fixtures and future phases can expose user-controlled knobs if
the need arises.

### 3. Per-event fields (the dataclass schema)

`NetworkAuditEvent` is a frozen, slotted dataclass — no post-construction
mutation. The fields are exactly those listed in the schema above,
plus one type-level invariant:

- `query_params_stored: Literal[False]`. The literal pins the static
  expectation; `__post_init__` raises `ValueError` at runtime if a
  caller somehow forces `True`. There is no code path anywhere in
  M17 in which query parameters reach disk.

Timestamps MUST be timezone-aware (UTC). The dataclass enforces this
in `__post_init__`; the store converts to epoch milliseconds for
indexing.

### 4. URL privacy invariants

A single helper, `metis_app.network_audit.events.sanitize_url`, is
the only code path that turns a raw URL into `(url_host,
url_path_prefix)`. Its contract:

- Host is `urlsplit(url).hostname` — lowercases, strips port, strips
  userinfo. Malformed URLs return `("unknown", "/")`.
- Path prefix is the first non-empty segment, prepended with `/`.
  Empty paths collapse to `"/"`. Everything beyond the first segment
  is dropped.
- Query string is **never** touched. Fragment is **never** touched.

Unit tests in `tests/test_network_audit_events.py` pin the behaviour
against the full corpus of example URLs (OpenAI with an `api_key=…`
query, Reddit subreddit paths, IPv6 hosts, userinfo-prefixed URLs,
localhost with port, malformed input). Loosening this helper without
updating both the ADR and the tests is a privacy regression.

### 5. ULID-compatible IDs without a dependency

Event IDs are 26-character Crockford-base32 ULIDs generated by
`metis_app.network_audit.store.new_ulid`. The implementation is
stdlib-only: `time.time_ns()` for the 48-bit millisecond prefix and
`secrets.token_bytes(10)` for the 80-bit random suffix. A canonical
ULID parser will accept these IDs — we match the spec closely enough
for interop without taking on an external `ulid-py` dependency for
one helper.

Monotonic-within-millisecond ordering is not guaranteed; if a future
phase needs strict ordering for events generated in the same
millisecond, the helper can be upgraded. The current use case
(newest-first display in the panel) tolerates the tie-break being
non-monotonic.

### 6. Migration posture

This is schema **v0**. No `schema_version` column, no migration
machinery. If the schema changes, Phase 2's decision is:

1. Add the column / table with a best-effort `CREATE … IF NOT EXISTS`
   on connect.
2. If the change is incompatible (rename, drop, type change), land a
   one-shot migration at the same PR that changes the schema, and
   introduce the `schema_version` column at that point.

The store is a rolling window of debug-grade telemetry, not a
system-of-record. Losing the contents to a bad migration is a
papercut, not a data-loss incident — so we do not front-load a
full migration framework.

### 7. Explicit boundaries — what we do NOT store

- **No full URL.** Host + first path segment only.
- **No query string.** Never, under any circumstance.
- **No userinfo.** `urlsplit(…).hostname` strips it.
- **No port.** Same.
- **No path beyond the first segment.** Reddit subreddit, arXiv
  paper ID, specific API endpoint — all dropped.
- **No request or response headers.** Not user-agent, not
  authorization, not anything.
- **No request or response bodies.** Not even size histograms beyond
  the `size_bytes_in` / `size_bytes_out` totals.
- **No analytics upload.** The file is local. If a future phase
  proposes any outbound from this subsystem, it must itself pass
  through the audit panel.
- **No per-user analytics.** METIS is single-user today; there is
  no "user ID" field because there is no multi-user layer to bind
  to.

## Consequences

**Positive:**
- The stored shape is small, auditable, and the user can open the
  file in any SQLite browser and verify the claims in this ADR
  against the bytes on disk.
- Per-provider count queries (the Phase 5 panel's "events in last 7
  days" column) are O(log n) on the
  `idx_audit_provider (provider_key, timestamp_ms)` index.
- The rolling window caps the file size to single-digit megabytes
  in the expected-usage case.
- No external dependency — SQLite is stdlib; ULID helper is stdlib.

**Negative / honest deficiencies of v0:**
- Aggregating across a longer window than 30 days is not possible
  from the store alone. If a future privacy-audit feature needs a
  longer horizon, it must either widen the window (at the cost of
  disk) or roll up to a separate aggregated-counts table. Both are
  acceptable extensions; neither is in scope for M17 v1.
- The store is single-writer. A future Tauri-sidecar enforcement
  path (Phase 8 stretch) that writes from Rust would need either
  IPC-through-Python or its own cooperative locking discipline.
- Schema changes cost a manual migration. This is a deliberate
  trade against prematurely building migration plumbing.

## Alternatives considered

### JSON-lines rolling log (mirror `metis_app/services/trace_store.py`)

*Rejected.* The trace store's append-only JSONL pattern is a clean
fit for "replay a single run"-style queries. It is the wrong tool
for the Phase 5 panel, which needs "count events by provider in the
last 7 days". On JSONL that is O(n) with a full-file scan per
request; on SQLite with a composite index it is O(log n) with an
index probe. The store *mirrors* the rolling-bounded-with-startup-
vacuum shape of `TraceStore` but diverges on the backing store by
design. Audit history and run-trace history have different
retention, different access patterns, and different audiences, and
should not piggyback on each other.

### External time-series database (InfluxDB, Prometheus, TimescaleDB)

*Rejected.* A TSDB would turn "count by provider in the last 7 days"
into a native query, but it contradicts the local-first posture of
the audit panel. Requiring a user to stand up a second database
(or, worse, pointing the audit subsystem at a remote endpoint) is
the opposite of the trust promise. A single-file SQLite database is
the right shape for a privacy surface.

### `ulid-py` dependency

*Rejected.* A 26-character Crockford-base32 ULID is a few dozen lines
of stdlib code; adding a wheel to the dependency tree for one
helper is a net cost. If future phases pull in a richer ULID feature
set (monotonic within-millisecond, canonical round-trip, etc.) we
revisit.

### Hashed full URLs

*Rejected.* Storing, say, `sha256(url)` would let the panel say "this
exact URL was fetched N times" without revealing the URL to a reader
of the DB. Two problems: the hash is not actually private against a
determined adversary (query-string space is small enough to brute-force
for common API patterns), and it does not help the user — they cannot
read a SHA-256 and reason about it. Keep the honest shape: host +
first path segment, and nothing more.

## References

- `plans/network-audit/plan.md` — Phase 2 section, lines 251-287.
- `plans/network-audit/plan.md` — *Privacy posture callout* and
  *What NOT to do in M17*.
- `docs/adr/0010-network-audit-interception.md` — Phase 1 ADR.
- `metis_app/network_audit/events.py` — `NetworkAuditEvent` and
  `sanitize_url` implementation.
- `metis_app/network_audit/store.py` — `NetworkAuditStore`,
  `new_ulid`, `make_synthetic_event`.
- `tests/test_network_audit_events.py` / `tests/test_network_audit_store.py`
  — invariants pinned.
