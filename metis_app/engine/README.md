# metis_app.engine

`metis_app.engine` is the proposed public core boundary between METIS frontends and METIS core functionality.

This package does not exist yet as runtime code. This README defines the intended contract for a future engine layer so that the web UI, CLI, and any other frontend can depend on one stable, typed API instead of importing service modules directly.

Once the engine layer exists, views, controllers, and frontends should stop reaching into `metis_app/services/*` for indexing, query, session, trace, and synthesis behavior. Those modules remain the current implementation backing for now, but they are not the intended long-term frontend integration surface.

## Status

- Proposed public contract only.
- Documentation-only placeholder.
- No behavior is implemented in `metis_app.engine` yet.

## Hard Rules

The engine layer must follow these rules:

- It must not import any UI toolkit.
- It must not accept or return UI objects such as widgets, signals, controllers, views, dialogs, or model instances owned by the UI shell.
- It must not depend on `AppModel`, `argparse.Namespace`, or any other frontend-specific container type.
- It must accept plain settings payloads as `dict[str, Any]`.
- It must return typed records, not raw UI-facing dict payloads assembled for a specific frontend.
- It may use callbacks or iterators for progress and streaming, but those contracts must also be typed and UI-agnostic.

## Public Types

The engine should reuse existing typed records where they already exist today.

| Engine type | Current source |
| --- | --- |
| `IndexBundle` | `metis_app.services.index_service.IndexBundle` |
| `IndexManifest` | `metis_app.models.parity_types.IndexManifest` |
| `QueryResult` | `metis_app.services.index_service.QueryResult` |
| `EvidenceSource` | `metis_app.models.session_types.EvidenceSource` |
| `SessionSummary` | `metis_app.models.session_types.SessionSummary` |
| `SessionMessage` | `metis_app.models.session_types.SessionMessage` |
| `SessionFeedback` | `metis_app.models.session_types.SessionFeedback` |
| `SessionDetail` | `metis_app.models.session_types.SessionDetail` |
| `TraceEvent` | `metis_app.models.parity_types.TraceEvent` |

These types are already plain, typed data records and are good candidates for direct reuse by the engine boundary.

## Draft Engine-Only Types

The current codebase does not yet have a stable typed streaming contract. The engine layer should introduce one.

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from metis_app.models.parity_types import TraceEvent
from metis_app.models.session_types import EvidenceSource


@dataclass(slots=True)
class EngineProgressEvent:
    kind: Literal["status", "progress", "log"]
    message: str = ""
    current: int | None = None
    total: int | None = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class EngineResponse:
    run_id: str
    session_id: str = ""
    response_text: str = ""
    sources: list[EvidenceSource] = field(default_factory=list)
    trace_events: list[TraceEvent] = field(default_factory=list)
    grounding_html_path: str = ""
    validation_notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class EngineStreamEvent:
    kind: Literal[
        "status",
        "progress",
        "retrieval",
        "delta",
        "trace",
        "result",
        "error",
    ]
    text: str = ""
    progress: EngineProgressEvent | None = None
    sources: list[EvidenceSource] = field(default_factory=list)
    trace_event: TraceEvent | None = None
    response: EngineResponse | None = None
    payload: dict[str, Any] = field(default_factory=dict)
```

Notes:

- `EngineProgressEvent` replaces ad hoc frontend callback payloads.
- `EngineResponse` is the final typed synthesis result for a run.
- `EngineStreamEvent` is the typed event envelope for incremental engine output.
- The first implementation can emit coarse events such as `status`, `retrieval`, `trace`, `result`, and `error` even if token-by-token `delta` streaming is not ready yet.

## Proposed Function Surface

The engine should be function-first for stateless indexing and retrieval operations.

```python
from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any


def build_index(
    documents: list[str],
    settings: dict[str, Any],
    *,
    progress: Callable[[EngineProgressEvent], None] | None = None,
    cancel_token: Any | None = None,
) -> IndexBundle:
    """Build an in-memory index bundle from source documents."""


def save_index(
    bundle: IndexBundle,
    *,
    settings: dict[str, Any],
    target_path: str | None = None,
    index_dir: str | None = None,
) -> IndexManifest:
    """Persist an index bundle and return the canonical manifest."""


