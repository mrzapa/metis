from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_network_audit_store(
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[None]:
    """Point the network_audit default store at a per-test tmp DB.

    Without this, any test that triggers a migrated call site (Phase 3b
    onward) evaluates ``get_default_store()`` as a kwarg default, which
    constructs ``NetworkAuditStore()`` at the module's ``DEFAULT_DB_PATH``
    (``<repo>/network_audit.db``). That leaks a SQLite file into the
    repo root, races under ``pytest -n auto``, and accumulates rows
    across runs.

    The fixture:
    1. Sets ``METIS_NETWORK_AUDIT_DB_PATH`` to a fresh tmp path before
       the test runs (the env override ``NetworkAuditStore.__init__``
       already honours).
    2. Calls ``reset_default_store_for_tests()`` before *and* after
       the test so the lazy module-level singleton is freshly
       constructed against the tmp path and torn down cleanly.
    """
    db_path: Path = tmp_path_factory.mktemp("network_audit") / "audit.db"
    monkeypatch.setenv("METIS_NETWORK_AUDIT_DB_PATH", str(db_path))

    # Local import: running the fixture module at collection time
    # should not force-import the audit package in suites that don't
    # touch it.
    from metis_app.network_audit.runtime import reset_default_store_for_tests

    reset_default_store_for_tests()
    try:
        yield
    finally:
        reset_default_store_for_tests()
