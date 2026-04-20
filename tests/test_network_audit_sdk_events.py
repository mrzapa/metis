"""Tests for the SDK-invocation audit surface (M17 Phase 4).

Covers:

- The ``source`` field on :class:`NetworkAuditEvent` — Literal
  validation + default.
- The schema migration: an older 13-column DB is re-opened and the
  14th ``source`` column is added via ``ALTER TABLE``.
- :func:`audit_sdk_call` context manager — pre-check + post-event
  around a vendor SDK call, with kill-switch short-circuit.
- The :class:`_ProviderAuditWrapper` (LLM) and
  :class:`_EmbeddingsAuditWrapper` (embeddings) proxies — every
  ``invoke`` / ``stream`` / ``embed_documents`` / ``embed_query`` call
  emits a ``source="sdk_invocation"`` event with the right provider
  key.

See ``plans/network-audit/plan.md`` Phase 4 and ADR 0010.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from metis_app.network_audit import (
    NetworkAuditEvent,
    NetworkAuditStore,
    NetworkBlockedError,
    TRIGGER_EMBEDDING_DOCUMENTS,
    TRIGGER_EMBEDDING_QUERY,
    TRIGGER_LLM_INVOKE,
    TRIGGER_LLM_STREAM,
    TRIGGER_WEB_SEARCH_TAVILY,
    audit_sdk_call,
    emit_sdk_invocation,
)
from metis_app.network_audit.kill_switches import AIRPLANE_MODE_KEY


# ---------------------------------------------------------------------------
# Event ``source`` field — Literal validator + default
# ---------------------------------------------------------------------------


def _minimal_event(**overrides: Any) -> NetworkAuditEvent:
    """Build a well-formed event with overridable fields."""
    fields: dict[str, Any] = {
        "id": "01HVTESTTESTTESTTESTTESTXX",
        "timestamp": datetime.now(timezone.utc),
        "method": "POST",
        "url_host": "api.openai.com",
        "url_path_prefix": "/chat",
        "query_params_stored": False,
        "provider_key": "openai",
        "trigger_feature": "unit_test",
        "size_bytes_in": None,
        "size_bytes_out": None,
        "latency_ms": None,
        "status_code": None,
        "user_initiated": False,
        "blocked": False,
    }
    fields.update(overrides)
    return NetworkAuditEvent(**fields)


def test_sdk_event_source_defaults_to_stdlib_urlopen() -> None:
    """Pre-Phase-4 callers that don't pass ``source=`` get the old label.

    This is the backwards-compat invariant: the Phase 3b stdlib
    wrappers continue to produce rows labelled ``"stdlib_urlopen"``
    without edits.
    """
    event = _minimal_event()
    assert event.source == "stdlib_urlopen"


def test_sdk_event_source_accepts_sdk_invocation() -> None:
    """Phase 4 call sites may set ``source='sdk_invocation'``."""
    event = _minimal_event(source="sdk_invocation")
    assert event.source == "sdk_invocation"


def test_network_audit_event_source_literal_rejected_at_runtime() -> None:
    """Any value outside the Literal set raises at construction."""
    with pytest.raises(ValueError, match="source"):
        _minimal_event(source="something_else")
    with pytest.raises(ValueError, match="source"):
        _minimal_event(source="")
    with pytest.raises(ValueError, match="source"):
        _minimal_event(source="SDK_INVOCATION")  # case-sensitive


# ---------------------------------------------------------------------------
# Store round-trip — ``source`` persists
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    return tmp_path / "audit.db"


def test_store_roundtrips_source_field(tmp_db: Path) -> None:
    """``source`` round-trips through ``append`` + ``recent`` faithfully."""
    from metis_app.network_audit.store import make_synthetic_event

    with NetworkAuditStore(tmp_db) as store:
        store.append(make_synthetic_event(source="sdk_invocation"))
        store.append(make_synthetic_event(source="stdlib_urlopen"))
        events = store.recent(limit=10)
        assert len(events) == 2
        # Newest first — the second insert is the stdlib one.
        sources = {event.source for event in events}
        assert sources == {"sdk_invocation", "stdlib_urlopen"}


# ---------------------------------------------------------------------------
# Schema migration — pre-Phase-4 DB gains the ``source`` column
# ---------------------------------------------------------------------------


def _create_legacy_schema_db(path: Path) -> None:
    """Create a 13-column ``network_audit_events`` table (pre-Phase 4).

    Simulates a user upgrading from a previous release. The ``source``
    column is intentionally omitted — the store's migration path must
    add it back via ``ALTER TABLE ... ADD COLUMN``.
    """
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(
            """
            CREATE TABLE network_audit_events (
                id               TEXT PRIMARY KEY,
                timestamp_ms     INTEGER NOT NULL,
                method           TEXT NOT NULL,
                url_host         TEXT NOT NULL,
                url_path_prefix  TEXT NOT NULL,
                provider_key     TEXT NOT NULL,
                trigger_feature  TEXT NOT NULL,
                size_bytes_in    INTEGER,
                size_bytes_out   INTEGER,
                latency_ms       INTEGER,
                status_code      INTEGER,
                user_initiated   INTEGER NOT NULL,
                blocked          INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO network_audit_events VALUES ("
            "'01HVLEGACYTESTTESTTESTTEST', 1745000000000, 'GET', 'api.openai.com', "
            "'/v1', 'openai', 'legacy_row', NULL, NULL, 42, 200, 0, 0"
            ")"
        )
        conn.commit()
    finally:
        conn.close()


def test_store_schema_adds_source_column_on_migration(tmp_db: Path) -> None:
    """Re-opening a pre-Phase-4 DB backfills ``source`` with the default."""
    _create_legacy_schema_db(tmp_db)

    # Confirm the legacy DB really lacks the column.
    conn = sqlite3.connect(str(tmp_db))
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(network_audit_events)")}
        assert "source" not in cols
        assert len(cols) == 13
    finally:
        conn.close()

    # Open the new store — it should ALTER TABLE to add ``source``.
    with NetworkAuditStore(tmp_db) as store:
        # Existing row is still readable with the default source.
        events = store.recent(limit=10)
        assert len(events) == 1
        assert events[0].id == "01HVLEGACYTESTTESTTESTTEST"
        assert events[0].source == "stdlib_urlopen"
        assert events[0].trigger_feature == "legacy_row"

    # Verify the column is now on the table.
    conn = sqlite3.connect(str(tmp_db))
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(network_audit_events)")}
        assert "source" in cols
    finally:
        conn.close()


def test_store_schema_migration_is_idempotent(tmp_db: Path) -> None:
    """Re-opening a fully-migrated store does not fail or double-add the column."""
    with NetworkAuditStore(tmp_db) as _:
        pass
    with NetworkAuditStore(tmp_db) as _:
        pass
    conn = sqlite3.connect(str(tmp_db))
    try:
        cols = [row[1] for row in conn.execute("PRAGMA table_info(network_audit_events)")]
        # Exactly one source column — migration did not duplicate.
        assert cols.count("source") == 1
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# audit_sdk_call — happy path, block path, exception path
# ---------------------------------------------------------------------------


def test_audit_sdk_call_emits_event_on_success(tmp_db: Path) -> None:
    """A successful ``audit_sdk_call`` block emits one sdk_invocation event."""
    with NetworkAuditStore(tmp_db) as store:
        with audit_sdk_call(
            provider_key="openai",
            trigger_feature=TRIGGER_LLM_INVOKE,
            url_host="api.openai.com",
            url_path_prefix="/chat",
            store=store,
            settings={},
        ):
            pass  # Simulate successful LLM call.

        events = store.recent(limit=10)
        assert len(events) == 1
        event = events[0]
        assert event.source == "sdk_invocation"
        assert event.provider_key == "openai"
        assert event.trigger_feature == TRIGGER_LLM_INVOKE
        assert event.url_host == "api.openai.com"
        assert event.url_path_prefix == "/chat"
        assert event.method == "POST"
        assert event.blocked is False
        assert event.latency_ms is not None and event.latency_ms >= 0


def test_audit_sdk_call_emits_event_on_exception(tmp_db: Path) -> None:
    """An exception in the body still produces a post-call event."""
    with NetworkAuditStore(tmp_db) as store:
        with pytest.raises(RuntimeError, match="boom"):
            with audit_sdk_call(
                provider_key="anthropic",
                trigger_feature=TRIGGER_LLM_INVOKE,
                url_host="api.anthropic.com",
                url_path_prefix="/chat",
                store=store,
                settings={},
            ):
                raise RuntimeError("boom")

        events = store.recent(limit=10)
        assert len(events) == 1
        assert events[0].blocked is False
        assert events[0].latency_ms is not None


def test_audit_sdk_call_blocks_on_airplane_mode(tmp_db: Path) -> None:
    """Airplane mode raises and records a blocked event."""
    with NetworkAuditStore(tmp_db) as store:
        body_ran = {"value": False}
        with pytest.raises(NetworkBlockedError):
            with audit_sdk_call(
                provider_key="openai",
                trigger_feature=TRIGGER_LLM_INVOKE,
                url_host="api.openai.com",
                url_path_prefix="/chat",
                store=store,
                settings={AIRPLANE_MODE_KEY: True},
            ):
                body_ran["value"] = True

        assert body_ran["value"] is False
        events = store.recent(limit=10)
        assert len(events) == 1
        event = events[0]
        assert event.blocked is True
        assert event.latency_ms is None
        assert event.source == "sdk_invocation"


def test_audit_sdk_call_without_store_is_no_op() -> None:
    """When no store is available the context still runs the body."""
    body_ran = {"value": False}
    # Pass store=None and settings={} — kill switch is not tripped, so
    # the body runs, and there's simply no append target.
    with audit_sdk_call(
        provider_key="openai",
        trigger_feature=TRIGGER_LLM_INVOKE,
        url_host="api.openai.com",
        url_path_prefix="/chat",
        store=None,
        settings={},
    ):
        body_ran["value"] = True
    assert body_ran["value"] is True


def test_emit_sdk_invocation_writes_event(tmp_db: Path) -> None:
    """The bare ``emit_sdk_invocation`` helper writes one row."""
    with NetworkAuditStore(tmp_db) as store:
        emit_sdk_invocation(
            provider_key="voyage",
            trigger_feature=TRIGGER_EMBEDDING_DOCUMENTS,
            url_host="api.voyageai.com",
            url_path_prefix="/embeddings",
            method="POST",
            user_initiated=False,
            latency_ms=100,
            blocked=False,
            store=store,
        )
        events = store.recent(limit=10)
        assert len(events) == 1
        assert events[0].source == "sdk_invocation"
        assert events[0].provider_key == "voyage"
        assert events[0].latency_ms == 100


# ---------------------------------------------------------------------------
# _ProviderAuditWrapper — LLM invoke + stream
# ---------------------------------------------------------------------------


class _FakeLLM:
    """Minimal stand-in for a LangChain ChatOpenAI instance."""

    def __init__(self) -> None:
        self.invoke_count = 0

    def invoke(self, messages: list[Any]) -> str:
        self.invoke_count += 1
        return "ok"

    def stream(self, messages: list[Any]):
        yield "chunk-1"
        yield "chunk-2"


@pytest.fixture
def isolated_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Patch the runtime default-store singleton to a tmp_path-backed one.

    The SDK wrappers pull from ``get_default_store()`` when no explicit
    store is passed (the production path). Tests need the same surface
    exercised — not a custom-passed store.
    """
    from metis_app.network_audit import runtime

    # Ensure we don't collide with a pre-existing singleton from another test.
    runtime.reset_default_store_for_tests()

    db_path = tmp_path / "audit.db"
    store = NetworkAuditStore(db_path)
    monkeypatch.setattr(runtime, "_store", store)
    monkeypatch.setattr(runtime, "_store_init_failed", False)

    # Settings are read via ``get_default_settings`` — patch it to the
    # empty dict by default; tests that need airplane mode override.
    monkeypatch.setattr(runtime, "get_default_settings", lambda: {})

    try:
        yield store
    finally:
        runtime.reset_default_store_for_tests()


def test_llm_wrapper_invoke_emits_sdk_event(isolated_store: NetworkAuditStore) -> None:
    """Every PooledLLM/_ProviderAuditWrapper invoke emits one sdk event."""
    from metis_app.utils.llm_providers import _ProviderAuditWrapper

    fake = _FakeLLM()
    wrapper = _ProviderAuditWrapper(fake, provider_key="openai", url_host="api.openai.com")
    result = wrapper.invoke([{"type": "human", "content": "hi"}])
    assert result == "ok"
    assert fake.invoke_count == 1

    events = isolated_store.recent(limit=10)
    assert len(events) == 1
    event = events[0]
    assert event.source == "sdk_invocation"
    assert event.provider_key == "openai"
    assert event.trigger_feature == TRIGGER_LLM_INVOKE
    assert event.url_host == "api.openai.com"
    assert event.url_path_prefix == "/chat"
    assert event.blocked is False
    assert event.latency_ms is not None and event.latency_ms >= 0


def test_llm_wrapper_stream_emits_sdk_event(isolated_store: NetworkAuditStore) -> None:
    """Stream() also emits, with the stream trigger."""
    from metis_app.utils.llm_providers import _ProviderAuditWrapper

    fake = _FakeLLM()
    wrapper = _ProviderAuditWrapper(
        fake, provider_key="anthropic", url_host="api.anthropic.com"
    )
    chunks = list(wrapper.stream([{"type": "human", "content": "hi"}]))
    assert chunks == ["chunk-1", "chunk-2"]

    events = isolated_store.recent(limit=10)
    assert len(events) == 1
    event = events[0]
    assert event.source == "sdk_invocation"
    assert event.provider_key == "anthropic"
    assert event.trigger_feature == TRIGGER_LLM_STREAM
    assert event.url_path_prefix == "/stream"


def test_llm_wrapper_stream_is_lazy_generator(
    isolated_store: NetworkAuditStore,
) -> None:
    """stream() must preserve the lazy-generator contract.

    engine/streaming.py iterates ``synthesis_llm.stream(...)``
    chunk-by-chunk to render tokens to the UI incrementally. An
    earlier Phase 4 draft materialised the inner generator into a
    list so the audit context manager could close before the caller
    consumed chunks; that regressed streaming UX (no tokens until
    full response arrived) and OOM'd on long completions. This test
    pins the lazy behaviour so a future refactor cannot re-introduce
    the bug.
    """
    from metis_app.utils.llm_providers import _ProviderAuditWrapper

    consumed: list[str] = []

    class _LazyFakeLLM:
        def stream(self, _messages: list[Any]) -> Any:
            # A generator that TRACKS when each chunk is pulled, so we
            # can assert caller iteration is driving the source.
            consumed.append("yielding-first")
            yield "chunk-1"
            consumed.append("yielding-second")
            yield "chunk-2"
            consumed.append("yielding-third")
            yield "chunk-3"

    wrapper = _ProviderAuditWrapper(
        _LazyFakeLLM(), provider_key="openai", url_host="api.openai.com"
    )
    stream = wrapper.stream([{"type": "human", "content": "hi"}])

    # Contract: stream() returns an iterator/generator, not a
    # pre-materialised list.
    import types

    assert isinstance(stream, types.GeneratorType), (
        "stream() must be a generator — regression if this fails"
    )

    # Consume one chunk; assert only the first source-side yield ran.
    # If the wrapper had materialised the inner generator into a list
    # before returning, consumed would already equal all three
    # "yielding-*" markers before we asked for the first chunk.
    first = next(stream)
    assert first == "chunk-1"
    assert consumed == ["yielding-first"], (
        "stream() materialised eagerly — regression on lazy-streaming contract"
    )

    # Consume the rest; the audit event should fire when the stream
    # exhausts (context manager exits normally).
    rest = list(stream)
    assert rest == ["chunk-2", "chunk-3"]
    assert consumed == [
        "yielding-first",
        "yielding-second",
        "yielding-third",
    ]

    events = isolated_store.recent(limit=10)
    assert len(events) == 1
    assert events[0].trigger_feature == TRIGGER_LLM_STREAM
    assert events[0].blocked is False


def test_llm_wrapper_blocks_when_airplane_mode_on(
    isolated_store: NetworkAuditStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With airplane mode on, invoke raises and the inner LLM is never called."""
    from metis_app.network_audit import runtime
    from metis_app.utils.llm_providers import _ProviderAuditWrapper

    monkeypatch.setattr(
        runtime, "get_default_settings", lambda: {AIRPLANE_MODE_KEY: True}
    )

    fake = _FakeLLM()
    wrapper = _ProviderAuditWrapper(fake, provider_key="openai", url_host="api.openai.com")
    with pytest.raises(NetworkBlockedError):
        wrapper.invoke([{"type": "human", "content": "hi"}])
    assert fake.invoke_count == 0

    events = isolated_store.recent(limit=10)
    assert len(events) == 1
    assert events[0].blocked is True
    assert events[0].source == "sdk_invocation"


def test_llm_wrapper_forwards_other_attributes(isolated_store: NetworkAuditStore) -> None:
    """Non-audited attributes pass through transparently to the inner model."""
    from metis_app.utils.llm_providers import _ProviderAuditWrapper

    class _WithAttrs:
        model_name = "gpt-4o-mini"

        def invoke(self, _messages: list[Any]) -> str:
            return "ok"

    wrapper = _ProviderAuditWrapper(
        _WithAttrs(), provider_key="openai", url_host="api.openai.com"
    )
    # Attribute forwarding via __getattr__.
    assert wrapper.model_name == "gpt-4o-mini"


def test_wrap_for_audit_honours_url_host_override() -> None:
    """Caller-supplied url_host_override replaces the map default.

    Caught by Codex review on PR #519: the _SDK_HOST_MAP hardcodes
    ``local_lm_studio -> localhost``, but a user-configured
    ``local_llm_url`` can point at a remote endpoint. The audit trail
    must reflect the real host, not silently log ``localhost``.
    """
    from metis_app.utils.llm_providers import _wrap_for_audit

    class _Noop:
        def invoke(self, _messages: list[Any]) -> str:
            return "ok"

    wrapped_default = _wrap_for_audit(_Noop(), "local_lm_studio")
    assert wrapped_default._url_host == "localhost"

    wrapped_remote = _wrap_for_audit(
        _Noop(), "local_lm_studio", url_host_override="192.168.1.5"
    )
    assert wrapped_remote._url_host == "192.168.1.5"

    # Empty / None override falls back to the map default (truthy
    # check — empty string should NOT silently override to "").
    wrapped_empty = _wrap_for_audit(_Noop(), "local_lm_studio", url_host_override="")
    assert wrapped_empty._url_host == "localhost"


def test_create_lm_studio_records_configured_remote_host(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store: NetworkAuditStore,
) -> None:
    """A remote-configured LM Studio surfaces the real host in the event.

    Regression for the PR #519 Codex finding. Previously the audit
    event always said ``localhost`` regardless of ``local_llm_url``.
    """
    # Stub the LangChain ChatOpenAI import so we don't need the real
    # library installed for this test path.
    import sys
    import types

    captured_base_url: list[str] = []

    class _StubChatOpenAI:
        def __init__(self, **kwargs: Any) -> None:
            captured_base_url.append(kwargs.get("base_url", ""))

        def invoke(self, _messages: list[Any]) -> str:
            return "stub-response"

    stub_module = types.ModuleType("langchain_openai")
    stub_module.ChatOpenAI = _StubChatOpenAI  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "langchain_openai", stub_module)

    from metis_app.utils.llm_providers import _create_lm_studio

    wrapped = _create_lm_studio(
        settings={"local_llm_url": "http://192.168.1.5:1234/v1"},
        model="llama-3",
        temperature=0.5,
        max_tokens=128,
    )
    assert captured_base_url == ["http://192.168.1.5:1234/v1"]

    wrapped.invoke([{"type": "human", "content": "hi"}])

    events = isolated_store.recent(limit=10)
    assert len(events) == 1
    event = events[0]
    assert event.provider_key == "local_lm_studio"
    # The audit panel must report the REAL host, not a hardcoded localhost.
    assert event.url_host == "192.168.1.5"


