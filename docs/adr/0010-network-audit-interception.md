# 0010 - Network Audit Interception Strategy

- **Status:** Accepted (proposed with this PR)
- **Date:** 2026-04-19

## Context

M17 introduces a first-class *Network Audit* panel: an in-app, free-tier
surface that tells the user — honestly, in real time, with durable history —
every outbound HTTP call METIS makes and which feature caused it. The panel
is a *truth surface*, not a firewall. Its credibility depends entirely on
covering the outbound surface completely. Any call that escapes the audit
makes the whole panel a lie.

The backend's outbound surface (as of 2026-04-19) breaks into two distinct
layers, which must be intercepted differently:

1. **Stdlib `urllib.request.urlopen`.** Every in-process HTTP call authored
   by METIS itself goes through stdlib `urllib`. There are **no** uses of
   `httpx`, `requests`, or `aiohttp` anywhere in `metis_app/` — verified by
   grep. The ten known call sites live in:
   - `metis_app/services/news_ingest_service.py` (RSS / HackerNews / Reddit)
   - `metis_app/services/nyx_catalog.py` (Nyx UI registry)
   - `metis_app/services/local_llm_recommender.py` (Hugging Face hub JSON +
     GGUF downloads)
   - `metis_app/services/brain_pass.py` (`huggingface_hub.snapshot_download`)
   - `metis_app/utils/web_search.py` (DuckDuckGo instant-answer + Jina Reader)
   Because the surface is uniform and small, a single wrapper covers 100%
   of stdlib traffic with no spooky action at a distance.
2. **LangChain vendor SDKs.** The LLM and embedding providers go through
   `langchain_openai`, `langchain_anthropic`, `langchain_google_genai`,
   `langchain_voyageai`, and `langchain_community.embeddings` (plus
   `tavily` and `weaviate-client` on the search / vector side). These
   libraries ship their own transport layers (most end up on `httpx`
   internally but we do not control that). Wrapping them cleanly from the
   outside is not feasible in v1 without vendoring or monkey-patching
   private internals.

The audit panel must cover *both* layers to be honest. This ADR picks the
strategy for each.

## Decision

### 1. Stdlib: explicit wrapper with required provenance kwargs

Introduce `metis_app/network_audit/client.py` (Phase 3 — not this PR; this
PR only lands the ADR + registry) exposing:

```python
def audited_urlopen(
    url: str | urllib.request.Request,
    *,
    trigger_feature: str,
    user_initiated: bool,
    data: bytes | None = None,
    timeout: float | None = None,
    # ... preserves the stdlib signature otherwise
) -> http.client.HTTPResponse: ...
```

The two extra kwargs are **required positional-by-keyword**. Every call
site must declare *why* it is reaching the network and *whether a human
just clicked something* — the two pieces of context the panel cannot
reconstruct after the fact.

Phase 3 migrates the ten existing `urllib.request.urlopen` call sites to
`audited_urlopen(...)`. Phase 3 also adds a CI guard (ruff custom rule or
pytest grep) that rejects any new `urllib.request.urlopen` import or call
outside of:

- `metis_app/network_audit/` itself (the wrapper's own implementation)
- a short allowlist documented in the guard (currently empty)

### 2. Vendor SDKs: classify-not-wrap, event at invocation layer

LangChain SDK calls are **not** wrapped in v1. Instead, the factory
functions that construct the clients — `_create_openai`,
`_create_anthropic`, `_create_google`, `_create_xai`, `_create_lm_studio`
in `metis_app/utils/llm_providers.py`, and the analogous factories in
`metis_app/utils/embedding_providers.py` — emit a `NetworkAuditEvent` at
invocation time (when a chain is actually run, not when the client is
constructed) with `source="sdk_invocation"` and a provider key looked up
from `KNOWN_PROVIDERS`. This is Phase 4 work, not this PR.

The panel labels these events as SDK-classified so the user can see the
difference between *"we saw this request go out the door"* (stdlib
wrapper) and *"we asked a vendor library to do this; we did not observe
the packet itself"* (SDK invocation). This is the honest v1 answer. A v2
pass may pursue per-SDK httpx hooks or a shared transport, but that is
not promised here.

### 3. Known-provider registry

A single `metis_app/network_audit/providers.py` module defines:

- `ProviderSpec` — frozen dataclass with `key`, `display_name`,
  `url_host_patterns: tuple[re.Pattern, ...]`, `kill_switch_setting_key:
  str | None`, `category: ProviderCategory`.
- `KNOWN_PROVIDERS: Mapping[str, ProviderSpec]` — a `MappingProxyType`
  wrapping the canonical dict, covering every provider named in the
  Phase 1 inventory plus an `unclassified` fallback.
- `classify_host(host: str) -> ProviderSpec` — returns the first
  matching entry, else `unclassified`. Classification is host-only; a
  provider whose host is shared with another provider (notably
  `api.openai.com` for both `openai` and `openai_embeddings`) returns
  whichever entry appears earlier in the registry. Per-trigger
  classification is a v2 concern; the ADR records this limitation
  explicitly so the panel UI can caveat it.

Loopback entries (`local_lm_studio`, `huggingface_local`) stay in the
registry even though, in the steady state, they do not leave the machine.
The user needs to see "zero loopback calls during airplane-mode
verification" with the same confidence as "zero remote calls". A code
comment on those entries notes that URL-level re-classification happens
at event time (a user who rebinds LM Studio to a non-loopback interface
will trip the remote-host classifier instead).

### 4. Kill-switch setting keys are *re-exposed*, not shadowed

Every entry in `KNOWN_PROVIDERS` either points its
`kill_switch_setting_key` at an **existing** setting
(`news_comets_enabled`, `autonomous_research_enabled`, `weaviate_url` as
empty-string-means-disabled) or sets it to `None` — signalling that a new
setting will be introduced in a later phase (notably
`provider_block_llm: dict[str, bool]` in Phase 4). The panel does not
invent a parallel kill-switch namespace; it is a user-friendly lens over
the settings that already block these providers today.

### 5. Phase 4 — SDK-invocation events are an explicit discriminator, not a flag buried in trigger_feature

Phase 4 lands the vendor-SDK audit surface (LangChain LLM + embedding
factories, plus Tavily via :class:`TavilyClient`). Two small schema
choices worth recording so the next agent does not re-litigate them:

- **``source`` is a Literal column, not a string convention.** The
  ``NetworkAuditEvent`` gains a ``source: Literal["stdlib_urlopen",
  "sdk_invocation"]`` field (default ``"stdlib_urlopen"`` for backwards
  compatibility with Phase 3b call sites). Runtime validation in
  ``__post_init__`` pins the set. The Phase 5 panel reads this field
  and labels the row — users see the honest distinction between
  observed wire traffic and declared intent (see `Consequences` below).
- **Schema migration uses `ALTER TABLE ... ADD COLUMN ... DEFAULT
  'stdlib_urlopen'`.** SQLite applies the default to pre-existing
  rows in a single DDL call, so a user upgrading from a 13-column DB
  lands on the 14-column schema without data loss. The migration is
  guarded by a ``PRAGMA table_info`` check and is idempotent. A
  ``_MIGRATIONS`` tuple in ``store.py`` is the canonical list of
  column-adds; future phases extend it in place rather than bypassing
  it with a one-off migration script.
- **Kill-switch scope for Phase 4 is airplane mode only.** The
  per-LLM-provider ``provider_block_llm`` map flagged in the plan
  (line 557) is a Phase 5 concern — it needs the settings UI to ship
  simultaneously. Phase 4's SDK wrappers call
  :func:`is_provider_blocked` with the LLM/embedding provider key;
  the existing predicate short-circuits on
  ``network_audit_airplane_mode=True``, which is sufficient to make
  the "prove offline" synthetic pass work. When Phase 5 lands the
  ``provider_block_llm`` map it plugs into the same predicate with
  no changes to the SDK wrapper shape.

### 6. Tauri-layer enforcement is a Phase 8 stretch, not a promise

For the privacy-purist user who wants enforcement rather than a
microscope, Phase 8 explores hooking the Tauri sidecar or OS-level
permissions. It is explicitly *not* part of v1. The ADR records this so
future agents do not conflate "the panel is honest" with "the panel is a
firewall".

## Consequences

**Positive:**
- A single interception point covers 100% of stdlib outbound traffic.
  The wrapper's explicit-kwargs shape forces every call site to carry
  its own provenance — the panel's `trigger_feature` / `user_initiated`
  columns are populated by the caller, not guessed by a stack walker.
- The CI guard prevents regression: a future dev who tries to reach for
  `urllib.request.urlopen` without thinking gets told by the linter.
- The audit panel is honest about the difference between observed and
  declared traffic. SDK events are labelled as such; the user sees
  `source: sdk_invocation` next to `source: stdlib_wrapper` and can
  draw their own conclusions.
- Kill-switch re-exposure means every provider toggle in the panel is
  already connected to a real setting the rest of the codebase
  honours — no dead toggles, no drift between the panel and the
  running system.

**Negative / honest deficiencies of v1:**
- SDK traffic is *classified*, not *observed*. If a LangChain release
  quietly adds a new telemetry endpoint, v1's audit will not catch it
  until the call surfaces in user-observable behaviour. This is named,
  not papered over; v2 considers per-SDK httpx hooks.
- No OS-level guarantee. A native dependency that shells out or links
  its own libcurl is invisible to v1. The stretch in Phase 8 explores
  Tauri-layer enforcement.
- Host-only classification collapses `openai` and `openai_embeddings`
  onto the same hostname (`api.openai.com`). The registry keeps them
  as distinct entries for kill-switch purposes, but URL → provider
  classification returns whichever entry appears first. The event
  emitters in Phase 4 attach the correct provider key at invocation
  time, bypassing this ambiguity for SDK-layer events; stdlib events
  hitting `api.openai.com` (none expected today) would need path-level
  disambiguation.

## Alternatives considered

### Startup monkey-patch of `urllib.request.urlopen`

*Rejected.* Replacing `urllib.request.urlopen` at import time with the
wrapper would have caught every call site for free — including future
third-party code inside the process that reaches for stdlib urllib. It
was rejected for three reasons:

1. **Spooky action at a distance.** A reader opening
   `news_ingest_service.py` would see a plain `urlopen` call and have
   no way to know it was instrumented. The repo's style is
   explicit-imports and visible dependencies.
2. **Bypassable.** Any code that imports `urllib.request.urlopen` and
   holds a reference before the patch fires escapes the audit. A
   wrapper at the call site is strictly more honest.
3. **Harder to test.** Monkey-patching is global state; the wrapper
   is an ordinary function that tests can import and exercise
   directly.

### Per-provider client factory

*Rejected.* A factory-per-provider approach (`openai_client()`,
`reddit_client()`, ...) would have hard-coded the provider classification
at the call site, removing the need for host-pattern matching. It was
rejected because the provider list is not stable — the user can paste an
RSS URL pointing at any host, and the `rss_feed` provider must match by
pattern, not by factory identity. The explicit wrapper + registry split
handles that cleanly; per-provider factories would have needed a pattern
registry *anyway* for the user-URL cases, doubling the surface.

### Tauri sidecar as the primary interception point

*Deferred to Phase 8 stretch.* Instrumenting outbound traffic at the
Tauri layer (Rust `reqwest` / OS-level permissions) would give real
enforcement, not just observation. It is the right long-term answer for
privacy-purist users, but it is a different skill set, a different risk
profile, and a different release cadence from the Python-side audit.
v1 ships the honest in-app truth surface; v2 and Phase 8 extend it.

## References

- `plans/network-audit/plan.md` — full M17 plan; Phase 1 is this PR.
- `plans/network-audit/plan.md` — *Outbound-call-site inventory* section
  for the ten stdlib sites and the A–M SDK / CDN rows.
- `docs/adr/0006-constellation-design-2d-primary.md` — format reference.
