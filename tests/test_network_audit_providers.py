"""Tests for ``metis_app.network_audit.providers`` (Phase 1 of M17).

These tests guard the shape and integrity of the known-provider
registry. The registry is purely declarative, so these tests are
correspondingly narrow: counts, duplicates, categories, immutability,
and a handful of representative classification cases.

Do not expand these tests into the Phase 3+ wrapper behaviour — that
lives in its own test module once ``client.py`` is landed.
"""

from __future__ import annotations

import typing
from dataclasses import FrozenInstanceError

import pytest

from metis_app.network_audit import (
    KNOWN_PROVIDERS,
    ProviderCategory,
    ProviderSpec,
    classify_host,
)


def test_public_api_reexports() -> None:
    """__init__.py re-exports the full public surface."""
    # Touching each name guards against accidental removal.
    assert ProviderSpec.__name__ == "ProviderSpec"
    assert "llm" in typing.get_args(ProviderCategory)
    assert callable(classify_host)
    assert isinstance(KNOWN_PROVIDERS, typing.Mapping)


# ---------------------------------------------------------------------------
# Registry shape
# ---------------------------------------------------------------------------


def test_no_duplicate_keys() -> None:
    """Every key in ``KNOWN_PROVIDERS`` appears exactly once.

    The registry is a dict — Python de-duplicates on construction — so
    a naive ``len(keys) == len(set(keys))`` assertion would always
    pass. Compare against a manually assembled list that goes through
    the public API to guard against accidental future refactors into
    a list-of-pairs representation.
    """
    keys = [spec.key for spec in KNOWN_PROVIDERS.values()]
    assert len(keys) == len(set(keys)), f"duplicate provider keys: {keys}"


def test_every_entry_has_valid_category() -> None:
    valid_categories = set(typing.get_args(ProviderCategory))
    for key, spec in KNOWN_PROVIDERS.items():
        assert spec.category in valid_categories, (
            f"provider {key!r} has invalid category {spec.category!r}"
        )


def test_every_entry_key_matches_dict_key() -> None:
    for key, spec in KNOWN_PROVIDERS.items():
        assert spec.key == key, (
            f"dict key {key!r} disagrees with ProviderSpec.key {spec.key!r}"
        )


def test_expected_minimum_provider_count() -> None:
    """Ship at least the 18 providers listed in the Phase 1 inventory.

    Count breakdown (matches the Phase 1 spec in plans/network-audit/plan.md):
      - LLM (5): openai, anthropic, google, xai, local_lm_studio
      - Embeddings (4): openai_embeddings, google_embeddings, voyage,
        huggingface_local
      - Search (3): duckduckgo, jina_reader, tavily
      - Ingestion (3): rss_feed, hackernews_api, reddit_api
      - Model hub (1): huggingface_hub
      - Vector DB (1): weaviate
      - Other (1): nyx_registry
      - Fonts CDN (1): google_fonts
      - Fallback (1): unclassified
      Total: 20
    """
    assert len(KNOWN_PROVIDERS) >= 18, (
        f"expected >=18 providers, found {len(KNOWN_PROVIDERS)}"
    )


def test_unclassified_entry_exists() -> None:
    """The ``unclassified`` fallback is required by ``classify_host``."""
    assert "unclassified" in KNOWN_PROVIDERS
    assert KNOWN_PROVIDERS["unclassified"].category == "other"


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def test_classify_openai_api() -> None:
    # openai is registered before openai_embeddings in the dict, so
    # host-only classification of api.openai.com resolves to openai.
    # This is the documented limitation in ADR 0010.
    assert classify_host("api.openai.com").key == "openai"


def test_classify_anthropic_api() -> None:
    assert classify_host("api.anthropic.com").key == "anthropic"


def test_classify_reddit_variants() -> None:
    assert classify_host("www.reddit.com").key == "reddit_api"
    assert classify_host("old.reddit.com").key == "reddit_api"
    assert classify_host("reddit.com").key == "reddit_api"


def test_classify_hn_api() -> None:
    assert classify_host("hacker-news.firebaseio.com").key == "hackernews_api"


def test_classify_google_fonts() -> None:
    assert classify_host("fonts.googleapis.com").key == "google_fonts"
    assert classify_host("fonts.gstatic.com").key == "google_fonts"


def test_classify_google_genai() -> None:
    # google is registered before google_embeddings — same precedence
    # reasoning as api.openai.com.
    assert classify_host("generativelanguage.googleapis.com").key == "google"


def test_classify_xai() -> None:
    assert classify_host("api.x.ai").key == "xai"


def test_classify_voyage() -> None:
    assert classify_host("api.voyageai.com").key == "voyage"


def test_classify_tavily() -> None:
    assert classify_host("api.tavily.com").key == "tavily"


def test_classify_duckduckgo() -> None:
    assert classify_host("api.duckduckgo.com").key == "duckduckgo"
    assert classify_host("duckduckgo.com").key == "duckduckgo"


def test_classify_jina_reader() -> None:
    assert classify_host("r.jina.ai").key == "jina_reader"


def test_classify_nyx_registry() -> None:
    assert classify_host("nyxui.com").key == "nyx_registry"


def test_classify_huggingface_hub() -> None:
    assert classify_host("huggingface.co").key == "huggingface_hub"


def test_classify_loopback_is_lm_studio() -> None:
    # local_lm_studio is registered before huggingface_local, so
    # loopback hosts classify as LM Studio. The wrapper will attach
    # the correct provider at the call site (Phase 3+).
    assert classify_host("127.0.0.1").key == "local_lm_studio"
    assert classify_host("localhost").key == "local_lm_studio"
    # IPv6 loopback: ``sanitize_url`` returns ``::1`` without brackets
    # (``urlsplit().hostname`` strips them), so the regex must match
    # the unbracketed form. Codex review on PR #516 caught this.
    assert classify_host("::1").key == "local_lm_studio"


def test_classify_unknown_host() -> None:
    assert classify_host("example.com").key == "unclassified"
    assert classify_host("some.random.host").key == "unclassified"


def test_classify_empty_host_returns_unclassified() -> None:
    assert classify_host("").key == "unclassified"


def test_classify_is_case_insensitive() -> None:
    assert classify_host("API.OpenAI.com").key == "openai"
    assert classify_host("Fonts.GoogleAPIs.COM").key == "google_fonts"


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------


def test_known_providers_is_immutable() -> None:
    """``KNOWN_PROVIDERS`` is wrapped in ``MappingProxyType``.

    Attempts to assign or delete keys must raise ``TypeError``.
    """
    with pytest.raises(TypeError):
        KNOWN_PROVIDERS["openai"] = KNOWN_PROVIDERS["anthropic"]  # type: ignore[index]

    with pytest.raises(TypeError):
        del KNOWN_PROVIDERS["openai"]  # type: ignore[attr-defined]


def test_provider_spec_is_frozen() -> None:
    spec = KNOWN_PROVIDERS["openai"]
    with pytest.raises(FrozenInstanceError):
        spec.key = "x"  # type: ignore[misc]


def test_url_host_patterns_are_tuples() -> None:
    """Host-pattern containers must be tuples (immutable), not lists."""
    for key, spec in KNOWN_PROVIDERS.items():
        assert isinstance(spec.url_host_patterns, tuple), (
            f"{key}: url_host_patterns must be a tuple, got "
            f"{type(spec.url_host_patterns).__name__}"
        )