def test_create_lm_studio_falls_back_to_localhost_on_malformed_url(
    monkeypatch: pytest.MonkeyPatch,
    isolated_store: NetworkAuditStore,
) -> None:
    """A malformed ``local_llm_url`` falls back to the map default.

    Belt-and-braces: sanitize_url returns ``("unknown", "/")`` for
    inputs that urlsplit can't parse meaningfully; rather than
    surfacing ``unknown`` in the panel (confusing for the user), we
    fall back to the map default for that provider.
    """
    import sys
    import types

    class _StubChatOpenAI:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def invoke(self, _messages: list[Any]) -> str:
            return "stub"

    stub_module = types.ModuleType("langchain_openai")
    stub_module.ChatOpenAI = _StubChatOpenAI  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "langchain_openai", stub_module)

    from metis_app.utils.llm_providers import _create_lm_studio

    # urlsplit tolerates most things; use an obviously hostless string.
    wrapped = _create_lm_studio(
        settings={"local_llm_url": "not a url at all"},
        model="llama-3",
        temperature=0.5,
        max_tokens=128,
    )
    wrapped.invoke([{"type": "human", "content": "hi"}])

    events = isolated_store.recent(limit=10)
    assert len(events) == 1
    assert events[0].url_host == "localhost"


# ---------------------------------------------------------------------------
# _EmbeddingsAuditWrapper — embed_documents + embed_query
# ---------------------------------------------------------------------------


