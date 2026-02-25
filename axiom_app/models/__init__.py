"""axiom_app.models — Data models, dataclasses, and domain exceptions.

Migrated so far:
  - SHTNode        (axiom_app.models.sht)
  - build_sht_tree (axiom_app.models.sht)

Planned (to be migrated from agentic_rag_gui.py):
  - JobCancelledError
  - EvidenceRef
  - Incident
  - SourceLocator
  - AgentProfile
  - TraceEvent
"""

from axiom_app.models.sht import SHTNode, build_sht_tree

__all__ = [
    "SHTNode",
    "build_sht_tree",
]
