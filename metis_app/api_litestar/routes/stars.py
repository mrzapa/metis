"""Star routes — content-first cluster placement (M24 Phase 1 + 2).

The Constellation IA reset (ADR 0019) replaces the M02 faculty-anchor
placement engine with a content-first clusterer.

* ``GET /v1/stars/clusters`` — read-side surface of the placement
  engine: one row per user star with cluster id and 2D position.
* ``POST /v1/stars/recommend`` — given a piece of content, returns
  the best-matching existing stars (M24 Phase 2) so the UI can offer
  "Add to Star X" instead of always creating a new one.

M25 will layer Project-pull on top of cluster centroids and populate
the recommender's ``project_member_star_ids`` boost — for M24, the
parameter is plumbed but never set.

Only the cluster + recommend routes live here today. Other star
concerns (nourishment, personality) remain in ``routes/assistant.py``
because they hang off the assistant snapshot, not the placement engine.
"""

from __future__ import annotations

from litestar import Router, get, post
from pydantic import BaseModel

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


class _RecommendRequest(BaseModel):
    """Body for ``POST /v1/stars/recommend``."""

    content: str
    content_type: str = ""


@post("/v1/stars/recommend", status_code=200)
def recommend_stars(data: _RecommendRequest) -> dict:
    """Rank existing user stars against ``content`` (M24 Phase 2).

    Returns ``{recommendations: [...], create_new_suggested: bool}``.
    The frontend uses ``create_new_suggested`` to decide whether to
    nudge the user toward a fresh star instead of attaching to an
    existing one.
    """
    return WorkspaceOrchestrator().recommend_stars_for_content(
        content=data.content,
        content_type=data.content_type,
    )


router = Router(
    path="",
    route_handlers=[get_star_clusters, recommend_stars],
    tags=["stars"],
)