class _FakeEmbeddings:
    """Minimal stand-in for a LangChain Embeddings instance."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * 3 for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [0.0] * 3


def test_embeddings_wrapper_embed_documents_emits_sdk_event(
    isolated_store: NetworkAuditStore,
) -> None:
    """embed_documents emits one sdk_invocation event."""
    from metis_app.utils.embedding_providers import _EmbeddingsAuditWrapper

    wrapper = _EmbeddingsAuditWrapper(
        _FakeEmbeddings(),
        provider_key="openai_embeddings",
        url_host="api.openai.com",
    )
    vectors = wrapper.embed_documents(["a", "b"])
    assert len(vectors) == 2

    events = isolated_store.recent(limit=10)
    assert len(events) == 1
    event = events[0]
    assert event.source == "sdk_invocation"
    assert event.provider_key == "openai_embeddings"
    assert event.trigger_feature == TRIGGER_EMBEDDING_DOCUMENTS
    assert event.url_host == "api.openai.com"
    assert event.url_path_prefix == "/embeddings"


def test_embeddings_wrapper_embed_query_emits_sdk_event(
    isolated_store: NetworkAuditStore,
) -> None:
    """embed_query emits with the query trigger."""
    from metis_app.utils.embedding_providers import _EmbeddingsAuditWrapper

    wrapper = _EmbeddingsAuditWrapper(
        _FakeEmbeddings(),
        provider_key="voyage",
        url_host="api.voyageai.com",
    )
    vec = wrapper.embed_query("hello")
    assert len(vec) == 3

    events = isolated_store.recent(limit=10)
    assert len(events) == 1
    event = events[0]
    assert event.trigger_feature == TRIGGER_EMBEDDING_QUERY
    assert event.provider_key == "voyage"


def test_embeddings_wrapper_blocks_when_airplane_mode(
    isolated_store: NetworkAuditStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Airplane mode blocks embed calls before the inner model runs."""
    from metis_app.network_audit import runtime
    from metis_app.utils.embedding_providers import _EmbeddingsAuditWrapper

    monkeypatch.setattr(
        runtime, "get_default_settings", lambda: {AIRPLANE_MODE_KEY: True}
    )

    called = {"embed_query": 0}

    class _Tracking(_FakeEmbeddings):
        def embed_query(self, text: str) -> list[float]:
            called["embed_query"] += 1
            return [0.0]

    wrapper = _EmbeddingsAuditWrapper(
        _Tracking(),
        provider_key="openai_embeddings",
        url_host="api.openai.com",
    )
    with pytest.raises(NetworkBlockedError):
        wrapper.embed_query("hello")
    assert called["embed_query"] == 0

    events = isolated_store.recent(limit=10)
    assert len(events) == 1
    assert events[0].blocked is True


