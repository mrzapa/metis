# M24 — Constellation IA Reset (UI) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship the user-visible half of the constellation IA reset — kill faculty-anchored placement, replace with content-embedding clusters; replace the Star-Observatory-as-Add-flow with a file-picker → AI-suggested-stars flow; give the central METIS star a real job (Everything chat over all stars). Backend faculty signal stays as invisible internal.

**Architecture:** Two new backend services (`star_clustering_service`, `star_recommender_service`) + three new HTTP routes. Frontend rip-out of `FACULTY_CONCEPTS` placement; new `AddStarDialog` and `EverythingChatSheet` components; central METIS star becomes click-to-open-everything-chat. `StellarProfile` archetype system + tiered-naming policy survive (per ADR 0006 + ADR 0019 carve-outs).

**Tech Stack:** Python 3.11+ / Litestar / SQLite / NumPy + scikit-learn (clustering) / existing embedding pipeline at `metis_app/utils/embedding_providers.py` (backend) · Next.js 16 / React 19 / react-hook-form / vitest (frontend) · pytest.

**Design doc:** [`docs/plans/2026-05-03-constellation-ia-reset-design.md`](2026-05-03-constellation-ia-reset-design.md). **ADR:** [`docs/adr/0019-constellation-ia-content-first-projects.md`](../adr/0019-constellation-ia-content-first-projects.md). Read both before any phase.

**TDD Mode:** pragmatic (matches M23 / M21 conventions). RED-step tests for behaviour with regression risk; pure visual / structural changes verified through browser preview.

**Worktree gotcha:** `apps/metis-web/node_modules` will need a junction to the main repo install (controller sets it up before dispatch). `pnpm vitest run` and `pnpm tsc --noEmit` work; `pnpm next dev` does NOT (Turbopack rejects the junction). Browser-preview verification deferred to Phase 6 on the main repo.

**Path corrections vs design doc:** None at draft time — verify during impl.

---

## Phase 1 — Backend clustering service (~2 days)

### Task 1.1: Add `scikit-learn` to backend deps if missing

**Files:**
- Verify: `pyproject.toml` (or `requirements.txt` — check first which is canonical)
- Verify: `metis_app/utils/embedding_providers.py` already imports the embedding helpers we need

**Step 1: Check current state**

Run:
```
grep -E "scikit-learn|sklearn" pyproject.toml requirements*.txt 2>&1 | head
```

If absent, add to dev / runtime dependencies. The clustering service uses `sklearn.cluster.HDBSCAN` and `sklearn.decomposition.PCA`.

**Step 2: Install**

```
pip install scikit-learn>=1.5.0
```

(or update the lockfile per project convention — match what M22 / M16 did when adding pytorch / fastai dependencies; check those plan docs.)

**Step 3: Verify import works**

```
python -c "from sklearn.cluster import HDBSCAN; from sklearn.decomposition import PCA; print('ok')"
```

Expected: `ok`.

**Step 4: Commit (deps only)**

```
git commit -m "chore(m24): add scikit-learn for clustering service"
```

---

### Task 1.2: `StarClusteringService` — embedding extraction + clustering

**Files:**
- Create: `metis_app/services/star_clustering_service.py`
- Test: `tests/test_star_clustering_service.py` (new)

**Step 1: Write the failing test**

`tests/test_star_clustering_service.py`:

