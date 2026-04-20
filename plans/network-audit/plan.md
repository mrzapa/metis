---
Milestone: Network audit (M17)
Status: In progress
Claim: claude/m17-phase7-export-discoverability (Phase 7: CSV export + first-run card + coordination-hooks docs)
Last updated: 2026-04-20 by claude/m17-phase7-export-discoverability
Vision pillar: Cross-cutting
---

## Progress

**Phases 1 through 6 are landed, and Phase 7 is in flight on
`claude/m17-phase7-export-discoverability`.** The audit module,
the stdlib call-site migration, the CI guard, the LangChain SDK
wrappers, the Litestar routes, the read-only `/settings/privacy`
panel, and the enforcement + prove-offline surface are all in
production on `main`. Every outbound HTTP call originating in
`metis_app/` now flows through either `audited_urlopen` (stdlib
path) or `audit_sdk_call` (vendor-SDK path) and is recorded in the
rolling SQLite store. The user can open the panel today and see a
live feed of calls, provider-scoped counts, the current airplane-
mode state, flip airplane-mode / per-provider kill switches from
the UI, and press "Prove offline" to run a synthetic pass that
reports zero outbound calls when airplane mode is on.

**Phase 7 scope** (in this PR): `GET
/v1/network-audit/export?days=30` CSV download + "Export last 30
days (CSV)" button on `/settings/privacy` + first-run home-page
discoverability card (`components/network-audit/first-run-card.tsx`)
+ `network_audit_discoverability_dismissed` default setting + the
coordination-hooks section below. Phase 8 (Tauri-layer
enforcement) remains a v2 stretch.

### Landed phases

