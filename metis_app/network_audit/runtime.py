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

:func:`get_default_settings` is a Phase 3b stub that returns an empty
mapping: the audit log records every call, but no kill switch is
active until Phase 5 replaces this with a live reader over
``settings_store``.

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
    """Return the current runtime settings as a mapping for kill-switch checks.

    Phase 3b stub: returns an empty dict. Every audit event is still
    recorded; no kill switch blocks any call yet. Phase 5 replaces
    this with a live reader over the runtime ``settings_store`` so the
    privacy panel's toggles take effect.
    """
    return {}


def reset_default_store_for_tests() -> None:
    """Test-only helper to clear the lazy singleton between integration tests.

    Not exported at the package level — integration tests import it
    from :mod:`metis_app.network_audit.runtime` directly. Closes the
    current store (if any) and forces the next
    :func:`get_default_store` call to build a fresh one.
    """
    global _store, _store_init_failed
    with _store_lock:
        if _store is not None:
            _store.close()
        _store = None
        _store_init_failed = False


__all__ = [
    "get_default_settings",
    "get_default_store",
]
