# Litestar API Experiment

- **Status**: Draft
- **Date**: 2026-03-14

## Context

ADR 0001 considered a performance-first API variant using Litestar but deferred it as premature. The FastAPI layer is now stable and its shape is settled. This document provides a self-contained reference for evaluating Litestar as a drop-in ASGI alternative for higher concurrency and lower per-request overhead, without committing to a migration. All conclusions here should be validated empirically before any ADR is updated.

---

## Porting Plan

### Concept Mapping

| FastAPI | Litestar |
|---|---|
| `FastAPI(title=..., version=...)` | `Litestar(route_handlers=[...])` |
| `APIRouter(prefix=..., tags=...)` | `Router(path=..., route_handlers=[...])` |
| `Depends(fn)` in handler signature | `Provide(fn)` at `Router`/app level; `Dependency()` annotation in handler |
| `HTTPException(status_code, detail)` | `HTTPException(status_code, detail)` (`litestar.exceptions`) |
| `StreamingResponse(gen, media_type="text/event-stream")` | `EventSourceResponse(gen)` with `ServerSentEvent` items |
| `CORSMiddleware(allow_origins=..., allow_origin_regex=...)` | `CORSConfig(allow_origins=...)` — no regex support; see note below |
| `@app.exception_handler(ValueError)` decorator | `exception_handlers={ValueError: fn}` in `Litestar(...)` constructor |

**CORS regex gap.** The current FastAPI app uses both `allow_origins` and `allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"`. Litestar's `CORSConfig` does not support regex. For Axiom's local-only deployment the enumerated `_DEFAULT_LOCAL_ORIGINS` list already covers every real origin; drop the regex and enumerate explicitly.

**Error translation.** The per-endpoint `_run_engine` wrapper (`ValueError → 400`, `RuntimeError → 503`) is replaced by a single `exception_handlers` dict at app construction. This removes the wrapper entirely and makes error handling globally consistent.

### Migration Sequence (lowest to highest risk)

1. **`GET /healthz`** — No DI, no models. Validates the app factory pattern.
2. **`GET /v1/settings`, `POST /v1/settings`** — No DI, direct `_store` module calls. Validates Pydantic v2 request/response handling and the 403 security guard.
3. **`POST /v1/index/build`, `GET /v1/index/list`** — Pydantic v2 models pass through unchanged. Validates the `from_engine` / `to_engine` adapter pattern.
4. **`POST /v1/query/rag`, `POST /v1/query/direct`** — Synchronous engine calls. Use `async def` handlers that call the sync functions directly; this is safe because no async context is required inside the handler. If event-loop starvation appears under load, wrap with `anyio.to_thread.run_sync`.
5. **`GET /v1/sessions`, `GET /v1/sessions/{session_id}`, `POST /v1/sessions/{session_id}/feedback`** — DI conversion: `Depends(get_session_repo)` becomes `Provide(get_session_repo)` registered on the sessions `Router`; handlers receive the repo via a `Dependency()` annotation.
6. **`POST /v1/query/rag/stream`** — Highest complexity. See streaming section below.

### Streaming Endpoint

The current implementation:

```python
# FastAPI
def _event_generator() -> Generator[str, None, None]:
    for event in stream_rag_answer(req):
        yield f"event: message\ndata: {json.dumps(event)}\n\n"

return StreamingResponse(_event_generator(), media_type="text/event-stream", ...)
```

The Litestar equivalent:

```python
# Litestar
from litestar.response import EventSourceResponse
from litestar.datastructures import ServerSentEvent
import anyio

async def _sse_generator(req):
    def _sync_iter():
        yield from stream_rag_answer(req)

    async for event in anyio.wrap_file(_sync_iter()):  # conceptual
        yield ServerSentEvent(data=json.dumps(event), event="message")

@post("/v1/query/rag/stream")
async def api_stream_rag(data: RagQueryRequestModel) -> EventSourceResponse:
    return EventSourceResponse(_sse_generator(data.to_engine()))
```

The correct async wrapping runs the sync iterator in a thread pool (`anyio.to_thread.run_sync`) and feeds items into an async queue, preserving true streaming without buffering. Any approach that collects all events before yielding the first one breaks TTFT guarantees and must be rejected.

---

## Latency-Sensitive Endpoints

### `POST /v1/query/rag/stream`

The most latency-sensitive endpoint. Time-to-first-token (TTFT) — the wall-clock time between request receipt and delivery of the first `token` SSE event — is the primary perceptual signal for streaming UX. Framework overhead must be under 2 ms per frame. Any buffering introduced by the async wrapping layer will be immediately visible to users. This endpoint is the primary benchmark target and the highest-risk translation.

### `GET /v1/sessions`

Polled frequently by the UI for refresh. Per-request DI overhead (opening the SQLite connection inside `get_session_repo`) accumulates at high poll rates. Under Litestar, evaluate whether `SessionRepository` can be app-scoped (initialized once at startup) rather than request-scoped. Thread-safety of the underlying SQLite connection must be verified before scoping it at the app level.

### `POST /v1/query/rag`, `POST /v1/query/direct`

Framework overhead is small relative to LLM round-trip time (RTT), but becomes visible under concurrent load when multiple requests queue behind a single worker. Validate that `async def` handlers calling synchronous engine functions do not starve the event loop. If starvation is observed, wrap with `anyio.to_thread.run_sync`.