def refresh_index(
    bundle: IndexBundle,
    *,
    settings: dict[str, Any],
) -> IndexManifest:
    """Rewrite persisted index metadata for an existing bundle."""


def list_indexes(
    index_dir: str,
    *,
    settings: dict[str, Any] | None = None,
) -> list[IndexManifest]:
    """List persisted indexes visible to the engine."""


def load_index(
    path: str,
    *,
    settings: dict[str, Any] | None = None,
) -> IndexBundle:
    """Load a persisted index bundle from a manifest, directory, or legacy JSON bundle."""


def query_index(
    bundle: IndexBundle,
    question: str,
    settings: dict[str, Any],
) -> QueryResult:
    """Run retrieval against a loaded bundle and return typed evidence."""


def stream_query(
    bundle: IndexBundle,
    question: str,
    settings: dict[str, Any],
    *,
    session_store: SessionStore | None = None,
    trace_store: TraceStore | None = None,
    session_id: str | None = None,
    cancel_token: Any | None = None,
) -> Iterator[EngineStreamEvent]:
    """Run retrieval plus synthesis and emit typed stream events until a final result is produced."""
```

Behavior notes:

- `build_index`, `save_index`, `refresh_index`, `list_indexes`, `load_index`, and `query_index` should remain UI-free wrappers around the current indexing and vector-store services.
- `stream_query` is the future high-level engine entrypoint for retrieval, synthesis, pipeline selection, trace emission, and optional session persistence.
- `stream_query` should not require a UI callback. Frontends should be able to iterate over `EngineStreamEvent` values directly.
- `cancel_token` must stay cooperative and toolkit-neutral.

## Proposed Stateful Classes

The engine should expose explicit persistence-oriented store objects for sessions and traces.

### SessionStore

`SessionStore` is the stable engine-facing wrapper for session persistence.

```python
class SessionStore:
    def create_session(...) -> SessionSummary: ...
    def upsert_session(...) -> SessionSummary: ...
    def list_sessions(...) -> list[SessionSummary]: ...
    def get_session(session_id: str) -> SessionDetail | None: ...
    def append_message(...) -> None: ...
    def save_feedback(...) -> None: ...
    def rename_session(session_id: str, title: str) -> SessionSummary: ...
    def duplicate_session(session_id: str, *, title: str | None = None) -> SessionSummary: ...
    def export_session(...) -> tuple[pathlib.Path, pathlib.Path]: ...
    def delete_session(session_id: str) -> None: ...
```

Behavior notes:

- `get_session` should return a typed `SessionDetail`.
- The engine contract should eventually define whether trace hydration is included by default or is an explicit composition step.
- The current code hydrates traces by combining session messages with trace reads; that behavior should move behind the engine boundary instead of living in a UI controller.

### TraceStore

`TraceStore` is the stable engine-facing wrapper for run trace persistence.

```python
class TraceStore:
    def append(self, record: TraceEvent | dict[str, Any]) -> TraceEvent: ...
    def append_event(self, **kwargs: Any) -> TraceEvent: ...
    def get_run(self, run_id: str) -> list[TraceEvent]: ...
    def get_runs(self, run_ids: list[str]) -> dict[str, list[TraceEvent]]: ...
