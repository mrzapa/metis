"""Network Audit package (M17).

Phase 1 lands the declarative pieces only: the known-provider registry
and the classification helper. Later phases add the interception
wrapper (``client.py``), the event model (``events.py``), the kill
switch layer (``kill_switches.py``), and the API routes.

See ``docs/adr/0010-network-audit-interception.md`` and
``plans/network-audit/plan.md`` for the full design.
"""

from metis_app.network_audit.providers import (
    KNOWN_PROVIDERS,
    ProviderCategory,
    ProviderSpec,
    classify_host,
)

__all__ = [
    "KNOWN_PROVIDERS",
    "ProviderCategory",
    "ProviderSpec",
    "classify_host",
]