| Phase | PR | Merge SHA | Ships |
|---|---|---|---|
| 1 — Provider registry + ADR 0010 | [#516](https://github.com/mrzapa/metis/pull/516) | `d147f87` | `KNOWN_PROVIDERS` (20 entries), `ProviderSpec`, `classify_host`, ADR 0010 |
| 2 — Event model + store + ADR 0011 | [#516](https://github.com/mrzapa/metis/pull/516) | `d147f87` | `NetworkAuditEvent` (frozen+slots), `NetworkAuditStore` (SQLite + rolling retention), `sanitize_url`, ADR 0011 |
| 3a — `audited_urlopen` wrapper + kill-switches | [#517](https://github.com/mrzapa/metis/pull/517) | `fe2d038` | `audited_urlopen`, `is_provider_blocked`, `NetworkBlockedError` |
| 3b — Call-site migration + CI guard | [#518](https://github.com/mrzapa/metis/pull/518) | `ddd2db2` | 6 stdlib `urlopen` sites migrated + `brain_pass.snapshot_download` wrap + CI guard |
| 4 — LangChain SDK invocation events | [#519](https://github.com/mrzapa/metis/pull/519) | `6aeee97` | `source` field, schema migration, `sdk_events.py`, `_ProviderAuditWrapper`, `_EmbeddingsAuditWrapper`, Tavily wrap |
| 5a — Litestar routes + real settings reader | [#520](https://github.com/mrzapa/metis/pull/520) | `ed99582` | 4 routes under `/v1/network-audit/*`, lifecycle hooks, live `get_default_settings()` |
| 5b — Read-only `/settings/privacy` panel | [#521](https://github.com/mrzapa/metis/pull/521) | `1b1995b` (in release) | 3 sections (airplane / matrix / live feed), SSE subscriber, tab link from main settings |
| 6 — Enforcement + prove-offline | [#525](https://github.com/mrzapa/metis/pull/525) | `3969170` | `provider_block_llm` settings map + airplane-mode default, functional airplane + per-provider kill-switch toggles on `/settings/privacy`, `POST /v1/network-audit/synthetic-pass` endpoint, `runNetworkAuditSyntheticPass` fetcher + modal, race-proof provider-block writes, modal a11y, blocked-row highlight |

### Remaining phases

| Phase | Ships |
|---|---|
| **7 — Export + discoverability** | In flight (`claude/m17-phase7-export-discoverability`): `GET /v1/network-audit/export?days=30` CSV + Export button + first-run card + coordination hooks docs. |
| 8 (stretch) — Tauri-layer enforcement | Deferred; v2 concern. |

What's in place today that M17 will lean on (or wrap):

- **No existing network-audit module.** `metis_app/audit.py` is a
  **parity audit** (pytest test-suite runner) — different concept,
  different concern. M17 introduces a new `metis_app/network_audit/`
  package; no name collision.
- **Outbound call sites are concentrated** in roughly five files
  (full inventory below). Every one of them uses stdlib
  `urllib.request.urlopen` — **no `httpx`, no `requests`, no
  `aiohttp` in `metis_app/`.** That is a gift: a single interception
  point (a `NetworkAuditedClient` wrapper) can cover 100% of
  in-process outbound if the codebase switches to it.
- **LLM and embedding calls are tunnelled through LangChain**
  (`langchain_openai`, `langchain_anthropic`,
  `langchain_google_genai`, `langchain_voyageai`, LM Studio via
  `ChatOpenAI(base_url=...)`). These emit HTTPS requests inside
  vendor SDKs, out of our direct view. Audit wrapping here is
  **harder** — see the interception-strategy discussion below.
- **Settings keys that are already de-facto kill switches** (M17
  inherits, does not duplicate):
  - `llm_provider` — "mock" disables all remote LLM calls.
  - `embedding_provider` / `embeddings_backend` — "mock" / local
    paths disable remote embeddings.
  - `news_comets_enabled` (default `false`) — master RSS/HN/Reddit
    ingestion toggle.
  - `news_comet_sources` — per-channel list (`["rss"]` by default;
    supports `rss`, `hackernews`, `reddit`).
  - `news_comet_rss_feeds`, `news_comet_reddit_subs` — per-provider
    subscription lists. Empty list = no fetches for that channel.
  - `autonomous_research_enabled` (default `false`) — toggles the
    M09 research loop that fans out to web search.
  - `autonomous_research_provider` (default `"tavily"`) — picks the
    search vendor. Empty / unknown value falls through to the
    DuckDuckGo HTML scrape in `utils/web_search.py`.
  - `web_search_api_key` — absence of key already forces fallback
    path; not a first-class kill switch but a de-facto one.
  - `weaviate_url` — empty string = the JSON vector store is used
    and no outbound vector-DB calls happen.
  - `local_llm_url` — points at `http://localhost:1234/v1` by
    default; LM Studio runs on `localhost`, so these calls are
    loopback (M17 must classify loopback vs. public correctly).
- **Trace-event infrastructure exists** (`metis_app/models/parity_types.py`
  — `TraceEvent`; `metis_app/services/trace_store.py` — rolling JSON
  store + `_emit_audit_log`). M17's audit-event model should fit
  alongside or inside this, not duplicate the serialisation plumbing.
- **Companion activity pub/sub is live** (M09 landed) —
  `CompanionActivityEvent` on the frontend (`apps/metis-web/lib/api.ts`)
  subscribed by the dock. Not the right bus for raw network events
  (too chatty, too low-level), but the same *pattern* (SSE from the
  backend → live-updating panel on the frontend) is the template.
- **The Tauri shell does not currently make HTTP calls** — no
  `reqwest`, `ureq`, `hyper`, or `std::net` usage in
  `apps/metis-desktop/src-tauri/src/`. All outbound traffic
  originates in the Litestar-hosted Python process or in the
  Next.js web app (via the browser fetch API, which is itself
  talking to loopback-hosted Litestar).

## Next up

Phase 7 is claimed by `claude/m17-phase7-export-discoverability`
and ships the four Phase 7 deliverables in one PR:

1. **`GET /v1/network-audit/export?days=30` CSV endpoint.** Route in
   `metis_app/api_litestar/routes/network_audit.py`; rowid-cursor
   walk via the new `NetworkAuditStore.iter_events_since`. Columns
   mirror the stored fields (without `id` / `query_params_stored`):
   `timestamp, method, url_host, url_path_prefix, provider_key,
   trigger_feature, size_bytes_in, size_bytes_out, latency_ms,
   status_code, user_initiated, blocked, source`. Days parameter
   is silently clamped to `[1, 90]`. Served locally; no upload.
2. **"Export last 30 days (CSV)" button on `/settings/privacy`.**
   Sits in the live-feed header alongside Prove offline. Self-
   disabling while download is in flight; inline error on failure.
   Vitest coverage in
   `app/settings/privacy/__tests__/page.test.tsx`.
3. **First-run discoverability card.**
   `components/network-audit/first-run-card.tsx` — fixed top-right
   on `app/page.tsx`. Copy: *"METIS shows you every outbound call.
   Open the network audit to see what's leaving your machine — and
   switch any provider off."* Dismissal writes
   `network_audit_discoverability_dismissed: true`. Vitest
   coverage in `components/network-audit/__tests__/first-run-card.test.tsx`.
4. **Coordination-hooks docs.** See the "Coordination hooks
   (Phase 7)" section at the bottom of this doc.

After this PR merges, M17 rows to `Landed` and Phase 8 remains the
only open v2 stretch.

## Blockers

- **No hard dependency blockers.** The milestone is 6/7 phases
  complete (Phase 8 is a post-v1 stretch and not counted toward
  v1 shipping scope) and unblocked. The original ordering risks
  below have been resolved by landing M17 first.
- **Resolved: M13 ordering.** M17 landed before M13 per the
  original recommendation. M13 (Seedling + Feed) will need to
  adopt `audited_urlopen` for any new stdlib call sites it adds
  — the CI guard (`tests/test_network_audit_no_raw_urlopen.py`)
  will force this mechanically.
- **Resolved: M15 (Pro tier launch) gating.** Phase 6
  (functional kill-switch enforcement + prove-offline button) —
  the feature that backs the Lifetime pitch "never being held
  hostage" — landed via PR #525. M15 is no longer gated on M17.
  Phase 7 (discoverability card) sharpens the pitch but doesn't
  gate it.
- **Phase 4 already flagged autonomous calls as
  `user_initiated=False`.** The coordination concern with M06 /
  M09 / M18 is satisfied at the event-emission layer; the remaining
  work is surfacing an "autonomous" tag in the feed UI (Phase 6 or
  7 — wherever it fits with the matrix-toggle work).

## Notes for the next agent

This milestone is the product feature that backs VISION.md's
strongest privacy claim — *"Nothing phones home without explicit
consent. Cloud features are opt-in and end-to-end encrypted."* The
audience for this milestone is narrower than most of METIS: the
privacy-conscious cohort already paying for Obsidian, Kagi, Mullvad,
Proton, Framework. They read audit panels the way most users read
README files. Under-deliver here and the Lifetime tier pitch —
*"The price of never being held hostage"* — rings hollow; the
pitch is exactly the feature.

**Two jobs, different implementation shapes. Do not conflate:**

1. **Observability** — *"show every outbound call."* A trace
   surface. Every HTTP request from `metis_app` gets logged with
   timestamp, destination, method, provider classification,
   size/latency, triggering feature, and user-initiated boolean.
   The user opens the panel and verifies "only calls I expect are
   happening."
2. **Control** — *"block per provider, prove offline."* A
   kill-switch matrix. Per LLM provider, per ingestion source, plus
   an "airplane mode" master. Dependent features must degrade
   gracefully (disabled-for-privacy state, not an exception that
   crashes a stage).

The "prove offline" part is load-bearing. Not making calls is
insufficient — the user needs *evidence*. The audit panel must
actively show a green "0 outbound calls in last N minutes"
indicator plus a synthetic-pass button that runs common operations
with airplane mode on and shows zero calls. This is the litmus
test for the privacy audience.

### Outbound-call-site inventory (first pass)

Every in-process outbound HTTP call site in `metis_app/`, as of
2026-04-19. **All use stdlib `urllib.request.urlopen` — no
`httpx`, `requests`, or `aiohttp` anywhere in the backend.** This
is the concrete surface M17 must cover. LangChain vendor SDKs add
another layer (below).

| # | File : line | Function | Triggering feature | Suggested provider class | User-initiated? |
|---|---|---|---|---|---|
| 1 | `metis_app/services/news_ingest_service.py:52` | `_safe_get` | RSS body fetch (`fetch_rss`) | `rss_feed` | mostly `false` (M13 worker) |
| 2 | `metis_app/services/news_ingest_service.py:52` | `_safe_get_json` via `_safe_get` → HN `/v0/topstories.json` | HackerNews top stories | `hackernews_api` | mostly `false` |
| 3 | `metis_app/services/news_ingest_service.py:52` | `_safe_get_json` via `_safe_get` → HN `/v0/item/{id}.json` | HackerNews per-item fetch | `hackernews_api` | mostly `false` |
| 4 | `metis_app/services/news_ingest_service.py:52` | `_safe_get_json` via `_safe_get` → Reddit `/r/{sub}/hot.json` | Reddit hot posts | `reddit_api` | mostly `false` |
| 5 | `metis_app/services/nyx_catalog.py:262` | `_default_fetch_json` | Nyx UI component registry lookup (`nyxui.com/r/{name}.json`) | `nyx_registry` | mostly `true` (user browses catalog) |
| 6 | `metis_app/services/local_llm_recommender.py:577` | GGUF download | Downloading a quantized model from `huggingface.co/{repo}/resolve/main/...` | `huggingface_hub` | `true` (user clicks "install") |
| 7 | `metis_app/services/local_llm_recommender.py:725` | `_read_json` | Hardware / catalog JSON reads via `huggingface.co/api/models/...` (line 506 builds the URL) | `huggingface_hub` | mixed |
| 8 | `metis_app/utils/web_search.py:72` | DuckDuckGo instant-answer API (`api.duckduckgo.com/?q=...`) | `web_search` fallback | `duckduckgo` | mixed (agent + user) |
| 9 | `metis_app/utils/web_search.py:117` | Jina reader (`r.jina.ai/{url}`) | URL content extraction | `jina_reader` | mixed |
| 10 | `metis_app/services/brain_pass.py:239` | `huggingface_hub.snapshot_download` | Tribev2 model snapshot fetch | `huggingface_hub` | `true` (user opts into brain-pass) |

**Vendor SDK call sites (not stdlib — audited via classification
rather than wrapper in v1):**

| # | Entry point | Library | Endpoint(s) | Provider class |
|---|---|---|---|---|
| A | `metis_app/utils/llm_providers.py:382` (`_create_openai`) | `langchain_openai.ChatOpenAI` | `api.openai.com/v1` | `openai` |
| B | `metis_app/utils/llm_providers.py:396` (`_create_anthropic`) | `langchain_anthropic.ChatAnthropic` | `api.anthropic.com/v1` | `anthropic` |
| C | `metis_app/utils/llm_providers.py:410` (`_create_google`) | `langchain_google_genai.ChatGoogleGenerativeAI` | `generativelanguage.googleapis.com` | `google` |
| D | `metis_app/utils/llm_providers.py:424` (`_create_xai`) | `langchain_openai.ChatOpenAI` w/ `base_url="https://api.x.ai/v1"` | `api.x.ai/v1` | `xai` |
| E | `metis_app/utils/llm_providers.py:439` (`_create_lm_studio`) | `langchain_openai.ChatOpenAI` w/ `base_url=local_llm_url` | default `localhost:1234` | `local_lm_studio` (loopback) |
| F | `metis_app/utils/embedding_providers.py:127` | `langchain_openai.OpenAIEmbeddings` | `api.openai.com/v1/embeddings` | `openai_embeddings` |
| G | `metis_app/utils/embedding_providers.py:134` | `langchain_google_genai.GoogleGenerativeAIEmbeddings` | Google GenAI | `google_embeddings` |
| H | `metis_app/utils/embedding_providers.py:145` (Voyage) | `langchain_voyageai.VoyageAIEmbeddings` | `api.voyageai.com` | `voyage` |
| I | `metis_app/utils/embedding_providers.py:171` | `langchain_community.embeddings.HuggingFaceEmbeddings` | loopback / local model cache | `huggingface_local` (loopback once downloaded) |
| J | `metis_app/services/autonomous_research_service.py:111` (via `web_search`) | `tavily.TavilyClient` (optional) or DuckDuckGo fallback | `api.tavily.com` or `api.duckduckgo.com` | `tavily` / `duckduckgo` |
| K | `metis_app/services/vector_store.py` (Weaviate branch) | `weaviate-client` | `weaviate_url` (user-provided) | `weaviate` (typically self-hosted; mark as user-config) |

**Frontend / fonts / CDNs:**

| # | File : line | Resource | Note |
|---|---|---|---|
| L | `apps/metis-web/app/page.tsx:5309` | `@import url('https://fonts.googleapis.com/css2?family=...')` | Google Fonts. Arguably phones home on first load. **Should be inlined or flagged** as part of M17 delivery. |
| M | `apps/metis-web/components/webgpu-companion/worker.ts:38` | Comment references `huggingface.co/spaces/webml-community/bonsai-webgpu` | WebGPU model fetch; verify whether the model actually downloads from HF or is bundled. |

**What the audit panel must cover in v1** (numbered 1–11 + L + M
above). Paid-tier-specific outbounds (M15) added when M15 ships,
not deferred behind Pro.

### Proposed phase breakdown

A first cut. Claimant is free to restructure, but every phase has
an explicit *what NOT to do* boundary. Target: each phase is 1–2
PRs wide, roughly ordered so "prove offline" becomes demonstrable
around Phase 5.

#### Phase 1 ✅ Landed (PR #516) — ADR 0010 (interception strategy) + known-provider registry

**Goal:** one file that names every outbound destination METIS can
talk to and the strategy for intercepting each.

- New file: `metis_app/network_audit/providers.py` — a
  `KNOWN_PROVIDERS: dict[str, ProviderSpec]` where each entry has
  `key`, `display_name`, `url_host_patterns: list[re.Pattern]`,
  `kill_switch_setting_key`, `category:
  Literal["llm","embeddings","ingestion","search","model_hub","vector_db","fonts_cdn","other"]`.
- Entries from the inventory: `openai`, `anthropic`, `google`,
  `xai`, `voyage`, `tavily`, `duckduckgo`, `jina_reader`,
  `rss_feed`, `hackernews_api`, `reddit_api`, `nyx_registry`,
  `huggingface_hub`, `huggingface_local`, `weaviate`,
  `local_lm_studio`, `google_fonts`, `other` (unclassified
  fallback).
- ADR 0010 records: stdlib `urllib` gets the wrapper; LangChain
  SDK calls get classified-not-wrapped in v1 (they still appear
  in the panel, labelled `source: sdk`); CI guard prohibits new
  `urllib.request.urlopen` outside `metis_app/network_audit/`.

**Not this phase:** the wrapper code, the UI, the store. This
phase is just the registry + the ADR.

#### Phase 2 ✅ Landed (PR #516) — Audit event model + store

**Goal:** durable, bounded, privacy-conscious event log.

- New module: `metis_app/network_audit/events.py`. Dataclass
  `NetworkAuditEvent` with fields:
  - `id: str` (ULID)
  - `timestamp: datetime` (UTC)
  - `method: str` (`GET`/`POST`/...)
  - `url_host: str` (e.g. `api.openai.com`; **never** full URL)
  - `url_path_prefix: str` (first path segment only, e.g. `/v1`;
    path-beyond-prefix is dropped)
  - `query_params_stored: Literal[False]` (hard-coded invariant —
    query params are never persisted)
  - `provider_key: str` (from `KNOWN_PROVIDERS`, or `"unclassified"`)
  - `trigger_feature: str` (e.g. `"news_comet_worker"`,
    `"autonomous_research"`, `"gguf_install"`)
  - `size_bytes_in: int | None`, `size_bytes_out: int | None`
  - `latency_ms: int | None`
  - `status_code: int | None`
  - `user_initiated: bool` (caller must set; default `False`)
  - `blocked: bool` (event is recorded even when kill switch
    intercepted the call — "you tried, we blocked it")
- Store: a new SQLite DB `network_audit.db` next to
  `skill_candidates.db`. Rolling bounded: keep last 30 days OR
  last 50,000 events, whichever is smaller. Vacuum on startup.
- Reuse pattern: mirror `metis_app/services/trace_store.py`
  (rolling JSON + structured logger). Do NOT piggyback on
  `TraceEvent` — different shape, different retention, and we
  don't want audit history to churn out with a RAG-run's trace.
- Serialisation invariant: unit-tested. A synthetic event with a
  URL `https://api.openai.com/v1/chat/completions?api_key=SECRET&prompt=foo`
  must round-trip as `{host: "api.openai.com", path_prefix: "/v1"}`
  with no trace of `api_key`, `prompt`, or the remaining path.

**Not this phase:** wrapping the call sites. Just the model and
store, plus a synthetic-event writer for tests.

#### Phase 3 ✅ Landed (PRs #517 + #518) — `audited_urlopen` wrapper + call-site migration + CI guard

**Goal:** every `urllib.request.urlopen` in the ten call sites
above routes through the wrapper, with zero behavioural regression.

- New file: `metis_app/network_audit/client.py`. Exposes
  `audited_urlopen(req_or_url, *, trigger_feature, user_initiated,
  timeout)` with the same signature as
  `urllib.request.urlopen` plus two required kwargs. Records an
  event, classifies by provider, checks the kill switch, calls
  through or raises `NetworkBlockedError`.
- Migrate `news_ingest_service._safe_get` →
  `audited_urlopen(..., trigger_feature="news_comet_*")`.
- Migrate `nyx_catalog._default_fetch_json` and
  `local_llm_recommender` download + `_read_json`.
- Migrate `utils/web_search.py` (DuckDuckGo + Jina reader calls).
- Migrate `brain_pass.py` (the `huggingface_hub.snapshot_download`
  path needs special treatment — we don't own the library's HTTP
  layer. Two options: (i) wrap the function with a pre/post
  event; (ii) set `HF_ENDPOINT` env var + a monkey-patch on
  `huggingface_hub.utils._http` at startup. Prefer (i) for
  simplicity in v1.)
- CI guard: add a `ruff` custom rule or a pytest that grep-fails
  if `urlopen(` appears outside `network_audit/` and a short
  allowlist.

**Not this phase:** the LangChain SDK wrappers (Phase 4). Leave
vendor-SDK calls unwrapped — they will be classified on the
settings side via known-provider routing only.

#### Phase 4 ✅ Landed (PR #519) — Vendor-SDK coverage (LLM + embeddings + Tavily)

**Goal:** the panel shows OpenAI/Anthropic/Google/xAI/Voyage
calls even though we don't wrap their HTTP client.

- Approach: emit an audit event at the `create_llm` /
  `create_embeddings` *invocation* layer, not the HTTP layer.
  When `PooledLLM.invoke()` or equivalent is called, emit a
  `NetworkAuditEvent` with `provider_key` = the provider name
  and `source: "sdk_invocation"` in a new metadata column. The
  event records intent to call, not the exact wire traffic
  — honest, and flagged as such in the UI ("SDK-level event;
  exact URL traffic is abstracted by the vendor library").
- Kill-switch enforcement: the `create_llm` factory checks the
  provider's kill switch setting before constructing the client
  and raises `NetworkBlockedError` with a clean degradation path.
- Document the limitation in the panel — this is the honest
  deficiency of v1. A Phase 6 stretch pursues deeper SDK-level
  interception (e.g. `httpx` event hooks inside the LangChain
  clients) if the privacy audience asks for it.

**Not this phase:** shipping bypass-proof SDK-HTTP interception.
That's a v2 concern and requires per-SDK work.

#### Phase 5 ✅ Landed (PRs #520 + #521) — Settings UI: audit panel + per-provider toggles

*Implementation split the original phase into two PRs: #520 shipped the Litestar routes + real settings reader + lifecycle hooks ("Phase 5a" in commit labels), and #521 shipped the read-only `/settings/privacy` page with three sections + SSE subscriber ("Phase 5b"). The plan's original Phase 5 covered both.*

*Note: per-provider kill-switch TOGGLES and the functional airplane-mode write are deferred to Phase 6 below — Phase 5 as shipped is read-only.*

**Goal:** a new privacy surface in settings. Live event feed +
per-provider kill switches + airplane-mode master.

- Location: new route `apps/metis-web/app/settings/privacy/page.tsx`,
  linked from the main settings page as a first-class tab
  ("Privacy & network"). Do **not** bury it inside an advanced
  drawer — this is a trust feature.
- Layout: three stacked sections.
  1. **Airplane mode** (big toggle at top; current indicator
     "0 outbound calls in last 5 minutes" pulled from
     `GET /v1/network-audit/recent-count?window=300`).
  2. **Per-provider matrix** — table with columns:
     Provider · Category · Enabled toggle · Events (7d) ·
     Last call · API key status. Rows populated from
     `GET /v1/network-audit/providers`.
  3. **Live event feed** — newest-first rolling table; columns:
     Time · Provider · Host · Feature · Size · Status · User?
     Fed by a server-sent-events stream
     `GET /v1/network-audit/stream`. Cap at 100 visible rows;
     "Export CSV" (Phase 7) sits above it.
- Backend routes: new file
  `metis_app/api_litestar/routes/network_audit.py` exposing
  `/v1/network-audit/{events,providers,recent-count,stream,
  export,synthetic-pass}`.
- Reuse `subscribeCompanionActivity` infra as a template — don't
  couple audit events to the companion event bus (wrong audience,
  wrong retention).

**Not this phase:** the "prove offline" synthetic pass (Phase 6);
export (Phase 7).

#### Phase 6 ✅ Landed (PR #525) — Enforcement + "prove offline" affordance

**Shipped via merge `3969170` on 2026-04-20.** `provider_block_llm`
settings map + airplane-mode default; functional airplane toggle
and per-provider kill-switch toggles on `/settings/privacy`;
`POST /v1/network-audit/synthetic-pass` endpoint that exercises a
scripted probe and reports per-provider counts; `runNetworkAudit
SyntheticPass` fetcher + modal with per-provider breakdown and
blocked-row highlight; race-proof provider-block writes and modal
a11y polish in the follow-up fixes (`5456613`, `35c6da3`).

**Original Phase 6 spec (preserved for reference):**

**Goal:** kill switches actually block, and the user can push a
button to see it.

- Every wrapped call (Phase 3) and every SDK factory (Phase 4)
  consults the kill-switch registry. Blocked calls emit an event
  with `blocked=True` and raise `NetworkBlockedError`. Callers
  degrade:
  - News-comet workers skip the fetch tick, log, continue loop.
  - Autonomous research shows a disabled-state badge in the dock.
  - `create_llm` falls back to `mock` provider with a clear
    user-facing message ("LLM provider blocked by your privacy
    settings").
- **Airplane mode semantics — prompt on first call, not silent
  drop.** When airplane mode is on and a background feature tries
  to emit, the audit panel raises a toast ("RSS worker tried to
  fetch. Blocked.") and records the event with `blocked=True`.
  Silent dropping erodes trust faster than a crash; explicit
  blocking earns it.
- "Prove offline" button: `POST /v1/network-audit/synthetic-pass`
  runs a 30-second scripted probe (autonomous research tick,
  RSS poll, LLM no-op call via `create_llm`, embedding no-op)
  and returns per-provider call counts. With airplane mode on,
  every count is `0`. Surface the result as a modal with a
  per-provider breakdown: "HackerNews: 0 calls. OpenAI: 0 calls.
  …". This is the litmus test feature.

**Not this phase:** deep SDK-HTTP interception (v2), or a global
firewall.

#### Phase 7 🔜 Next — Export, coordination hooks, onboarding callout

**Goal:** the audit panel is discoverable, exportable, and
coordinated with neighbouring milestones.

- `GET /v1/network-audit/export?days=30` returns a CSV. Served
  locally; no upload.
- First-run experience: a one-shot card in the home page empty
  state when the user has never opened the privacy panel —
  "METIS shows you every outbound call. Open the network audit."
  Dismissible, not gated, never re-shown.
- Coordination hooks:
  - **M13 (Seedling)** — the worker emits per-tick summary
    events that roll up aggregate counts for the dock's breathing
    indicator.
  - **M06 / M09 (autonomous)** — every call has
    `user_initiated=false` and surfaces with a visible "autonomous"
    tag in the feed.
  - **M15 (Pro tier)** — Pro-only features (e.g. autonomous
    research expanded quota) register their own trigger-feature
    strings. Audit panel remains **Free**, always.
- Document the panel in `docs/` (README-length only, not a
  marketing post) so the privacy audience can link to it.

**Not this phase:** deep-packet-level guarantees, OS-level
firewalling, or anything that requires Tauri IPC work. Those are
v2+.

#### Phase 8 (stretch) — Tauri-layer enforcement

**Goal:** a deeper promise for the privacy purist — block at the
process boundary, not in Python.

- Experiment with Tauri's network permission model on
  macOS/Linux/Windows. A v2 stretch only.
- Deliverable of this phase if attempted: ADR documenting per-OS
  feasibility and a feature-flag-gated preview. **Do not ship
  silently.** Most users will not need this; flag it as "privacy
  purist" territory.

**Not this phase:** full OS firewall implementation; any shipped
default-on behaviour.

### Open decisions requiring ADRs

1. **ADR 0010 — Interception strategy** (Phase 1). Wrapper +
   classification + CI guard is the recommended shape.
2. **ADR 0011 — Audit-log retention + privacy** (Phase 2). How
   long? What fields? Hashed URL paths vs. prefix-only vs. full?
   The recommended default in this plan (host + first path
   segment, no query params, 30 days / 50k events) is a first
   cut; the ADR should lock it after one implementation pass.
3. **ADR 0012 — Airplane-mode semantics** (Phase 6). Prompt-on-call
   vs silent-drop. This plan recommends prompt-on-call as the
   default; the ADR justifies it with reference to product
   principle #6 (*"Nothing phones home without explicit consent"*).
4. **Open question** (decide during implementation, may or may
   not need an ADR): should `user_initiated` be inferrable from
   the call site, or must every caller pass it explicitly? Plan
   recommends explicit, so background work can never accidentally
   masquerade as foreground.

### Coordination risks

- **M13 (Seedling + Feed, Draft)** — M13 is the single biggest
  future source of outbound traffic. Both plans cite each other.
  If M17 ships first, M13 must adopt `audited_urlopen` from its
  first commit (the M13 plan's harvest list points at exactly
  the call sites M17 wraps). If M13 ships first, it owes M17
  hooks for every fetch it adds.
- **M06 (Skill self-evolution, Ready)** — overnight reflection
  and candidate promotion may call LLMs autonomously. Every such
  call must emit `user_initiated=false`. M17 does not block M06;
  M06 must co-design the event emission.
- **M09 (Companion realtime visibility, Landed)** — the thought
  log uses `CompanionActivityEvent`. M17 must **not** repurpose
  that bus. Separate SSE channel (`/v1/network-audit/stream`).
- **M14 (The Forge, Draft)** — the technique gallery may fetch
  remote arXiv / GitHub references. Each new fetcher the Forge
  ships must register as a provider in `KNOWN_PROVIDERS`. Soft
  coordination; no blocking.
- **M15 (Pro tier launch, Draft)** — Pro features with their own
  outbound calls must register provider entries. The audit panel
  itself stays Free — it is a trust feature, not a paid
  differentiator. Marketing-site analytics (Plausible / Pirsch /
  etc., filed in `pro-tier-launch/plan.md`) is **outside** M17's
  scope — those requests originate from the marketing site
  domain, not the product. M17 explicitly documents the
  boundary.
- **M16 (Personal evals, Draft)** — eval runs may make LLM calls
  to a configured model for grading. Same `user_initiated=false`
  expectation.
- **M18 (LoRA stretch)** / **M19 (Mobile stretch)** — out of
  scope for M17 v1. Flag interactions in the plan: LoRA training
  is typically local but a "download base model" event must be
  audited; a mobile client introduces a new class of
  desktop-sync outbound, which M17 v1 does not anticipate.

### Privacy posture callout (load-bearing)

M17 is the product feature that backs the VISION.md promise
"Nothing phones home without explicit consent." Three concrete
expectations follow:

- **No METIS-internal telemetry.** METIS itself must never send
  its own usage data anywhere. If any existing code already
  does this (e.g. an anonymous error ping, a version check),
  M17 surfaces it in the panel and removes it — there is no
  "hidden healthy" outbound category. Audit the codebase for
  this during Phase 1.
- **No "hide outbound calls" affordance.** The panel shows
  everything, including embarrassing bursts. Trust is earned by
  disclosure. Opt-in filtering ("show only background calls") is
  fine; opt-out of categories is not.
- **The audit panel is Free, not Pro.** It must work in
  airplane mode on day one of a Lifetime install. Gating it
  behind a paid tier would invert the promise.

### What NOT to do in M17

- **Don't build a full firewall.** The panel is an in-app truth
  surface, not a network perimeter. The only deeper promise we
  explore (Phase 8 stretch) is Tauri-layer enforcement for
  purists — and it is flagged, not shipped silently.
- **Don't add METIS-owned telemetry.** No usage pings, no
  "anonymous version check", no crash-report upload by default.
  If any of those are proposed later, they must pass through the
  audit panel like any other outbound.
- **Don't store full URLs.** Host + first path segment only.
  Query params never. User-generated URLs (arXiv paper links,
  blog posts they pasted) are out of scope for long-term
  retention; if the event schema ever grows to include them,
  hash them at minimum.
- **Don't gate the panel behind Pro.** Free tier. First-run
  prominent.
- **Don't add a "pause audit logging" toggle.** Trust erodes
  fast. If the user wants fewer events, they toggle providers
  off — they don't turn the microscope off.
- **Don't conflate this with parity audit.** `metis_app/audit.py`
  is the pytest-suite runner for backend parity. M17's new
  namespace is `metis_app/network_audit/`. Keep the naming
  unambiguous in imports, docs, and settings keys.
- **Don't re-invent existing kill switches.** `news_comets_enabled`,
  `autonomous_research_enabled`, and the provider-is-mock pattern
  already function as blocks. M17's per-provider UI should
  *re-expose* them uniformly, not shadow them with a second set
  of keys. Every provider entry in `KNOWN_PROVIDERS` points its
  `kill_switch_setting_key` at an **existing** setting where one
  exists; new settings are added only for providers that have
  none today (notably the vendor LLM/embedding providers — a new
  `provider_block_llm: dict[str, bool]` map).

### Key files the next agent will touch

Backend (new):
- `metis_app/network_audit/__init__.py`
- `metis_app/network_audit/providers.py` *(KNOWN_PROVIDERS registry)*
- `metis_app/network_audit/events.py` *(NetworkAuditEvent + store)*
- `metis_app/network_audit/client.py` *(`audited_urlopen`)*
- `metis_app/network_audit/kill_switches.py` *(consults settings,
  raises NetworkBlockedError)*
- `metis_app/api_litestar/routes/network_audit.py`
- `metis_app/default_settings.json` *(add `network_audit_*` +
  `provider_block_llm` keys)*

Backend (modified):
- `metis_app/services/news_ingest_service.py` *(replace
  `urllib.request.urlopen` → `audited_urlopen`)*
- `metis_app/services/nyx_catalog.py` *(same)*
- `metis_app/services/local_llm_recommender.py` *(same; HF
  endpoints)*
- `metis_app/services/brain_pass.py` *(snapshot_download wrap)*
- `metis_app/utils/web_search.py` *(same)*
- `metis_app/utils/llm_providers.py` *(emit SDK-invocation events;
  consult kill switches)*
- `metis_app/utils/embedding_providers.py` *(same)*
- `metis_app/api_litestar/app.py` *(register route module)*

Frontend (new):
- `apps/metis-web/app/settings/privacy/page.tsx`
- `apps/metis-web/lib/network-audit-types.ts`
- `apps/metis-web/components/network-audit/*` *(event feed,
  provider matrix, airplane toggle, synthetic-pass modal)*

Frontend (modified):
- `apps/metis-web/app/settings/page.tsx` *(top-nav link to
  privacy panel)*
- `apps/metis-web/lib/api.ts` *(add network-audit fetchers +
  SSE subscription)*
- `apps/metis-web/app/page.tsx` *(remove / inline the Google
  Fonts `@import` at line 5309 — otherwise the audit panel
  honestly needs to list `google_fonts` as an outbound provider)*

ADRs (new):
- `docs/adr/0010-network-audit-interception.md`
- `docs/adr/0011-network-audit-retention.md`
- `docs/adr/0012-airplane-mode-semantics.md`

### Prior art to read before starting

- `VISION.md` — product principle #6 (*Local by default. Always.*)
  and principle #5 (*Trace everything.*); the Lifetime-tier pitch
  ("*The price of never being held hostage*").
- `plans/seedling-and-feed/plan.md` — M13's harvest list of news
  fetchers and the `news_comet_*` kill-switch settings. M17 is
  the privacy face of those knobs.
- `plans/pro-tier-launch/plan.md` — the marketing-site analytics
  discussion (Plausible / Pirsch / Simple Analytics / Fathom).
  Marketing-site analytics is **out of M17 scope**; the boundary
  is explicit.
- `plans/companion-realtime-visibility/plan.md` — M09's
  `CompanionActivityEvent` pub/sub. M17 borrows the pattern;
  does **not** share the bus.
- `metis_app/services/trace_store.py` — the rolling JSON store
  pattern M17's event store mirrors.
- `metis_app/services/news_ingest_service.py` (`_safe_get`,
  lines 48–56) — the single most-migrated function; a good
  spike target for Phase 3.
- `metis_app/utils/llm_providers.py` (`create_llm`, line 217) —
  the SDK-invocation emission point for Phase 4.
- `docs/adr/0005-product-vision-living-ai-workspace.md` — vision
  ADR; any decision in M17 must be consistent with it.
- `docs/adr/0004-one-interface-next-plus-litestar.md` — why the
  audit lives in Litestar, not a separate daemon.

### A note on the current state

The codebase is already *good* about outbound traffic —
stdlib-only in-process, tight timeout + size caps in
`_safe_get`, feature flags default-off for the noisy providers
(news-comet, autonomous research). M17 is not a rescue operation;
it is a **disclosure operation**. The honest summary of current
outbound posture, for reference:

- **Default-install outbound traffic is ~zero.** A fresh METIS
  with no API keys, `news_comets_enabled: false`,
  `autonomous_research_enabled: false`, `llm_provider: anthropic`
  (but no key) → no outbound calls will complete until the user
  configures something.
- **The most common first-non-zero outbound** is a Google Fonts
  `@import` on first web-app paint (see row L above). This is
  honestly phoning-home-for-fonts and will be flagged or inlined
  during M17. Small, fixable, and symbolically important.
- **The most common intentional outbound** is an LLM chat call
  once the user plugs in an API key. M17 makes this explicit in
  the panel with provider, rough traffic volume, and user-vs-
  autonomous classification.

That starting point — small surface, clean defaults, clear
intent — is exactly why M17 is *writeable* now instead of being
a months-long excavation. The work is naming what is already
happening, giving the user controls over it, and proving the
controls work.

---

## Coordination hooks (Phase 7)

Phase 7 locks in the coordination contract between M17 and its
neighbouring milestones. Each bullet below is the *minimum* a
neighbour plan must do to remain compatible with the audit panel;
everything stricter is a nice-to-have. The format is deliberately
short so each neighbour's plan doc can link to a single anchor and
follow a one-line rule.

### M13 — Seedling + Feed (`plans/seedling-and-feed/plan.md`)

- **Every new stdlib outbound goes through `audited_urlopen`.** The
  Phase 3b CI guard (`tests/test_network_audit_no_raw_urlopen.py`)
  enforces this mechanically; the Seedling worker and news-comet
  ingestion loops must pass `trigger_feature="news_comet_*"` or
  `trigger_feature="seedling_*"` and `user_initiated=False`.
- **Worker heartbeats are NOT audit events.** The per-tick breathing
  indicator on the dock is a M09 activity event, not a
  `NetworkAuditEvent`. Do not conflate the two buses.
- **New providers register in `KNOWN_PROVIDERS`.** Any vendor the
  Seedling reaches (local or remote) that is not already in
  `providers.py` gets a new `ProviderSpec` entry with a sensible
  default kill-switch setting key (use `news_comets_enabled` where
  the feature is covered by the existing master kill switch).

### M06 — Skill self-evolution (`docs/plans/2026-04-01-hermes-sotaku-implementation.md`, Phase 3)

- **Autonomous LLM / embedding calls set `user_initiated=False`.**
  This is already the Phase 4 SDK-wrapper default; M06's skill
  promotion loop must not override it to `True`. The feed's
  "autonomous" tag relies on this being honest.
- **Candidate promotion workflows pick up the kill-switch side-effect
  for free.** `create_llm` already raises `NetworkBlockedError` when
  a provider is blocked; M06's graceful-degrade path should catch it
  and skip the promotion (no retry), then resume on the next cycle.
  Swallowing the error and synthesising a fallback is wrong — the
  user explicitly turned the provider off.

### M09 — Companion realtime visibility (`plans/companion-realtime-visibility/plan.md`)

- **No shared bus.** Audit events use `/v1/network-audit/stream`; M09
  uses `/v1/companion/activity/stream`. Do not merge them. Retention,
  audience, and verbosity all differ.
- **Blocked-call events are visible to the user on the audit panel,
  not on the dock.** The dock is an activity surface, not a privacy
  surface. If the user cares "why is the news comet quiet", they'll
  follow the link from the dock to the audit panel to see the
  `blocked=True` rows.
- **Activity events never borrow `user_initiated`.** `CompanionActivityEvent`
  has its own schema; the audit boolean is audit-specific.

### M15 — Pro tier + public launch (`plans/pro-tier-launch/plan.md`)

- **The audit panel stays Free.** It is a trust feature, not a paid
  differentiator. Gating any part of `/settings/privacy` behind Pro
  breaks the Lifetime-tier pitch.
- **Pro-only outbound features register their own provider entries.**
  If Pro expands autonomous research quotas or adds a new search
  vendor, the new vendor needs a `ProviderSpec` in
  `providers.py` and its own `trigger_feature` tag (e.g.
  `pro_research_*`). No feature flag should bypass the audit layer.
- **Marketing-site analytics is out of scope.** Plausible / Pirsch /
  Simple Analytics / Fathom requests originate from the marketing
  site domain, not from `metis_app`. M17 does not attempt to
  enumerate them. `pro-tier-launch/plan.md` documents the privacy
  posture for that separately.

### Phase 7 landed (2026-04-20)

| Deliverable | Where |
|---|---|
| `GET /v1/network-audit/export?days=30` CSV | `metis_app/api_litestar/routes/network_audit.py`; streams row-by-row from `NetworkAuditStore.iter_events_since` |
| `NetworkAuditStore.iter_events_since(cutoff_ms, chunk_size=1000)` | `metis_app/network_audit/store.py`; rowid-cursor walk |
| "Export last 30 days (CSV)" button + fetcher | `apps/metis-web/app/settings/privacy/page.tsx`; `downloadNetworkAuditExport` in `lib/api.ts` |
| First-run discoverability card | `apps/metis-web/components/network-audit/first-run-card.tsx`; wired from `app/page.tsx` |
| `network_audit_discoverability_dismissed: false` default | `metis_app/default_settings.json` |
| Coordination-hooks section (this one) | You're reading it. |

Phase 8 (Tauri-layer enforcement) remains a v2 stretch.
