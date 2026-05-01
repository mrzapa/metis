"""Tests for the M14 Forge gallery routes (Phases 1 + 2a)."""

from __future__ import annotations

import pathlib
from typing import Any
from unittest.mock import patch

import pytest
from litestar.testing import TestClient

from metis_app.api_litestar import create_app
from metis_app.services.forge_registry import (
    find_missing_setting_keys,
    get_descriptor,
    get_registry,
)


def _client() -> TestClient:
    return TestClient(app=create_app())


def test_list_techniques_returns_registry_inventory() -> None:
    with _client() as client:
        resp = client.get("/v1/forge/techniques")
        assert resp.status_code == 200
        payload = resp.json()

    assert payload["phase"] == 6
    techniques = payload["techniques"]
    assert len(techniques) == len(get_registry())

    ids = {item["id"] for item in techniques}
    # Spot-check the marquee techniques the UI promises in the
    # harvest inventory (plans/the-forge/plan.md).
    for required in (
        "iterrag-convergence",
        "swarm-personas",
        "heretic-abliteration",
        "tribev2-multimodal",
        "timesfm-forecasting",
        "news-comets",
        "reranker",
        "hybrid-search",
        "sub-query-expansion",
    ):
        assert required in ids, f"missing technique: {required}"


def test_list_techniques_response_shape() -> None:
    with _client() as client:
        resp = client.get("/v1/forge/techniques")
        techniques = resp.json()["techniques"]

    required_fields = {
        "id",
        "name",
        "description",
        "pillar",
        "enabled",
        "setting_keys",
        "engine_symbols",
        "recent_uses",
        # Phase 3 additions — every entry exposes its toggle posture
        # and (when toggleable) the settings overrides the frontend
        # writes through ``POST /v1/settings``.
        "toggleable",
        "enable_overrides",
        "disable_overrides",
        # Phase 3b additions — runtime readiness probe output. Every
        # entry reports a ``runtime_status`` (default "ready") plus a
        # blockers list and an optional CTA descriptor for the
        # gallery's "Get ready" affordance.
        "runtime_status",
        "runtime_blockers",
        "runtime_cta_kind",
        "runtime_cta_target",
    }
    for entry in techniques:
        assert required_fields <= entry.keys()
        assert isinstance(entry["id"], str) and entry["id"]
        assert isinstance(entry["name"], str) and entry["name"]
        assert isinstance(entry["description"], str) and entry["description"]
        assert entry["pillar"] in {"cosmos", "companion", "cortex", "cross-cutting"}
        assert isinstance(entry["enabled"], bool)
        assert isinstance(entry["setting_keys"], list)
        assert all(isinstance(key, str) for key in entry["setting_keys"])
        assert isinstance(entry["engine_symbols"], list)
        # Phase 6 — trace integration. ``recent_uses`` is reserved for
        # the per-technique detail endpoint; the list response keeps
        # the field as an empty list to preserve the existing shape.
        # The card-face counter rides on ``weekly_use_count`` instead.
        assert entry["recent_uses"] == []
        assert "weekly_use_count" in entry
        assert isinstance(entry["weekly_use_count"], int)
        assert entry["weekly_use_count"] >= 0
        assert isinstance(entry["toggleable"], bool)
        if entry["toggleable"]:
            assert isinstance(entry["enable_overrides"], dict)
            assert isinstance(entry["disable_overrides"], dict)
            assert entry["enable_overrides"], "toggleable technique must declare enable_overrides"
            assert entry["disable_overrides"], "toggleable technique must declare disable_overrides"
        else:
            assert entry["enable_overrides"] is None
            assert entry["disable_overrides"] is None
        assert entry["runtime_status"] in {"ready", "blocked"}
        assert isinstance(entry["runtime_blockers"], list)
        assert all(isinstance(b, str) for b in entry["runtime_blockers"])
        if entry["runtime_status"] == "ready":
            assert entry["runtime_blockers"] == []
        else:
            assert entry["runtime_blockers"], "blocked status must list at least one blocker"
        if entry["runtime_cta_kind"] is not None:
            assert entry["runtime_cta_kind"] in {"install_heretic", "switch_chat_path"}


def test_toggleable_overrides_reference_real_setting_keys() -> None:
    """Every override key must exist in default_settings.json — same
    invariant as the descriptor's ``setting_keys``, applied to the
    overrides too. Drift here would land the frontend writing a key
    the engine ignores.
    """
    import metis_app.settings_store as settings_store

    settings = settings_store.load_settings()

    with _client() as client:
        techniques = client.get("/v1/forge/techniques").json()["techniques"]

    for entry in techniques:
        if not entry["toggleable"]:
            continue
        for payload_label, payload in (
            ("enable_overrides", entry["enable_overrides"]),
            ("disable_overrides", entry["disable_overrides"]),
        ):
            for key in payload.keys():
                assert key in settings, (
                    f"{entry['id']!r} {payload_label} references missing "
                    f"setting key {key!r}"
                )


def test_overrides_flip_the_descriptor_predicate() -> None:
    """Self-check: applying ``enable_overrides`` to the default
    settings makes ``is_enabled`` return ``True``; applying
    ``disable_overrides`` makes it return ``False``. Without this,
    the frontend toggle could silently land settings the predicate
    interprets the wrong way.
    """
    import metis_app.settings_store as settings_store

    base = dict(settings_store.load_settings())
    # Stub the Heretic CLI check globally for this test so the
    # predicate behaves like CLI-on-PATH. The dedicated probe tests
    # (``test_heretic_probe_*``) cover the missing-CLI branch.
    with patch(
        "metis_app.services.heretic_service.is_heretic_available",
        return_value=True,
    ):
        for descriptor in get_registry():
            if not descriptor.toggleable:
                continue
            on = dict(base)
            on.update(descriptor.enable_overrides or {})
            assert descriptor.is_enabled(on) is True, (
                f"{descriptor.id!r} enable_overrides did not flip the predicate ON"
            )
            off = dict(base)
            off.update(descriptor.disable_overrides or {})
            assert descriptor.is_enabled(off) is False, (
                f"{descriptor.id!r} disable_overrides did not flip the predicate OFF"
            )


