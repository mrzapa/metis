---
Milestone: Tribev2 homological scaffold (M10)
Status: Landed
Claim: Landed (`cc3923f` + `6fa1ff2`, 2026-04-05)
Last updated: 2026-04-22 by claude/reconcile-trive-v2-homological-scaffold (audit pass — all 6 steps shipped)
Vision pillar: Companion + Cosmos
---

# TriveV2 — Homological Scaffold: The Living Brain

> **Status: Landed — all 6 steps shipped across two commits.**
> The sections below are kept as the historical design spec; see the pointer
> table for the canonical live code.
>
> | Step | Landed at | Shipped in |
> |---|---|---|
> | 1 — Edge weight foundation | `metis_app/models/brain_graph.py` (`BrainEdge.weight`, `compute_edge_weights()` called at end of `build_from_indexes_and_sessions`) | `cc3923f` (2026-03-28) |
> | 2 — Topological scaffold service | `metis_app/services/topo_scaffold.py` (`ScaffoldResult` dataclass with `betti_0/1`, `h1_pairs`, `scaffold_edges`, `summary`; `compute_scaffold()`; `scaffold_to_payload()`) | `cc3923f` (2026-03-28) |
> | 3 — `GET /v1/brain/scaffold` | `metis_app/api/app.py` (FastAPI) and `metis_app/api_litestar/routes/core.py` (Litestar) | `6fa1ff2` (2026-04-05) |
> | 4 — Frontend visual encoding | `apps/metis-web/lib/api.ts::fetchBrainScaffold`; `components/brain/brain-graph-view-model.ts` (`isScaffoldEdge`, `persistenceWeight`); `components/brain/brain-graph-3d.tsx` (`THREE.TorusGeometry` H₁ rings + scaffold-edge glow) | `6fa1ff2` (2026-04-05) |
> | 5 — Companion topology awareness | `metis_app/utils/feature_flags.py::FeatureFlag.TOPO_SCAFFOLD_ENABLED` (default True); `metis_app/services/assistant_companion.py` (scaffold lines in both reflection paths) | `6fa1ff2` (2026-04-05) |
> | 6 — 2D constellation scaffold links | `apps/metis-web/app/page.tsx` (`scaffoldEdgesRef` fetched from `/v1/brain/scaffold`, scaffold-driven star-to-star rendering); `apps/metis-web/lib/constellation-types.ts` (`scaffoldWeights` on `UserStar`) | `6fa1ff2` (2026-04-05) |
>
> Follow-on topology work has continued organically beyond this plan — e.g.
> `b05181a` added topology-aware nourishment events that integrate the
> scaffold signal into a broader nourishment state.
>
> Note: `USER_STAR_LINK_MAX_DISTANCE` remains in `app/page.tsx` but now drives
> only the interactive drag-to-link anchor proximity check
> (`getSelectedLinkAnchor`), not the automatic star-to-star rendering the
> plan targeted — those are now scaffold-driven.

**Branch:** `feature/trive-v2-homological-scaffold`
**Description:** Apply persistent homology (Petri et al. 2014) to the METIS knowledge graph so the companion can perceive and reason about the topological structure of its own mind.

## Goal

Drawing from *Homological scaffolds of brain functional networks* (Petri et al. 2014), we treat the METIS BrainGraph as a weighted functional network and compute its persistent homology. The resulting homological scaffold — edges weighted by how often they appear in long-lived topological cycles — reveals which knowledge connections act as **integration hubs**, exactly as the paper found persistent cross-modular connections in the psilocybin brain condition. This gives the METIS companion (TrIVeV2) a neurologically-grounded self-model: it can see its own brain topology, identify integration loops between faculties, and surface that awareness in reflections — making it feel less like a chatbot and more like a thinking entity with lived cognitive structure.

## Paper-to-METIS Mapping

