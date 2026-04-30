"""Forge "absorb a technique" pipeline (M14 Phase 4a).

Takes a URL the user paste-drops into the gallery, fetches the
referenced paper or page, cross-references its content against the
existing technique registry, and (when no close match exists)
asks the assistant's configured LLM to summarise the technique into
a structured ``TechniqueProposal`` the user can review.

ADR 0014 caps this scope: the proposal is a *document* (name,
claim, pillar guess, implementation sketch), never executable code.
The Forge does not run untrusted code from arXiv links.

Phase boundaries:

* **Phase 4a** (this module + the ``/v1/forge/absorb`` route): the
  fetch → cross-reference → LLM-summary loop. No persistence —
  the proposal is returned in the response and lost on reload.
* **Phase 4b** (deferred): persist proposals to ``forge_proposals.db``
  and add the review pane.
* **Phase 4c** (deferred): tie into the news-comet pipeline so
  high-score arxiv comets land in the proposal review pane
  automatically.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from metis_app.network_audit.client import NetworkBlockedError, audited_urlopen
from metis_app.network_audit.runtime import (
    get_default_settings,
    get_default_store,
)
from metis_app.services.forge_registry import (
    TechniqueDescriptor,
    get_registry,
)

log = logging.getLogger(__name__)

_TRIGGER_FORGE_ABSORB = "forge.absorb"
_HTTP_TIMEOUT = 12.0
_MAX_BODY_BYTES = 1_500_000  # arxiv abstracts are tiny; HTML pages cap at ~1.5 MB
_ARXIV_ATOM_NS = {"a": "http://www.w3.org/2005/Atom"}

_ARXIV_ID_PATTERNS = (
    # /abs/2501.12345 or /abs/2501.12345v2 or /abs/cs.AI/0501001
    re.compile(r"arxiv\.org/abs/([A-Za-z\.\-]+/\d{7}|\d{4}\.\d{4,5}(?:v\d+)?)", re.IGNORECASE),
    # /pdf/2501.12345.pdf or /pdf/2501.12345v3.pdf
    re.compile(r"arxiv\.org/pdf/(\d{4}\.\d{4,5}(?:v\d+)?)\.pdf", re.IGNORECASE),
)


# ── URL fetching ──────────────────────────────────────────────────


def _safe_get_bytes(url: str, *, timeout: float = _HTTP_TIMEOUT) -> bytes | None:
    """Fetch *url* through the M17 network-audit layer.

    Returns the response body on success, ``None`` on any error
    (bad URL, blocked by audit kill switch, network failure, oversized
    response). The caller decides what to do with ``None``; the
    pipeline collapses to an "error" result so the user sees a clear
    message rather than a 500.

    Mirrors the size-cap + timeout pattern from
    ``news_ingest_service._safe_get`` but uses its own ``trigger``
    so the audit panel attributes Forge fetches separately.
    """
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "METIS/1.0"})
        with audited_urlopen(
            req,
            trigger_feature=_TRIGGER_FORGE_ABSORB,
            user_initiated=True,
            timeout=timeout,
            store=get_default_store(),
            settings=get_default_settings(),
        ) as resp:
            return resp.read(_MAX_BODY_BYTES)
    except (urllib.error.URLError, NetworkBlockedError, OSError, ValueError) as exc:
        log.warning("Forge absorb fetch failed for %s: %s", url, exc)
        return None


# ── arXiv extractor ───────────────────────────────────────────────


def extract_arxiv_id(url: str) -> str | None:
    """Pull the arxiv ID out of an ``arxiv.org`` URL, ``None`` for
    everything else.

    Supports the three URL shapes the user is most likely to paste:
    ``/abs/<id>``, ``/abs/<id>v<N>``, ``/pdf/<id>.pdf``, plus the
    legacy ``/abs/<archive>/<id>`` form for pre-2007 papers.
    """
    for pattern in _ARXIV_ID_PATTERNS:
        match = pattern.search(url)
        if match:
            return match.group(1)
    return None


def fetch_arxiv_metadata(arxiv_id: str) -> dict[str, Any] | None:
    """Pull the title + abstract for *arxiv_id* from the arxiv API.

    The arxiv Atom feed is small, predictable, and free — much
    cheaper to parse than the full HTML page. Returns a dict with
    ``arxiv_id``, ``title``, ``summary``, ``source_url``, or
    ``None`` if the fetch or parse fails. Keeps the failure paths
    tight so the absorb pipeline can degrade gracefully.
    """
    api_url = f"https://export.arxiv.org/api/query?id_list={arxiv_id}"
    body = _safe_get_bytes(api_url)
    if body is None:
        return None
    try:
        # Lazy import — keeps the module's import cost low when the
        # absorb route isn't hit.
        import xml.etree.ElementTree as ET

        root = ET.fromstring(body)
    except ET.ParseError as exc:
        log.warning("arxiv API returned non-XML for %s: %s", arxiv_id, exc)
        return None

    entry = root.find("a:entry", _ARXIV_ATOM_NS)
    if entry is None:
        return None
    title = (entry.findtext("a:title", default="", namespaces=_ARXIV_ATOM_NS) or "").strip()
    summary = (entry.findtext("a:summary", default="", namespaces=_ARXIV_ATOM_NS) or "").strip()
    if not title and not summary:
        return None
    return {
        "arxiv_id": arxiv_id,
        "title": title,
        "summary": summary,
        "source_url": f"https://arxiv.org/abs/{arxiv_id}",
    }


# ── Cross-reference against the existing registry ─────────────────


def _tokens(text: str) -> set[str]:
    """Lowercase, alphanumeric word tokens longer than 3 characters."""
    return {
        word
        for word in re.findall(r"[A-Za-z0-9]+", text.lower())
        if len(word) > 3
    }


def _descriptor_keyword_set(descriptor: TechniqueDescriptor) -> set[str]:
    """Tokenised name + description for matching. Stop-words and the
    constant phrase "metis" / "forge" are dropped so the matcher
    isn't biased toward generic noise."""
    stop = {"metis", "forge", "this", "that", "with", "from", "into", "over", "your", "their", "user"}
    return _tokens(f"{descriptor.name} {descriptor.description}") - stop


