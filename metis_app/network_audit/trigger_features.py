"""Named ``trigger_feature`` values for :func:`audited_urlopen`.

Each call site in :mod:`metis_app` passes one of these constants to
the wrapper so the audit panel can group events by the feature that
caused them. Phase 4 will add SDK-invocation trigger strings
(LangChain providers); Phase 5's Pro-tier features add more. Keep this
file in sync with the audit panel's filter UI.

The wrapper's ``trigger_feature`` kwarg is typed as ``str`` rather
than an ``Enum`` because many call sites read from settings or tag
dynamically — passing a bare string constant keeps the signature
ergonomic for both static (``TRIGGER_*``) and dynamic (computed-key)
callers.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# News ingestion (M13's pipeline — see metis_app/services/news_ingest_service.py)
# ---------------------------------------------------------------------------
# RSS uses feedparser.parse() (its own HTTP layer), not stdlib urlopen;
# this constant is reserved for a Phase 4 feedparser SDK wrap.
TRIGGER_NEWS_COMET_RSS = "news_comet_rss"
TRIGGER_NEWS_COMET_HACKERNEWS = "news_comet_hackernews"
TRIGGER_NEWS_COMET_REDDIT = "news_comet_reddit"

# ---------------------------------------------------------------------------
# UI component catalog (see metis_app/services/nyx_catalog.py)
# ---------------------------------------------------------------------------
TRIGGER_NYX_REGISTRY = "nyx_registry"

# ---------------------------------------------------------------------------
# Model hub / downloads
# ---------------------------------------------------------------------------
# GGUF download — metis_app/services/local_llm_recommender.py download_import.
TRIGGER_GGUF_DOWNLOAD = "gguf_download"
# Hugging Face catalog API — metis_app/services/local_llm_recommender.py _read_json.
TRIGGER_HF_CATALOG = "huggingface_catalog"
# TRIBE v2 snapshot download — metis_app/services/brain_pass.py.
TRIGGER_TRIBEV2_SNAPSHOT = "tribev2_snapshot"

# ---------------------------------------------------------------------------
# Web search (autonomous or user-initiated — see metis_app/utils/web_search.py)
# ---------------------------------------------------------------------------
TRIGGER_WEB_SEARCH_DUCKDUCKGO = "web_search_duckduckgo"
TRIGGER_WEB_SEARCH_JINA_READER = "web_search_jina_reader"


__all__ = [
    "TRIGGER_GGUF_DOWNLOAD",
    "TRIGGER_HF_CATALOG",
    "TRIGGER_NEWS_COMET_HACKERNEWS",
    "TRIGGER_NEWS_COMET_REDDIT",
    "TRIGGER_NEWS_COMET_RSS",
    "TRIGGER_NYX_REGISTRY",
    "TRIGGER_TRIBEV2_SNAPSHOT",
    "TRIGGER_WEB_SEARCH_DUCKDUCKGO",
    "TRIGGER_WEB_SEARCH_JINA_READER",
]
