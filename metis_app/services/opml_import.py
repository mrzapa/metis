"""OPML import for news-comet feeds (ADR 0008 §5).

The only sanctioned XML parser is :mod:`defusedxml.ElementTree` per
ADR 0008. The bare stdlib :mod:`xml.etree` does not expose a clean
knob to disable DTD/external-entity expansion across all supported
Python versions; relying on transitive ``defusedxml`` from
``langchain-core`` is a coin flip on environment resolution. We
declare ``defusedxml`` as a real dependency so the parser is
predictable.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from urllib.parse import urlparse

from defusedxml import ElementTree as DET  # type: ignore[import-untyped]

log = logging.getLogger(__name__)


class OpmlImportError(ValueError):
    """Raised when the OPML payload cannot be parsed or contains no feeds."""


@dataclass(frozen=True, slots=True)
class OpmlImportResult:
    added: list[str]
    skipped_duplicate: list[str]
    skipped_invalid: list[str]
    errors: list[str]

    def to_payload(self) -> dict[str, object]:
        return {
            "added": len(self.added),
            "added_urls": self.added,
            "skipped_duplicate": len(self.skipped_duplicate),
            "skipped_invalid": len(self.skipped_invalid),
            "errors": self.errors,
        }


_RSS_TYPES: frozenset[str] = frozenset({"rss", "atom", ""})


def parse_opml(payload: bytes | str) -> list[str]:
    """Return the unique ``xmlUrl`` values from an OPML document.

    Outlines without ``xmlUrl`` are ignored. Only outlines whose
    ``type`` attribute is ``rss``, ``atom``, or absent are accepted —
    other outline types (folders, web links) are skipped without error.
    Raises :class:`OpmlImportError` if the document is not parseable
    XML or has no recognisable ``xmlUrl`` entries at all.
    """
    if isinstance(payload, bytes):
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise OpmlImportError("OPML payload is not valid UTF-8") from exc
    else:
        text = payload

    try:
        root = DET.fromstring(text)
    except DET.ParseError as exc:
        raise OpmlImportError(f"OPML XML is malformed: {exc}") from exc

    if root.tag.split("}", 1)[-1].lower() != "opml":
        raise OpmlImportError("Document root is not <opml>")

    seen: set[str] = set()
    urls: list[str] = []
    for outline in root.iter():
        # ElementTree namespace-aware tag is "{ns}name" — strip
        if outline.tag.split("}", 1)[-1].lower() != "outline":
            continue
        outline_type = (outline.get("type") or "").strip().lower()
        if outline_type not in _RSS_TYPES:
            continue
        url = (outline.get("xmlUrl") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        urls.append(url)

    if not urls:
        raise OpmlImportError("OPML contains no xmlUrl entries")
    return urls


def is_safe_feed_url(url: str) -> bool:
    """Reject obviously unsafe feed URLs before they reach the cursor table.

    Mirrors the SSRF gate posture of
    :func:`metis_app.services.news_ingest_service._safe_get`: only HTTP
    and HTTPS, with a hostname. Loopback / private-RFC1918 / link-local
    rejection is left to ``audited_urlopen``'s existing checks at fetch
    time so we do not duplicate that policy here; this function is a
    cheap shape check at import time.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    if not parsed.hostname:
        return False
    return True


def merge_feed_urls(
    existing: list[str], incoming: list[str]
) -> tuple[list[str], list[str], list[str]]:
    """Merge *incoming* into *existing* without duplicates.

    Returns ``(added, skipped_duplicate, skipped_invalid)`` so the
    caller can report counts back through the API. Comparison is
    case-sensitive and exact; duplicate detection does not normalize
    the URL because the user's intent (keep both feeds) should win
    over a heuristic.
    """
    known: set[str] = set(existing)
    added: list[str] = []
    skipped_duplicate: list[str] = []
    skipped_invalid: list[str] = []
    for url in incoming:
        if not is_safe_feed_url(url):
            skipped_invalid.append(url)
            continue
        if url in known:
            skipped_duplicate.append(url)
            continue
        known.add(url)
        added.append(url)
    return added, skipped_duplicate, skipped_invalid
