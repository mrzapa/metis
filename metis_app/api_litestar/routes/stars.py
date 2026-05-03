"""Star-cluster endpoints (M24 Phase 1).

Backend half of the constellation IA reset (ADR 0019). The route exists
as a *backend-only* surface in M24 Phase 1 — the frontend continues to
render faculty-anchor placement until M24 Phase 3 swaps the renderer.
Shipping the route now lets the frontend phases gate on a stable backend
contract.
"""

from __future__ import annotations

from typing import Any

from litestar import Router, get

import metis_app.settings_store as _settings_store
from metis_app.services.workspace_orchestrator import WorkspaceOrchestrator


@get("/v1/stars/clusters")
def api_get_star_clusters() -> list[dict[str, Any]]:
    """Return cluster assignments + 2D positions for the user's stars.

    Each entry is ``{"star_id", "cluster_id", "x", "y", "cluster_label"}``.

    - ``cluster_id`` is HDBSCAN's label: ``-1`` means the star didn't
      land in a dense cluster (rendered as a "drift" star by the
      frontend); ``>=0`` is a real cluster.
    - ``x`` and ``y`` are normalised to ``[-1, 1]`` so the frontend can
      scale them to any canvas size.
    - ``cluster_label`` is empty in M24 Phase 1; later phases attach
      human-readable labels (TF-IDF + LLM).

    Empty when the user has no stars yet — the frontend uses this as
    the "first-run constellation" signal.
    """
    settings = _settings_store.load_settings()
    return WorkspaceOrchestrator().get_star_clusters(settings)


router = Router(
    path="",
    route_handlers=[api_get_star_clusters],
    tags=["stars"],
)