def cross_reference_against_registry(text: str) -> list[dict[str, Any]]:
    """Return registry entries whose name + description tokens
    overlap with *text* by more than the noise threshold.

    A loose-but-honest matcher: counts the size of the token
    intersection between the user-supplied text and each
    descriptor's name+description, sorts by overlap descending, and
    returns the top hits. The LLM call later decides whether the
    match is "this is exactly what they asked for" or "adjacent
    technique"; this function just surfaces candidates.
    """
    text_tokens = _tokens(text)
    if not text_tokens:
        return []

    scored: list[tuple[int, TechniqueDescriptor]] = []
    for descriptor in get_registry():
        descriptor_tokens = _descriptor_keyword_set(descriptor)
        overlap = len(text_tokens & descriptor_tokens)
        # Two shared meaningful tokens is enough — fewer leaks too
        # much noise (every paper has a "approach" or "method").
        if overlap >= 2:
            scored.append((overlap, descriptor))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [
        {
            "id": d.id,
            "name": d.name,
            "pillar": d.pillar,
            "description": d.description,
            "match_score": score,
        }
        for score, d in scored[:5]
    ]


# ── LLM-driven proposal ───────────────────────────────────────────


_PROPOSAL_SYSTEM_PROMPT = (
    "You are the METIS companion's technique-absorption assistant. The user "
    "has pasted a paper or article URL. Your job is to summarise the "
    "technique into a short, structured proposal the user can review.\n\n"
    "You MUST respond with a single JSON object and nothing else. The JSON "
    "object must have exactly these fields:\n"
    "  - name (string): a short, distinctive name for the technique.\n"
    "  - claim (string): one or two sentences summarising what the technique does.\n"
    "  - pillar_guess (string): one of \"cosmos\", \"companion\", \"cortex\", \"cross-cutting\".\n"
    "  - implementation_sketch (string): one sentence on how METIS would activate it.\n\n"
    "Do not write code. Do not invent capabilities the source does not describe."
)


