"""Vendor-SDK invocation audit helpers (M17 Phase 4).

Phase 3's :func:`metis_app.network_audit.client.audited_urlopen` wraps
stdlib ``urllib`` — it observes wire traffic directly and emits events
with ``source="stdlib_urlopen"``. Phase 4 adds an *intent-level* audit
surface for the vendor SDK calls we cannot wrap cleanly (LangChain
``ChatOpenAI`` / ``ChatAnthropic`` / ``ChatGoogleGenerativeAI`` /
``OpenAIEmbeddings`` / ``VoyageAIEmbeddings`` / ``HuggingFaceEmbeddings``;
``tavily.TavilyClient``). See ADR 0010 — *"Vendor SDKs: classify-not-wrap"*.

This module exposes two pieces:

- :func:`emit_sdk_invocation` — build and persist a single
  :class:`NetworkAuditEvent` with ``source="sdk_invocation"``. All
  field handling (default store lookup, timestamp stamping, safe
  ``store.append`` wrapping) is centralised here so per-provider
  wrapping sites stay small.
- :func:`audit_sdk_call` — a context manager that pre-checks the kill
  switch, records ``perf_counter`` start, and emits a post-call event
  with the observed latency on successful or exceptional exit. This is
  the primary public shape: nine call sites across
  :mod:`metis_app.utils.llm_providers`,
  :mod:`metis_app.utils.embedding_providers`, and
  :mod:`metis_app.utils.web_search` share this block instead of
  re-implementing the try/finally dance.

**Honesty about the "intent-level" caveat.** Because the wire is inside
the vendor SDK, the event fields are synthesised from the registry:
``url_host`` is the provider's *declared* primary API host (e.g.
``"api.openai.com"``), and ``url_path_prefix`` is a coarse label like
``"/chat"`` or ``"/embeddings"``. The ``source="sdk_invocation"`` tag
is the flag the Phase 5 panel uses to caveat these rows as declared,
not observed. ``status_code`` and ``size_bytes_*`` are always ``None``
for the same reason — we have nothing to observe.

**Kill-switch semantics (Phase 4).** :func:`audit_sdk_call` consults
:func:`metis_app.network_audit.kill_switches.is_provider_blocked`,
which honours airplane mode as a master switch and the per-provider
``kill_switch_setting_key`` mapping from :data:`KNOWN_PROVIDERS`. For
the LLM and embedding providers, no provider-specific setting key is
registered yet (see ``providers.py``), so *airplane mode is the only
kill switch active on these providers in Phase 4*. Phase 5 introduces
the ``provider_block_llm`` / ``provider_block_embeddings`` settings
maps and the UI switches; this module will pick up that extension
automatically via the shared predicate.

**Audit failures never crash the wrapped call.** Append failures are
logged at warning level and swallowed — same invariant
:func:`audited_urlopen` enforces. See the ``_safe_append`` doc in
``client.py`` for the design rationale.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator, Mapping

from metis_app.network_audit import runtime as _runtime
from metis_app.network_audit.events import NetworkAuditEvent
from metis_app.network_audit.kill_switches import (
    NetworkBlockedError,
    is_provider_blocked,
)
from metis_app.network_audit.store import NetworkAuditStore, new_ulid

logger = logging.getLogger(__name__)


def _safe_append(store: NetworkAuditStore, event: NetworkAuditEvent) -> None:
    """Append ``event`` to ``store`` but swallow any exception.

    Mirrors :func:`metis_app.network_audit.client._safe_append`. The
    audit panel's promise is "show everything we can"; a disk-full
    SQLite or a locked WAL file must never break a wrapped LLM call.
    """
    try:
        store.append(event)
    except Exception:  # noqa: BLE001 — audit must never crash caller
        logger.warning(
            "network_audit: failed to append sdk_invocation event for "
            "provider=%s trigger=%s; wrapped call will still proceed",
            event.provider_key,
            event.trigger_feature,
            exc_info=True,
        )


def emit_sdk_invocation(
    *,
    provider_key: str,
    trigger_feature: str,
    url_host: str,
    url_path_prefix: str,
    method: str = "POST",
    user_initiated: bool = False,
    latency_ms: int | None = None,
    blocked: bool = False,
    size_bytes_in: int | None = None,
    size_bytes_out: int | None = None,
    status_code: int | None = None,
    store: NetworkAuditStore | None = None,
    timestamp: datetime | None = None,
) -> None:
    """Record a single ``source="sdk_invocation"`` event.

    Callers that want the full audit-with-kill-switch-check shape
    should use :func:`audit_sdk_call` instead; this bare emitter is
    useful for tests and for edge cases that need to emit a blocked
    event outside the context-manager flow.

    If ``store`` is ``None`` the module-level default from
    :func:`metis_app.network_audit.runtime.get_default_store` is used;
    if that returns ``None`` (store init failed — see the runtime
    module docstring) the call silently no-ops, matching the wrapped
    call's "audit failure is never fatal" invariant.
    """
    effective_store = store if store is not None else _runtime.get_default_store()
    if effective_store is None:
        return
    event = NetworkAuditEvent(
        id=new_ulid(),
        timestamp=timestamp or datetime.now(timezone.utc),
        method=method,
        url_host=url_host,
        url_path_prefix=url_path_prefix,
        query_params_stored=False,
        provider_key=provider_key,
        trigger_feature=trigger_feature,
        size_bytes_in=size_bytes_in,
        size_bytes_out=size_bytes_out,
        latency_ms=latency_ms,
        status_code=status_code,
        user_initiated=user_initiated,
        blocked=blocked,
        source="sdk_invocation",
    )
    _safe_append(effective_store, event)


@contextmanager
def audit_sdk_call(
    *,
    provider_key: str,
    trigger_feature: str,
    url_host: str,
    url_path_prefix: str,
    method: str = "POST",
    user_initiated: bool = False,
    store: NetworkAuditStore | None = None,
    settings: Mapping[str, Any] | None = None,
) -> Iterator[None]:
    """Context manager: check kill switch, measure latency, emit event.

    Used by the Phase 4 SDK wrappers. Usage::

        with audit_sdk_call(
            provider_key="openai",
            trigger_feature=TRIGGER_LLM_INVOKE,
            url_host="api.openai.com",
            url_path_prefix="/chat",
        ):
            return self._llm.invoke(messages)

    Behaviour on each call:

    1. Resolve the store (explicit or default-singleton) and settings
       (explicit or runtime default). Either may be missing; the
       emitter degrades to a silent no-op per the design invariant.
    2. Consult :func:`is_provider_blocked` for the ``provider_key``.
       On block: emit a ``blocked=True`` event with ``latency_ms=None``
       and raise :class:`NetworkBlockedError`. The wrapped body never
       runs.
    3. Otherwise: start a ``perf_counter`` and yield control to the
       caller. On exit — whether the body returned normally or raised
       — emit a ``blocked=False`` event with the observed latency in
       milliseconds. The original exception (if any) propagates to
       the caller after the event has been recorded.

    Both the pre-block and the post-call emits go through
    :func:`_safe_append`, so a disk-full or WAL-locked store never
    affects the wrapped operation.
    """
    effective_store = store if store is not None else _runtime.get_default_store()
    effective_settings: Mapping[str, Any] = (
        settings if settings is not None else _runtime.get_default_settings()
    )

    # --- Block path -----------------------------------------------------
    if is_provider_blocked(provider_key, effective_settings):
        if effective_store is not None:
            _safe_append(
                effective_store,
                NetworkAuditEvent(
                    id=new_ulid(),
                    timestamp=datetime.now(timezone.utc),
                    method=method,
                    url_host=url_host,
                    url_path_prefix=url_path_prefix,
                    query_params_stored=False,
                    provider_key=provider_key,
                    trigger_feature=trigger_feature,
                    size_bytes_in=None,
                    size_bytes_out=None,
                    latency_ms=None,
                    status_code=None,
                    user_initiated=user_initiated,
                    blocked=True,
                    source="sdk_invocation",
                ),
            )
        raise NetworkBlockedError(
            provider_key,
            "blocked by network-audit kill switch (sdk invocation)",
        )

    # --- Pass-through path ---------------------------------------------
    start = time.perf_counter()
    try:
        yield
    finally:
        latency_ms = int((time.perf_counter() - start) * 1000)
        if effective_store is not None:
            _safe_append(
                effective_store,
                NetworkAuditEvent(
                    id=new_ulid(),
                    timestamp=datetime.now(timezone.utc),
                    method=method,
                    url_host=url_host,
                    url_path_prefix=url_path_prefix,
                    query_params_stored=False,
                    provider_key=provider_key,
                    trigger_feature=trigger_feature,
                    size_bytes_in=None,
                    size_bytes_out=None,
                    latency_ms=latency_ms,
                    status_code=None,
                    user_initiated=user_initiated,
                    blocked=False,
                    source="sdk_invocation",
                ),
            )


__all__ = [
    "audit_sdk_call",
    "emit_sdk_invocation",
]
