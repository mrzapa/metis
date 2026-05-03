"""Star routes — content-first cluster placement (M24 Phase 1).

The Constellation IA reset (ADR 0019) replaces the M02 faculty-anchor
placement engine with a content-first clusterer. ``GET /v1/stars/clusters``
is the read-side surface of that engine: the frontend canvas calls it
to fetch one row per user star carrying the cluster id and a 2D
position. M25 will layer Project-pull on top of the centroids; for
now the route simply returns whatever the orchestrator produces.

Only the cluster route lives here today. Other star concerns
(nourishment, personality) remain in ``routes/assistant.py`` because
they hang off the assistant snapshot, not the placement engine.
"""

from __future__ import annotations

from litestar import Router, get

import metis_app.settings_store as _store
from metis_app.services.workspace_orchestrator import WorkspaceOrchestrator


@get("/v1/stars/clusters")
def get_star_clusters() -> list[dict]:
    """Return cluster + 2D-layout assignments for the user's stars.

    Empty when ``landing_constellation_user_stars`` is unset / empty.
    Otherwise each row is ``{star_id, cluster_id, x, y, cluster_label}``
    — see
    :class:`metis_app.services.star_clustering_service.StarClusterAssignment`.
    """
    settings = _store.load_settings()
    return WorkspaceOrchestrator().get_star_clusters(settings)


router = Router(
    path="",
    route_handlers=[get_star_clusters],
    tags=["stars"],
)
