"""Network Audit package (M17).

Phase 1 landed the declarative pieces: the known-provider registry and
the classification helper. Phase 2 (this landing) adds the audit
event model (``events.py``) and the SQLite-backed rolling store
(``store.py``). Later phases add the interception wrapper
(``client.py``), the kill-switch layer (``kill_switches.py``), and the
API routes.

See ``docs/adr/0010-network-audit-interception.md``,
``docs/adr/0011-network-audit-retention.md``, and
``plans/network-audit/plan.md`` for the full design.
"""

from metis_app.network_audit.events import (
    NetworkAuditEvent,
    sanitize_url,
)
from metis_app.network_audit.providers import (
    KNOWN_PROVIDERS,
    ProviderCategory,
    ProviderSpec,
    classify_host,
)
from metis_app.network_audit.store import (
    NetworkAuditStore,
)

__all__ = [
    "KNOWN_PROVIDERS",
    "NetworkAuditEvent",
    "NetworkAuditStore",
    "ProviderCategory",
    "ProviderSpec",
    "classify_host",
    "sanitize_url",
]