def test_disable_overrides_clear_every_predicate_input_for_or_predicates() -> None:
    """Regression test for the semantic-chunking OR-predicate bug
    (Codex P1 review on PR #579): when a predicate ORs multiple
    settings keys, ``disable_overrides`` must zero every one of them.

    The earlier ``test_overrides_flip_the_descriptor_predicate``
    starts from default settings, where the predicate's "companion
    keys" happen to be off, so it would let a partial disable through
    silently. This test seeds a *maximally-on* base — every key the
    descriptor declares in ``setting_keys`` is set to a value that
    would individually satisfy the predicate — and then asserts the
    disable payload still drives ``is_enabled`` to ``False``. Any
    future OR-predicate descriptor that ships a one-knob disable
    will trip here.
    """
    import metis_app.settings_store as settings_store

    truthy_seed = settings_store.load_settings()
    # Same Heretic-CLI stub as the simpler predicate test above —
    # the maximally-on seed includes a heretic_output_dir, but the
    # predicate also requires the CLI on PATH. The dedicated
    # ``test_heretic_probe_*`` cases cover the runtime-only branch.
    with patch(
        "metis_app.services.heretic_service.is_heretic_available",
        return_value=True,
    ):
        for descriptor in get_registry():
            if not descriptor.toggleable:
                continue
            # Build a settings dict where every key the predicate could
            # read has been explicitly set to a value that, on its own,
            # makes the predicate read True.
            seed = dict(truthy_seed)
            for key in descriptor.setting_keys:
                seed[key] = _maximally_on_value_for(key)
            # Sanity: the seed should make the predicate ON.
            assert descriptor.is_enabled(seed) is True, (
                f"test seed did not make {descriptor.id!r} read ON; "
                "_maximally_on_value_for likely needs a new branch for "
                f"{descriptor.setting_keys!r}"
            )
            off = dict(seed)
            off.update(descriptor.disable_overrides or {})
            assert descriptor.is_enabled(off) is False, (
                f"{descriptor.id!r} disable_overrides leaves the "
                "predicate reading ON when other companion keys had been "
                "previously enabled — the disable payload must clear every "
                "input the predicate ORs over"
            )


def test_absorb_route_returns_arxiv_proposal_payload() -> None:
    """End-to-end through the route: an arxiv URL is fetched (mocked),
    cross-referenced, and (with a mocked LLM) returns a proposal."""
    fake_atom = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2501.12345v1</id>
    <title>Cross-encoder reranking that matters</title>
    <summary>We propose a sparse cross-encoder reranking method that
combines BM25 hits with a neural reranking pass.</summary>
  </entry>
</feed>
"""
    fake_proposal = (
        '{"name": "Sparse Cross-Encoder Reranking",'
        ' "claim": "Reranks BM25 hits with a small cross-encoder.",'
        ' "pillar_guess": "cortex",'
        ' "implementation_sketch": "Score top-k hits with a cross-encoder."}'
    )

    class _FakeLLM:
        def invoke(self, _msgs: object) -> object:
            return type("R", (), {"content": fake_proposal})()

    with (
        patch(
            "metis_app.services.forge_absorb._safe_get_bytes",
            return_value=fake_atom,
        ),
        patch(
            "metis_app.api_litestar.routes.forge._build_llm_for_absorb",
            return_value=_FakeLLM(),
        ),
        _client() as client,
    ):
        resp = client.post(
            "/v1/forge/absorb",
            json={"url": "https://arxiv.org/abs/2501.12345"},
        )
        assert resp.status_code == 200
        body = resp.json()

    assert body["source_kind"] == "arxiv"
    assert "Cross-encoder reranking" in body["title"]
    assert body["proposal"]["name"] == "Sparse Cross-Encoder Reranking"
    # Existing-registry cross-reference: the reranker descriptor
    # surfaces because the abstract mentions "reranking" / "BM25".
    assert any(m["id"] == "reranker" for m in body["matches"])


def test_absorb_route_rejects_missing_url() -> None:
    """A request with no ``url`` field is a 4xx (Litestar surfaces a
    ``ValidationException`` as 400; the absorb route raises one when
    ``url`` is missing). The exact code is 400 — anything else means
    the route silently accepted a request it shouldn't have."""
    with _client() as client:
        resp = client.post("/v1/forge/absorb", json={})
    assert resp.status_code == 400


