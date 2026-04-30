"""Tests for the M14 Phase 4c news-comet → Forge proposal bridge."""

from __future__ import annotations

import pathlib
from typing import Any
from unittest.mock import patch


_ARXIV_ATOM_RESPONSE = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2501.12345v1</id>
    <title>Cross-encoder reranking that matters</title>
    <summary>We propose a sparse cross-encoder reranking method.</summary>
  </entry>
</feed>
"""

_FAKE_PROPOSAL_JSON = (
    '{"name": "Sparse Cross-Encoder Reranking",'
    ' "claim": "Reranks BM25 hits with a small cross-encoder.",'
    ' "pillar_guess": "cortex",'
    ' "implementation_sketch": "Score top-k hits with a small CE model."}'
)


class _FakeLLM:
    def invoke(self, _msgs: object) -> object:
        return type("R", (), {"content": _FAKE_PROPOSAL_JSON})()


def _make_event(
    *,
    decision: str,
    url: str,
    comet_id: str = "comet_abc123",
    title: str = "Some paper",
):
    """Build a minimal ``CometEvent`` for the bridge."""
    from metis_app.models.comet_event import CometEvent, NewsItem

    item = NewsItem(title=title, url=url, summary="Body", source_channel="rss")
    event = CometEvent(comet_id=comet_id, news_item=item)
    event.decision = decision  # type: ignore[assignment]
    return event


def test_bridge_skips_events_with_non_absorb_decision(tmp_path: pathlib.Path) -> None:
    """``decision=="approach"`` and ``"drift"`` events are noise from
    the bridge's perspective. They never trigger an absorb call, so
    no proposal lands in the db."""
    from metis_app.services import forge_proposals
    from metis_app.services.forge_comet_bridge import auto_absorb_comets

    db_path = tmp_path / "forge_proposals.db"
    events = [
        _make_event(decision="approach", url="https://arxiv.org/abs/2501.11111"),
        _make_event(decision="drift", url="https://arxiv.org/abs/2501.22222"),
    ]

    saved = auto_absorb_comets(
        events,
        db_path=db_path,
        llm_factory=lambda: _FakeLLM(),
    )
    assert saved == []
    assert forge_proposals.list_proposals(db_path=db_path) == []


def test_bridge_skips_non_arxiv_absorb_events(tmp_path: pathlib.Path) -> None:
    """The arxiv-only Phase 4a/4b absorb pipeline doesn't accept
    blog or HN URLs; the bridge silently skips them rather than
    saving an "unsupported" proposal."""
    from metis_app.services import forge_proposals
    from metis_app.services.forge_comet_bridge import auto_absorb_comets

    db_path = tmp_path / "forge_proposals.db"
    events = [
        _make_event(decision="absorb", url="https://example.com/blog/a-post"),
        _make_event(decision="absorb", url="https://news.ycombinator.com/item?id=1"),
    ]

    saved = auto_absorb_comets(
        events,
        db_path=db_path,
        llm_factory=lambda: _FakeLLM(),
    )
    assert saved == []
    assert forge_proposals.list_proposals(db_path=db_path) == []


def test_bridge_persists_arxiv_absorb_events(tmp_path: pathlib.Path) -> None:
    """Happy path: an arxiv absorb-decision flows through the
    absorb pipeline (network + LLM mocked) and lands in
    ``forge_proposals.db`` with ``source="comet"`` and the
    originating ``comet_id`` for traceability."""
    from metis_app.services import forge_proposals
    from metis_app.services.forge_comet_bridge import auto_absorb_comets

    db_path = tmp_path / "forge_proposals.db"
    events = [
        _make_event(
            decision="absorb",
            url="https://arxiv.org/abs/2501.12345",
            comet_id="comet_xyz",
        ),
    ]

    with patch(
        "metis_app.services.forge_absorb._safe_get_bytes",
        return_value=_ARXIV_ATOM_RESPONSE,
    ):
        saved = auto_absorb_comets(
            events,
            db_path=db_path,
            llm_factory=lambda: _FakeLLM(),
        )

    assert len(saved) == 1
    rows = forge_proposals.list_proposals(db_path=db_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["source"] == "comet"
    assert row["comet_id"] == "comet_xyz"
    assert row["proposal_name"] == "Sparse Cross-Encoder Reranking"


def test_bridge_skips_when_proposal_generation_fails(
    tmp_path: pathlib.Path,
) -> None:
    """If the LLM call returns nothing, the bridge does NOT persist
    a hollow row — the user has to re-run absorb manually once a
    provider is configured. (We don't want the news-comet pipeline
    to silently spam the review pane with title-only rows.)"""
    from metis_app.services import forge_proposals
    from metis_app.services.forge_comet_bridge import auto_absorb_comets

    db_path = tmp_path / "forge_proposals.db"
    events = [
        _make_event(decision="absorb", url="https://arxiv.org/abs/2501.12345"),
    ]

    class _DeadLLM:
        def invoke(self, _msgs: object) -> object:
            return type("R", (), {"content": ""})()

    with patch(
        "metis_app.services.forge_absorb._safe_get_bytes",
        return_value=_ARXIV_ATOM_RESPONSE,
    ):
        saved = auto_absorb_comets(
            events,
            db_path=db_path,
            llm_factory=lambda: _DeadLLM(),
        )

    assert saved == []
    assert forge_proposals.list_proposals(db_path=db_path) == []


def test_bridge_dedups_against_existing_pending_comet_id(
    tmp_path: pathlib.Path,
) -> None:
    """The poll cycle can fire repeatedly within a session. The
    bridge must not re-persist a comet whose proposal is already
    pending; otherwise the review pane would fill up with
    duplicate rows for the same paper."""
    from metis_app.services import forge_proposals
    from metis_app.services.forge_comet_bridge import auto_absorb_comets

    db_path = tmp_path / "forge_proposals.db"
    # Pre-seed a pending proposal from comet_dup.
    forge_proposals.save_proposal(
        db_path=db_path,
        source_url="https://arxiv.org/abs/2501.12345",
        arxiv_id="2501.12345",
        title="Cross-encoder reranking that matters",
        summary="",
        proposal_name="Sparse Cross-Encoder Reranking",
        proposal_claim="Reranks BM25 hits.",
        proposal_pillar="cortex",
        proposal_sketch="Score top-k hits.",
        source="comet",
        comet_id="comet_dup",
    )

    events = [
        _make_event(
            decision="absorb",
            url="https://arxiv.org/abs/2501.12345",
            comet_id="comet_dup",
        ),
    ]

    with patch(
        "metis_app.services.forge_absorb._safe_get_bytes",
        return_value=_ARXIV_ATOM_RESPONSE,
    ):
        saved = auto_absorb_comets(
            events,
            db_path=db_path,
            llm_factory=lambda: _FakeLLM(),
        )

    assert saved == []
    assert len(forge_proposals.list_proposals(db_path=db_path)) == 1