# ---------------------------------------------------------------------------
# Factory integration — _create_openai returns a wrapped model
# ---------------------------------------------------------------------------


def test_create_llm_returns_wrapper_for_openai(
    isolated_store: NetworkAuditStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """create_llm(provider='openai') returns a _ProviderAuditWrapper.

    This is the key regression-safety test: code paths that construct
    LLMs go through the wrapper, so audit events fire on real invokes.
    """
    # Stub out ChatOpenAI so we don't hit the network; the wrapper is
    # what we're testing.
    import langchain_openai

    class _StubChatOpenAI:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

        def invoke(self, _messages: list[Any]) -> str:
            return "stubbed"

        def stream(self, _messages: list[Any]):
            yield "chunk"

    monkeypatch.setattr(langchain_openai, "ChatOpenAI", _StubChatOpenAI)

    from metis_app.utils.llm_providers import (
        _ProviderAuditWrapper,
        create_llm,
        clear_llm_cache,
    )

    clear_llm_cache()  # Avoid cache poisoning from other tests.
    llm = create_llm(
        {"llm_provider": "openai", "api_key_openai": "sk-test", "llm_model": "gpt-4o"}
    )
    assert isinstance(llm, _ProviderAuditWrapper)

    result = llm.invoke([{"type": "human", "content": "hi"}])
    assert result == "stubbed"

    events = isolated_store.recent(limit=10)
    assert len(events) == 1
    assert events[0].provider_key == "openai"
    assert events[0].source == "sdk_invocation"

    clear_llm_cache()


def test_create_embeddings_returns_wrapper_for_openai(
    isolated_store: NetworkAuditStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """create_embeddings(provider='openai') returns a _EmbeddingsAuditWrapper."""
    import langchain_openai

    class _StubOpenAIEmbeddings:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return [[0.0] * 3 for _ in texts]

        def embed_query(self, _text: str) -> list[float]:
            return [0.0] * 3

    monkeypatch.setattr(langchain_openai, "OpenAIEmbeddings", _StubOpenAIEmbeddings)

    from metis_app.utils.embedding_providers import (
        _EmbeddingsAuditWrapper,
        create_embeddings,
    )

    emb = create_embeddings(
        {
            "embedding_provider": "openai",
            "api_key_openai": "sk-test",
            "embedding_model": "text-embedding-3-small",
        }
    )
    assert isinstance(emb, _EmbeddingsAuditWrapper)

    vec = emb.embed_query("hello")
    assert len(vec) == 3

    events = isolated_store.recent(limit=10)
    assert len(events) == 1
    assert events[0].provider_key == "openai_embeddings"
    assert events[0].trigger_feature == TRIGGER_EMBEDDING_QUERY


# ---------------------------------------------------------------------------
# SDK event sanitisation — no secrets or wire details
# ---------------------------------------------------------------------------


def test_sdk_event_has_sanitized_host_and_path(isolated_store: NetworkAuditStore) -> None:
    """SDK-invocation events never leak query strings or deep paths.

    The wrapper constructs the event host / path from declared constants
    (``api.openai.com`` + ``/chat``), not from a full URL, so there is
    nothing to sanitise — but we pin the invariant so a future refactor
    that starts passing raw URLs through has to grapple with the
    privacy regression.
    """
    from metis_app.utils.llm_providers import _ProviderAuditWrapper

    wrapper = _ProviderAuditWrapper(
        _FakeLLM(), provider_key="openai", url_host="api.openai.com"
    )
    wrapper.invoke([])
    events = isolated_store.recent(limit=10)
    assert len(events) == 1
    event = events[0]
    # No query string remnants.
    assert "?" not in event.url_host
    assert "?" not in event.url_path_prefix
    # No deep path.
    assert "/" not in event.url_path_prefix[1:], (
        f"url_path_prefix {event.url_path_prefix!r} should be a single segment"
    )
    # No secret-looking strings.
    assert "api_key" not in event.url_host
    assert "Bearer" not in event.url_path_prefix


# ---------------------------------------------------------------------------
# Tavily audit — sanity check the wrapper path
# ---------------------------------------------------------------------------


def test_tavily_emits_sdk_event_on_success(
    isolated_store: NetworkAuditStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A successful Tavily search path records an sdk_invocation event."""
    # Stub out ``TavilyClient`` and the DDG fallback so we don't hit the net.
    import sys
    import types

    fake_tavily = types.ModuleType("tavily")

    class _StubTavilyClient:
        def __init__(self, api_key: str) -> None:
            self.api_key = api_key

        def search(self, _query: str, **_kwargs: Any) -> dict[str, Any]:
            return {
                "results": [
                    {"title": "t", "url": "https://example.com", "content": "body"}
                ]
            }

    fake_tavily.TavilyClient = _StubTavilyClient  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "tavily", fake_tavily)

    from metis_app.utils.web_search import _tavily_search

    results = _tavily_search("query", n_results=3, api_key="tav-key")
    assert len(results) == 1

    events = isolated_store.recent(limit=10)
    assert len(events) == 1
    event = events[0]
    assert event.source == "sdk_invocation"
    assert event.provider_key == "tavily"
    assert event.trigger_feature == TRIGGER_WEB_SEARCH_TAVILY
    assert event.url_host == "api.tavily.com"
    assert event.blocked is False
