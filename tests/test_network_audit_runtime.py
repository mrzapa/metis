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