| Paper concept | METIS equivalent |
|---|---|
| fMRI partial-correlation matrix | `BrainGraph` weighted adjacency (session co-use + BrainLink confidence) |
| Filtration over descending edge weights | Vietoris-Rips filtration on the knowledge graph |
| H₁ generators (topological loops) | Knowledge integration cycles — nodes that bridge faculties |
| Persistence scaffold (edges weighted by cycle lifetime) | `ScaffoldResult.scaffold_edges` — highlighted as hub connections |
| Frequency scaffold (edges in many cycles) | Frequency-weighted scaffold edges for visual emphasis |
| Cross-modular persistent connections (psilocybin condition) | More sessions/memories → stronger, more persistent integration loops |
| Community structure | TrIVe faculty communities — how integrated vs siloed the companion's knowledge is |

## Decisions

- **H₁ ring visibility**: Always-on glowing topology rings in the 3D brain view. Persistent loops are a core visual metaphor — they should always be present and scale with filtration persistence.
- **2D constellation**: In scope as Step 6. Replacing proximity-based star links with scaffold-edge links gives the home screen semantic meaning.
- **gudhi dependency**: Pure-Python only. Works for typical graph sizes (<200 nodes). An optional `gudhi` fast-path is noted in comments but not added as a dependency.

## Implementation Steps

### Step 1: Edge Weight Foundation
**Files:**
- `metis_app/models/brain_graph.py`
- `metis_app/api/app.py`

**What:**
Add `weight: float = 1.0` to `BrainEdge`. Add `BrainGraph.compute_edge_weights()` using: (1) session co-use count for `uses_index`/`category_member` edges, and (2) `AssistantBrainLink.confidence` for `learned_from_session`/`about_index` edges. Call `compute_edge_weights()` at the end of `build_from_indexes_and_sessions()`. Expose `weight` in the `/v1/brain/graph` JSON serialization.

**Testing:** Unit test verifies weights > 1.0 for co-used edges; API test confirms `weight` appears in every edge of the response.

---

### Step 2: Topological Scaffold Service
**Files:**
- `metis_app/services/topo_scaffold.py` *(new)*

**What:**
Pure-Python persistent homology engine on `BrainGraph`. Mirrors Petri et al. §3–4:
1. Sort edges descending by weight (strong edges = low filtration value = included first).
2. Sweep filtration; maintain connected components via union-find for H₀ persistence pairs.
3. Detect H₁ generators via cycle space: each non-spanning-tree edge at step k closes a fundamental cycle; birth = k, death = step when all cycle nodes merge.
4. Build persistence scaffold (edges weighted by sum of cycle persistence) and frequency scaffold (edges weighted by cycle count).
5. Return `ScaffoldResult` dataclass: `betti_0`, `betti_1`, `h0_pairs`, `h1_pairs`, `scaffold_edges`, and human-readable `summary` string.

**Testing:** Unit test on 5-node graph with known 4-cycle verifies exactly 1 H₁ generator with correct birth/death. Test `summary` is non-empty.

---

### Step 3: Scaffold API Endpoint
**Files:**
- `metis_app/api/app.py`

**What:**
Add `GET /v1/brain/scaffold` alongside `/v1/brain/graph`. Builds BrainGraph, calls `compute_edge_weights()`, runs `compute_scaffold()`, returns JSON: `betti_0`, `betti_1`, `h0_pairs`, `h1_pairs`, `scaffold_edges` (list of `[source_id, target_id, persistence_weight, frequency_weight]`), `summary`. 30-second in-process cache keyed on settings hash.

**Testing:** Integration test verifies response schema and `betti_0 >= 1`.

---

### Step 4: Frontend Visual Encoding
**Files:**
- `apps/metis-web/lib/api.ts`
- `apps/metis-web/components/brain/brain-graph-view-model.ts`
- `apps/metis-web/components/brain/brain-graph-3d.tsx`

**What:**
**(a)** Add `weight: number` to `BrainEdge` TypeScript type and `BrainScaffoldResult` type in `api.ts`.
**(b)** In `brain-graph-view-model.ts`: map `weight` → `linkWidth` (`sqrt(weight)` scaled) and `linkOpacity` (base + weight factor); add `isScaffoldEdge: boolean` and `persistenceWeight: number` to `BrainSceneLink`.
**(c)** In `brain-graph-3d.tsx`: after force simulation converges, fetch `/v1/brain/scaffold` and render one `THREE.TorusGeometry` ring per H₁ persistence pair — centered at member-node centroid, radius from bounding circle, emissive glow scaled by `death - birth` persistence, colored by dominant faculty of member nodes. Scaffold edges render with elevated `linkWidth` and a distinct glow.

