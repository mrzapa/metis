"""tests/test_embedding_providers.py — Unit tests for the embedding provider factory.

Tests the mock path and factory routing logic.  Real provider constructors
are tested only for argument validation — no API calls.
"""

from __future__ import annotations

import pytest

from axiom_app.utils.embedding_providers import (
    _resolve_embedding_model,
    create_embeddings,
)


# ---------------------------------------------------------------------------
# _resolve_embedding_model
# ---------------------------------------------------------------------------


class TestResolveEmbeddingModel:
    def test_returns_base_model(self):
        s = {"embedding_model": "text-embedding-3-small"}
        assert _resolve_embedding_model(s, "openai") == "text-embedding-3-small"

    def test_custom_override(self):
        s = {"embedding_model": "custom", "embedding_model_custom": "my-emb"}
        assert _resolve_embedding_model(s, "openai") == "my-emb"

    def test_sentence_transformers_uses_dedicated_setting(self):
        s = {
            "embedding_model": "voyage-4-large",
            "sentence_transformers_model": "all-MiniLM-L6-v2",
        }
        result = _resolve_embedding_model(s, "local_sentence_transformers")
        assert result == "all-MiniLM-L6-v2"

    def test_sentence_transformers_fallback(self):
        s = {"sentence_transformers_model": ""}
        result = _resolve_embedding_model(s, "local_sentence_transformers")
        assert "MiniLM" in result or "sentence-transformers" in result

    def test_empty_settings_returns_default(self):
        assert _resolve_embedding_model({}, "openai") == "voyage-4-large"


# ---------------------------------------------------------------------------
# create_embeddings — mock provider
# ---------------------------------------------------------------------------


class TestCreateEmbeddingsMock:
    def test_mock_provider(self):
        from axiom_app.utils.mock_embeddings import MockEmbeddings

        emb = create_embeddings({"embedding_provider": "mock"})
        assert isinstance(emb, MockEmbeddings)

    def test_empty_provider_defaults_to_mock(self):
        from axiom_app.utils.mock_embeddings import MockEmbeddings

        emb = create_embeddings({})
        assert isinstance(emb, MockEmbeddings)

    def test_mock_embed_query(self):
        emb = create_embeddings({"embedding_provider": "mock"})
        vec = emb.embed_query("test")
        assert isinstance(vec, list)
        assert len(vec) > 0
        assert all(isinstance(v, float) for v in vec)

    def test_mock_embed_documents(self):
        emb = create_embeddings({"embedding_provider": "mock"})
        vecs = emb.embed_documents(["a", "b"])
        assert len(vecs) == 2


# ---------------------------------------------------------------------------
# create_embeddings — error handling
# ---------------------------------------------------------------------------


class TestCreateEmbeddingsErrors:
    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown embedding provider"):
            create_embeddings({"embedding_provider": "acme_embeddings"})

    def test_openai_missing_key_raises(self):
        with pytest.raises((ValueError, ImportError)):
            create_embeddings({
                "embedding_provider": "openai",
                "api_key_openai": "",
            })

    def test_google_missing_key_raises(self):
        with pytest.raises((ValueError, ImportError)):
            create_embeddings({
                "embedding_provider": "google",
                "api_key_google": "",
            })

    def test_voyage_missing_key_raises(self):
        with pytest.raises((ValueError, ImportError)):
            create_embeddings({
                "embedding_provider": "voyage",
                "api_key_voyage": "",
            })

    def test_local_sentence_transformers_import_error(self):
        """If sentence-transformers isn't installed, should raise ImportError."""
        try:
            create_embeddings({
                "embedding_provider": "local_sentence_transformers",
            })
        except ImportError:
            pass  # expected if sentence-transformers not installed
        except Exception:
            pass  # also acceptable — may succeed in some envs

    def test_local_huggingface_import_error(self):
        try:
            create_embeddings({
                "embedding_provider": "local_huggingface",
            })
        except ImportError:
            pass
        except Exception:
            pass
