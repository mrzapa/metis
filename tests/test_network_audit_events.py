"""Tests for ``metis_app.network_audit.events`` (Phase 2 of M17).

Pins the privacy-invariant URL sanitiser and the runtime enforcement
on :class:`NetworkAuditEvent.query_params_stored`. See
``docs/adr/0011-network-audit-retention.md`` for the rationale behind
each assertion — relaxing any of these is a privacy regression.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from metis_app.network_audit import NetworkAuditEvent, sanitize_url


# ---------------------------------------------------------------------------
# sanitize_url — privacy invariants
# ---------------------------------------------------------------------------


def test_sanitize_url_strips_query_params() -> None:
    """An ``api_key=SECRET`` query parameter never reaches the returned tuple."""
    url = "https://api.openai.com/v1/chat/completions?api_key=SECRET&prompt=foo"
    host, path = sanitize_url(url)
    assert host == "api.openai.com"
    assert path == "/v1"
    # Defence in depth: neither the secret nor the prompt appears anywhere.
    assert "SECRET" not in host + path
    assert "prompt" not in host + path
    assert "api_key" not in host + path


def test_sanitize_url_strips_path_beyond_prefix() -> None:
    """Only the first path segment survives."""
    host, path = sanitize_url("https://api.openai.com/v1/chat/completions")
    assert host == "api.openai.com"
    assert path == "/v1"
    # The full path MUST NOT leak.
    assert "chat" not in path
    assert "completions" not in path


def test_sanitize_url_strips_userinfo() -> None:
    """Embedded userinfo (``user:pass@``) is dropped along with the port."""
    host, path = sanitize_url("https://user:pass@example.com/foo")
    assert host == "example.com"
    assert path == "/foo"
    assert "user" not in host
    assert "pass" not in host


def test_sanitize_url_strips_port() -> None:
    """Port is stripped from the host."""
    host, path = sanitize_url("http://localhost:1234/v1/x")
    assert host == "localhost"
    assert path == "/v1"
    assert "1234" not in host


def test_sanitize_url_lowercases_host() -> None:
    """Host is lowercased; path case is preserved."""
    host, path = sanitize_url("https://API.OpenAI.COM/V1")
    assert host == "api.openai.com"
    assert path == "/V1"


def test_sanitize_url_handles_root_path() -> None:
    """Empty / root paths collapse to ``/``."""
    assert sanitize_url("https://huggingface.co") == ("huggingface.co", "/")
    assert sanitize_url("https://huggingface.co/") == ("huggingface.co", "/")


def test_sanitize_url_handles_ipv6_host() -> None:
    """IPv6 hosts (bracketed in the URL) come back un-bracketed."""
    host, path = sanitize_url("https://[::1]:8080/v1/chat")
    assert host == "::1"
    assert path == "/v1"


def test_sanitize_url_handles_no_path() -> None:
    """Hostname with no trailing slash collapses to ``/``."""
    assert sanitize_url("https://example.com") == ("example.com", "/")


def test_sanitize_url_handles_hackernews() -> None:
    """HackerNews firebase URL — documented example."""
    assert sanitize_url("https://hacker-news.firebaseio.com/v0/topstories.json") == (
        "hacker-news.firebaseio.com",
        "/v0",
    )


def test_sanitize_url_handles_reddit() -> None:
    """Reddit subreddit URL — subreddit name is dropped."""
    host, path = sanitize_url("https://www.reddit.com/r/LocalLLaMA/hot.json")
    assert host == "www.reddit.com"
    assert path == "/r"
    # The subreddit name MUST NOT leak through.
    assert "LocalLLaMA" not in path


def test_sanitize_url_handles_fonts_cdn() -> None:
    """Google Fonts CDN with query — only the ``/css2`` segment survives."""
    assert sanitize_url("https://fonts.googleapis.com/css2?family=Inter") == (
        "fonts.googleapis.com",
        "/css2",
    )
    # The font family never reaches disk.
    assert "Inter" not in "/".join(sanitize_url("https://fonts.googleapis.com/css2?family=Inter"))


def test_sanitize_url_handles_malformed_string() -> None:
    """Unparseable input collapses to the sentinel."""
    assert sanitize_url("not a url") == ("unknown", "/")
    assert sanitize_url("") == ("unknown", "/")
    assert sanitize_url("   ") == ("unknown", "/")


def test_sanitize_url_handles_url_with_no_scheme() -> None:
    """A bare host (no scheme) has no parseable hostname and collapses."""
    # urlsplit of a no-scheme URL yields hostname=None.
    assert sanitize_url("example.com/foo") == ("unknown", "/")


def test_sanitize_url_rejects_non_string() -> None:
    """Non-string input is treated as malformed."""
    # noinspection PyTypeChecker
    assert sanitize_url(None) == ("unknown", "/")  # type: ignore[arg-type]
    # noinspection PyTypeChecker
    assert sanitize_url(12345) == ("unknown", "/")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# NetworkAuditEvent — frozen + runtime invariants
# ---------------------------------------------------------------------------


def _good_event() -> NetworkAuditEvent:
    """Return a minimal well-formed event. Helper for several tests below."""
    return NetworkAuditEvent(
        id="01HVTESTTESTTESTTESTTESTXX",
        timestamp=datetime.now(timezone.utc),
        method="GET",
        url_host="api.openai.com",
        url_path_prefix="/v1",
        query_params_stored=False,
        provider_key="openai",
        trigger_feature="unit_test",
        size_bytes_in=123,
        size_bytes_out=None,
        latency_ms=45,
        status_code=200,
        user_initiated=False,
        blocked=False,
    )


def test_network_audit_event_is_frozen() -> None:
    """Mutating any field raises FrozenInstanceError."""
    event = _good_event()
    with pytest.raises(FrozenInstanceError):
        event.blocked = True  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        event.url_path_prefix = "/v2"  # type: ignore[misc]


def test_network_audit_event_query_params_stored_invariant() -> None:
    """Constructing with ``query_params_stored=True`` raises."""
    with pytest.raises(ValueError, match="query_params_stored"):
        NetworkAuditEvent(
            id="01HVTESTTESTTESTTESTTESTXX",
            timestamp=datetime.now(timezone.utc),
            method="GET",
            url_host="api.openai.com",
            url_path_prefix="/v1",
            query_params_stored=True,  # type: ignore[arg-type]
            provider_key="openai",
            trigger_feature="unit_test",
            size_bytes_in=None,
            size_bytes_out=None,
            latency_ms=None,
            status_code=None,
            user_initiated=False,
            blocked=False,
        )


def test_network_audit_event_requires_tz_aware_timestamp() -> None:
    """A naive ``datetime`` is rejected by ``__post_init__``."""
    with pytest.raises(ValueError, match="timezone-aware"):
        NetworkAuditEvent(
            id="01HVTESTTESTTESTTESTTESTXX",
            timestamp=datetime(2026, 4, 19, 12, 0, 0),  # naive — no tz.
            method="GET",
            url_host="api.openai.com",
            url_path_prefix="/v1",
            query_params_stored=False,
            provider_key="openai",
            trigger_feature="unit_test",
            size_bytes_in=None,
            size_bytes_out=None,
            latency_ms=None,
            status_code=None,
            user_initiated=False,
            blocked=False,
        )


def test_network_audit_event_has_slots() -> None:
    """``slots=True`` is on — no per-instance __dict__."""
    event = _good_event()
    assert not hasattr(event, "__dict__")


def test_network_audit_event_round_trip_uses_sanitized_fields() -> None:
    """Constructing an event from sanitize_url output gives the documented shape.

    This is the spec's serialisation invariant: a URL with secrets in
    the query string round-trips as host + first-path-segment only.
    """
    url = "https://api.openai.com/v1/chat/completions?api_key=SECRET&prompt=foo"
    host, path = sanitize_url(url)
    event = NetworkAuditEvent(
        id="01HVTESTTESTTESTTESTTESTXX",
        timestamp=datetime.now(timezone.utc),
        method="POST",
        url_host=host,
        url_path_prefix=path,
        query_params_stored=False,
        provider_key="openai",
        trigger_feature="unit_test",
        size_bytes_in=None,
        size_bytes_out=None,
        latency_ms=None,
        status_code=None,
        user_initiated=False,
        blocked=False,
    )
    assert event.url_host == "api.openai.com"
    assert event.url_path_prefix == "/v1"
    # The ordering invariant holds: no secret, no prompt, no completions.
    for field_value in (event.url_host, event.url_path_prefix):
        assert "SECRET" not in field_value
        assert "prompt" not in field_value
        assert "completions" not in field_value
