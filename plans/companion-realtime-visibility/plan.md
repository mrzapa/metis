---
Milestone: M09 — Companion realtime visibility
Status: Landed
Claim: Landed (`68634ba`, 2026-04-18)
Last updated: 2026-04-20 by claude/m17-phase5b-privacy-ui (plan-sweep pass)
Vision pillar: Companion
---

# Companion Real-Time Visibility

**Branch:** `feat/companion-realtime-visibility`
**Description:** Surface METIS companion thoughts, autonomous research phases, and new constellation stars to the user in real-time via an activity log in the dock and auto-refresh on the constellation canvas.

## Progress

**All 5 steps have code landed in main as of 2026-04-18.** This slice closes
the two remaining gaps called out in Step 2's definition of done and adds
the regression tests that had been deferred.

- **Step 1 — Phase events inside `AutonomousResearchService`** ✅
  (`metis_app/services/autonomous_research_service.py`:60-151). `run()` and
  `run_batch()` both accept `progress_cb` and emit typed phase dicts.
  Orchestrator (`workspace_orchestrator.run_autonomous_research`) threads
  the callback through. Unit tests exist at
  `tests/test_autonomous_research_service.py:178-242`.

- **Step 2 — SSE stream + status endpoint** ⚠️→✅.
  - `POST /v1/autonomous/research/stream` landed earlier
    (`metis_app/api_litestar/routes/autonomous.py:50-96`). Integration tests
    exist at `tests/test_api_app.py:2031-2087`.
  - **This slice:** added the `is_running` in-process flag. Module-level
    counter + lock in `workspace_orchestrator.py` wraps every
    `run_autonomous_research` invocation so the SSE and fire-and-forget
    trigger endpoints are both covered. `GET /v1/autonomous/status` now
    returns `is_running: bool`. Frontend `AutonomousStatus` interface
    gained an optional `is_running` field.
  - Note: the plan mentioned a FastAPI router duplicate at
    `metis_app/api/autonomous.py`. That tree no longer exists — METIS is
    Litestar-only. No FastAPI work to do.

- **Step 3 — Frontend API client** ✅
  (`apps/metis-web/lib/api.ts`): `CompanionActivityEvent.source` union,
  `AutoResearchStreamEvent` type, `triggerAutonomousResearchStream`, and
  `reflectAssistant` emitting companion activity events all landed
  (lines 981-2808).

- **Step 4 — Live thought log in `MetisCompanionDock`** ✅
  (`apps/metis-web/components/shell/metis-companion-dock.tsx`:80-263).
  sessionStorage-backed ring buffer of the last 8 events, "Recent activity"
  section, source-colour badges, state icons, unseen-count badge while
  minimized, auto-refresh toast on autonomous completion. **This slice
  added** the regression test
  (`components/shell/__tests__/metis-companion-dock.test.tsx`) that fires a
  simulated companion event stream and asserts the thought log renders.

- **Step 5 — Constellation auto-refresh** ✅
  (`apps/metis-web/app/page.tsx`:1572-1582). A `useEffect` subscribes and,
  on `autonomous_research` + `completed`, calls `refreshAvailableIndexes`
  in silent mode. **This slice added** the regression test
  (`apps/metis-web/app/__tests__/home-page.test.tsx`) that captures the
  listener, fires an event, asserts `fetchIndexes` is called again, and
  that non-matching events do not trigger a refetch.

## Verification

- `pytest tests/test_autonomous_research_service.py tests/test_workspace_orchestrator.py tests/test_api_app.py -q` — new
  tests for the is_running counter and the status endpoint's is_running
  field pass alongside the existing suite.
- `pnpm --filter metis-web test -- components/shell/__tests__/metis-companion-dock.test.tsx apps/metis-web/app/__tests__/home-page.test.tsx`
  — new thought-log and auto-refresh tests pass.
- `pnpm exec tsc --noEmit` — clean.

## Notes for the next agent

- **Out-of-scope items remain deferred** (see the section at the bottom of
  this plan): constellation visual pulse during research, reflection
  streaming, notification toasts.
- **`is_running` is an in-process flag.** If the API is ever split across
  multiple processes (e.g., a worker pool), the flag will not be
  authoritative — swap for a cross-process signal (Redis, a status row in
  the sessions DB) before that point.
