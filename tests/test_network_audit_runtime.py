"""Tests for the network-audit runtime singleton + graceful construction failure.

Phase 3b scope. The P1 Codex review on PR #518 flagged that
:func:`get_default_store` must never let a SQLite-construction failure
(read-only FS, invalid env path, disk full) bubble up as a user-facing
error — the wrapper's core promise is "audit never crashes the wrapped
call." This test file pins that behaviour.
"""
from __future__ import annotations

import logging
import sqlite3
from typing import Iterator

import pytest

from metis_app.network_audit import runtime
from metis_app.network_audit.runtime import (
    close_default_store,
    get_default_settings,
    get_default_store,
    reset_default_store_for_tests,
)


@pytest.fixture(autouse=True)
def _reset_singleton() -> Iterator[None]:
    """Force a fresh runtime state for each test.

    The repo-wide autouse fixture in ``conftest.py`` already sets
    ``METIS_NETWORK_AUDIT_DB_PATH`` to a tmp path and resets the
    singleton. This fixture is a belt-and-braces reset after any
    in-test poking at the private ``_store_init_failed`` flag.
    """
    yield
    reset_default_store_for_tests()


def test_get_default_store_returns_none_when_construction_fails(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An OperationalError during store construction yields None, not a raise."""

    def _explode(*_args: object, **_kwargs: object) -> None:
        raise sqlite3.OperationalError("unable to open database file")

    monkeypatch.setattr(runtime, "NetworkAuditStore", _explode)
    reset_default_store_for_tests()

    with caplog.at_level(logging.WARNING, logger="metis_app.network_audit.runtime"):
        store = get_default_store()

    assert store is None
    assert any(
        "failed to construct default store" in record.message
        for record in caplog.records
    ), "Expected a one-shot warning on construction failure"


def test_get_default_store_caches_failure_across_calls(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """After a failed construction, subsequent calls return None without retrying.

    This avoids spamming the log with a warning per call and avoids
    re-paying the SQLite-open cost on every failed request. The
    failure clears only on ``reset_default_store_for_tests`` or
    process restart.
    """
    call_count = 0

    def _counting_explode(*_args: object, **_kwargs: object) -> None:
        nonlocal call_count
        call_count += 1
        raise sqlite3.OperationalError("unable to open database file")

    monkeypatch.setattr(runtime, "NetworkAuditStore", _counting_explode)
    reset_default_store_for_tests()

    with caplog.at_level(logging.WARNING, logger="metis_app.network_audit.runtime"):
        assert get_default_store() is None
        assert get_default_store() is None
        assert get_default_store() is None

    assert call_count == 1, "NetworkAuditStore() should only be attempted once"
    warnings = [r for r in caplog.records if "failed to construct" in r.message]
    assert len(warnings) == 1, "Should warn once, not on every call"


def test_reset_default_store_clears_failure_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``reset_default_store_for_tests`` allows a subsequent init to succeed.

    This is load-bearing for the autouse fixture in ``conftest.py``:
    if one test injects a broken ``NetworkAuditStore`` and the flag
    persisted, later tests in the same process would get ``None`` back
    silently and their assertions about "event was recorded" would
    fail mysteriously.
    """
    attempts: list[str] = []

    def _first_call_fails_then_succeeds(
        *_args: object, **_kwargs: object
    ) -> object:
        attempts.append("call")
        if len(attempts) == 1:
            raise sqlite3.OperationalError("unable to open database file")
        # Return the real NetworkAuditStore on the second call.
        from metis_app.network_audit.store import NetworkAuditStore

        return NetworkAuditStore()

    monkeypatch.setattr(runtime, "NetworkAuditStore", _first_call_fails_then_succeeds)

    reset_default_store_for_tests()
    assert get_default_store() is None  # first call fails

    reset_default_store_for_tests()
    store = get_default_store()
    assert store is not None
    assert len(attempts) == 2


# ---------------------------------------------------------------------------
# Phase 5a — real get_default_settings reader
# ---------------------------------------------------------------------------


def test_get_default_settings_reads_live_settings_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``get_default_settings`` delegates to ``settings_store.load_settings``.

    The reader is re-evaluated on every call (no caching in the
    runtime module) so a settings flip takes effect on the next
    audited call. This test pins that behaviour by changing the
    fake ``load_settings`` return between two calls.
    """
    import metis_app.settings_store as settings_store

    stub_settings: dict[str, object] = {"network_audit_airplane_mode": False}

    def _fake_load_settings() -> dict[str, object]:
        return dict(stub_settings)

    monkeypatch.setattr(settings_store, "load_settings", _fake_load_settings)

    first = get_default_settings()
    assert first.get("network_audit_airplane_mode") is False

    # Flip the stub and confirm the next call sees the new value.
    stub_settings["network_audit_airplane_mode"] = True
    second = get_default_settings()
    assert second.get("network_audit_airplane_mode") is True


def test_get_default_settings_returns_empty_on_load_failure(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A raising ``load_settings`` degrades to ``{}``, not an exception.

    The invariant is "audit infra must not crash the wrapped call".
    A corrupted ``settings.json`` or a loader validation error must
    therefore resolve to "no kill switches active" (return ``{}``)
    with a single-line warning in the log.
    """
    import metis_app.settings_store as settings_store

    def _explode() -> dict[str, object]:
        raise RuntimeError("settings.json parse failure")

    monkeypatch.setattr(settings_store, "load_settings", _explode)

    with caplog.at_level(
        logging.WARNING, logger="metis_app.network_audit.runtime"
    ):
        result = get_default_settings()

    assert result == {}
    assert any(
        "failed to load settings" in record.message
        for record in caplog.records
    ), "Expected a warning log line on load failure"


# ---------------------------------------------------------------------------
# Phase 5a — close_default_store (production semantics)
# ---------------------------------------------------------------------------


def test_close_default_store_releases_singleton() -> None:
    """``close_default_store`` closes the live singleton and nulls it.

    A subsequent ``get_default_store`` call constructs a fresh store.
    This is the production hook wired into the Litestar
    ``on_shutdown`` callback.
    """
    first = get_default_store()
    assert first is not None

    close_default_store()
    assert runtime._store is None

    second = get_default_store()
    assert second is not None
    assert second is not first


def test_close_default_store_is_idempotent() -> None:
    """Calling ``close_default_store`` twice is a no-op on the second call."""
    get_default_store()
    close_default_store()
    # Second call must not raise even though the store is already None.
    close_default_store()


def test_close_default_store_preserves_init_failed_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``close_default_store`` does NOT clear the init-failed sentinel.

    This is the key difference from ``reset_default_store_for_tests``:
    if the startup hook's warm-up failed, a subsequent shutdown hook
    must not accidentally retry construction via the flag reset. Only
    the test helper clears the flag.
    """

    def _explode(*_args: object, **_kwargs: object) -> None:
        raise sqlite3.OperationalError("unable to open database file")

    monkeypatch.setattr(runtime, "NetworkAuditStore", _explode)
    reset_default_store_for_tests()  # clean slate

    assert get_default_store() is None
    assert runtime._store_init_failed is True

    close_default_store()

    # Flag must survive close_default_store.
    assert runtime._store_init_failed is True
    # get_default_store still returns None without retrying construction.
    assert get_default_store() is None