```python
"""Tests for the star clustering service."""

from __future__ import annotations

import numpy as np
import pytest

from metis_app.services.star_clustering_service import (
    StarClusteringService,
    StarClusterAssignment,
)


def test_compute_clusters_groups_similar_embeddings():
    """Five embeddings, two natural clusters → service returns two cluster IDs."""
    # Two tight clusters in 4-dim space
    embeddings = {
        "star_a": np.array([1.0, 1.0, 0.0, 0.0]),
        "star_b": np.array([0.95, 1.05, 0.0, 0.0]),
        "star_c": np.array([1.05, 0.95, 0.0, 0.0]),
        "star_d": np.array([0.0, 0.0, 1.0, 1.0]),
        "star_e": np.array([0.0, 0.0, 0.95, 1.05]),
    }
    service = StarClusteringService()
    assignments = service.compute_clusters(embeddings)

    # Five assignments returned
    assert len(assignments) == 5

    # star_a, star_b, star_c are in the same cluster
    cluster_a = next(a.cluster_id for a in assignments if a.star_id == "star_a")
    cluster_b = next(a.cluster_id for a in assignments if a.star_id == "star_b")
    cluster_c = next(a.cluster_id for a in assignments if a.star_id == "star_c")
    assert cluster_a == cluster_b == cluster_c

    # star_d, star_e are in a different cluster
    cluster_d = next(a.cluster_id for a in assignments if a.star_id == "star_d")
    cluster_e = next(a.cluster_id for a in assignments if a.star_id == "star_e")
    assert cluster_d == cluster_e
    assert cluster_a != cluster_d


def test_compute_clusters_returns_2d_coordinates():
    """Each assignment has finite (x, y) screen-space coordinates."""
    embeddings = {f"star_{i}": np.random.rand(8) for i in range(10)}
    service = StarClusteringService()
    assignments = service.compute_clusters(embeddings)

    for a in assignments:
        assert isinstance(a.x, float)
        assert isinstance(a.y, float)
        assert -1.0 <= a.x <= 1.0  # normalized
        assert -1.0 <= a.y <= 1.0


def test_compute_clusters_handles_empty_input():
    service = StarClusteringService()
    assignments = service.compute_clusters({})
    assert assignments == []


def test_compute_clusters_single_star():
    """One star → one cluster (cluster_id = 0), centred at origin."""
    embeddings = {"only_star": np.array([0.5, 0.5, 0.5, 0.5])}
    service = StarClusteringService()
    assignments = service.compute_clusters(embeddings)

    assert len(assignments) == 1
    assert assignments[0].star_id == "only_star"
    assert assignments[0].cluster_id == 0
```

**Step 2: Run tests; confirm 4 FAIL with `ModuleNotFoundError`:**

```
PYTHONPATH=$PWD pytest tests/test_star_clustering_service.py -v
```

**Step 3: Implement** `metis_app/services/star_clustering_service.py`:

```python
"""Cluster stars by content embedding into 2D screen-space positions.

Replaces the M02 / ADR 0006 faculty-anchor placement system. Stars are grouped
by content fingerprint and projected to 2D for canvas rendering.

Per ADR 0019, this service is the M24 placement engine. M25 layers Project-pull
on top of cluster centroids.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import numpy as np
from sklearn.cluster import HDBSCAN
from sklearn.decomposition import PCA


@dataclass(slots=True)
class StarClusterAssignment:
    """One star's cluster ID + 2D canvas position."""
    star_id: str
    cluster_id: int        # -1 = unclustered (HDBSCAN noise label); >=0 = real cluster
    x: float               # normalized to [-1, 1]
    y: float               # normalized to [-1, 1]
    cluster_label: str = ""  # filled later by label generator (TF-IDF + LLM)


class StarClusteringService:
    """Compute cluster assignments and 2D layout for a set of star embeddings."""

    def __init__(
        self,
        *,
        min_cluster_size: int = 2,
        pca_components: int = 2,
    ) -> None:
        self._min_cluster_size = min_cluster_size
        self._pca_components = pca_components

    def compute_clusters(
        self, embeddings: dict[str, np.ndarray | list[float]],
    ) -> list[StarClusterAssignment]:
        """Cluster + project. Returns one assignment per input star."""
        if not embeddings:
            return []

        star_ids = list(embeddings.keys())

        if len(star_ids) == 1:
            return [
                StarClusterAssignment(
                    star_id=star_ids[0],
                    cluster_id=0,
                    x=0.0,
                    y=0.0,
                )
            ]

        # Stack into a matrix
        matrix = np.asarray([np.asarray(embeddings[sid], dtype=np.float64) for sid in star_ids])

        # Cluster (HDBSCAN; noise → cluster_id = -1)
        clusterer = HDBSCAN(min_cluster_size=self._min_cluster_size)
        cluster_labels = clusterer.fit_predict(matrix)

        # Project to 2D
        if matrix.shape[1] >= self._pca_components:
            pca = PCA(n_components=self._pca_components)
            coords = pca.fit_transform(matrix)
        else:
            # Fall back: pad with zeros if input dim < pca_components
            coords = np.zeros((len(star_ids), self._pca_components))
            coords[:, : matrix.shape[1]] = matrix

        # Normalize coords to [-1, 1]
        max_abs = max(abs(coords.min()), abs(coords.max()), 1e-9)
        coords = coords / max_abs

        return [
            StarClusterAssignment(
                star_id=sid,
                cluster_id=int(label),
                x=float(coords[i, 0]),
                y=float(coords[i, 1]),
            )
            for i, (sid, label) in enumerate(zip(star_ids, cluster_labels))
        ]
```

**Step 4: Run tests; confirm 4 PASS.**