- The `is_running` counter tolerates overlapping calls (e.g., the
  fire-and-forget trigger and the SSE endpoint both running). It reaches 0
  only when every in-flight call has cleared its finally block.

## Goal

The companion currently researches, reflects, and expands the constellation entirely invisibly — users have no idea when or why new stars appear. This feature wires up the existing-but-unused `CompanionActivityEvent` pub/sub system to a live thought log in `MetisCompanionDock`, adds SSE streaming to the autonomous research pipeline so each phase is reported as it happens, and makes the constellation auto-refresh when a new auto-research star is indexed.

---

## Implementation Steps

### Step 1: Phase events inside AutonomousResearchService

**Files:**
- `metis_app/services/autonomous_research_service.py`
- `metis_app/services/workspace_orchestrator.py`

**What:**
Add `progress_cb: Callable[[dict[str, Any]], None] | None = None` to `AutonomousResearchService.run()` (and `run_batch()`). Call it at the start of each named phase with a typed dict `{"phase": str, "faculty_id": str, "detail": str}`:

| Phase key | When called | Detail example |
|---|---|---|
| `"scanning"` | Before `scan_faculty_gaps()` | `"Scanning constellation for gaps…"` |
| `"formulating"` | Before `formulate_query()` | `"Formulating research query for {faculty}…"` |
| `"searching"` | Before `_web_search()` | `"Searching: {query}"` |
| `"synthesizing"` | Before `synthesize_document()` | `"Synthesising {n} sources…"` |
| `"indexing"` | Before `orchestrator.build_index()` | `"Building star index: {index_id}"` |
| `"complete"` | On successful return | `"New star added: {title}"` |
| `"skipped"` | When no faculty gaps found | `"Constellation fully covered, skipping"` |

Update `workspace_orchestrator.run_autonomous_research()` to accept and pass through `progress_cb` to `svc.run()` / `svc.run_batch()`.

**Testing:**
- Write / update `tests/test_autonomous_research_service.py`: mock all external calls, pass a `progress_cb` collector, assert all expected phase keys appear in order and detail strings match.
- Confirm existing tests still pass (progress_cb defaults to None → no regression).

---

### Step 2: SSE streaming endpoints for autonomous research

**Files:**
- `metis_app/api_litestar/routes/autonomous.py`
- `metis_app/api/autonomous.py`

**What:**
Add `POST /v1/autonomous/research/stream` to both Litestar and FastAPI routers, following the exact pattern from `POST /v1/index/build/stream`.

Implementation pattern (identical in both routers):
```python
@post("/v1/autonomous/research/stream")
async def trigger_autonomous_research_stream(payload: ...) -> ServerSentEvent:
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[dict] = asyncio.Queue()

    def _progress_cb(event: dict) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, event)

    future = loop.run_in_executor(
        None,
        lambda: orchestrator.run_autonomous_research(settings, progress_cb=_progress_cb),
    )

    async def _event_gen():
        yield {"type": "research_started", "faculty_id": None}
        while not future.done():
            try:
                event = await asyncio.wait_for(queue.get(), timeout=0.05)
                yield event
            except asyncio.TimeoutError:
                pass
        # drain queue
        while not queue.empty():
            yield queue.get_nowait()
        result = future.result()
        yield {"type": "research_complete", "result": result}

    return ServerSentEvent(_event_gen())  # Litestar; FastAPI uses StreamingResponse
```

Emit events in the format: `{"type": "research_phase", "phase": "...", "faculty_id": "...", "detail": "..."}`.

Also update `GET /v1/autonomous/status` to add `"is_running": bool` by tracking an in-process flag on the orchestrator.

**Testing:**
- Add integration test in `tests/test_api_litestar.py` (or new file): POST `/v1/autonomous/research/stream`, mock orchestrator, assert SSE events arrive in correct order and final `research_complete` event is emitted.

---

### Step 3: Frontend API client — autonomous research stream

**Files:**
- `apps/metis-web/lib/api.ts`

**What:**
1. Extend the `CompanionActivityEvent.source` union:
   ```typescript
   source: "rag_stream" | "index_build" | "autonomous_research" | "reflection";
   ```

