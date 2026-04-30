"""News-comet → Forge proposal bridge (M14 Phase 4c).

The M13 comet decision-engine emits ``decision == "absorb"`` for
high-relevance news items. Phase 4c plumbs those into the same
proposal pipeline a manual absorb uses, so a user opening the Forge
the next morning sees "your METIS noticed N papers overnight — review
them" instead of having to paste each URL by hand.

Scope kept narrow:

* **Arxiv only.** The Phase 4a/4b absorb pipeline already restricts
  itself to arxiv hosts; non-arxiv comets (HN, Reddit) silently skip
  the bridge. A future phase can extend to other sources by widening
  the absorb pipeline.
* **No proposal, no row.** If the LLM call inside the absorb
  pipeline returns an empty / unparseable response, the bridge does
  *not* persist a hollow row. The user keeps a clean review pane;
  they can re-run absorb manually once an LLM provider is configured.
* **Dedup by ``comet_id``.** A poll cycle can fire repeatedly. The
  bridge skips comets whose proposal is already pending in the db.
* **Caller-supplied LLM factory.** Lets the worker decide whether
  to spin up the assistant LLM at all (the comet pipeline runs in
  the background; pulling in a heavy provider on every tick would
  be wasteful).
"""

from __future__ import annotations

import logging
import pathlib
from typing import Any, Callable, Iterable

from metis_app.models.comet_event import CometEvent
from metis_app.services import forge_absorb, forge_proposals

log = logging.getLogger(__name__)

LlmFactory = Callable[[], Any]


def _already_pending_comet_ids(db_path: pathlib.Path) -> set[str]:
    """Return the set of comet_ids that already have a pending row.

    The dedup is intentionally tight to ``status="pending"`` — once
    the user has accepted or rejected a comet's proposal, a future
    repeat absorption can produce a fresh row (the user might have
    changed their mind about a topic, and the previous skill draft
    has already been written).
    """
    pending = forge_proposals.list_proposals(db_path=db_path, status="pending")
    return {row["comet_id"] for row in pending if row.get("comet_id")}


def auto_absorb_comets(
    events: Iterable[CometEvent],
    *,
    db_path: pathlib.Path,
    llm_factory: LlmFactory,
) -> list[int]:
    """Run the absorb pipeline for each ``decision=="absorb"`` arxiv
    comet in *events* and persist the resulting proposals.

    Returns the list of newly-saved proposal IDs. Events that don't
    qualify (non-absorb decision, non-arxiv URL, already-pending
    duplicate, empty LLM response) are silently skipped — the
    bridge is best-effort and never throws into the comet pipeline.
    """
    seen_pending = _already_pending_comet_ids(db_path)
    new_ids: list[int] = []
    llm_cached: Any | None = None

    for event in events:
        if getattr(event, "decision", None) != "absorb":
            continue
        url = getattr(event.news_item, "url", "") or ""
        if forge_absorb.extract_arxiv_id(url) is None:
            # Not an arxiv URL — out of scope for the absorb pipeline.
            continue
        if event.comet_id in seen_pending:
            continue

        if llm_cached is None:
            try:
                llm_cached = llm_factory()
            except Exception as exc:  # noqa: BLE001
                log.warning("forge_comet_bridge: llm_factory failed: %s", exc)
                # Still try to run absorb — the pipeline degrades to
                # cross-reference-only when the LLM is missing, which
                # produces no proposal. So the loop will just skip
                # the persistence path on the next iteration.
                llm_cached = None

        try:
            result = forge_absorb.absorb(url, llm=llm_cached)
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "forge_comet_bridge: absorb failed for comet %s: %s",
                event.comet_id,
                exc,
            )
            continue

        proposal = result.get("proposal")
        if not proposal:
            # No proposal => no persistence. The cross-reference
            # matches alone aren't worth a review-pane row; the user
            # never asked for this paper specifically.
            continue

        try:
            new_id = forge_proposals.save_proposal(
                db_path=db_path,
                source_url=str(result.get("source_url") or url),
                arxiv_id=str(result.get("arxiv_id") or "") or None,
                title=str(result.get("title") or event.news_item.title or ""),
                summary=str(result.get("summary") or "") or None,
                proposal_name=str(proposal.get("name") or ""),
                proposal_claim=str(proposal.get("claim") or ""),
                proposal_pillar=str(proposal.get("pillar_guess") or "cross-cutting"),
                proposal_sketch=str(proposal.get("implementation_sketch") or ""),
                source="comet",
                comet_id=event.comet_id,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "forge_comet_bridge: save_proposal failed for comet %s: %s",
                event.comet_id,
                exc,
            )
            continue

        new_ids.append(new_id)
        seen_pending.add(event.comet_id)

    return new_ids
