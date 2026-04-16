"""Tests for metis_app.services.knowledge_cache."""

from unittest.mock import patch

import pytest

from metis_app.services.knowledge_cache import (
    QueryResultCache,
    _cache_key,
    _SCHEMA_VERSION,
)

# ---------------------------------------------------------------------------
# _cache_key
# ---------------------------------------------------------------------------

def test_cache_key_is_deterministic():
    k1 = _cache_key("What is X?", "openai", "idx-1")
    k2 = _cache_key("What is X?", "openai", "idx-1")
    assert k1 == k2


def test_cache_key_is_hex_64_chars():
    k = _cache_key("question", "provider", "index")
    assert len(k) == 64
    assert all(c in "0123456789abcdef" for c in k)


def test_cache_key_differs_on_different_question():
    k1 = _cache_key("abc", "p", "i")
    k2 = _cache_key("def", "p", "i")
    assert k1 != k2


def test_cache_key_differs_on_different_provider():
    k1 = _cache_key("q", "openai", "i")
    k2 = _cache_key("q", "anthropic", "i")
    assert k1 != k2


def test_cache_key_differs_on_different_index_id():
    k1 = _cache_key("q", "p", "index-a")
    k2 = _cache_key("q", "p", "index-b")
    assert k1 != k2


# ---------------------------------------------------------------------------
# build() classmethod
# ---------------------------------------------------------------------------

def test_build_uses_ttl_from_settings(tmp_path):
    settings = {
        "cache_dir": str(tmp_path / "cache"),
        "knowledge_cache_ttl_hours": 48,
        "embedding_provider": "openai",
    }
    cache = QueryResultCache.build(settings, index_id="test")
    assert cache._ttl_hours == 48
    cache.close()


def test_build_defaults_ttl_when_missing(tmp_path):
    settings = {"cache_dir": str(tmp_path / "cache")}
    cache = QueryResultCache.build(settings)
    # Should not raise; default TTL is applied
    assert cache._ttl_hours > 0
    cache.close()


# ---------------------------------------------------------------------------
# No-op when duckdb is absent
# ---------------------------------------------------------------------------

def test_get_returns_none_when_duckdb_missing(tmp_path):
    with patch(
        "metis_app.services.knowledge_cache._try_import_duckdb",
        return_value=None,
    ):
        cache = QueryResultCache(
            db_path=tmp_path / "cache.db",
            embedding_provider="openai",
        )
        assert cache.get("some question") is None
        cache.close()


def test_put_is_noop_when_duckdb_missing(tmp_path):
    with patch(
        "metis_app.services.knowledge_cache._try_import_duckdb",
        return_value=None,
    ):
        cache = QueryResultCache(db_path=tmp_path / "cache.db")
        # Should not raise
        cache.put("question", {"answer": "42"})
        cache.close()


# ---------------------------------------------------------------------------
# Round-trip (requires duckdb)
# ---------------------------------------------------------------------------

@pytest.fixture()
def live_cache(tmp_path):
    pytest.importorskip("duckdb")
    cache = QueryResultCache(
        db_path=tmp_path / "cache.db",
        embedding_provider="openai",
        index_id="test-idx",
        ttl_hours=24,
    )
    yield cache
    cache.close()


def test_round_trip_put_get(live_cache):
    payload = {"chunks": ["a", "b"], "score": 0.9}
    live_cache.put("What is the answer?", payload)
    result = live_cache.get("What is the answer?")
    assert result == payload


def test_cache_miss_returns_none(live_cache):
    result = live_cache.get("a question that was never stored")
    assert result is None


def test_ttl_expiry_returns_none(tmp_path):
    pytest.importorskip("duckdb")
    cache = QueryResultCache(
        db_path=tmp_path / "ttl_cache.db",
        embedding_provider="openai",
        ttl_hours=0,  # immediately expired
    )
    cache.put("expired question", {"data": "value"})
    result = cache.get("expired question")
    cache.close()
    assert result is None


def test_schema_version_mismatch_returns_none(live_cache):
    """A cached entry with a different schema_ver is treated as a miss."""
    live_cache.put("schema question", {"data": "valid"})
    # Patch schema version to something different during get()
    with patch(
        "metis_app.services.knowledge_cache._SCHEMA_VERSION",
        _SCHEMA_VERSION + 99,
    ):
        result = live_cache.get("schema question")
    assert result is None


def test_invalidate_removes_entry(live_cache):
    live_cache.put("removable question", {"x": 1})
    live_cache.invalidate("removable question")
    assert live_cache.get("removable question") is None


def test_purge_expired_returns_non_negative_int(live_cache):
    count = live_cache.purge_expired()
    assert isinstance(count, int)
    assert count >= 0


# ---------------------------------------------------------------------------
# close() idempotency
# ---------------------------------------------------------------------------

def test_close_multiple_times_no_error(tmp_path):
    cache = QueryResultCache(db_path=tmp_path / "c.db")
    cache.close()
    cache.close()  # second call must not raise
