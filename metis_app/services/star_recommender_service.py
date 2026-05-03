"""Recommend existing user stars for a piece of content (M24 Phase 2).

When the user creates / opens content, the Constellation IA flow needs
to surface the *best matching existing star* (so we can offer "Add to
Star X" instead of forcing a fresh star every time). This service does
the ranking: cosine similarity over embeddings, with a content-type
tiebreak.

See:
- ``docs/adr/0019-constellation-ia-content-first-projects.md``
- ``docs/plans/2026-05-03-constellation-ia-reset-design.md``
- ``docs/plans/2026-05-03-constellation-ia-reset-m24-implementation.md``
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(slots=True)
class StarRecommendation:
    """One ranked candidate star for the current content.

    Attributes:
        star_id: Stable identifier of the candidate star.
        similarity: Adjusted cosine similarity. Includes any tiebreak /
            project-pull boost applied during ranking, so a value can
            exceed ``1.0`` by the boost increments (``+0.001`` / ``+0.01``).
        label: Human-readable label copied from ``star_metadata`` (empty
            when absent).
        archetype: Star archetype copied from ``star_metadata`` (empty
            when absent).
    """

    star_id: str
    similarity: float
    label: str = ""
    archetype: str = ""


class StarRecommenderService:
    """Rank candidate stars by cosine similarity to a query embedding."""

    # Tiebreak / boost constants. Kept tiny on purpose: they should
    # only swing ordering when the cosine scores are otherwise tied.
    _CONTENT_TYPE_BOOST = 0.001
    _PROJECT_MEMBER_BOOST = 0.01

    def rank(
        self,
        *,
        query_embedding: np.ndarray | list[float],
        star_embeddings: dict[str, np.ndarray | list[float]],
        star_metadata: dict[str, dict],
        top_k: int = 5,
        content_type_hint: str = "",
        project_member_star_ids: set[str] | None = None,
    ) -> list[StarRecommendation]:
        """Rank ``star_embeddings`` against ``query_embedding``.

        Args:
            query_embedding: Embedding of the new content.
            star_embeddings: ``{star_id: embedding}`` for candidate stars.
            star_metadata: ``{star_id: {"label": ..., "archetype": ...}}``.
                Missing stars / keys default to empty strings.
            top_k: Maximum number of recommendations to return.
            content_type_hint: When non-empty and equal to a candidate's
                archetype, that candidate gets a ``+0.001`` similarity
                boost (intentionally tiny — it only flips the ordering
                of otherwise-tied scores).
            project_member_star_ids: Set of star ids that belong to the
                same Project as the new content. Members get a
                ``+0.01`` boost. **M25 placeholder** — the parameter
                is plumbed through M24 but never populated; M25 wires
                it in once Projects exist.

        Returns:
            Up to ``top_k`` :class:`StarRecommendation` rows sorted by
            adjusted similarity descending. Empty input -> ``[]``.
        """
        if not star_embeddings:
            return []

        q = np.asarray(query_embedding, dtype=np.float64)
        # Norm safety: clamp to prevent division-by-zero on a zero query
        # vector AND numerical instability on tiny-but-nonzero norms
        # (e.g. ``1e-20``). ``or 1e-9`` would only catch the exact-zero
        # case; ``max(...)`` covers both.
        q_norm = max(float(np.linalg.norm(q)), 1e-9)

        members = project_member_star_ids or set()

        recommendations: list[StarRecommendation] = []
        for star_id, raw in star_embeddings.items():
            v = np.asarray(raw, dtype=np.float64)
            v_norm = max(float(np.linalg.norm(v)), 1e-9)
            similarity = float(np.dot(q, v) / (q_norm * v_norm))

            meta = star_metadata.get(star_id, {}) or {}
            archetype = str(meta.get("archetype", "") or "")
            label = str(meta.get("label", "") or "")

            if content_type_hint and content_type_hint == archetype:
                similarity += self._CONTENT_TYPE_BOOST
            if star_id in members:
                similarity += self._PROJECT_MEMBER_BOOST

            recommendations.append(
                StarRecommendation(
                    star_id=star_id,
                    similarity=similarity,
                    label=label,
                    archetype=archetype,
                )
            )

        recommendations.sort(key=lambda r: r.similarity, reverse=True)
        return recommendations[:top_k]