def test_absorb_route_returns_error_payload_for_unsupported_url() -> None:
    """Non-arxiv URLs return a 200 with ``source_kind="unsupported"``
    so the gallery can render a "Phase 4a is arxiv-only" message
    without treating the response as an error."""
    with _client() as client:
        resp = client.post(
            "/v1/forge/absorb",
            json={"url": "https://example.com/blog/post"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["source_kind"] == "unsupported"
    assert body["proposal"] is None


def test_absorb_route_persists_successful_proposals(tmp_path) -> None:
    """When the LLM returns a proposal, the route saves it to
    ``forge_proposals.db`` and includes the new row's ``proposal_id``
    in the response so the frontend can mark it pending in the
    review pane immediately."""
    from metis_app.services import forge_proposals

    fake_atom = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2501.12345v1</id>
    <title>Cross-encoder reranking that matters</title>
    <summary>We propose a sparse cross-encoder reranking method.</summary>
  </entry>
</feed>
"""
    fake_proposal = (
        '{"name": "Sparse Cross-Encoder Reranking",'
        ' "claim": "Reranks BM25 hits with a small cross-encoder.",'
        ' "pillar_guess": "cortex",'
        ' "implementation_sketch": "Score top-k hits with a CE model."}'
    )

    class _FakeLLM:
        def invoke(self, _msgs: object) -> object:
            return type("R", (), {"content": fake_proposal})()

    db_path = tmp_path / "forge_proposals.db"

    with (
        patch(
            "metis_app.services.forge_absorb._safe_get_bytes",
            return_value=fake_atom,
        ),
        patch(
            "metis_app.api_litestar.routes.forge._build_llm_for_absorb",
            return_value=_FakeLLM(),
        ),
        patch(
            "metis_app.api_litestar.routes.forge._proposal_db_path",
            return_value=db_path,
        ),
        _client() as client,
    ):
        resp = client.post(
            "/v1/forge/absorb",
            json={"url": "https://arxiv.org/abs/2501.12345"},
        )
        body = resp.json()

    assert body["proposal_id"] is not None
    rows = forge_proposals.list_proposals(db_path=db_path)
    assert len(rows) == 1
    assert rows[0]["status"] == "pending"
    assert rows[0]["proposal_name"] == "Sparse Cross-Encoder Reranking"


def test_list_proposals_route_returns_pending_only_by_default(
    tmp_path,
) -> None:
    """GET /v1/forge/proposals defaults to pending so the review pane
    doesn't show old accepted/rejected rows."""
    from metis_app.services.forge_proposals import (
        mark_accepted,
        save_proposal,
    )

    db_path = tmp_path / "forge_proposals.db"
    save_proposal(  # type: ignore[arg-type]
        db_path=db_path,
        source_url="https://arxiv.org/abs/2501.00001",
        arxiv_id="2501.00001",
        title="Pending Paper",
        summary="",
        proposal_name="Pending",
        proposal_claim="A pending claim.",
        proposal_pillar="cortex",
        proposal_sketch="A pending sketch.",
    )
    accepted_id = save_proposal(  # type: ignore[arg-type]
        db_path=db_path,
        source_url="https://arxiv.org/abs/2501.00002",
        arxiv_id="2501.00002",
        title="Accepted Paper",
        summary="",
        proposal_name="Accepted",
        proposal_claim="An accepted claim.",
        proposal_pillar="cortex",
        proposal_sketch="An accepted sketch.",
    )
    mark_accepted(db_path=db_path, proposal_id=accepted_id, skill_path="skills/x/SKILL.md")

    with (
        patch(
            "metis_app.api_litestar.routes.forge._proposal_db_path",
            return_value=db_path,
        ),
        _client() as client,
    ):
        resp = client.get("/v1/forge/proposals")
        body = resp.json()

    assert resp.status_code == 200
    assert len(body["proposals"]) == 1
    assert body["proposals"][0]["proposal_name"] == "Pending"


def test_accept_proposal_route_writes_skill_draft_and_marks_accepted(
    tmp_path,
) -> None:
    """POST /v1/forge/proposals/<id>/accept drafts the skill md file
    and updates the row's status. The response carries the relative
    ``skill_path`` so the frontend can deep-link the user to the
    file they should edit."""
    from metis_app.services.forge_proposals import (
        get_proposal,
        save_proposal,
    )

    db_path = tmp_path / "forge_proposals.db"
    skills_root = tmp_path / "skills"
    proposal_id = save_proposal(  # type: ignore[arg-type]
        db_path=db_path,
        source_url="https://arxiv.org/abs/2501.00001",
        arxiv_id="2501.00001",
        title="Pending Paper",
        summary="",
        proposal_name="Sparse Reranker",
        proposal_claim="Reranks hits.",
        proposal_pillar="cortex",
        proposal_sketch="Score top-k hits.",
    )

    with (
        patch(
            "metis_app.api_litestar.routes.forge._proposal_db_path",
            return_value=db_path,
        ),
        patch(
            "metis_app.api_litestar.routes.forge._skills_root_for_drafts",
            return_value=skills_root,
        ),
        _client() as client,
    ):
        resp = client.post(f"/v1/forge/proposals/{proposal_id}/accept", json={})
        body = resp.json()

    assert resp.status_code == 200
    assert body["status"] == "accepted"
    assert body["skill_path"].endswith("SKILL.md")
    row = get_proposal(db_path=db_path, proposal_id=proposal_id)
    assert row is not None
    assert row["status"] == "accepted"
    skill_file = skills_root / "sparse-reranker" / "SKILL.md"
    assert skill_file.exists()


def test_accept_proposal_route_returns_409_if_skill_draft_exists(
    tmp_path,
) -> None:
    """A second accept on the same proposal slug must not silently
    clobber the existing draft. The route returns a 409."""
    from metis_app.services.forge_proposals import save_proposal

    db_path = tmp_path / "forge_proposals.db"
    skills_root = tmp_path / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)
    # Pre-create the skill dir with a SKILL.md so the writer trips.
    (skills_root / "sparse-reranker").mkdir()
    (skills_root / "sparse-reranker" / "SKILL.md").write_text("existing", encoding="utf-8")

    proposal_id = save_proposal(  # type: ignore[arg-type]
        db_path=db_path,
        source_url="https://arxiv.org/abs/2501.00001",
        arxiv_id="2501.00001",
        title="Pending Paper",
        summary="",
        proposal_name="Sparse Reranker",
        proposal_claim="Reranks hits.",
        proposal_pillar="cortex",
        proposal_sketch="Score top-k hits.",
    )

    with (
        patch(
            "metis_app.api_litestar.routes.forge._proposal_db_path",
            return_value=db_path,
        ),
        patch(
            "metis_app.api_litestar.routes.forge._skills_root_for_drafts",
            return_value=skills_root,
        ),
        _client() as client,
    ):
        resp = client.post(f"/v1/forge/proposals/{proposal_id}/accept", json={})

    assert resp.status_code == 409


def test_reject_proposal_route_marks_rejected(tmp_path) -> None:
    from metis_app.services.forge_proposals import (
        get_proposal,
        save_proposal,
    )

    db_path = tmp_path / "forge_proposals.db"
    proposal_id = save_proposal(  # type: ignore[arg-type]
        db_path=db_path,
        source_url="https://arxiv.org/abs/2501.00001",
        arxiv_id="2501.00001",
        title="Pending Paper",
        summary="",
        proposal_name="Sparse Reranker",
        proposal_claim="Reranks hits.",
        proposal_pillar="cortex",
        proposal_sketch="Score top-k hits.",
    )

    with (
        patch(
            "metis_app.api_litestar.routes.forge._proposal_db_path",
            return_value=db_path,
        ),
        _client() as client,
    ):
        resp = client.post(f"/v1/forge/proposals/{proposal_id}/reject", json={})

    assert resp.status_code == 200
    row = get_proposal(db_path=db_path, proposal_id=proposal_id)
    assert row is not None
    assert row["status"] == "rejected"


def test_accept_proposal_route_returns_404_for_unknown_id(tmp_path) -> None:
    db_path = tmp_path / "forge_proposals.db"
    skills_root = tmp_path / "skills"

    with (
        patch(
            "metis_app.api_litestar.routes.forge._proposal_db_path",
            return_value=db_path,
        ),
        patch(
            "metis_app.api_litestar.routes.forge._skills_root_for_drafts",
            return_value=skills_root,
        ),
        _client() as client,
    ):
        resp = client.post("/v1/forge/proposals/9999/accept", json={})

    assert resp.status_code == 404


def test_absorb_route_rejects_non_http_scheme() -> None:
    """SSRF guard at the route level: ``file://``, ``ftp://`` and the
    empty string come back as ``source_kind="error"`` without
    touching the network."""
    with _client() as client:
        resp = client.post(
            "/v1/forge/absorb",
            json={"url": "file:///etc/passwd"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["source_kind"] == "error"


def test_list_candidates_route_returns_pending_candidates(tmp_path) -> None:
    """``GET /v1/forge/candidates`` exposes the seedling's pending
    skill candidates with default-slug + trace-excerpt fields the
    review pane needs."""
    from metis_app.services.skill_repository import SkillRepository

    candidates_db = tmp_path / "skill_candidates.db"
    repo = SkillRepository(skills_dir=tmp_path / "skills")
    repo.save_candidate(
        db_path=candidates_db,
        query_text="How does reranking work?",
        trace_json='{"iterations": 3}',
        convergence_score=0.97,
    )

    with (
        patch(
            "metis_app.api_litestar.routes.forge._candidates_db_path",
            return_value=candidates_db,
        ),
        _client() as client,
    ):
        resp = client.get("/v1/forge/candidates")
        body = resp.json()

    assert resp.status_code == 200
    assert len(body["candidates"]) == 1
    row = body["candidates"][0]
    assert row["query_text"] == "How does reranking work?"
    assert row["default_slug"] == "how-does-reranking-work"
    assert "iterations" in row["trace_excerpt"]


def test_accept_candidate_route_writes_skill_and_flips_settings(
    tmp_path,
) -> None:
    """The route drafts a SKILL.md, calls the settings writer, and
    marks the candidate promoted. Settings are written through the
    existing ``save_settings`` helper, so we patch it to capture the
    payload."""
    from metis_app.services.skill_repository import SkillRepository

    candidates_db = tmp_path / "skill_candidates.db"
    skills_root = tmp_path / "skills"
    repo = SkillRepository(skills_dir=skills_root)
    repo.save_candidate(
        db_path=candidates_db,
        query_text="What is BM25?",
        trace_json="{}",
        convergence_score=0.95,
    )

    captured: list[dict[str, Any]] = []

    def fake_save_settings(payload: dict[str, Any]) -> dict[str, Any]:
        captured.append(payload)
        return payload

    with (
        patch(
            "metis_app.api_litestar.routes.forge._candidates_db_path",
            return_value=candidates_db,
        ),
        patch(
            "metis_app.api_litestar.routes.forge._skills_root_for_drafts",
            return_value=skills_root,
        ),
        patch(
            "metis_app.api_litestar.routes.forge._save_settings",
            side_effect=fake_save_settings,
        ),
        _client() as client,
    ):
        resp = client.post("/v1/forge/candidates/1/accept", json={})

    assert resp.status_code == 200
    body = resp.json()
    assert body["slug"] == "what-is-bm25"
    assert body["skill_path"].endswith("SKILL.md")
    assert pathlib.Path(body["skill_path"]).exists()
    assert captured, "expected settings_writer to be invoked"
    assert captured[0]["skills"]["enabled"]["what-is-bm25"] is True


def test_accept_candidate_route_passes_slug_override(tmp_path) -> None:
    from metis_app.services.skill_repository import SkillRepository

    candidates_db = tmp_path / "skill_candidates.db"
    skills_root = tmp_path / "skills"
    repo = SkillRepository(skills_dir=skills_root)
    repo.save_candidate(
        db_path=candidates_db,
        query_text="Whatever",
        trace_json="{}",
        convergence_score=0.95,
    )

    with (
        patch(
            "metis_app.api_litestar.routes.forge._candidates_db_path",
            return_value=candidates_db,
        ),
        patch(
            "metis_app.api_litestar.routes.forge._skills_root_for_drafts",
            return_value=skills_root,
        ),
        patch(
            "metis_app.api_litestar.routes.forge._save_settings",
            side_effect=lambda payload: payload,
        ),
        _client() as client,
    ):
        resp = client.post(
            "/v1/forge/candidates/1/accept",
            json={"slug": "Custom Reranker"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["slug"] == "custom-reranker"


def test_accept_candidate_route_returns_404_for_unknown_id(tmp_path) -> None:
    candidates_db = tmp_path / "skill_candidates.db"
    skills_root = tmp_path / "skills"
    with (
        patch(
            "metis_app.api_litestar.routes.forge._candidates_db_path",
            return_value=candidates_db,
        ),
        patch(
            "metis_app.api_litestar.routes.forge._skills_root_for_drafts",
            return_value=skills_root,
        ),
        patch(
            "metis_app.api_litestar.routes.forge._save_settings",
            side_effect=lambda payload: payload,
        ),
        _client() as client,
    ):
        resp = client.post("/v1/forge/candidates/9999/accept", json={})
    assert resp.status_code == 404


def test_accept_candidate_route_returns_409_when_skill_exists(
    tmp_path,
) -> None:
    """If the target slug folder already has a SKILL.md, the route
    surfaces 409 instead of clobbering."""
    from metis_app.services.skill_repository import SkillRepository

    candidates_db = tmp_path / "skill_candidates.db"
    skills_root = tmp_path / "skills"
    repo = SkillRepository(skills_dir=skills_root)
    repo.save_candidate(
        db_path=candidates_db,
        query_text="Some query",
        trace_json="{}",
        convergence_score=0.95,
    )
    target = skills_root / "some-query" / "SKILL.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("existing", encoding="utf-8")

    with (
        patch(
            "metis_app.api_litestar.routes.forge._candidates_db_path",
            return_value=candidates_db,
        ),
        patch(
            "metis_app.api_litestar.routes.forge._skills_root_for_drafts",
            return_value=skills_root,
        ),
        patch(
            "metis_app.api_litestar.routes.forge._save_settings",
            side_effect=lambda payload: payload,
        ),
        _client() as client,
    ):
        resp = client.post("/v1/forge/candidates/1/accept", json={})
    assert resp.status_code == 409


def test_reject_candidate_route_marks_rejected(tmp_path) -> None:
    from metis_app.services.skill_repository import SkillRepository

    candidates_db = tmp_path / "skill_candidates.db"
    repo = SkillRepository(skills_dir=tmp_path / "skills")
    repo.save_candidate(
        db_path=candidates_db,
        query_text="Whatever",
        trace_json="{}",
        convergence_score=0.95,
    )

    with (
        patch(
            "metis_app.api_litestar.routes.forge._candidates_db_path",
            return_value=candidates_db,
        ),
        _client() as client,
    ):
        resp = client.post("/v1/forge/candidates/1/reject", json={})

    assert resp.status_code == 200
    import sqlite3

    with sqlite3.connect(candidates_db) as conn:
        row = conn.execute(
            "SELECT promoted, rejected FROM skill_candidates WHERE id = 1"
        ).fetchone()
    assert row == (1, 1)


def test_reject_candidate_route_returns_404_for_unknown_id(tmp_path) -> None:
    candidates_db = tmp_path / "skill_candidates.db"
    with (
        patch(
            "metis_app.api_litestar.routes.forge._candidates_db_path",
            return_value=candidates_db,
        ),
        _client() as client,
    ):
        resp = client.post("/v1/forge/candidates/9999/reject", json={})
    assert resp.status_code == 404


def test_heretic_enable_override_uses_service_default_output_dir() -> None:
    """The Forge's enable payload must write the same output root the
    Heretic service falls back to on its own. CWD-relative paths
    break in packaged/desktop runs where the process working
    directory is read-only or unstable.

    The service's default lives inline at
    ``HereticService.__init__`` (``output_root or
    pathlib.Path.home() / ".metis_heretic"``); we mirror it as
    ``HERETIC_DEFAULT_OUTPUT_DIR`` in ``forge_registry``. If either
    drifts, this test trips.
    """
    import pathlib

    from metis_app.services.forge_registry import HERETIC_DEFAULT_OUTPUT_DIR

    descriptor = get_descriptor("heretic-abliteration")
    assert descriptor is not None
    assert descriptor.enable_overrides is not None
    assert descriptor.enable_overrides == {
        "heretic_output_dir": HERETIC_DEFAULT_OUTPUT_DIR,
    }

    expected_default = str(pathlib.Path.home() / ".metis_heretic")
    assert HERETIC_DEFAULT_OUTPUT_DIR == expected_default
    # Hard guard: path must be absolute. A CWD-relative path here is
    # exactly the bug Codex P1 caught on PR #580.
    assert pathlib.Path(HERETIC_DEFAULT_OUTPUT_DIR).is_absolute()


def test_heretic_probe_blocks_when_cli_missing() -> None:
    """When the ``heretic`` CLI is not on ``$PATH``, the descriptor's
    readiness probe returns ``status="blocked"`` with a single
    blocker referring to the missing CLI and an ``install_heretic``
    CTA for the frontend.
    """
    from metis_app.services.forge_registry import RuntimeReadiness

    descriptor = get_descriptor("heretic-abliteration")
    assert descriptor is not None

    with patch(
        "metis_app.services.heretic_service.is_heretic_available",
        return_value=False,
    ):
        readiness = descriptor.readiness({})

    assert isinstance(readiness, RuntimeReadiness)
    assert readiness.status == "blocked"
    assert any("PATH" in b for b in readiness.blockers)
    assert readiness.cta_kind == "install_heretic"


def test_heretic_probe_ready_when_cli_available() -> None:
    descriptor = get_descriptor("heretic-abliteration")
    assert descriptor is not None
    with patch(
        "metis_app.services.heretic_service.is_heretic_available",
        return_value=True,
    ):
        readiness = descriptor.readiness({})
    assert readiness.status == "ready"
    assert readiness.blockers == ()


def test_timesfm_probe_is_informational_blocked() -> None:
    """TimesFM is not toggleable from the gallery; the probe reports
    a permanent blocker pointing to the chat-mode picker so the
    frontend can render a deep-link CTA."""
    descriptor = get_descriptor("timesfm-forecasting")
    assert descriptor is not None
    readiness = descriptor.readiness({})
    assert readiness.status == "blocked"
    assert any("Forecast" in b for b in readiness.blockers)
    assert readiness.cta_kind == "switch_chat_path"
    assert readiness.cta_target == "/chat"


def test_route_serialises_runtime_blocker_for_blocked_techniques() -> None:
    """End-to-end: with the Heretic CLI absent, the route output's
    ``heretic-abliteration`` row reports ``runtime_status="blocked"``
    and includes the blocker text in ``runtime_blockers``."""
    with patch(
        "metis_app.services.heretic_service.is_heretic_available",
        return_value=False,
    ):
        with _client() as client:
            techniques = client.get("/v1/forge/techniques").json()["techniques"]
    heretic = next(t for t in techniques if t["id"] == "heretic-abliteration")
    assert heretic["runtime_status"] == "blocked"
    assert any("PATH" in b for b in heretic["runtime_blockers"])
    assert heretic["runtime_cta_kind"] == "install_heretic"
    # TimesFM is independent of Heretic but always informational-blocked.
    timesfm = next(t for t in techniques if t["id"] == "timesfm-forecasting")
    assert timesfm["runtime_status"] == "blocked"
    assert timesfm["runtime_cta_kind"] == "switch_chat_path"


def test_readiness_swallows_probe_errors() -> None:
    """A probe that raises must collapse to ``status="blocked"``
    rather than propagate up to the route handler. The collapsed
    state's blocker text mentions the failure so debugging stays
    cheap."""
    from metis_app.services.forge_registry import (
        RuntimeReadiness,
        TechniqueDescriptor,
    )

    def boom(_settings: object) -> RuntimeReadiness:
        raise RuntimeError("network down")

    descriptor = TechniqueDescriptor(
        id="boom",
        name="Boom",
        description="boom",
        pillar="cortex",
        setting_keys=(),
        enabled_predicate=lambda _: False,
        runtime_probe=boom,
    )
    readiness = descriptor.readiness({})
    assert readiness.status == "blocked"
    assert any("network down" in b for b in readiness.blockers)


def _maximally_on_value_for(key: str) -> object:
    """Pick a value for ``key`` that would make any predicate that
    reads it interpret it as 'on'. Boolean keys → True; the handful
    of value-keys read by current predicates have known on values.
    """
    # Value keys that current predicates read explicitly. Add new
    # entries here when a future predicate gates on a string or
    # numeric value.
    explicit_on = {
        "hybrid_alpha": 0.5,
        "retrieval_mode": "mmr",
        "swarm_n_personas": 8,
        "chat_path": "Forecast",
        "chunk_strategy": "semantic",
        "heretic_output_dir": "/tmp/heretic",
        "agentic_max_iterations": 4,
        "agentic_convergence_threshold": 0.95,
        "agentic_iteration_budget": 4,
        "swarm_n_rounds": 4,
        "subquery_max_docs": 100,
        "mmr_lambda": 0.5,
        "hebbian_boost": 1.0,
        "hebbian_decay": 0.999,
        "forecast_model_id": "google/timesfm-2.5-200m-pytorch",
        "forecast_max_context": 2048,
        "forecast_max_horizon": 256,
        "forecast_use_quantiles": True,
        "forecast_xreg_mode": "xreg + timesfm",
        "brain_pass_native_enabled": True,
        "brain_pass_native_text_enabled": True,
        "brain_pass_model_id": "facebook/tribev2",
        "news_comet_sources": ["arxiv"],
        "news_comet_poll_interval_seconds": 300,
        "news_comet_max_active": 5,
        "news_comet_auto_absorb_threshold": 0.5,
        "news_comet_rss_feeds": [],
        "news_comet_reddit_subs": [],
        "enable_claim_level_grounding_citefix_lite": True,
    }
    if key in explicit_on:
        return explicit_on[key]
    # Default: treat unknown keys as booleans flipped on.
    return True


def test_list_techniques_ids_are_unique_and_url_safe() -> None:
    """Slugs are stable URL anchors per ADR 0014; renames need a
    redirect or deprecation pass. Guard them mechanically."""
    with _client() as client:
        techniques = client.get("/v1/forge/techniques").json()["techniques"]

    ids = [item["id"] for item in techniques]
    assert len(ids) == len(set(ids)), "duplicate technique slug detected"
    for slug in ids:
        assert slug == slug.lower(), f"slug must be lowercase: {slug}"
        # Anchor-safe: lowercase letters, digits, hyphens. Underscores
        # and other separators force escaping in URLs and break the
        # `/forge#<id>` deep-link contract.
        assert all(ch.isalnum() or ch == "-" for ch in slug), (
            f"slug must be alphanumeric or hyphen: {slug}"
        )


def test_registry_setting_keys_reference_real_settings() -> None:
    """Every ``setting_keys`` entry must exist in the live settings
    store. Drift between the hand-curated registry and
    ``default_settings.json`` is caught here.
    """
    import metis_app.settings_store as settings_store

    settings = settings_store.load_settings()
    missing = find_missing_setting_keys(settings)
    assert missing == {}, (
        "Forge registry references settings keys that do not exist in "
        f"default_settings.json: {missing}"
    )


def test_enabled_field_reflects_live_settings_overrides() -> None:
    """Phase 2a promise: user toggles surface in the gallery.

    Patch ``load_settings`` at the route layer so the response reflects
    a synthetic settings dict in which a few defaults are flipped, and
    confirm the ``enabled`` flag tracks the override per descriptor.
    """
    base = {
        # Defaults that should make the corresponding techniques on:
        "use_sub_queries": True,
        "use_reranker": True,
        "enable_brain_pass": True,
        "enable_hebbian": True,
        "enable_citation_v2": True,
        # Defaults off:
        "agentic_mode": False,
        "hybrid_alpha": 1.0,
        "retrieval_mode": "flat",
        "swarm_n_personas": 0,
        "chat_path": "RAG",
        "heretic_output_dir": "",
        "news_comets_enabled": False,
        "chunk_strategy": "fixed",
        "structure_aware_ingestion": False,
        "semantic_layout_ingestion": False,
    }

    overrides: dict[str, Any] = dict(base)
    overrides.update(
        {
            "agentic_mode": True,  # iterrag-convergence on
            "hybrid_alpha": 0.6,  # hybrid-search on
            "retrieval_mode": "mmr",  # mmr-diversification on
            "swarm_n_personas": 3,  # swarm-personas on
            "news_comets_enabled": True,  # news-comets on
            "chunk_strategy": "semantic",  # semantic-chunking on
            "use_reranker": False,  # reranker off
        }
    )

    with patch(
        "metis_app.api_litestar.routes.forge.load_settings",
        return_value=overrides,
    ):
        with _client() as client:
            resp = client.get("/v1/forge/techniques")
            techniques = {item["id"]: item for item in resp.json()["techniques"]}

    assert techniques["iterrag-convergence"]["enabled"] is True
    assert techniques["hybrid-search"]["enabled"] is True
    assert techniques["mmr-diversification"]["enabled"] is True
    assert techniques["swarm-personas"]["enabled"] is True
    assert techniques["news-comets"]["enabled"] is True
    assert techniques["semantic-chunking"]["enabled"] is True
    assert techniques["reranker"]["enabled"] is False
    # Spot-check a few that should match the base defaults:
    assert techniques["sub-query-expansion"]["enabled"] is True
    assert techniques["tribev2-multimodal"]["enabled"] is True
    assert techniques["citation-v2"]["enabled"] is True
    assert techniques["timesfm-forecasting"]["enabled"] is False


def test_descriptor_predicate_swallows_predicate_errors() -> None:
    """Defensive guard: a misbehaving predicate returns ``False``
    rather than crashing the gallery endpoint.
    """
    descriptor = get_descriptor("reranker")
    assert descriptor is not None

    # ``int.real`` access on a None will raise — confirm ``is_enabled``
    # converts the exception to a clean ``False``.
    class _BoomDict(dict):
        def get(self, *args, **kwargs):  # type: ignore[override]
            raise RuntimeError("boom")

    assert descriptor.is_enabled(_BoomDict()) is False


@pytest.mark.parametrize(
    "slug",
    [
        "iterrag-convergence",
        "reranker",
        "tribev2-multimodal",
        "news-comets",
    ],
)
def test_get_descriptor_resolves_known_slugs(slug: str) -> None:
    descriptor = get_descriptor(slug)
    assert descriptor is not None
    assert descriptor.id == slug


def test_get_descriptor_returns_none_for_unknown_slug() -> None:
    assert get_descriptor("not-a-real-technique") is None


# ── M14 Phase 6 — trace integration ───────────────────────────────


@pytest.fixture
def _phase6_trace_store(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    """Redirect ``TraceStore`` to a tmp_path-backed dir for the Phase 6
    routes. The route reads from the ``METIS_TRACE_DIR`` env var, so
    this monkeypatch is enough to isolate the test from any real trace
    data on disk."""
    monkeypatch.setenv("METIS_TRACE_DIR", str(tmp_path))
    from metis_app.services.trace_store import TraceStore

    store = TraceStore(tmp_path)
    return store


def test_list_techniques_response_includes_weekly_use_count(
    _phase6_trace_store,
) -> None:
    """The card face shows "Used X times this week" — a per-technique
    scalar that the list endpoint must surface so the gallery doesn't
    need a per-card detail call just to render the badge.

    The counter is *runs-this-week*, not *marker-events-this-week*
    (Codex P2 on PR #585), so we seed two distinct runs even though
    each emits the same single marker event.
    """
    store = _phase6_trace_store
    store.append_event(
        run_id="run-A", stage="reflection", event_type="iteration_complete"
    )
    store.append_event(
        run_id="run-B", stage="reflection", event_type="iteration_complete"
    )

    with _client() as client:
        techniques = client.get("/v1/forge/techniques").json()["techniques"]

    by_id = {entry["id"]: entry for entry in techniques}
    assert "weekly_use_count" in by_id["iterrag-convergence"], (
        "list endpoint must expose weekly_use_count for the card pill"
    )
    assert by_id["iterrag-convergence"]["weekly_use_count"] >= 2


def test_recent_uses_route_returns_filtered_events(
    _phase6_trace_store,
) -> None:
    store = _phase6_trace_store
    store.append_event(
        run_id="run-1", stage="reflection", event_type="iteration_complete",
        payload={"summary": "converged in 2"},
    )
    store.append_event(
        run_id="run-1", stage="synthesis", event_type="llm_response"
    )

    with _client() as client:
        resp = client.get(
            "/v1/forge/techniques/iterrag-convergence/recent-uses"
        )

    assert resp.status_code == 200
    body = resp.json()
    assert "events" in body
    assert "weekly_count" in body
    types = {e["event_type"] for e in body["events"]}
    assert types == {"iteration_complete"}


def test_recent_uses_route_404s_for_unknown_technique() -> None:
    with _client() as client:
        resp = client.get("/v1/forge/techniques/not-a-thing/recent-uses")
    assert resp.status_code == 404


def test_recent_uses_route_returns_empty_for_descriptor_without_markers(
    _phase6_trace_store,
) -> None:
    """Phase 6 ships markers for the marquee techniques only. Cards
    whose descriptor has no markers wired yet must still get a clean
    empty response (not a 500), so the gallery renders consistently."""
    # Find a descriptor that has no trace markers wired and probe it.
    from metis_app.services.forge_registry import get_registry

    candidates = [d for d in get_registry() if not d.trace_event_types]
    if not candidates:
        pytest.skip(
            "every descriptor declares trace markers — empty-marker test "
            "no longer applicable"
        )

    target = candidates[0].id
    with _client() as client:
        resp = client.get(f"/v1/forge/techniques/{target}/recent-uses")
    assert resp.status_code == 200
    body = resp.json()
    assert body["events"] == []
    assert body["weekly_count"] == 0


# ── M14 Phase 7 — `.metis-skill` bundle export/import ─────────────


def _write_phase7_skill(
    skills_root: pathlib.Path,
    slug: str,
    *,
    body: str = "phase 7 fixture body\n",
) -> pathlib.Path:
    """Write a parse_skill_file-valid SKILL.md fixture under
    ``<skills_root>/<slug>/`` for the bundle-route tests.
    """
    import yaml as _yaml

    skill_dir = skills_root / slug
    skill_dir.mkdir(parents=True, exist_ok=True)
    frontmatter = {
        "id": slug,
        "name": slug.replace("-", " ").title(),
        "description": f"Fixture skill {slug}.",
        "enabled_by_default": False,
        "priority": 50,
        "triggers": {
            "keywords": [],
            "modes": [],
            "file_types": [],
            "output_styles": [],
        },
        "runtime_overrides": {},
    }
    fm_text = _yaml.safe_dump(frontmatter, sort_keys=False)
    skill_path = skill_dir / "SKILL.md"
    skill_path.write_text(f"---\n{fm_text}---\n{body}", encoding="utf-8")
    return skill_path


def test_list_installed_skills_returns_skills_root_contents(
    tmp_path: pathlib.Path,
) -> None:
    skills_root = tmp_path / "skills"
    _write_phase7_skill(skills_root, "qa-fixture")
    _write_phase7_skill(skills_root, "swarm-fixture")

    with (
        patch(
            "metis_app.api_litestar.routes.forge._skills_root_for_drafts",
            return_value=skills_root,
        ),
        _client() as client,
    ):
        resp = client.get("/v1/forge/skills")

    assert resp.status_code == 200
    payload = resp.json()
    ids = {entry["id"] for entry in payload["skills"]}
    assert ids == {"qa-fixture", "swarm-fixture"}
    for entry in payload["skills"]:
        assert isinstance(entry["name"], str) and entry["name"]
        assert isinstance(entry["description"], str)
        assert isinstance(entry["path"], str)


def test_list_installed_skills_returns_empty_for_missing_root(
    tmp_path: pathlib.Path,
) -> None:
    """An empty or missing ``skills/`` directory must not 500 the
    Forge — the gallery should still render with a blank list."""
    nowhere = tmp_path / "no-such-dir"

    with (
        patch(
            "metis_app.api_litestar.routes.forge._skills_root_for_drafts",
            return_value=nowhere,
        ),
        _client() as client,
    ):
        resp = client.get("/v1/forge/skills")

    assert resp.status_code == 200
    assert resp.json() == {"skills": []}


def test_export_skill_returns_base64_bundle_with_sha(
    tmp_path: pathlib.Path,
) -> None:
    import base64 as _b64
    import hashlib as _hashlib

    from metis_app.services import forge_bundle as _forge_bundle

    skills_root = tmp_path / "skills"
    _write_phase7_skill(skills_root, "qa-fixture")

    with (
        patch(
            "metis_app.api_litestar.routes.forge._skills_root_for_drafts",
            return_value=skills_root,
        ),
        _client() as client,
    ):
        resp = client.post(
            "/v1/forge/skills/qa-fixture/export",
            json={"version": "0.2.0", "author": "tests@example.com"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["filename"] == "qa-fixture-0.2.0.metis-skill"
    raw = _b64.b64decode(body["content_base64"])
    assert _hashlib.sha256(raw).hexdigest() == body["sha256"]

    bundle_path = tmp_path / "decoded.metis-skill"
    bundle_path.write_bytes(raw)
    inspected = _forge_bundle.inspect_bundle(bundle_path)
    assert inspected.errors == []
    assert inspected.manifest.skill_id == "qa-fixture"
    assert inspected.manifest.version == "0.2.0"
    assert inspected.manifest.author == "tests@example.com"


def test_export_unknown_skill_returns_404(tmp_path: pathlib.Path) -> None:
    skills_root = tmp_path / "skills"
    skills_root.mkdir()

    with (
        patch(
            "metis_app.api_litestar.routes.forge._skills_root_for_drafts",
            return_value=skills_root,
        ),
        _client() as client,
    ):
        resp = client.post(
            "/v1/forge/skills/does-not-exist/export",
            json={"version": "0.1.0"},
        )

    assert resp.status_code == 404


def test_export_skill_400_on_missing_version(tmp_path: pathlib.Path) -> None:
    """The ADR 0015 manifest schema requires a non-empty ``version``."""
    skills_root = tmp_path / "skills"
    _write_phase7_skill(skills_root, "qa-fixture")

    with (
        patch(
            "metis_app.api_litestar.routes.forge._skills_root_for_drafts",
            return_value=skills_root,
        ),
        _client() as client,
    ):
        resp = client.post(
            "/v1/forge/skills/qa-fixture/export",
            json={},
        )

    assert resp.status_code == 400


def test_export_skill_400_on_path_separator_in_version(
    tmp_path: pathlib.Path,
) -> None:
    """Codex P2 — `version` flows directly into the bundle filename.
    A version with `/` or `\\` makes `pack_skill` try to write to a
    nested non-existent directory, which would 500 if the route
    didn't validate up front."""
    skills_root = tmp_path / "skills"
    _write_phase7_skill(skills_root, "qa-fixture")

    bad_versions = (
        "1/2",
        "1\\2",
        "../escape",
        "../../etc/passwd",
        "1.0/v",
        "v\\1",
    )

    with (
        patch(
            "metis_app.api_litestar.routes.forge._skills_root_for_drafts",
            return_value=skills_root,
        ),
        _client() as client,
    ):
        for bad in bad_versions:
            resp = client.post(
                "/v1/forge/skills/qa-fixture/export",
                json={"version": bad},
            )
            assert resp.status_code == 400, (
                f"version={bad!r} should be 400, got {resp.status_code}"
            )


def test_import_preview_returns_manifest_and_no_conflict(
    tmp_path: pathlib.Path,
) -> None:
    from metis_app.services import forge_bundle as _forge_bundle

    src_root = tmp_path / "src"
    target_root = tmp_path / "target"
    target_root.mkdir()
    _write_phase7_skill(src_root, "qa-fixture")
    bundle_path = _forge_bundle.pack_skill(
        skill_dir=src_root / "qa-fixture",
        version="0.1.0",
        dest_dir=tmp_path,
    )

    with (
        patch(
            "metis_app.api_litestar.routes.forge._skills_root_for_drafts",
            return_value=target_root,
        ),
        _client() as client,
    ):
        resp = client.post(
            "/v1/forge/skills/import/preview",
            files={"file": ("qa.metis-skill", bundle_path.read_bytes())},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["manifest"]["skill_id"] == "qa-fixture"
    assert body["manifest"]["version"] == "0.1.0"
    assert body["manifest"]["bundle_format_version"] == 1
    assert body["conflict"] is False
    assert body["errors"] == []


def test_import_preview_flags_conflict_when_slug_exists(
    tmp_path: pathlib.Path,
) -> None:
    from metis_app.services import forge_bundle as _forge_bundle

    src_root = tmp_path / "src"
    target_root = tmp_path / "target"
    _write_phase7_skill(src_root, "qa-fixture")
    _write_phase7_skill(target_root, "qa-fixture", body="existing\n")
    bundle_path = _forge_bundle.pack_skill(
        skill_dir=src_root / "qa-fixture",
        version="0.1.0",
        dest_dir=tmp_path,
    )

    with (
        patch(
            "metis_app.api_litestar.routes.forge._skills_root_for_drafts",
            return_value=target_root,
        ),
        _client() as client,
    ):
        resp = client.post(
            "/v1/forge/skills/import/preview",
            files={"file": ("qa.metis-skill", bundle_path.read_bytes())},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["conflict"] is True
    assert body["errors"] == []


def test_import_preview_400_on_missing_file(tmp_path: pathlib.Path) -> None:
    with _client() as client:
        resp = client.post("/v1/forge/skills/import/preview", files={})
    assert resp.status_code == 400


def test_import_install_writes_skill_to_skills_root(
    tmp_path: pathlib.Path,
) -> None:
    from metis_app.services import forge_bundle as _forge_bundle

    src_root = tmp_path / "src"
    target_root = tmp_path / "target"
    _write_phase7_skill(src_root, "qa-fixture", body="from bundle\n")
    bundle_path = _forge_bundle.pack_skill(
        skill_dir=src_root / "qa-fixture",
        version="0.1.0",
        dest_dir=tmp_path,
    )

    with (
        patch(
            "metis_app.api_litestar.routes.forge._skills_root_for_drafts",
            return_value=target_root,
        ),
        _client() as client,
    ):
        resp = client.post(
            "/v1/forge/skills/import/install",
            files={"file": ("qa.metis-skill", bundle_path.read_bytes())},
            data={"replace": "false"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["skill_id"] == "qa-fixture"
    assert body["replaced"] is False
    on_disk = (target_root / "qa-fixture" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "from bundle" in on_disk


def test_import_install_409_on_slug_conflict_without_replace(
    tmp_path: pathlib.Path,
) -> None:
    from metis_app.services import forge_bundle as _forge_bundle

    src_root = tmp_path / "src"
    target_root = tmp_path / "target"
    _write_phase7_skill(src_root, "qa-fixture", body="from bundle\n")
    _write_phase7_skill(target_root, "qa-fixture", body="local edits\n")
    bundle_path = _forge_bundle.pack_skill(
        skill_dir=src_root / "qa-fixture",
        version="0.1.0",
        dest_dir=tmp_path,
    )

    with (
        patch(
            "metis_app.api_litestar.routes.forge._skills_root_for_drafts",
            return_value=target_root,
        ),
        _client() as client,
    ):
        resp = client.post(
            "/v1/forge/skills/import/install",
            files={"file": ("qa.metis-skill", bundle_path.read_bytes())},
            data={"replace": "false"},
        )

    assert resp.status_code == 409
    on_disk = (target_root / "qa-fixture" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "local edits" in on_disk


def test_import_install_replace_true_overwrites(
    tmp_path: pathlib.Path,
) -> None:
    from metis_app.services import forge_bundle as _forge_bundle

    src_root = tmp_path / "src"
    target_root = tmp_path / "target"
    _write_phase7_skill(src_root, "qa-fixture", body="from bundle\n")
    _write_phase7_skill(target_root, "qa-fixture", body="local edits\n")
    bundle_path = _forge_bundle.pack_skill(
        skill_dir=src_root / "qa-fixture",
        version="0.1.0",
        dest_dir=tmp_path,
    )

    with (
        patch(
            "metis_app.api_litestar.routes.forge._skills_root_for_drafts",
            return_value=target_root,
        ),
        _client() as client,
    ):
        resp = client.post(
            "/v1/forge/skills/import/install",
            files={"file": ("qa.metis-skill", bundle_path.read_bytes())},
            data={"replace": "true"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["replaced"] is True
    on_disk = (target_root / "qa-fixture" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "from bundle" in on_disk
    assert "local edits" not in on_disk


def test_import_install_400_on_invalid_bundle(
    tmp_path: pathlib.Path,
) -> None:
    """A tarball missing the skill payload must come back as 400."""
    import tarfile as _tarfile
    from io import BytesIO as _BytesIO

    import yaml as _yaml

    bad_path = tmp_path / "bad.metis-skill"
    target_root = tmp_path / "target"
    target_root.mkdir()
    manifest_text = _yaml.safe_dump(
        {
            "bundle_format_version": 1,
            "skill_id": "qa-fixture",
            "name": "x",
            "description": "x",
            "version": "0.1.0",
            "exported_at": "2026-05-01T12:00:00Z",
            "min_metis_version": "0.1.0",
        }
    ).encode("utf-8")
    with _tarfile.open(bad_path, mode="w") as tf:
        info = _tarfile.TarInfo(name="manifest.yaml")
        info.size = len(manifest_text)
        tf.addfile(info, _BytesIO(manifest_text))

    with (
        patch(
            "metis_app.api_litestar.routes.forge._skills_root_for_drafts",
            return_value=target_root,
        ),
        _client() as client,
    ):
        resp = client.post(
            "/v1/forge/skills/import/install",
            files={"file": ("bad.metis-skill", bad_path.read_bytes())},
            data={"replace": "false"},
        )

    assert resp.status_code == 400


def test_import_install_400_on_missing_file(tmp_path: pathlib.Path) -> None:
    with _client() as client:
        resp = client.post(
            "/v1/forge/skills/import/install", data={"replace": "false"}
        )
    assert resp.status_code == 400