2. Add a typed `AutoResearchStreamEvent` interface:
   ```typescript
   export interface AutoResearchStreamEvent {
     type: "research_started" | "research_phase" | "research_complete" | "research_error";
     phase?: string;       // "scanning" | "formulating" | "searching" | "synthesizing" | "indexing" | "complete" | "skipped"
     faculty_id?: string;
     detail?: string;
     result?: { faculty_id: string; index_id: string; title: string; sources: string[] };
   }
   ```

3. Add `triggerAutonomousResearchStream()` function:
   ```typescript
   export async function triggerAutonomousResearchStream(
     settings: Record<string, unknown>,
     options: {
       signal?: AbortSignal;
       onEvent: (event: AutoResearchStreamEvent) => void;
     },
   ): Promise<void>
   ```

   Inside, emit `CompanionActivityEvent` for each phase (mapping `"searching"` → `state: "running"`, `"complete"` → `state: "completed"`, `"skipped"` → `state: "completed"`, errors → `state: "error"`).

Also: emit a `CompanionActivityEvent` from `reflectAssistant()` with `source: "reflection"` — both a `"running"` event before the call and a `"completed"` event after.

**Testing:**
- Unit tests are not needed here (pure wiring); covered by the existing `__tests__` in the web layer.

---

### Step 4: Live thought log in MetisCompanionDock

**Files:**
- `apps/metis-web/components/shell/metis-companion-dock.tsx`

**What:**
Subscribe to `subscribeCompanionActivity` in a `useEffect` and maintain a capped ring-buffer of the last 8 events in component state. Render a scrollable "Thoughts" section in the expanded dock body, above the action buttons.

Design:
- Each entry: status icon (`Loader2` spinning for `"running"`, `Check` for `"completed"`, `AlertTriangle` for `"error"`) + source badge (`RAG` / `Index` / `Research` / `Reflect`) + truncated summary text + relative timestamp.
- Auto-scrolls to newest entry. Collapses gracefully when there are no entries yet (no space taken).
- The existing "Reflect Now" button emits `CompanionActivityEvent` (from Step 3) so the thought log lights up immediately when manually triggered.

```tsx
// New state
const [thoughts, setThoughts] = useState<CompanionActivityEvent[]>([]);

// New effect
useEffect(() => {
  return subscribeCompanionActivity((event) => {
    setThoughts(prev => [event, ...prev].slice(0, 8));
  });
}, []);
```

Source label mapping:
```
"rag_stream"          → "RAG"
"index_build"         → "Index"
"autonomous_research" → "Research"
"reflection"          → "Reflect"
```

**Testing:**
- Update `components/shell/__tests__/metis-companion-dock.test.tsx`: mock `subscribeCompanionActivity`, fire events, assert thought log entries render with correct text and icons.

---

### Step 5: Constellation auto-refresh on new autonomous star

**Files:**
- `apps/metis-web/app/page.tsx`

**What:**
Subscribe to `subscribeCompanionActivity` in a `useEffect` in `page.tsx`. When an event arrives with `source === "autonomous_research"` and `state === "completed"`, call the existing `fetchIndexes()` function and merge the result into `indexSummaries` state using the existing `mergeFetchedIndexes()` helper. The new star will appear on the canvas without a page reload.

```tsx
useEffect(() => {
  return subscribeCompanionActivity((event) => {
    if (event.source === "autonomous_research" && event.state === "completed") {
      fetchIndexes()
        .then((indexes) => setIndexSummaries(prev => mergeFetchedIndexes(prev, indexes)))
        .catch(() => {/* non-critical */});
    }
  });
}, []);
```

This is intentionally minimal — it reuses all existing fetch/merge infrastructure and does not add a polling loop.

**Testing:**
- Add a unit test or Vitest integration test: mock `subscribeCompanionActivity` to fire a completed autonomous_research event, mock `fetchIndexes`, assert `mergeFetchedIndexes` is called and state is updated.

---

## Out of Scope (follow-on work)

- **Constellation visual pulse during research** — pulsing the active faculty node on the canvas while research is in-flight. Deferred because it requires threading `is_running` + active `faculty_id` into the canvas render loop.
- **Reflection streaming** — the `reflect()` LLM call is synchronous; making it incremental requires switching to a streaming LLM call. Deferred.
- **Notification toasts** — a toast/snackbar on research completion. Deferred (thought log covers this use case at launch).
