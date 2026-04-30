"""Tests for the M14 Phase 4a Forge absorb pipeline."""

from __future__ import annotations

from unittest.mock import patch



def test_extract_arxiv_id_from_abs_url() -> None:
    """Standard arxiv URLs (``/abs/<id>``) yield the bare ID."""
    from metis_app.services.forge_absorb import extract_arxiv_id

    assert extract_arxiv_id("https://arxiv.org/abs/2501.12345") == "2501.12345"
    assert extract_arxiv_id("http://arxiv.org/abs/2501.12345v2") == "2501.12345v2"
    assert extract_arxiv_id("https://www.arxiv.org/abs/cs.AI/0501001") == "cs.AI/0501001"


def test_extract_arxiv_id_from_pdf_url() -> None:
    """``/pdf/<id>.pdf`` URLs strip the suffix and resolve to the same ID."""
    from metis_app.services.forge_absorb import extract_arxiv_id

    assert extract_arxiv_id("https://arxiv.org/pdf/2501.12345.pdf") == "2501.12345"
    assert extract_arxiv_id("https://arxiv.org/pdf/2501.12345v3.pdf") == "2501.12345v3"


def test_extract_arxiv_id_returns_none_for_non_arxiv() -> None:
    from metis_app.services.forge_absorb import extract_arxiv_id

    assert extract_arxiv_id("https://example.com/foo") is None
    assert extract_arxiv_id("https://github.com/user/repo") is None
    assert extract_arxiv_id("https://blog.example.com/posts/intro") is None


def test_extract_arxiv_id_rejects_lookalike_hosts() -> None:
    """Hostname must be exactly an arxiv host. ``notarxiv.org`` and
    subdomain shenanigans like ``arxiv.org.attacker.com`` would
    otherwise match the regex's substring search and trick the
    pipeline into treating an arbitrary URL as an arxiv source.

    Codex P2 review on PR #581 caught this — the original
    ``re.search`` over the whole URL string allowed
    ``notarxiv.org/abs/2501.12345`` through.
    """
    from metis_app.services.forge_absorb import extract_arxiv_id

    assert extract_arxiv_id("https://notarxiv.org/abs/2501.12345") is None
    assert extract_arxiv_id("https://arxiv.org.attacker.com/abs/2501.12345") is None
    assert extract_arxiv_id("https://attacker-arxiv.org/abs/2501.12345") is None


def test_extract_arxiv_id_ignores_arxiv_in_query_string() -> None:
    """An arxiv-shaped substring inside a query parameter must not
    promote the URL to an arxiv source. The pipeline ends up
    fetching the real arxiv.org for the spoofed ID, so the
    ``source_kind="arxiv"`` payload would be wrong by attribution."""
    from metis_app.services.forge_absorb import extract_arxiv_id

    assert extract_arxiv_id(
        "https://attacker.example/r?to=https://arxiv.org/abs/2501.12345"
    ) is None


def test_extract_arxiv_id_accepts_export_subdomain() -> None:
    """``export.arxiv.org`` is the documented API host and a
    legitimate alias when users paste the API URL directly."""
    from metis_app.services.forge_absorb import extract_arxiv_id

    assert (
        extract_arxiv_id("https://export.arxiv.org/abs/2501.12345")
        == "2501.12345"
    )


_ARXIV_ATOM_RESPONSE = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2501.12345v1</id>
    <title>An Imaginary Paper About Something Cool</title>
    <summary>This paper proposes a novel reranking approach that combines
cross-encoder scoring with a small graph-walk over retrieved
neighbors. We show 3.2 NDCG@10 lift on BEIR.</summary>
    <author><name>A. Researcher</name></author>
  </entry>
