# 0008 - Feed Storage Format

- **Status:** Accepted (M13 Phase 3 prep)
- **Date:** 2026-04-25

## Context

M13 Phase 2 (PR #541) shipped the Seedling lifecycle shell — a ticking
worker, a status surface, and a companion-activity bridge. Phase 2 is
deliberately a no-op heartbeat: it does not poll feeds, classify items,
or move comets through their lifecycle.

Phase 3 turns that heartbeat into a continuous-ingestion loop. Before
the worker can call into `NewsIngestService` from inside a tick, the
plan (`plans/seedling-and-feed/plan.md` Phase 3) requires a durable
home for two things the news-comet pipeline currently keeps in
volatile memory:

1. **Active comets.** `metis_app/api_litestar/routes/comets.py:36`
   declares `_active_comets: list[CometEvent] = []` at module scope. A
   process restart loses every drifting/approaching comet, so a comet
   the user saw last night never resolves on this morning's run.
2. **Seen-item dedup.** `NewsIngestService._seen_hashes`
   (`metis_app/services/news_ingest_service.py:252`) is an in-process
   `OrderedDict` capped at 2 000 hashes. After restart it is empty;
   the next poll re-emits the entire RSS / HN window as "new" and
   the user sees a flood of stale comets.

Phase 3 also wants per-source cursors so polling becomes incremental
rather than re-scanning every entry every cycle, and it wants OPML
import so users can move their existing feed reader into METIS without
hand-editing JSON.

This ADR locks the storage shape for those four concerns —
durable comets, durable dedup, per-source cursors, and OPML import —
before any worker code touches them.

The repo already ships the load-bearing patterns:

- `metis_app/services/skill_repository.py::_DEFAULT_CANDIDATES_DB_PATH`
  established the per-feature single-SQLite-file convention at
  `<repo_root>/skill_candidates.db`. ADR 0011 followed that same
  pattern with `network_audit.db`.
- `metis_app/services/atlas_repository.py` shows the in-repo SQLite
  scaffolding: `_connect`, `_transaction`, `init_db` with idempotent
  `CREATE TABLE IF NOT EXISTS` plus targeted indexes, and a
  `_shared_conn` for `:memory:` test mode.
- `metis_app/models/comet_event.py` already gives us the wire-shape
  dataclasses (`NewsItem`, `CometEvent`) plus `to_dict()` / phase
  enums. The store does not need to invent a new schema vocabulary.

Phase 3 therefore has to wire these together; it does not need to
re-invent SQLite plumbing. This ADR records the shape.

## Decision

Store news-comet state in a new per-feature SQLite file at
`<repo_root>/news_items.db`, accessed through a new
`metis_app/services/news_feed_repository.py` that mirrors the
`atlas_repository` pattern. **Do not extend `rag_sessions.db`.** The
shared session DB is already four tables wide (atlas, assistants,
sessions, improvements) and adding feed churn on top of it would
muddy backup, retention, and Phase 5 panel queries.

### 1. Three tables — `news_items`, `comet_events`, `feed_cursors`

```sql
CREATE TABLE news_items (
    item_hash         TEXT PRIMARY KEY,        -- 16-char sha256 prefix; see "Dedup hash" below
    item_id           TEXT NOT NULL,           -- existing NewsItem.item_id (12-char hex)
    title             TEXT NOT NULL,
    summary           TEXT NOT NULL,
    url               TEXT NOT NULL,
    source_channel    TEXT NOT NULL,           -- "rss" / "hn" / "reddit" / "exa" / ...
    source_url        TEXT NOT NULL,           -- which feed/sub/channel produced it; "" for global
    published_at      REAL NOT NULL,           -- epoch seconds
    fetched_at        REAL NOT NULL,
    raw_metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX idx_news_items_fetched ON news_items (fetched_at DESC);
CREATE INDEX idx_news_items_source  ON news_items (source_channel, source_url, fetched_at DESC);

CREATE TABLE comet_events (
    comet_id              TEXT PRIMARY KEY,
    item_hash             TEXT NOT NULL REFERENCES news_items(item_hash),
    faculty_id            TEXT NOT NULL DEFAULT '',
    secondary_faculty_id  TEXT NOT NULL DEFAULT '',
    classification_score  REAL NOT NULL DEFAULT 0.0,
    decision              TEXT NOT NULL,        -- "drift" / "approach" / "absorb"
    relevance_score       REAL NOT NULL DEFAULT 0.0,
    gap_score             REAL NOT NULL DEFAULT 0.0,
    phase                 TEXT NOT NULL,        -- CometPhase literal
    created_at            REAL NOT NULL,
    decided_at            REAL NOT NULL DEFAULT 0.0,
    absorbed_at           REAL NOT NULL DEFAULT 0.0,
    atlas_entry_id        TEXT NOT NULL DEFAULT '',  -- set by Phase 3+ when an absorb completes
    notes                 TEXT NOT NULL DEFAULT ''   -- absorb/dismiss notes
);
CREATE INDEX idx_comet_events_phase   ON comet_events (phase, created_at DESC);
CREATE INDEX idx_comet_events_active  ON comet_events (created_at DESC)
    WHERE phase NOT IN ('absorbed','dismissed','fading');
CREATE INDEX idx_comet_events_atlas   ON comet_events (atlas_entry_id)
    WHERE atlas_entry_id != '';

CREATE TABLE feed_cursors (
    source_channel        TEXT NOT NULL,        -- "rss" / "hn" / "reddit" / ...
    source_url            TEXT NOT NULL,        -- feed URL, sub name, or "" for global
    last_polled_at        REAL NOT NULL,
    last_success_at       REAL NOT NULL DEFAULT 0.0,
    last_item_hash        TEXT NOT NULL DEFAULT '',
    failure_count         INTEGER NOT NULL DEFAULT 0,
    paused_until          REAL NOT NULL DEFAULT 0.0,
    PRIMARY KEY (source_channel, source_url)
);
```

WAL journal mode (`PRAGMA journal_mode=WAL`) is enabled on connect so
the SSE comet stream can read while the worker writes. All writes go
through a single `threading.Lock` per `NewsFeedRepository` instance —
matching the `atlas_repository` posture and the
`network_audit.runtime` pattern.

Note that `comet_events.item_hash` is a plain reference, not
`ON DELETE CASCADE`. The cleaner in §4 is responsible for protecting
active comets explicitly; an unconditional cascade would silently
erase a `drifting`/`approaching`/`absorbing` comet whose parent
`news_items` row aged out of the rolling window. The retention path
must always pass through the phase guard described below.

Schema posture follows ADR 0011 §6: this is **v0**, additive
`CREATE … IF NOT EXISTS` is used for compatible changes (extra
columns with defaults, new indexes), and a one-shot migration is
committed in the same PR for any incompatible change. There is no
migration framework. `init_db` is idempotent and is invoked from
`NewsFeedRepository`'s first `_transaction`, matching how
`atlas_repository.init_db` is gated on `_schema_ready`. No app-startup
hook is needed.

`NewsFeedRepository` accepts `db_path=":memory:"` for tests; the
shared in-process connection pattern from `atlas_repository._shared_conn`
applies, so memory-mode tests do not lose state between transactions.

`raw_metadata_json` extends the stored shape beyond the existing
`CometEvent.to_dict()` wire shape — `to_dict()` does not include
`NewsItem.raw_metadata`. The repository hydrates the column back into
`NewsItem.raw_metadata` on read so the dataclass round-trip is
faithful even though the HTTP response shape is unchanged.

### 2. Dedup hash — keep the existing algorithm, persist it

Use the existing
`NewsIngestService._item_hash(title, url) = sha256(f"{title.lower()}|{url.lower()}")[:16]`.
Phase 3 wraps it as `news_feed_repository.compute_item_hash(...)` so
both the ingest service and the repository agree, and stores it as
`news_items.item_hash` (the primary key). On every poll, the worker
runs the same hash over fetched items and uses
`INSERT … ON CONFLICT(item_hash) DO NOTHING` to drop duplicates
without an explicit "have I seen this?" round-trip per item.

`NewsIngestService._seen_hashes` becomes an in-process **read-through
cache** in front of the repository, kept for fast-path latency on
high-frequency polls. The persisted set is the source of truth.

### 3. Per-source cursors

Every poll cycle reads `feed_cursors` for the configured RSS feeds
and Reddit subs, fetches incrementally where the source supports it
(RSS: `If-Modified-Since` / `ETag` against `last_polled_at` /
`last_item_hash`; HN/Reddit: per-source ordering already keeps newest
first, so cursor is the newest hash seen last cycle), and writes
`last_polled_at`, `last_success_at`, and `last_item_hash` back at the
end of the cycle. `failure_count` and `paused_until` move the existing
`_SourceHealth` backoff state from process memory into the DB so a
restart does not lose the "this feed has been failing for an hour,
back off" signal.

### 4. Retention policy

Two writers, one cleaner. The cleaner is the only deleter; ad-hoc
`DELETE` from outside `news_feed_repository.cleanup(...)` is a bug.

- **`news_items`:** rolling 14-day window, evict oldest by
  `fetched_at`. Hard cap of 50 000 rows, whichever hits first. The
  cleaner **must** guard against orphaning live comets:

  ```sql
  DELETE FROM news_items
   WHERE fetched_at < :cutoff
     AND item_hash NOT IN (
       SELECT item_hash FROM comet_events
        WHERE phase IN ('entering','drifting','approaching','absorbing')
           OR (phase = 'absorbed' AND atlas_entry_id != '')
     );
  ```

  The 50 000-row cap uses the same `NOT IN` exclusion against the
  bottom-N-by-`fetched_at`. This is the load-bearing reason
  `comet_events.item_hash` is **not** declared `ON DELETE CASCADE`:
  an unguarded cascade would silently delete an active comet whose
  parent item aged out, contradicting the next bullet.
- **`comet_events`:**
  - Active phases (`entering`, `drifting`, `approaching`,
    `absorbing`) survive eviction regardless of age — losing those
    contradicts decision (1) of the *Context* above.
  - `dismissed` and `fading` evicted after 7 days.
  - `absorbed` rows with a non-empty `atlas_entry_id` are retained
    until the linked Atlas entry is removed. The lookup is done in
    Python, **not** in cross-database SQL: `atlas_entries` lives in
    `rag_sessions.db`, not in `news_items.db`, so a literal
    `SELECT … FROM atlas_entries` from inside this DB would fail at
    runtime. Per cycle the cleaner instead:
    1. Reads `SELECT comet_id, atlas_entry_id FROM comet_events
       WHERE phase = 'absorbed' AND atlas_entry_id != ''` from
       `news_items.db`.
    2. Calls `AtlasRepository.list_entry_ids()` (a thin Python
       helper that wraps `SELECT entry_id FROM atlas_entries` on
       `rag_sessions.db`) to get the set of live entry IDs.
    3. Computes the orphan set in Python (`linked_ids - live_ids`)
       and issues a parameterized
       `DELETE FROM comet_events WHERE comet_id IN (?, ?, …)` against
       `news_items.db`, bounded by the absorbed-linked row count
       (in practice ≤ a few thousand even at the 50 000-row cap).

    `ATTACH DATABASE` is intentionally not used; keeping the two
    DBs strictly independent keeps backup/restore, `:memory:`
    tests, and packaging boundaries clean.
  - `absorbed` rows whose `atlas_entry_id` is still empty (no link
    written yet) are evicted on the same 7-day window as
    `dismissed`/`fading`; this prevents an unbounded build-up if the
    Phase 3 absorb path stops linking.
- **`feed_cursors`:** never auto-evicted. A cursor row is the size of
  a settings entry; if the user removes the feed from
  `news_comet_rss_feeds`, the worker leaves the cursor row in place
  for one week so re-adding the same feed resumes incremental polling
  rather than re-scanning the whole archive.

The cleaner runs once per Seedling tick (Phase 3 introduces it), not
on a separate schedule. `news_feed_repository.cleanup(now)` is a pure
function over `(now, retention_policy)` and is tested with frozen
`now` rather than wall-clock sleeps.

### 5. OPML import

OPML is a tree of `<outline>` elements; a feed reader's export is a
flat list of `<outline xmlUrl="…" type="rss" />` nested inside one
outer `<outline text="Subscriptions">`. Phase 3 v1 supports import
only.

- New endpoint: `POST /v1/comets/opml/import` accepting
  `multipart/form-data` with a single OPML file (≤
  `seedling_opml_import_max_bytes`, default 1 MiB).
- Parser: **`defusedxml.ElementTree.fromstring`** is the only sanctioned
  parser. `defusedxml` is the standard hardened wrapper for stdlib
  `xml.etree`; bare stdlib `xml.etree.ElementTree.XMLParser` does not
  expose a clean knob to disable DTD/external-entity expansion in
  every supported Python version, and inheriting `defusedxml`
  transitively through `langchain-core` is a coin flip on environment
  resolution. Adding `defusedxml` as a real declared dependency is
  the one accepted exception to *Constraints*' "do not add a new
  dependency" rule, justified by the security-load-bearing nature of
  XML parsing on user-supplied input. `defusedxml` is pure-Python,
  has no native build, and ships in the same wheels universe as the
  rest of the project.
- Behaviour: the parser walks the tree, collects every `xmlUrl`
  attribute on outlines whose `type` attribute is `rss` (or absent),
  validates each as a URL through the same SSRF gate that
  `NewsIngestService._safe_get` already uses, dedups against the
  existing `news_comet_rss_feeds` setting, and appends new entries.
  For each new feed it writes a `feed_cursors` row with
  `last_polled_at = 0` so the next worker tick treats it as a cold
  feed.
- HTTP error contract: `400` for malformed XML or non-OPML root,
  `413` for payloads above
  `seedling_opml_import_max_bytes`, `422` for OPML that parses but
  contains zero `xmlUrl` attributes (treated as caller error so a
  bad upload doesn't silently succeed). On success the endpoint
  returns `200` with `{added: int, skipped_duplicate: int,
  skipped_invalid: int, errors: [...]}`. It does **not** start a
  poll synchronously — the next worker tick picks up the new feeds.
- Export deferred to a follow-up. Tracked in `plans/IDEAS.md` as
  *"OPML export of current feed list"*.

## Constraints

- Preserve ADR 0004: single Litestar process, no second daemon. The
  store is a SQLite file the worker opens; no service mesh, no
  network DB.
- Preserve ADR 0011's privacy posture, but understand its scope.
  ADR 0011's "never persist the full URL" rule applies to the
  **outbound network audit log** of *what METIS fetched on the user's
  behalf*. ADR 0008 stores the **content the user explicitly opted
  in to ingesting** — the feeds they configured, the items those
  feeds returned. URLs and titles of those items *are* recorded —
  by design, for dedup and for "show me the comets I dismissed" —
  and live on the user's disk only. The two ADRs are not in
  conflict: 0011 governs the audit log of egress, 0008 governs
  user-curated reading material. The `news_items.db` retention
  windows above are the explicit honest answer to "what exactly
  are you keeping about my reading habits?".
- Coordinate with M17 (Network audit). Every outbound fetch the
  worker triggers — RSS fetch, HN fetch, Reddit fetch, OPML feed
  validation — must already be going through `audited_urlopen` with
  a `trigger_feature` tag. This ADR does not introduce new outbound
  call sites; it persists the *results* of the existing audited
  ones.
- Coordinate with M09 (`AutonomousResearchService`) and the comet
  decision engine. The repository owns serialization; the decision
  engine continues to own scoring. No business logic moves into
  `news_feed_repository`.
- One accepted dependency exception: `defusedxml` for OPML parsing
  (see §5). All other persistence and parsing concerns stay on
  stdlib (`sqlite3`, `xml.etree`). The exception is justified by
  the security-load-bearing nature of parsing user-supplied XML,
  and `defusedxml` is the textbook answer.

## Alternatives Considered

- **Extend `rag_sessions.db` with `news_items` / `comet_events`
  tables.** Rejected. The shared DB is already the home of atlas,
  sessions, assistants, and improvements. Adding feed churn on top
  introduces lock contention for the user-facing chat path against
  the background poller, complicates retention (atlas entries are
  permanent; comet rows roll over), and crosses the "one decision
  per file" principle that ADR 0011 used to justify
  `network_audit.db` as a separate file.

- **Extend `atlas_repository` with `news_items` and treat absorbed
  comets as draft Atlas entries.** Tempting, because absorbed
  comets *do* eventually become Atlas-style provenance for stars,
  but the lifecycle is too different. Atlas entries are user-curated
  end-state artefacts; comets are transient and most never reach
  absorption. Forcing a comet through the Atlas data model bloats
  Atlas with throwaway rows.

- **JSON files on disk** (one per active comet, one per cursor).
  Rejected. The existing in-memory list already outgrew its first
  shape; a file-per-comet approach would be slower for the
  "list_active_comets" query that the constellation polls every few
  seconds, and harder to atomically rewrite during eviction.

- **A second event-log SQLite file** (`comet_events.db`) separate
  from `news_items.db`. Rejected. The two tables are tightly
  coupled by `item_hash`; splitting them across files breaks
  foreign-key enforcement and forces a manual cleanup join the
  cleaner does not need.

- **Store feed cursors in `default_settings.json`.** Rejected. The
  settings file is user-readable and user-editable; cursors change
  every poll cycle. Mixing those write rates would break the "edit
  settings without losing my place" mental model and would force
  the worker to take a write lock on a file the UI also writes to.

## Consequences

Accepted implementation follow-ups (Phase 3+):

- Add `metis_app/services/news_feed_repository.py` with the schema
  above, plus `add_news_items`, `record_comet`, `update_phase`,
  `list_active`, `get_cursor`, `update_cursor`, `cleanup` methods.
  Tests in `tests/test_news_feed_repository.py` use `:memory:` mode
  and assert idempotent `init_db`, dedup-on-conflict, retention
  windows, and cursor round-trips.
- Refactor `metis_app/api_litestar/routes/comets.py` so
  `_active_comets`, `_last_poll`, and `_gc_terminal_comets` are
  thin wrappers over the repository. The HTTP shape does not
  change in Phase 3.
- Refactor `metis_app/services/news_ingest_service.py` so
  `_seen_hashes` is an LRU on top of `news_feed_repository`. The
  service still owns fetch + parse + classification staging; the
  repository owns persistence.
- Add `seedling_feed_db_path` setting (default
  `<repo_root>/news_items.db`) so packaged deployments and tests can
  override the location through the same path the existing
  `local_gguf_*` overrides use.
- Add `seedling_feed_retention_days` (default 14),
  `seedling_feed_max_rows` (default 50 000), and
  `seedling_opml_import_max_bytes` (default 1048576) to
  `metis_app/default_settings.json`. The first two are advisory;
  the cleaner clamps both. The third is a hard reject limit for
  the OPML import endpoint.
- All `phase` mutations go through `news_feed_repository.update_phase`.
  The Seedling worker tick is the only caller for engine-driven
  transitions (`entering` → `drifting` → `approaching` → `absorbing`
  → `absorbed`/`fading`). The user-driven `/v1/comets/{id}/absorb`
  and `/dismiss` route handlers also call `update_phase` — they do
  not mutate the repository directly — so tests can assert against
  a single seam and the cleaner's phase-guard query (§4) only has
  to consider one source of truth.
- `list_active` returns at most `news_comet_max_active` (already in
  `default_settings.json`) rows ordered by `created_at DESC`. The
  active set is bounded by that setting; `news_items.db` does not
  add its own pagination layer in v0. If a future setting raises
  the cap above ~100, revisit and add explicit `LIMIT/OFFSET`.
- The OPML import endpoint registers under
  `routes/comets.py::router` — there is no new "feeds" router.
  Authorisation uses the same `require_token_guard` as the rest of
  `protected_routes`.
- Add `AtlasRepository.list_entry_ids() -> set[str]` (or
  `Iterable[str]`) — a thin read-only helper over the existing
  `atlas_entries` table — so the feed cleaner has a single sanctioned
  way to learn which Atlas entries are live without reaching across
  database files. Phase 3 introduces the helper alongside the
  cleaner; both land together so the contract specified in §4 stays
  testable.

## Open Questions

- Should a comet that was *absorbed* before Phase 5's growth-stage
  signal lands count toward the "stars indexed" threshold? Phase 5
  needs to decide; this ADR notes the question so the
  `comet_events.phase = 'absorbed'` row stays the canonical
  provenance.
- The cleaner runs on every Seedling tick. For a once-a-minute tick
  with 50k-row caps, the per-tick work is bounded, but if Phase 5
  raises `seedling_tick_interval_seconds` above one minute the
  cleaner should not skip cycles. Track in Phase 5 retro.
- Long-term: does OPML import deserve a settings-level UI surface
  (drag-drop OPML in the comets settings page), or only a CLI / API
  call? Tracked in `plans/IDEAS.md` after the API endpoint lands and
  user feedback decides.
- If a feed sets `If-Modified-Since` headers but lies about
  `Last-Modified`, the cursor will under- or over-fetch. The
  fallback (cursor by newest item hash) covers correctness but
  wastes bandwidth. Note for Phase 3 measurement, not an ADR-level
  decision.
