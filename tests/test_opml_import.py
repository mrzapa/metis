"""Tests for OPML parsing and merge helpers (ADR 0008 §5)."""

from __future__ import annotations

import pytest

from metis_app.services.opml_import import (
    OpmlImportError,
    is_safe_feed_url,
    merge_feed_urls,
    parse_opml,
)


_VALID_OPML = """<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
  <head><title>Subscriptions</title></head>
  <body>
    <outline title="News">
      <outline type="rss" text="Hacker News" xmlUrl="https://news.ycombinator.com/rss" />
      <outline type="atom" text="Lobsters" xmlUrl="https://lobste.rs/rss" />
    </outline>
    <outline type="rss" text="LWN" xmlUrl="https://lwn.net/headlines/rss" />
  </body>
</opml>
"""


def test_parse_opml_extracts_xml_urls() -> None:
    urls = parse_opml(_VALID_OPML)
    assert urls == [
        "https://news.ycombinator.com/rss",
        "https://lobste.rs/rss",
        "https://lwn.net/headlines/rss",
    ]


def test_parse_opml_accepts_bytes() -> None:
    urls = parse_opml(_VALID_OPML.encode("utf-8"))
    assert len(urls) == 3


def test_parse_opml_rejects_non_opml_root() -> None:
    with pytest.raises(OpmlImportError, match="not <opml>"):
        parse_opml("<rss><channel/></rss>")


def test_parse_opml_rejects_malformed_xml() -> None:
    with pytest.raises(OpmlImportError, match="malformed"):
        parse_opml("<opml><body><outline xmlUrl='https://x'><<")


def test_parse_opml_rejects_no_xml_url() -> None:
    payload = """<?xml version="1.0"?>
    <opml><body>
      <outline title="A folder" type="folder">
        <outline title="Just text"/>
      </outline>
    </body></opml>"""
    with pytest.raises(OpmlImportError, match="no xmlUrl"):
        parse_opml(payload)


def test_parse_opml_skips_unknown_outline_types() -> None:
    payload = """<?xml version="1.0"?>
    <opml><body>
      <outline type="link" url="https://example.com/about" text="not a feed" />
      <outline type="rss" xmlUrl="https://example.com/feed" />
    </body></opml>"""
    assert parse_opml(payload) == ["https://example.com/feed"]


def test_parse_opml_dedups_within_document() -> None:
    payload = """<?xml version="1.0"?>
    <opml><body>
      <outline type="rss" xmlUrl="https://x.com/feed" />
      <outline type="rss" xmlUrl="https://x.com/feed" />
    </body></opml>"""
    assert parse_opml(payload) == ["https://x.com/feed"]


def test_parse_opml_rejects_non_utf8_bytes() -> None:
    with pytest.raises(OpmlImportError, match="UTF-8"):
        parse_opml(b"\xff\xfe<opml/>")


# ---------------------------------------------------------------------------
# is_safe_feed_url
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://example.com/feed", True),
        ("http://example.com/feed", True),
        ("ftp://example.com/feed", False),
        ("file:///etc/passwd", False),
        ("https:///no-host", False),
        ("not-a-url", False),
        ("", False),
    ],
)
def test_is_safe_feed_url(url: str, expected: bool) -> None:
    assert is_safe_feed_url(url) is expected


# ---------------------------------------------------------------------------
# merge_feed_urls
# ---------------------------------------------------------------------------


def test_merge_feed_urls_dedups_against_existing() -> None:
    existing = ["https://x.com/feed", "https://y.com/feed"]
    incoming = [
        "https://x.com/feed",       # duplicate
        "https://z.com/feed",       # new
        "ftp://bad.com/feed",       # invalid
        "https://y.com/feed",       # duplicate
    ]
    added, dup, invalid = merge_feed_urls(existing, incoming)
    assert added == ["https://z.com/feed"]
    assert dup == ["https://x.com/feed", "https://y.com/feed"]
    assert invalid == ["ftp://bad.com/feed"]


def test_merge_feed_urls_handles_empty_inputs() -> None:
    added, dup, invalid = merge_feed_urls([], [])
    assert added == [] and dup == [] and invalid == []
