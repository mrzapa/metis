"""Network Audit package (M17).

Phase 1 landed the declarative pieces: the known-provider registry and
the classification helper. Phase 2 added the audit event model
(``events.py``) and the SQLite-backed rolling store (``store.py``).
Phase 3a added the interception wrapper (``client.py``) and the
kill-switch layer (``kill_switches.py``). Phase 3b (this landing)
adds the lazy-singleton runtime bindings (``runtime.py``), the named
trigger-feature constants (``trigger_features.py``), and migrates the
six stdlib ``urlopen`` call sites plus the ``huggingface_hub``
snapshot path onto the wrapper. Later phases add the Litestar routes
and the vendor-SDK invocation-layer events (Phase 4), plus the
privacy panel UI (Phase 5).

See ``docs/adr/0010-network-audit-interception.md``,
``docs/adr/0011-network-audit-retention.md``, and
``plans/network-audit/plan.md`` for the full design.
"""

from metis_app.network_audit.client import (
    audited_urlopen,
)
from metis_app.network_audit.events import (
    NetworkAuditEvent,
    sanitize_url,
)
from metis_app.network_audit.kill_switches import (
    NetworkBlockedError,
    is_provider_blocked,
)
from metis_app.network_audit.providers import (
    KNOWN_PROVIDERS,
    ProviderCategory,
    ProviderSpec,
    classify_host,
)
from metis_app.network_audit.runtime import (
    get_default_settings,
    get_default_store,
)
from metis_app.network_audit.sdk_events import (
    audit_sdk_call,
    emit_sdk_invocation,
)
from metis_app.network_audit.store import (
    NetworkAuditStore,
)
from metis_app.network_audit.trigger_features import (
    TRIGGER_EMBEDDING_DOCUMENTS,
    TRIGGER_EMBEDDING_QUERY,
    TRIGGER_GGUF_DOWNLOAD,
    TRIGGER_HF_CATALOG,
    TRIGGER_LLM_INVOKE,
    TRIGGER_LLM_STREAM,
    TRIGGER_NEWS_COMET_HACKERNEWS,
    TRIGGER_NEWS_COMET_REDDIT,
    TRIGGER_NEWS_COMET_RSS,
    TRIGGER_NYX_REGISTRY,
    TRIGGER_TRIBEV2_SNAPSHOT,
    TRIGGER_WEB_SEARCH_DUCKDUCKGO,
    TRIGGER_WEB_SEARCH_JINA_READER,
    TRIGGER_WEB_SEARCH_TAVILY,
)

__all__ = [
    "KNOWN_PROVIDERS",
    "NetworkAuditEvent",
    "NetworkAuditStore",
    "NetworkBlockedError",
    "ProviderCategory",
    "ProviderSpec",
    "TRIGGER_EMBEDDING_DOCUMENTS",
    "TRIGGER_EMBEDDING_QUERY",
    "TRIGGER_GGUF_DOWNLOAD",
    "TRIGGER_HF_CATALOG",
    "TRIGGER_LLM_INVOKE",
    "TRIGGER_LLM_STREAM",
    "TRIGGER_NEWS_COMET_HACKERNEWS",
    "TRIGGER_NEWS_COMET_REDDIT",
    "TRIGGER_NEWS_COMET_RSS",
    "TRIGGER_NYX_REGISTRY",
    "TRIGGER_TRIBEV2_SNAPSHOT",
    "TRIGGER_WEB_SEARCH_DUCKDUCKGO",
    "TRIGGER_WEB_SEARCH_JINA_READER",
    "TRIGGER_WEB_SEARCH_TAVILY",
    "audit_sdk_call",
    "audited_urlopen",
    "classify_host",
    "emit_sdk_invocation",
    "get_default_settings",
    "get_default_store",
    "is_provider_blocked",
    "sanitize_url",
]