```

Behavior notes:

- The engine-facing read methods should prefer typed `TraceEvent` values over raw dict rows.
- The current `metis_app.services.trace_store.TraceStore` reads dict payloads; the engine wrapper can normalize them into `TraceEvent` instances.

## Mapping To Current Code

This proposed engine surface must remain a thin, typed boundary over the code that already exists today.

| Proposed engine API | Current backing implementation | Notes |
| --- | --- | --- |
| `build_index(...)` | `metis_app/services/vector_store.py` and `metis_app/services/index_service.py::build_index_bundle` | Current adapters already route build requests to the shared index builder. |
| `save_index(...)` | `metis_app/services/vector_store.py` and `metis_app/services/index_service.py::persist_index_bundle` / `save_index_bundle` | Engine should return `IndexManifest` even if a backend currently returns a manifest path. |
| `refresh_index(...)` | `metis_app/services/index_service.py::refresh_index_bundle` | Existing function rewrites persisted bundle and manifest metadata. |
| `list_indexes(...)` | `metis_app/services/index_service.py::list_index_manifests` and `metis_app/services/vector_store.py::VectorStoreAdapter.list_indexes` | Engine should standardize on `list[IndexManifest]`. |
| `load_index(...)` | `metis_app/services/index_service.py::load_index_bundle` and `metis_app/services/vector_store.py::VectorStoreAdapter.load` | Supports manifest-backed directories and legacy JSON bundles today. |
| `query_index(...)` | `metis_app/services/index_service.py::query_index_bundle` and backend adapter `query(...)` methods in `metis_app/services/vector_store.py` | Existing retrieval already returns typed `QueryResult`. |
| `stream_query(...)` retrieval phase | `metis_app/services/index_service.py::query_index_bundle` or backend adapter query routing in `metis_app/services/vector_store.py` | Engine should emit a typed retrieval event before synthesis. |
| `stream_query(...)` synthesis phase | `metis_app/services/response_pipeline.py` and `metis_app/utils/llm_providers.py::create_llm` | Current controller uses `run_blinkist_summary_pipeline`, `run_tutor_pipeline`, and `llm.invoke(...)`. |
| `stream_query(...)` trace emission | `metis_app/services/trace_store.py` plus `metis_app.models.parity_types.TraceEvent` | Current controller appends trace events around retrieval, synthesis, validation, and grounding. |
| `SessionStore` | `metis_app/services/session_repository.py::SessionRepository` and repo-root `rag_sessions.db` | Current persistence already returns `SessionSummary` and `SessionDetail`. |
| `TraceStore` | `metis_app/services/trace_store.py::TraceStore`, repo-root `traces/runs.jsonl`, and `traces/runs/<run_id>.jsonl` | Current trace persistence is append-only JSONL. |
| Session trace hydration | `SessionRepository.get_session(...)` plus `TraceStore.read_runs(...)`, currently composed in `metis_app/controllers/app_controller.py::_session_trace_payload` | This composition should move out of the UI controller and behind the engine boundary. |

## Current Gaps The Engine Should Close

- Frontends currently import service modules directly instead of calling one stable engine API.
- Query synthesis is orchestrated in `AppController`, not in a reusable frontend-agnostic engine function.
- Progress messages are currently plain dict callbacks, not typed engine events.
- Trace reads currently return raw dicts rather than typed `TraceEvent` instances.
- There is no public streaming query interface yet, even though the controller already has enough pieces to support one.

## Example Frontend Usage

This is the intended style of usage for any future frontend, including the web UI, CLI, or other shells.

```python
from metis_app.engine import load_index, stream_query

settings: dict[str, object] = {
    "llm_provider": "mock",
    "selected_mode": "Q&A",
    "retrieval_k": 4,
    "top_k": 4,
}

bundle = load_index("indexes/my-index/manifest.json", settings=settings)

for event in stream_query(bundle, "What changed in this project?", settings):
    if event.kind == "status":
        print(event.text)
    elif event.kind == "retrieval":
        for source in event.sources:
            print(source.sid, source.label, source.file_path)
    elif event.kind == "delta":
        print(event.text, end="")
    elif event.kind == "result" and event.response is not None:
        print(event.response.response_text)
```

The important point is that the caller only passes plain settings, plain strings, and engine store objects, and only receives typed engine records back. No UI-framework objects, widgets, signals, controllers, or `AppModel` instances cross this boundary.

## Acceptance Checklist For Future Engine Work

- Frontends can index, load, query, stream, and persist sessions without importing `metis_app/services/*` directly.
- The engine can be imported in any non-UI process without pulling in UI-framework dependencies.
- All engine entrypoints accept `dict[str, Any]` settings.
- Engine entrypoints return typed records instead of frontend-shaped dict payloads.
- Session and trace persistence map cleanly to the current `SessionRepository` and `TraceStore` implementations.
- Streaming is exposed as a typed iterator contract, even if the first implementation is coarse-grained.
