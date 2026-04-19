"""Known-provider registry for the M17 Network Audit panel.

This module is *purely declarative*. It lists every outbound destination
that METIS can talk to today (as catalogued in the Phase 1 inventory in
``plans/network-audit/plan.md``) and names the existing kill-switch
setting (if any) that already blocks each one.

The registry is consumed by:

- ``metis_app/network_audit/client.py`` (Phase 3 — not yet landed) to
  label every ``NetworkAuditEvent`` with a provider key.
- ``metis_app/network_audit/kill_switches.py`` (Phase 3+) to look up the
  setting key that controls a given provider.
- ``metis_app/api_litestar/routes/network_audit.py`` (Phase 5) to
  populate the panel's provider matrix.

**Design notes.**

- ``ProviderSpec`` is frozen and slotted. Registry entries are
  effectively constants and must not be mutated at runtime.
- ``KNOWN_PROVIDERS`` is wrapped in ``types.MappingProxyType`` so that
  accidental ``KNOWN_PROVIDERS["openai"] = ...`` raises at runtime.
- ``classify_host`` returns the *first* matching entry. For hosts
  shared between providers (notably ``api.openai.com`` for ``openai``
  and ``openai_embeddings``), the iteration order of this dict decides
  the classification. Per-trigger classification is a v2 concern
  tracked in ``docs/adr/0010-network-audit-interception.md``.
- Loopback providers (``local_lm_studio``, ``huggingface_local``) are
  listed intentionally so the audit panel can show "zero loopback
  calls too" during airplane-mode verification. See inline comments.

This file is authored by hand. Do not generate it from a vendored
inventory; the inventory in the plan is the source of truth and this
module must be kept in sync by hand when a new provider is added.
"""

from __future__ import annotations

import re
import types
from dataclasses import dataclass
from typing import Literal, Mapping

ProviderCategory = Literal[
    "llm",
    "embeddings",
    "ingestion",
    "search",
    "model_hub",
    "vector_db",
    "fonts_cdn",
    "other",
]


@dataclass(frozen=True, slots=True)
class ProviderSpec:
    """Declarative spec for one known outbound provider.

    Attributes:
        key: Canonical provider identifier. Must match the key used in
            ``KNOWN_PROVIDERS``.
        display_name: Human-readable label for the audit panel UI.
        url_host_patterns: Tuple of pre-compiled regex patterns. A host
            matches this provider iff at least one pattern matches.
            Patterns are anchored (``^...$``) against the hostname; path
            and scheme are not considered.
        kill_switch_setting_key: Name of the settings.json key that
            already gates this provider's traffic today, or ``None`` if
            no such setting exists (a new one will be introduced in a
            later phase — notably ``provider_block_llm`` in Phase 4).
        category: Broad grouping for the audit panel's filter tabs.
    """

    key: str
    display_name: str
    url_host_patterns: tuple[re.Pattern[str], ...]
    kill_switch_setting_key: str | None
    category: ProviderCategory


# Convenience: a compiled pattern that matches nothing.
# Used for the ``unclassified`` fallback so ``classify_host`` logic is
# uniform (iterate, match, fall through to unclassified).
_MATCH_NOTHING: tuple[re.Pattern[str], ...] = ()


def _host(*patterns: str) -> tuple[re.Pattern[str], ...]:
    """Compile the given host regex strings with IGNORECASE."""
    return tuple(re.compile(p, re.IGNORECASE) for p in patterns)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
#
# Ordering matters for ``classify_host``: the first matching entry wins.
# Keep SDK-level LLM/embedding providers before any broader catch-all so
# a shared-host case (e.g. api.openai.com for both chat + embeddings)
# resolves to the chat entry by default. The Phase 4 invocation-layer
# emitter attaches the correct provider key directly, bypassing
# host-only classification for SDK calls.