```
PYTHONPATH=$PWD pytest tests/test_star_clustering_service.py -v
```

**Step 5: Commit**

```
git add metis_app/services/star_clustering_service.py tests/test_star_clustering_service.py
git commit -m "feat(m24): StarClusteringService — HDBSCAN + PCA layout"
```

---

### Task 1.3: Wire `StarClusteringService` into `WorkspaceOrchestrator` with caching

**Files:**
- Modify: `metis_app/services/workspace_orchestrator.py` (add cluster-fetching method)
- Test: `tests/test_workspace_orchestrator.py` (append)

**Spec:**

The orchestrator method `get_star_clusters(settings) -> list[dict]` should:

1. Fetch all user stars and their attached indexes.
2. For each star, get its content embedding (use index manifests if available; embed star title+description as fallback).
3. Run `StarClusteringService.compute_clusters(embeddings)`.
4. Return `[{"star_id": ..., "cluster_id": ..., "x": ..., "y": ..., "cluster_label": ...}]`.

Caching: store results on the orchestrator instance keyed by a hash of `(sorted star IDs + content fingerprints)`. Invalidate when stars are added/removed or content changes.

**Step 1: Read existing helpers**

```
grep -n "def list_user_stars\|def get_star_embedding\|create_embeddings" metis_app/services/workspace_orchestrator.py | head
```

Find existing user-star access. The settings-store has a `landing_constellation_user_stars` key (per `assistant.py:127`).

**Step 2: Write failing tests:**

```python
def test_get_star_clusters_returns_one_per_star(tmp_path, monkeypatch):
    """Three user stars → three cluster assignments."""
    # Use a real settings store with three mock user stars and mock embeddings
    orch = _make_orchestrator(tmp_path, user_stars=[
        {"id": "star1", "label": "Python perf"},
        {"id": "star2", "label": "Python tooling"},
        {"id": "star3", "label": "Cooking recipes"},
    ])
    result = orch.get_star_clusters(settings={})
    assert len(result) == 3
    assert {item["star_id"] for item in result} == {"star1", "star2", "star3"}
    for item in result:
        assert "cluster_id" in item
        assert "x" in item
        assert "y" in item


def test_get_star_clusters_caches_results(tmp_path, monkeypatch):
    """Calling twice with same star list does not re-run clustering."""
    # Track clustering invocations via a spy
    ...
```

(Match the existing `_make_orchestrator` fixture pattern in the test file. If absent, build inline.)

**Step 3: Implement** the method. Add to `WorkspaceOrchestrator`:

```python
def get_star_clusters(self, settings: dict[str, Any]) -> list[dict[str, Any]]:
    """Compute or fetch cached cluster assignments + 2D positions for user stars."""
    import hashlib
    import json

    user_stars = list(settings.get("landing_constellation_user_stars") or [])
    if not user_stars:
        return []

    # Build embeddings dict (title + notes as embedding input for now;
    # M26 may swap this for full content-embedding lookup from index manifests).
    from metis_app.utils.embedding_providers import create_embeddings
    embedder = create_embeddings(settings)

    texts = [
        f"{s.get('label', '')} {s.get('notes', '')}".strip() or s.get("id", "")
        for s in user_stars
    ]
    star_ids = [s["id"] for s in user_stars]

    # Cache key: hash of (star_ids + texts)
    cache_key = hashlib.sha256(
        json.dumps([star_ids, texts], sort_keys=True).encode()
    ).hexdigest()

    cached = getattr(self, "_cluster_cache", {}).get(cache_key)
    if cached is not None:
        return cached

    raw_embeddings = embedder.embed_documents(texts)
    embeddings_dict = {sid: emb for sid, emb in zip(star_ids, raw_embeddings)}

    from metis_app.services.star_clustering_service import StarClusteringService
    service = StarClusteringService()
    assignments = service.compute_clusters(embeddings_dict)

    result = [
        {
            "star_id": a.star_id,
            "cluster_id": a.cluster_id,
            "x": a.x,
            "y": a.y,
            "cluster_label": a.cluster_label,
        }
        for a in assignments
    ]

    if not hasattr(self, "_cluster_cache"):
        self._cluster_cache = {}
    self._cluster_cache[cache_key] = result
    return result
```