---

## Risks

| Risk | Severity | Notes |
|---|---|---|
| asyncio migration complexity | High | The engine layer is entirely synchronous. Incorrect SSE wrapping can buffer all tokens before the first flush, breaking TTFT. This must be validated with an explicit wall-clock TTFT test before Stage 2 is considered passed. |
| Ecosystem maturity | Medium | Litestar is younger than FastAPI with a smaller community and fewer third-party integrations. Axiom uses no third-party FastAPI middleware, so the direct impact is low; the risk is primarily in long-term support and community knowledge availability. |
| Long-term maintenance | Medium | FastAPI has broader corporate backing (Tiangolo / Sebastián Ramírez + broad community). Litestar is actively maintained but has a smaller contributor base. Evaluate bus-factor risk before committing. |
| `allow_origin_regex` gap | Low | The workaround (enumerated origins) is functionally equivalent for local-only deployment. No user-visible impact. |
| Pydantic v2 compatibility | Low | Both frameworks fully support Pydantic v2. Existing models in `axiom_app/api/models.py` need no changes. |
| Security advisories | Low | Litestar has no published CVEs to date. FastAPI has a longer track record but the local-only deployment surface is minimal regardless of framework. Monitor both `fastapi` and `litestar` on the Python security advisory feed. |
| Python version constraint | Unknown | Verify that the current Litestar release supports the Python version range declared in `pyproject.toml` before adding it as a dependency. |

---

## Staged Evaluation Plan

### Stage 1 — Shadow Port

Implement `axiom_app/api_litestar/` as a parallel package. Do not modify `axiom_app/api/`. The FastAPI layer remains the default and production path throughout Stage 1.

Point the existing test suite (`tests/test_api_app.py`, `tests/test_api_sessions.py`, `tests/test_api_settings.py`) at the Litestar test client. All tests must pass without modification to test logic.

**Exit criterion:** 100% test pass rate against the Litestar client.

### Stage 2 — Benchmark

Run both apps under identical conditions: same machine, same uvicorn worker count, same Python version. Use `httpx` with the existing `pytest-benchmark` infrastructure or `locust` for concurrency testing.

All thresholds are stated as maximum acceptable regression relative to the FastAPI baseline. Improvement is always acceptable.

| Metric | Measurement method | Threshold |
|---|---|---|
| TTFT p95 — first `token` SSE event on `/v1/query/rag/stream` | Wall-clock from request send to first event received | ≤ FastAPI baseline + 50 ms |
| Non-streaming RTT p95 — `/v1/query/rag` | Full round-trip with a mock LLM backend | ≤ FastAPI baseline + 20 ms |
| Session list RTT p95 — `GET /v1/sessions` | Full round-trip with a seeded test DB | ≤ FastAPI baseline + 5 ms |
| Max concurrent connections before first error | Ramp concurrent requests until first 5xx | ≥ FastAPI baseline |
| RSS memory per worker at 50 concurrent requests | `psutil.Process().memory_info().rss` at peak | ≤ FastAPI baseline + 20 MB |

**Exit criterion:** All five metrics within threshold.

### Stage 3 — Integration Test Parity

Verify behavioral equivalence between the two implementations:

- SSE event sequence: `run_started → retrieval_complete → token (1..N) → final` with correct JSON shapes
- HTTP status codes: 400 for `ValueError`, 403 for `api_key_*` write attempt without env flag, 404 for missing session, 503 for `RuntimeError`
- CORS response headers: `Access-Control-Allow-Origin` present and correct for all enumerated local origins
- Settings redaction: `api_key_*` fields absent from all responses
- Error payloads: `{"detail": "..."}` shape preserved

**Exit criterion:** Zero behavioral divergences.

### Stage 4 — Gradual Rollout

If Stages 1–3 all pass, expose `AXIOM_API_BACKEND=litestar` as an environment variable that selects the Litestar app at startup. The FastAPI path remains the default.

Run both paths in parallel for one sprint. Collect real TTFT measurements from the Litestar path.

- **If no regressions:** Record the decision in a new or updated ADR. Archive (do not delete) the FastAPI path with a note pointing to the new ADR.
- **If regressions found:** Close the experiment. Document the specific failure modes in this file under a `## Findings` section. Update ADR 0001 with a note that the option was evaluated and deferred again.

---

## Open Questions

- Does `EventSourceResponse` flush immediately on each `ServerSentEvent` yield, or does uvicorn batch small writes? This must be measured empirically in Stage 2 before TTFT results are trusted.
- Should `SessionRepository` be app-scoped or request-scoped under Litestar? App-scoped reduces per-request SQLite overhead, but thread-safety of the connection must be verified.
- What is the minimum Python version required by current Litestar releases? Verify against `pyproject.toml` before adding the dependency.
- Is there a Litestar equivalent for `allow_origin_regex` that is not currently documented? Check the Litestar changelog and issue tracker before finalizing the enumerated-origins workaround.

---

**See also:** [API Benchmark Harness Guide](api_bench.md) — reproducible `wrk`/`hey`
commands, a results table template, and Axiom-specific metric definitions (SSE
stability, request overhead, serialization overhead) for capturing the FastAPI
baseline required by Stage 2 of this experiment.
