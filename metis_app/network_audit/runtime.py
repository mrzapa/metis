"""Lazy-singleton runtime bindings for the M17 Network Audit wrapper.

Phase 3b (this module) centralises the two pieces of lifecycle state
that :func:`audited_urlopen` callers need: the shared
:class:`NetworkAuditStore` instance and the settings mapping consulted
by :func:`is_provider_blocked`. Migrated call sites import
:func:`get_default_store` and :func:`get_default_settings` from here so
no individual service grows store-ownership responsibility.

Phase 5 layers real Litestar startup / shutdown hooks on top of this
module: the ``app.on_startup`` hook calls :func:`get_default_store` to
warm the singleton (so the first HTTP request does not pay the SQLite
open cost) and the ``app.on_shutdown`` hook calls the underlying
``store.close()``. The wrapper functions here and the Litestar
bootstrap share ONE :class:`NetworkAuditStore` instance — the whole
point of centralising the lazy creation here.

:func:`get_default_settings` is Phase 5's real reader over the runtime
``settings_store``: each call re-loads ``settings.json`` so changes
take effect immediately on the next audited call. A load failure
degrades gracefully to an empty mapping (no kill switches active, all
events still recorded) — same "audit infra never crashes the wrapped
call" invariant as :func:`get_default_store`.

See ``plans/network-audit/plan.md`` (Phases 3b, 5) and
``docs/adr/0010-network-audit-interception.md`` for the lifecycle
rationale.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Mapping

from metis_app.network_audit.store import NetworkAuditStore

logger = logging.getLogger(__name__)

_store: NetworkAuditStore | None = None
_store_init_failed = False
_store_lock = threading.Lock()


def get_default_store() -> NetworkAuditStore | None:
    """Return the process-wide default :class:`NetworkAuditStore`, or ``None``.

    Lazy-instantiated on first call. Uses
    :data:`metis_app.network_audit.store.DEFAULT_DB_PATH` (or the
    ``METIS_NETWORK_AUDIT_DB_PATH`` env override) for persistence.
    Phase 5 wires the same instance into the Litestar startup /
    shutdown hooks for graceful teardown — this function and that
    wiring share one instance.

    Returns ``None`` if SQLite construction fails (read-only install
    directory, invalid env path, disk full). This preserves the
    wrapper's "audit never crashes the wrapped call" invariant: an
    audit-infrastructure failure degrades to a silent no-op rather
    than a user-facing outage for callers like GGUF downloads or web
    search. On failure the warning is logged once and subsequent
    calls return ``None`` without retrying — callers MUST treat the
    return as ``NetworkAuditStore | None`` and skip recording when
    ``None``. :func:`audited_urlopen` already tolerates ``store=None``.

    Thread-safety: construction is guarded by a module-level lock so
    two concurrent callers on cold-start cannot race each other into
    creating two SQLite connections.
    """
    global _store, _store_init_failed
    with _store_lock:
        if _store is not None:
            return _store
        if _store_init_failed:
            return None
        try:
            _store = NetworkAuditStore()
        except Exception:  # noqa: BLE001 — audit infra must not crash callers
            _store_init_failed = True
            logger.warning(
                "network_audit: failed to construct default store; "
                "events will not be recorded until process restart. "
                "Set METIS_NETWORK_AUDIT_DB_PATH to a writable path.",
                exc_info=True,
            )
            return None
        return _store


def get_default_settings() -> Mapping[str, Any]:
    """Return the current runtime settings for kill-switch checks.

    Reads :func:`metis_app.settings_store.load_settings` on each call
    so a settings change (toggling airplane mode, flipping a
    per-provider kill switch) takes effect immediately on the next
    audited call — no cache, no singleton, no restart required. The
    settings loader itself is already cheap (a JSON read of
    ``settings.json`` + merge of defaults); if profiling shows this
    matters under load, Phase 6+ can add a short TTL cache here.

    Graceful degradation: if :func:`load_settings` raises (corrupted
    settings.json, missing defaults, validation error), this function
    logs a warning and returns ``{}``. An empty mapping means "no
    kill switches active" — events are still recorded. This mirrors
    :func:`get_default_store`'s posture that an audit-infrastructure
    failure must not crash the wrapped call.

    The import is deferred into the function body so this module
    stays importable in contexts where :mod:`metis_app.settings_store`
    is not available (e.g. a minimal unit-test harness that monkeys
    :mod:`metis_app.network_audit` without pulling the full settings
    loader and its Pydantic validation stack).
    """
    from metis_app.settings_store import load_settings

    try:
        return load_settings()
    except Exception:  # noqa: BLE001 — audit infra must not crash callers
        logger.warning(
            "network_audit: failed to load settings for kill-switch "
            "check; falling back to empty mapping (no kill switches "
            "active). Fix settings.json or restart the app.",
            exc_info=True,
        )
        return {}


def close_default_store() -> None:
    """Close the process-wide default store, if it was constructed.

    Intended to be wired into the Litestar ``on_shutdown`` hook so
    the SQLite connection is flushed and released cleanly on a normal
    shutdown. Idempotent — a second call is a no-op. Does NOT clear
    the init-failed sentinel, so a shutdown sequence that follows an
    init failure will not accidentally retry construction mid-teardown.

    For test-teardown semantics (close AND clear the init-failed
    sentinel so the next ``get_default_store`` call retries cleanly),
    use :func:`reset_default_store_for_tests` instead.
    """
    global _store
    with _store_lock:
        if _store is not None:
            try:
                _store.close()
            finally:
                _store = None


def reset_default_store_for_tests() -> None:
    """Test-only helper: close the singleton AND clear the init-failed flag.

    Not exported at the package level — integration tests import it
    from :mod:`metis_app.network_audit.runtime` directly. Closes the
    current store (if any) and forces the next
    :func:`get_default_store` call to build a fresh one, even if the
    previous attempt set the init-failed sentinel.

    Production code should use :func:`close_default_store` instead;
    the two have intentionally different semantics around the
    init-failed flag. See that function's docstring.
    """
    global _store_init_failed
    close_default_store()
    with _store_lock:
        _store_init_failed = False


__all__ = [
    "close_default_store",
    "get_default_settings",
    "get_default_store",
]