def summarise_to_proposal(
    *,
    title: str,
    summary: str,
    llm: Any,
) -> dict[str, Any] | None:
    """Ask *llm* to summarise the paper into a structured proposal.

    Returns a ``TechniqueProposal``-shaped dict with the four fields
    the system prompt enforces, or ``None`` when the LLM response is
    empty / unparseable / missing required fields. Callers should
    surface a "couldn't generate proposal" status to the user when
    this returns ``None``; the cross-reference matches stay useful
    even without a fresh proposal.
    """
    if llm is None:
        return None
    user_prompt = (
        f"Title: {title}\n\n"
        f"Source summary:\n{summary}\n\n"
        "Return only the JSON proposal."
    )
    try:
        resp = llm.invoke([
            {"type": "system", "content": _PROPOSAL_SYSTEM_PROMPT},
            {"type": "human", "content": user_prompt},
        ])
        raw = str(getattr(resp, "content", resp) or "").strip()
    except Exception as exc:  # noqa: BLE001
        log.warning("Forge absorb LLM call failed: %s", exc)
        return None

    if not raw:
        return None

    # Models sometimes wrap JSON in ```json fences. Strip them.
    cleaned = raw
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        log.warning("Forge absorb LLM returned non-JSON: %s", exc)
        return None

    if not isinstance(parsed, dict):
        return None

    required = {"name", "claim", "pillar_guess", "implementation_sketch"}
    if not required.issubset(parsed.keys()):
        return None

    pillar = parsed["pillar_guess"]
    if pillar not in ("cosmos", "companion", "cortex", "cross-cutting"):
        # Coerce unknown pillars to cross-cutting; cheaper than rejecting
        # the whole proposal because the model wandered off the enum.
        parsed["pillar_guess"] = "cross-cutting"

    return {
        "name": str(parsed["name"]).strip(),
        "claim": str(parsed["claim"]).strip(),
        "pillar_guess": parsed["pillar_guess"],
        "implementation_sketch": str(parsed["implementation_sketch"]).strip(),
    }


# ── Orchestrator ──────────────────────────────────────────────────


def _is_safe_http_url(url: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:  # noqa: BLE001
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def absorb(url: str, *, llm: Any) -> dict[str, Any]:
    """Run the absorb pipeline against *url*.

    Returns a dict shaped for the route's response body:
    ``source_kind``, ``title``, ``summary``, ``source_url``,
    ``matches`` (registry cross-reference), ``proposal`` (LLM
    output), and an optional ``error`` string when things go wrong.

    Handles three URL kinds explicitly:

    1. arxiv URLs → fetch the abstract via the arxiv API.
    2. (Phase 4b) other URLs → currently unsupported; collapses to
       an error payload pointing at the arxiv-only scope.
    3. Anything that isn't an http(s) URL → SSRF guard rejects.
    """
    if not _is_safe_http_url(url):
        return _error("unsafe URL — only http(s) schemes are accepted", url=url)

    arxiv_id = extract_arxiv_id(url)
    if arxiv_id is None:
        return _error(
            "Phase 4a only supports arxiv.org URLs; non-arxiv "
            "ingestion lands in a follow-up phase.",
            url=url,
            source_kind="unsupported",
        )

    meta = fetch_arxiv_metadata(arxiv_id)
    if meta is None:
        return _error(
            "could not fetch arxiv metadata for that ID",
            url=url,
            source_kind="error",
        )

    matches = cross_reference_against_registry(f"{meta['title']}\n{meta['summary']}")
    proposal = summarise_to_proposal(
        title=meta["title"],
        summary=meta["summary"],
        llm=llm,
    )
    return {
        "source_kind": "arxiv",
        "title": meta["title"],
        "summary": meta["summary"],
        "source_url": meta["source_url"],
        "matches": matches,
        "proposal": proposal,
        "error": None,
    }


def _error(
    message: str, *, url: str, source_kind: str = "error"
) -> dict[str, Any]:
    return {
        "source_kind": source_kind,
        "title": None,
        "summary": None,
        "source_url": url,
        "matches": [],
        "proposal": None,
        "error": message,
    }