**Testing:** Visual smoke test confirms link widths vary and rings appear when `betti_1 > 0`. `pnpm typecheck` passes.

---

### Step 5: Companion Topology Awareness
**Files:**
- `metis_app/utils/feature_flags.py`
- `metis_app/services/assistant_companion.py`

**What:**
Add `TOPO_SCAFFOLD_ENABLED: bool = True` to `feature_flags.py`. In `AssistantCompanionService._generate_reflection()`, when the flag is enabled, call `topo_scaffold.compute_scaffold()` after building the brain graph and format 2–3 topology bullet lines (Betti numbers + scaffold summary). Append to `context_lines` before calling `build_assistant_reflection_prompt()`. No signature changes needed — the existing `context_lines` parameter absorbs the topology context cleanly.

Example companion output enabled by this: *"I notice a persistent integration loop between your research and memory faculties — these knowledge domains are deeply cross-linked in my current scaffold."*

**Testing:** Mock `compute_scaffold()` and verify topology Betti numbers appear in the resulting reflection prompt. Integration test triggers `reflect()` and confirms `AssistantMemoryEntry.details` references topology.

---

### Step 6: 2D Constellation Semantic Wiring
**Files:**
- `apps/metis-web/app/page.tsx`
- `apps/metis-web/lib/constellation-types.ts`

**What:**
Replace `USER_STAR_LINK_MAX_DISTANCE` proximity-based links with scaffold-edge links fetched from `/v1/brain/scaffold`. Stars connected by scaffold edges are those whose underlying index/session nodes appear together in H₁ generators. Add `scaffoldWeight: number` to the `UserStar` connection type and render scaffold connections with weight-scaled opacity, giving the home constellation semantic meaning — stars that share deep knowledge loops visibly pulse with stronger connections.

**Testing:** Confirm on multi-session workspace that star links now reflect index co-use rather than canvas proximity. `pnpm typecheck` passes.

---

## Architecture Diagram

```
BrainGraph.build_from_indexes_and_sessions()
    └─ .compute_edge_weights()                   ← Step 1
         ↓
topo_scaffold.compute_scaffold(graph)            ← Step 2
    → ScaffoldResult {
        betti_0, betti_1,
        h0_pairs, h1_pairs,
        scaffold_edges,
        summary
      }
      ↓                              ↓
GET /v1/brain/scaffold          assistant_companion._generate_reflection()
(Step 3)                            └─ context_lines += topology_lines  (Step 5)
    ↓
brain-graph-3d.tsx
    ├─ weight → linkWidth/opacity    (Step 4a/b)
    ├─ scaffold edges → glow         (Step 4b)
    └─ h1_pairs → TorusGeometry rings (Step 4c)

app/page.tsx
    └─ scaffold_edges → star links   (Step 6)
```

## Files Changed

| File | Action | Step |
|------|--------|------|
| `metis_app/models/brain_graph.py` | Edit — `weight` on `BrainEdge`, `compute_edge_weights()` | 1 |
| `metis_app/api/app.py` | Edit — expose weight; add scaffold endpoint | 1, 3 |
| `metis_app/services/topo_scaffold.py` | **Create** — persistent homology engine | 2 |
| `metis_app/utils/feature_flags.py` | Edit — `TOPO_SCAFFOLD_ENABLED` flag | 5 |
| `metis_app/services/assistant_companion.py` | Edit — scaffold call in `_generate_reflection()` | 5 |
| `apps/metis-web/lib/api.ts` | Edit — `weight` on `BrainEdge`; `BrainScaffoldResult` type | 4 |
| `apps/metis-web/components/brain/brain-graph-view-model.ts` | Edit — weight → link visual encoding | 4 |
| `apps/metis-web/components/brain/brain-graph-3d.tsx` | Edit — H₁ ring overlays + scaffold glow | 4 |
| `apps/metis-web/app/page.tsx` | Edit — scaffold-edge star links | 6 |
| `apps/metis-web/lib/constellation-types.ts` | Edit — `scaffoldWeight` on connection type | 6 |