(Match local style — if `WorkspaceOrchestrator` already has an `_caches` pattern, use it. If `__init__` doesn't expose caches, add one.)

**Step 4: Run tests; confirm PASS.**

**Step 5: Commit**

```
git commit -m "feat(m24): WorkspaceOrchestrator.get_star_clusters with cache"
```

---

### Task 1.4: `GET /v1/stars/clusters` Litestar route

**Files:**
- Modify: `metis_app/api_litestar/routes/stars.py` (or wherever star routes live; check first — may need new file)
- Test: `tests/test_api_litestar.py` (append)

**Step 1: Find existing star routes**

```
ls metis_app/api_litestar/routes/ | grep -i star
```

If `stars.py` doesn't exist, the user-star endpoints may live in a different module — confirm before adding.

**Step 2: Write failing test:**

```python
def test_get_star_clusters_route_returns_assignments(client_with_seeded_stars):
    response = client_with_seeded_stars.get("/v1/stars/clusters")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    if body:
        first = body[0]
        assert {"star_id", "cluster_id", "x", "y", "cluster_label"} <= set(first.keys())


def test_get_star_clusters_route_empty_when_no_stars(client):
    response = client.get("/v1/stars/clusters")
    assert response.status_code == 200
    assert response.json() == []
```

**Step 3: Implement.** Add to the star-routes file (or create one):

```python
from litestar import Router, get

from metis_app.services.workspace_orchestrator import WorkspaceOrchestrator
import metis_app.settings_store as _store


@get("/v1/stars/clusters")
def get_star_clusters() -> list[dict]:
    settings = _store.load_settings()
    return WorkspaceOrchestrator().get_star_clusters(settings)


# Add to Router(...) registration if route file already has one
router = Router(path="", route_handlers=[get_star_clusters], tags=["stars"])
```

If a stars router already exists, append `get_star_clusters` to its `route_handlers` list.

Register the router in the main app at `metis_app/api_litestar/app.py` if newly created.

**Step 4: Run tests; confirm PASS.**

**Step 5: Commit**

```
git commit -m "feat(m24): GET /v1/stars/clusters route"
```

---

## Phase 2 — Backend Add recommender (~1 day)

### Task 2.1: `StarRecommenderService` — cosine ranking

**Files:**
- Create: `metis_app/services/star_recommender_service.py`
- Test: `tests/test_star_recommender_service.py` (new)

**Step 1: Write failing tests:**

```python
"""Tests for the star recommender service."""

import numpy as np
from metis_app.services.star_recommender_service import (
    StarRecommenderService,
    StarRecommendation,
)


def test_rank_returns_top_k_by_cosine_similarity():
    """Most similar star ranks first."""
    star_embeddings = {
        "python_perf": np.array([1.0, 0.0, 0.0]),
        "python_tooling": np.array([0.95, 0.31, 0.0]),
        "cooking": np.array([0.0, 0.0, 1.0]),
    }
    star_metadata = {
        "python_perf": {"label": "Python perf", "archetype": "main_sequence"},
        "python_tooling": {"label": "Python tooling", "archetype": "main_sequence"},
        "cooking": {"label": "Cooking recipes", "archetype": "main_sequence"},
    }
    query_embedding = np.array([1.0, 0.05, 0.0])  # very close to python_perf

    service = StarRecommenderService()
    recommendations = service.rank(
        query_embedding=query_embedding,
        star_embeddings=star_embeddings,
        star_metadata=star_metadata,
        top_k=3,
    )

    assert len(recommendations) == 3
    assert recommendations[0].star_id == "python_perf"
    assert recommendations[0].similarity > recommendations[1].similarity
    assert recommendations[2].star_id == "cooking"


def test_rank_content_type_tiebreak():
    """When similarity ties, matching content_type wins."""
    star_embeddings = {
        "doc_a": np.array([1.0, 0.0]),
        "doc_b": np.array([1.0, 0.0]),  # identical fingerprint
    }
    star_metadata = {
        "doc_a": {"archetype": "main_sequence"},  # paper
        "doc_b": {"archetype": "pulsar"},          # podcast
    }
    query_embedding = np.array([1.0, 0.0])

    service = StarRecommenderService()
    recommendations = service.rank(
        query_embedding=query_embedding,
        star_embeddings=star_embeddings,
        star_metadata=star_metadata,
        top_k=2,
        content_type_hint="main_sequence",
    )

    assert recommendations[0].star_id == "doc_a"  # archetype matches hint


def test_rank_handles_empty_star_set():
    service = StarRecommenderService()
    recommendations = service.rank(
        query_embedding=np.array([1.0]),
        star_embeddings={},
        star_metadata={},
        top_k=5,
    )
    assert recommendations == []
```

**Step 2: Run tests; confirm 3 FAIL.**

**Step 3: Implement:**

```python
"""Rank existing stars by similarity to a query embedding for the Add flow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(slots=True)
class StarRecommendation:
    star_id: str
    similarity: float
    label: str = ""
    archetype: str = ""


class StarRecommenderService:
    """Cosine-similarity ranking with content-type tiebreak."""

    def rank(
        self,
        *,
        query_embedding: np.ndarray | list[float],
        star_embeddings: dict[str, np.ndarray | list[float]],
        star_metadata: dict[str, dict[str, Any]],
        top_k: int = 5,
        content_type_hint: str = "",
        project_member_star_ids: set[str] | None = None,  # M25 boost
    ) -> list[StarRecommendation]:
        """Return top-K most-similar stars."""
        if not star_embeddings:
            return []

        q = np.asarray(query_embedding, dtype=np.float64)
        q_norm = np.linalg.norm(q) or 1e-9

        scored: list[tuple[float, str]] = []
        for sid, emb in star_embeddings.items():
            v = np.asarray(emb, dtype=np.float64)
            v_norm = np.linalg.norm(v) or 1e-9
            similarity = float(np.dot(q, v) / (q_norm * v_norm))

            # Content-type tiebreak (small additive boost when hint matches)
            archetype = star_metadata.get(sid, {}).get("archetype", "")
            if content_type_hint and archetype == content_type_hint:
                similarity += 0.001

            # M25 same-Project boost (no-op until M25 wires it in)
            if project_member_star_ids and sid in project_member_star_ids:
                similarity += 0.01

            scored.append((similarity, sid))

        scored.sort(reverse=True)

        return [
            StarRecommendation(
                star_id=sid,
                similarity=sim,
                label=star_metadata.get(sid, {}).get("label", ""),
                archetype=star_metadata.get(sid, {}).get("archetype", ""),
            )
            for sim, sid in scored[:top_k]
        ]
```

**Step 4: Run tests; confirm 3 PASS.**

**Step 5: Commit**

```
git commit -m "feat(m24): StarRecommenderService — cosine + tiebreak"
```

---

### Task 2.2: `POST /v1/stars/recommend` route

**Files:**
- Modify: `metis_app/api_litestar/routes/stars.py` (or the file from Task 1.4)
- Test: `tests/test_api_litestar.py` (append)

**Spec:** Endpoint accepts `{content: str, content_type?: str}`, embeds the content, ranks against existing stars' embeddings, returns the top-5.

**Implementation outline:**

```python
from pydantic import BaseModel


class _RecommendRequest(BaseModel):
    content: str
    content_type: str = ""


@post("/v1/stars/recommend", status_code=200)
def recommend_stars(data: _RecommendRequest) -> dict:
    settings = _store.load_settings()
    return WorkspaceOrchestrator().recommend_stars_for_content(
        content=data.content,
        content_type=data.content_type,
    )
```

The orchestrator wrapper `recommend_stars_for_content`:
1. Embeds the input content via `create_embeddings(settings).embed_query(content)`.
2. Uses cached star embeddings (computed during clustering or refreshed here).
3. Calls `StarRecommenderService.rank(...)`.
4. Returns `{"recommendations": [{star_id, similarity, label, archetype}, ...], "create_new_suggested": bool}`.

`create_new_suggested` is `True` when there are no existing stars, OR when the top match's adjusted similarity is below `_CREATE_NEW_THRESHOLD` (currently `0.5` — the threshold for "no good match"). Concretely:

```python
create_new_suggested = bool(
    not recommendations
    or recommendations[0].similarity < _CREATE_NEW_THRESHOLD
)
```

**Step 1–5:** RED → write `recommend_stars_for_content` orchestrator method + route → GREEN → commit.

```
git commit -m "feat(m24): POST /v1/stars/recommend route + orchestrator wrapper"
```

---

## Phase 3 — Frontend cluster placement (~3 days)

### Task 3.1: `lib/api.ts` client helpers

**Files:**
- Modify: `apps/metis-web/lib/api.ts` (add two helpers)
- Test: `apps/metis-web/lib/__tests__/stars-api.test.ts` (new file)

**Helpers to add:**

```ts
export interface StarClusterAssignment {
  star_id: string;
  cluster_id: number;
  x: number;
  y: number;
  cluster_label: string;
}

export interface StarRecommendation {
  star_id: string;
  similarity: number;
  label: string;
  archetype: string;
}

export interface RecommendResponse {
  recommendations: StarRecommendation[];
  create_new_suggested: boolean;
}

export async function fetchStarClusters(): Promise<StarClusterAssignment[]> {
  const res = await apiFetch(`${await getApiBase()}/v1/stars/clusters`, {});
  if (!res.ok) throw new Error(`fetch star clusters failed: ${res.status}`);
  return res.json();
}

export async function recommendStarsForContent(
  content: string,
  contentType?: string,
): Promise<RecommendResponse> {
  const res = await apiFetch(`${await getApiBase()}/v1/stars/recommend`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content, content_type: contentType ?? "" }),
  });
  if (!res.ok) throw new Error(`recommend stars failed: ${res.status}`);
  return res.json();
}
```

Add 2 vitest cases mirroring the `assistant-api.test.ts` shape.

**Commit:** `feat(m24): api.ts helpers for cluster fetch + star recommend`

---

### Task 3.2: Replace `FACULTY_CONCEPTS` placement with cluster placement

**Files:**
- Modify: `apps/metis-web/app/page.tsx` (heavy — `FACULTY_CONCEPTS` at line 176, `NodeData.concept` references throughout, render functions)
- The biggest single change in M24. This needs careful attention.

**Approach:**

1. **Don't delete `FACULTY_CONCEPTS` immediately.** Add a feature-flag-shaped boolean `USE_CLUSTER_PLACEMENT` (initially `true`) that switches between the old and new path. Deletes the dead path in Task 3.4 once the cluster path proves working.

2. Add `useEffect` to fetch clusters on mount via `fetchStarClusters()`.

3. Build a new placement shape `ClusterPlacement = { star_id: string; x: number; y: number; cluster_id: number }`. Map cluster `(x, y)` (in [-1, 1]) to canvas coordinates.

4. Replace the faculty-anchor placement block in the existing star-positioning code path. The faculty `concept` field on `NodeData` becomes optional (will be removed in Task 3.4).

5. Cluster boundary halo (optional polish): draw a faint coloured halo around each cluster. Cluster colour derived from cluster_id hash.

**Risk:** `app/page.tsx` is the highest-churn file in the repo (per `repowise get_overview` data). Read carefully before editing. Use `git diff` after each substantial edit to spot accidents.

This task is large (~150 lines of edits). Break into sub-commits:
- 3.2a: Fetch + state machinery for clusters (no rendering change yet)
- 3.2b: Conditional placement (flag-gated)
- 3.2c: Cluster halo rendering (optional)

**Commits:**
```
git commit -m "feat(m24): fetch star clusters on home mount"
git commit -m "feat(m24): conditional cluster placement (flag-gated)"
git commit -m "feat(m24): cluster halo rendering"
```

---

### Task 3.3: Migration toast — "Your constellation has been re-laid out by content"

**Files:**
- Modify: `apps/metis-web/app/page.tsx` (toast on first cluster-placement render after migration)
- Modify: `apps/metis-web/lib/local-storage-keys.ts` (add `m24_layout_migrated_v1` key — check existing pattern)

**Spec:** On first mount where `localStorage["m24_layout_migrated_v1"]` is absent AND user stars exist, show a toast: `Your constellation has been re-laid out by content. [Undo for this session]`. Set the localStorage key on render. Undo button restores the previous faculty-anchored layout *for the session only* (re-render with `USE_CLUSTER_PLACEMENT=false`); next visit resumes cluster placement.

**Commit:** `feat(m24): one-time migration toast for cluster placement`

---

### Task 3.4: Remove faculty-anchor code path

**Files:**
- Modify: `apps/metis-web/app/page.tsx` — delete `FACULTY_CONCEPTS`, `FacultyConcept`, `FacultyArtRenderState`, faculty-ring rendering helpers
- Modify: anywhere downstream that references the deleted types

**Spec:** Once cluster placement is verified working (Task 3.2 + 3.3 commits behave correctly), delete the dead faculty-anchor path. Removes ~150-200 lines from `app/page.tsx`.

**Verification:** `pnpm tsc --noEmit` clean; `pnpm vitest run` clean (no test references the deleted types).

**Commit:** `refactor(m24): remove faculty-anchor placement code`

---

## Phase 4 — Frontend Add flow (~3 days)

### Task 4.1: `AddStarDialog` component scaffold

**Files:**
- Create: `apps/metis-web/components/home/add-star-dialog.tsx`
- Create: `apps/metis-web/components/home/__tests__/add-star-dialog.test.tsx`

**Component shape:**

```tsx
"use client";

import { useState } from "react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { recommendStarsForContent, type StarRecommendation } from "@/lib/api";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (decision: AddDecision) => Promise<void>;
}

type AddDecision =
  | { kind: "attach"; star_id: string; content: string; files: File[] }
  | { kind: "create_new"; content: string; files: File[]; suggested_label?: string };

export function AddStarDialog({ open, onOpenChange, onConfirm }: Props) {
  const [step, setStep] = useState<"input" | "suggestions">("input");
  const [content, setContent] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [recommendations, setRecommendations] = useState<StarRecommendation[]>([]);

  async function handleNext() {
    const result = await recommendStarsForContent(content);
    setRecommendations(result.recommendations);
    setStep("suggestions");
  }

  // ... render the input step (file picker + textarea) and suggestions step
  // (top-5 star cards + "Create new star" card side-by-side)
}
```

Tests cover: input → next button → suggestions render; attach action; create-new action.

**Commits:**
- `feat(m24): AddStarDialog scaffold + input step`
- `feat(m24): AddStarDialog suggestions step + 3 vitest cases`

---

### Task 4.2: Wire `AddStarDialog` to the existing `+ ADD` button

**Files:**
- Modify: `apps/metis-web/app/page.tsx` (find `HomeActionFab` and route the gold-FAB click to `AddStarDialog`)

**Spec:** The current `+ ADD` button enters a "tool: add" canvas mode where the user clicks a position. Replace this with: click `+ ADD` → `AddStarDialog` opens immediately. The canvas-position-pick flow is retired.

**Migration note:** The `tool === "add"` branch and `ADD_CANDIDATE_HIT_RADIUS_PX` constants become dead in this task. Mark for cleanup in Phase 6.

**Commit:** `feat(m24): wire +ADD button to new AddStarDialog`

---

### Task 4.3: Backend attach + create-new endpoints (or reuse existing)

**Spec:** Confirm `POST /v1/stars/:id/attach-content` exists for attaching new content to an existing star. If not, add it (it's the existing index-build pipeline scoped to one star). Same for `POST /v1/stars` (create-new) — likely already exists.

Tests: 2 route round-trips.

**Commit:** `feat(m24): wire attach-content + create-new for AddStarDialog flow`

---

## Phase 5 — Frontend Everything chat (~2 days)

### Task 5.1: `EverythingChatSheet` component

**Files:**
- Create: `apps/metis-web/components/home/everything-chat-sheet.tsx`
- Create: `apps/metis-web/components/home/__tests__/everything-chat-sheet.test.tsx`

**Spec:** Slide-over sheet (use existing dialog or sheet primitive) that hosts the existing `ChatPanel` from `apps/metis-web/components/chat/chat-panel.tsx`, with a special `index_id = "_all_stars"` marker that the backend interprets as "RAG over the union of all star indexes."

**Commit:** `feat(m24): EverythingChatSheet hosting ChatPanel against virtual index`

---

### Task 5.2: Central METIS star click handler

**Files:**
- Modify: `apps/metis-web/app/page.tsx` (locate `drawPolarisMetis` ~line 3946; add hit-test in the canvas pointer handler)

**Spec:** Add a hit-test for the central METIS star's canvas position. On pointer-up within hit radius, open `EverythingChatSheet`.

**Commit:** `feat(m24): central METIS star opens EverythingChatSheet on click`

---

### Task 5.3: Backend `_all_stars` virtual retrieval

**Files:**
- Modify: `metis_app/services/workspace_orchestrator.py` (add `run_everything_chat`)
- Modify: `metis_app/services/querying.py` (or wherever RAG retrieval is dispatched) — accept `index_id = "_all_stars"` as a sentinel that triggers union retrieval
- Test: `tests/test_everything_chat.py` (new)

**Spec:** `run_everything_chat(query, settings)` runs RAG against every attached index in parallel, merges results, re-ranks via existing reranker.

**Commit:** `feat(m24): _all_stars virtual retrieval for Everything chat`

---

## Phase 6 — Verify + observatory cleanup (~2 days)

### Task 6.1: Remove `faculty-glyph-panel` from Star Observatory

**Files:**
- Modify: `apps/metis-web/components/constellation/star-observatory-dialog.tsx`
- Search for: `faculty-glyph-panel`, `FacultyGlyph`, `faculty_id` on user-star draft state

**Spec:** Cleanly remove the faculty-glyph picker from the dialog. The Stellar Identity card / archetype picker / learning-route panel survive (per ADR 0006 + ADR 0019 carve-outs).

Update tests in `star-observatory-dialog.test.tsx` to reflect the removed UI.

**Commit:** `refactor(m24): remove faculty-glyph-panel from star observatory`

---

### Task 6.2: Purge faculty references in copy

**Files:**
- Search: `grep -rn "faculty\|Faculty" apps/metis-web/app/setup/page.tsx apps/metis-web/app/settings/page.tsx`
- Modify: any user-facing copy that mentions faculty

**Spec:** Remove or rephrase any user-visible string referencing faculty/sigil. The 11 faculty IDs remain in backend code (M26 cleans those up); the frontend should have zero user-visible faculty references after this task.

**Commit:** `refactor(m24): purge faculty references from user-visible copy`

---

### Task 6.3: Retire 8 named landmark constellations from `star-name-generator.ts`

**Files:**
- Modify: `apps/metis-web/lib/landing-stars/star-name-generator.ts`

**Spec:** Per ADR 0019 and the design doc *Open question 8*, the 8 classical-named landmark constellations (Perseus, Auriga, Draco, Hercules, Gemini, Big Dipper, Lyra, Boötes) are decorative leftovers from the faculty era. Retire their generation. The `kind: "landmark"` branch in `generateStarName` returns null or is removed.

**Confirmation status:** user approved retirement during the 2026-05-03 brainstorm — see ADR 0019 *Open Questions* (resolved). Proceed without further confirmation.

**Commit:** `refactor(m24): retire 8 classical landmark constellation names`

---

### Task 6.4: Remove dead `tool === "add"` canvas-pick path

**Files:**
- Modify: `apps/metis-web/app/page.tsx` (remove `ADD_CANDIDATE_HIT_RADIUS_PX` references, the `tool === "add"` branch, hover-add affordances)

**Commit:** `refactor(m24): remove dead canvas-pick add-star path`

---

### Task 6.5: Browser-preview verification

**Spec:** With the controller running in main repo (Turbopack works there, not in worktree), walk these steps and screenshot any failure:

1. Load `/`. Canvas renders cluster-grouped layout. No 8-faculty ring. No faculty title text.
2. Click `+ ADD`. `AddStarDialog` opens. Pick a file. See top-5 suggestions plus Create-new card. Pick a suggestion. Star animates into its cluster.
3. Click central METIS star. `EverythingChatSheet` slides in. Send a message. See RAG response across all stars.
4. Open Star Observatory on any star. Stellar Identity / archetype / learning-route panels render. No faculty-glyph panel.
5. Reload page. Cluster layout persists.
6. Toggle prefers-reduced-motion. No regressions.
7. With local backend down, page renders without crashing (degraded layout).

If any step fails, write a regression test, fix, re-walk.

---

### Task 6.6: Update design doc + plan stub with landed status

**Files:**
- Modify: `plans/constellation-ia-reset/plan.md` — flip `Status: Ready` → `Status: Landed`
- Modify: `plans/IMPLEMENTATION.md` — flip M24 row to Landed with merge SHA

(Done after PR merges, mirroring M23 Phase 6 pattern.)

---

## Done definition

- All 17 tasks landed in commits.
- Backend pytest green at +6 to +8 new tests.
- Frontend vitest + tsc clean at +6 to +8 new tests.
- Browser-preview QA complete (the 7-step Task 6.5 walk).
- `app/page.tsx` has zero references to `FACULTY_CONCEPTS` / `FacultyConcept` / faculty-anchor placement.
- `AddStarDialog` is the canonical Add-star flow; canvas-pick path is dead code removed.
- Central METIS star opens Everything chat.
- Star Observatory has no faculty-glyph panel.
- IMPLEMENTATION.md M24 row at `Status: Landed` with merge commit + final test counts.
- ADR 0019 referenced from any future faculty-related changes.

## What's explicitly out of scope (do not add)

- **Backend faculty taxonomy removal.** That's M26. `comet_decision_engine`, `autonomous_research_service`, `star_nourishment_gen`, Tribev2 classifier all stay untouched.
- **Projects / drawable lines.** That's M25.
- **Per-Project Forge config.** That's M25.
- **Cluster-label LLM generation.** Default to TF-IDF top-3 keywords for first ship; LLM-summary path is M25 polish.
- **User-renamable cluster labels.** Clusters get auto-generated labels; users name Projects (M25), not clusters.
- **Brand-new chat UI.** Everything chat reuses the existing `ChatPanel` shell.
- **Animations on cluster rebalance.** Stars snap to new positions; smooth re-layout animation is post-M25 polish.
- **Search-by-cluster filtering.** No cluster-based filter in the catalogue search (M12 territory).