</feed>
"""


def test_fetch_arxiv_metadata_parses_atom_response() -> None:
    """The arxiv API returns an Atom feed; extractor pulls title +
    summary into a normalised dict so the LLM prompt and the
    cross-reference matcher both see the same shape."""
    from metis_app.services.forge_absorb import fetch_arxiv_metadata

    with patch(
        "metis_app.services.forge_absorb._safe_get_bytes",
        return_value=_ARXIV_ATOM_RESPONSE,
    ):
        meta = fetch_arxiv_metadata("2501.12345")

    assert meta is not None
    assert meta["arxiv_id"] == "2501.12345"
    assert meta["title"] == "An Imaginary Paper About Something Cool"
    assert "reranking approach" in meta["summary"]
    assert meta["source_url"] == "https://arxiv.org/abs/2501.12345"


def test_fetch_arxiv_metadata_returns_none_on_fetch_error() -> None:
    """Network or parse failures collapse to ``None`` rather than
    propagating — the caller falls back to the generic URL fetcher."""
    from metis_app.services.forge_absorb import fetch_arxiv_metadata

    with patch(
        "metis_app.services.forge_absorb._safe_get_bytes",
        return_value=None,
    ):
        assert fetch_arxiv_metadata("2501.99999") is None


def test_fetch_arxiv_metadata_returns_none_on_invalid_xml() -> None:
    from metis_app.services.forge_absorb import fetch_arxiv_metadata

    with patch(
        "metis_app.services.forge_absorb._safe_get_bytes",
        return_value=b"not really xml",
    ):
        assert fetch_arxiv_metadata("2501.99999") is None


def test_cross_reference_finds_existing_when_keyword_overlaps() -> None:
    """A summary that mentions ``reranking`` should match the
    Reranker descriptor in the registry. The matcher is intentionally
    loose so paraphrases still surface a hit; the LLM call later
    refines the proposal."""
    from metis_app.services.forge_absorb import cross_reference_against_registry

    summary = (
        "This paper proposes a novel reranking approach that combines "
        "cross-encoder scoring with a graph walk."
    )
    matches = cross_reference_against_registry(summary)
    ids = [m["id"] for m in matches]
    assert "reranker" in ids


def test_cross_reference_returns_empty_when_no_overlap() -> None:
    from metis_app.services.forge_absorb import cross_reference_against_registry

    matches = cross_reference_against_registry(
        "This paper studies migration patterns of monarch butterflies."
    )
    assert matches == []


def test_cross_reference_match_carries_descriptor_metadata() -> None:
    """A match exposes id, name, pillar, enabled state — same shape
    the gallery uses, so the frontend can render the same card style
    when surfacing matches."""
    from metis_app.services.forge_absorb import cross_reference_against_registry

    matches = cross_reference_against_registry("hybrid retrieval combines BM25 and vector")
    assert matches, "expected hybrid-search to surface"
    entry = next(m for m in matches if m["id"] == "hybrid-search")
    assert entry["name"]
    assert entry["pillar"] in {"cosmos", "companion", "cortex", "cross-cutting"}


_FAKE_LLM_JSON = (
    '{"name": "Sparse Cross-Encoder Reranking",'
    ' "claim": "Reranks BM25 hits with a sparse cross-encoder.",'
    ' "pillar_guess": "cortex",'
    ' "implementation_sketch": "Score top-k hits with a small CE model."}'
)


def test_summarise_to_proposal_calls_llm_and_returns_proposal() -> None:
    """The orchestrator threads through the assistant's configured
    LLM (via ``create_llm``) and parses the JSON response into a
    ``TechniqueProposal``-shaped dict."""
    from metis_app.services.forge_absorb import summarise_to_proposal

    fake_llm = type("Fake", (), {"invoke": lambda self, msgs: type("R", (), {"content": _FAKE_LLM_JSON})()})()

    proposal = summarise_to_proposal(
        title="An Imaginary Paper",
        summary="This paper proposes a novel reranking approach.",
        llm=fake_llm,
    )

    assert proposal is not None
    assert proposal["name"] == "Sparse Cross-Encoder Reranking"
    assert proposal["pillar_guess"] == "cortex"
    assert "Reranks BM25" in proposal["claim"]


def test_summarise_to_proposal_returns_none_on_empty_response() -> None:
    """A blank LLM response collapses to None rather than a partial
    proposal; the caller surfaces 'couldn't generate proposal' to
    the user."""
    from metis_app.services.forge_absorb import summarise_to_proposal

    fake_llm = type("Fake", (), {"invoke": lambda self, msgs: type("R", (), {"content": ""})()})()
    assert summarise_to_proposal(title="x", summary="y", llm=fake_llm) is None


def test_summarise_to_proposal_returns_none_on_invalid_json() -> None:
    from metis_app.services.forge_absorb import summarise_to_proposal

    fake_llm = type("Fake", (), {"invoke": lambda self, msgs: type("R", (), {"content": "this is not json"})()})()
    assert summarise_to_proposal(title="x", summary="y", llm=fake_llm) is None


def test_absorb_arxiv_url_runs_full_pipeline() -> None:
    """End-to-end (with the network and LLM both mocked): an arxiv URL
    flows through extraction → cross-reference → LLM proposal."""
    from metis_app.services.forge_absorb import absorb

    fake_llm = type("Fake", (), {"invoke": lambda self, msgs: type("R", (), {"content": _FAKE_LLM_JSON})()})()

    with patch(
        "metis_app.services.forge_absorb._safe_get_bytes",
        return_value=_ARXIV_ATOM_RESPONSE,
    ):
        result = absorb("https://arxiv.org/abs/2501.12345", llm=fake_llm)

    assert result["source_kind"] == "arxiv"
    assert result["title"] == "An Imaginary Paper About Something Cool"
    assert result["proposal"] is not None
    assert result["proposal"]["name"] == "Sparse Cross-Encoder Reranking"
    # The reranker registry entry should match too.
    assert any(m["id"] == "reranker" for m in result["matches"])


def test_absorb_returns_error_payload_on_unfetchable_url() -> None:
    """A URL we can't fetch returns a result with ``source_kind = "error"``
    and a human-readable message; the route can surface that to the
    user without throwing."""
    from metis_app.services.forge_absorb import absorb

    with patch(
        "metis_app.services.forge_absorb._safe_get_bytes",
        return_value=None,
    ):
        result = absorb("https://arxiv.org/abs/2501.99999", llm=None)

    assert result["source_kind"] == "error"
    assert "fetch" in result["error"].lower()
    assert result["proposal"] is None


def test_absorb_rejects_non_http_urls() -> None:
    """SSRF guard: non-http(s) schemes are rejected before any fetch."""
    from metis_app.services.forge_absorb import absorb

    result = absorb("file:///etc/passwd", llm=None)
    assert result["source_kind"] == "error"
    assert "url" in result["error"].lower()