_REGISTRY: dict[str, ProviderSpec] = {
    # ------------------------------------------------------------------
    # LLM providers (LangChain SDK call sites, rows A-E in the plan)
    # ------------------------------------------------------------------
    "openai": ProviderSpec(
        key="openai",
        display_name="OpenAI",
        url_host_patterns=_host(r"^api\.openai\.com$"),
        # No existing kill switch; Phase 4 adds provider_block_llm.openai.
        kill_switch_setting_key=None,
        category="llm",
    ),
    "anthropic": ProviderSpec(
        key="anthropic",
        display_name="Anthropic",
        url_host_patterns=_host(r"^api\.anthropic\.com$"),
        kill_switch_setting_key=None,
        category="llm",
    ),
    "google": ProviderSpec(
        key="google",
        display_name="Google GenAI",
        url_host_patterns=_host(r"^generativelanguage\.googleapis\.com$"),
        kill_switch_setting_key=None,
        category="llm",
    ),
    "xai": ProviderSpec(
        key="xai",
        display_name="xAI",
        url_host_patterns=_host(r"^api\.x\.ai$"),
        kill_switch_setting_key=None,
        category="llm",
    ),
    # Loopback by default, but the user can rebind LM Studio to a
    # non-loopback interface. Event-time classification in Phase 3
    # re-checks the concrete URL; if the host slips the loopback
    # pattern it will hit ``unclassified`` and the panel will
    # surface it as an unexpected remote call. Intentional.
    "local_lm_studio": ProviderSpec(
        key="local_lm_studio",
        display_name="LM Studio (local)",
        url_host_patterns=_host(
            r"^localhost$",
            r"^127\.0\.0\.1$",
            r"^\[::1\]$",
        ),
        kill_switch_setting_key=None,
        category="llm",
    ),
    # ------------------------------------------------------------------
    # Embedding providers (rows F-I in the plan)
    # ------------------------------------------------------------------
    # INVARIANT: ``openai_embeddings`` MUST stay after ``openai`` above
    # (and ``google_embeddings`` MUST stay after ``google``). Host-only
    # classification returns first-insertion-order match; alphabetising
    # this dict silently flips classification. Pinned by
    # tests/test_network_audit_providers.py::test_classify_openai_api
    # and ::test_classify_google_genai. SDK-invocation events attach
    # ``openai_embeddings`` / ``google_embeddings`` directly in Phase 4.
    # See ADR 0010.
    "openai_embeddings": ProviderSpec(
        key="openai_embeddings",
        display_name="OpenAI Embeddings",
        url_host_patterns=_host(r"^api\.openai\.com$"),
        kill_switch_setting_key=None,
        category="embeddings",
    ),
    "google_embeddings": ProviderSpec(
        key="google_embeddings",
        display_name="Google GenAI Embeddings",
        url_host_patterns=_host(r"^generativelanguage\.googleapis\.com$"),
        kill_switch_setting_key=None,
        category="embeddings",
    ),
    "voyage": ProviderSpec(
        key="voyage",
        display_name="Voyage AI",
        url_host_patterns=_host(r"^api\.voyageai\.com$"),
        kill_switch_setting_key=None,
        category="embeddings",
    ),
    # Loopback once the local model cache is populated. If the user
    # has never downloaded the model, a first-run fetch hits
    # huggingface.co (which is covered by the huggingface_hub entry).
    "huggingface_local": ProviderSpec(
        key="huggingface_local",
        display_name="HuggingFace Embeddings (local)",
        url_host_patterns=_host(
            r"^localhost$",
            r"^127\.0\.0\.1$",
            r"^\[::1\]$",
        ),
        kill_switch_setting_key=None,
        category="embeddings",
    ),
    # ------------------------------------------------------------------
    # Search providers (rows 8-9 stdlib + row J SDK)
    # ------------------------------------------------------------------
    # Both autonomous research and user-initiated web search can hit
    # DuckDuckGo. The autonomous-research kill switch is the stricter
    # gate and the one the panel should re-expose; per-trigger
    # classification is v2 per ADR 0010.
    "duckduckgo": ProviderSpec(
        key="duckduckgo",
        display_name="DuckDuckGo",
        url_host_patterns=_host(
            r"^api\.duckduckgo\.com$",
            r"^duckduckgo\.com$",
        ),
        kill_switch_setting_key="autonomous_research_enabled",
        category="search",
    ),
    "jina_reader": ProviderSpec(
        key="jina_reader",
        display_name="Jina Reader",
        url_host_patterns=_host(r"^r\.jina\.ai$"),
        kill_switch_setting_key=None,
        category="search",
    ),
    # Tavily is the default autonomous-research provider when an API
    # key is configured. The ``autonomous_research_provider`` setting
    # pointing at anything other than ``tavily`` routes around this
    # provider de facto.
    "tavily": ProviderSpec(
        key="tavily",
        display_name="Tavily",
        url_host_patterns=_host(r"^api\.tavily\.com$"),
        kill_switch_setting_key="autonomous_research_provider",
        category="search",
    ),
    # ------------------------------------------------------------------
    # Ingestion providers (news comets — rows 1-4)
    # ------------------------------------------------------------------
    # RSS feeds are user-configured (``news_comet_rss_feeds``) and can
    # point at any host. The registry cannot enumerate them; an empty
    # pattern tuple means ``classify_host`` will never return this
    # entry automatically. The wrapper will attach ``provider="rss_feed"``
    # at the call site in Phase 3 where the caller knows it is an RSS
    # fetch. The panel still shows the entry (and its kill switch) in
    # the provider matrix.
    "rss_feed": ProviderSpec(
        key="rss_feed",
        display_name="RSS feeds (user-configured)",
        url_host_patterns=_MATCH_NOTHING,
        kill_switch_setting_key="news_comets_enabled",
        category="ingestion",
    ),
    "hackernews_api": ProviderSpec(
        key="hackernews_api",
        display_name="Hacker News API",
        url_host_patterns=_host(r"^hacker-news\.firebaseio\.com$"),
        kill_switch_setting_key="news_comets_enabled",
        category="ingestion",
    ),
    "reddit_api": ProviderSpec(
        key="reddit_api",
        display_name="Reddit API",
        url_host_patterns=_host(r"^(www\.|old\.)?reddit\.com$"),
        kill_switch_setting_key="news_comets_enabled",
        category="ingestion",
    ),
    # ------------------------------------------------------------------
    # Model hub (rows 6, 7, 10)
    # ------------------------------------------------------------------
    "huggingface_hub": ProviderSpec(
        key="huggingface_hub",
        display_name="Hugging Face Hub",
        url_host_patterns=_host(
            r"^huggingface\.co$",
            r"^.*\.huggingface\.co$",
        ),
        # Gated at the UX layer (the "install model" confirmation) in
        # Phase 6. No single settings.json key today.
        kill_switch_setting_key=None,
        category="model_hub",
    ),
    # ------------------------------------------------------------------
    # Vector DB (row K)
    # ------------------------------------------------------------------
    # Weaviate URL is user-provided. We use a broad pattern that matches
    # any host containing the literal "weaviate" and accept false
    # negatives for custom-named deployments; the wrapper will attach
    # ``provider="weaviate"`` at the call site in Phase 3. The setting
    # key's empty-string semantics (empty = disabled) is the de facto
    # kill switch.
    "weaviate": ProviderSpec(
        key="weaviate",
        display_name="Weaviate (self-hosted)",
        url_host_patterns=_host(r".*weaviate.*"),
        kill_switch_setting_key="weaviate_url",
        category="vector_db",
    ),
    # ------------------------------------------------------------------
    # Other (stdlib row 5)
    # ------------------------------------------------------------------
    "nyx_registry": ProviderSpec(
        key="nyx_registry",
        display_name="Nyx UI Registry",
        url_host_patterns=_host(r"^nyxui\.com$"),
        kill_switch_setting_key=None,
        category="other",
    ),
    # ------------------------------------------------------------------
    # Frontend / CDN (row L)
    # ------------------------------------------------------------------
    # The plan's Phase 1 flags this for inlining. Until that lands,
    # the audit panel honestly lists google_fonts as an outbound
    # provider (the @import in apps/metis-web/app/page.tsx:5309
    # phones home on first page load).
    "google_fonts": ProviderSpec(
        key="google_fonts",
        display_name="Google Fonts (CDN)",
        url_host_patterns=_host(
            r"^fonts\.googleapis\.com$",
            r"^fonts\.gstatic\.com$",
        ),
        kill_switch_setting_key=None,
        category="fonts_cdn",
    ),
    # ------------------------------------------------------------------
    # Fallback — always last
    # ------------------------------------------------------------------
    "unclassified": ProviderSpec(
        key="unclassified",
        display_name="Unclassified",
        url_host_patterns=_MATCH_NOTHING,
        kill_switch_setting_key=None,
        category="other",
    ),
}


KNOWN_PROVIDERS: Mapping[str, ProviderSpec] = types.MappingProxyType(_REGISTRY)
"""Immutable mapping of provider key -> :class:`ProviderSpec`."""


def classify_host(host: str) -> ProviderSpec:
    """Return the first provider spec whose host pattern matches ``host``.

    Host comparison is case-insensitive (patterns are compiled with
    ``re.IGNORECASE``) and anchored (patterns use ``^...$``). Path and
    scheme are not considered; callers holding a full URL should pass
    only the ``urlparse(url).hostname`` slice.

    Returns the ``unclassified`` entry if no pattern matches — never
    raises. Callers can compare the returned ``.key`` against
    ``"unclassified"`` to decide whether a host is known.
    """
    if host:
        for spec in _REGISTRY.values():
            for pattern in spec.url_host_patterns:
                if pattern.match(host):
                    return spec
    return _REGISTRY["unclassified"]


__all__ = [
    "KNOWN_PROVIDERS",
    "ProviderCategory",
    "ProviderSpec",
    "classify_host",
]
