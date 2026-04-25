"""Companion bootstrap, reflection, and snapshot logic."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import pathlib
from typing import Any

import metis_app.settings_store as settings_store
from metis_app.models.assistant_types import (
    AssistantBrainLink,
    AssistantIdentity,
    AssistantMemoryEntry,
    AssistantPlaybook,
    AssistantPolicy,
    AssistantRuntime,
    AssistantStatus,
)
from metis_app.models.star_nourishment import (
    NourishmentState,
    StarEvent,
    TopologySignal,
    compute_nourishment,
)
from metis_app.services.assistant_repository import AssistantRepository
from metis_app.services.skill_repository import SkillRepository, _DEFAULT_CANDIDATES_DB_PATH
from metis_app.services.local_llm_recommender import LocalLlmRecommenderService
from metis_app.services.local_model_registry import LocalModelRegistryService
from metis_app.services.session_repository import SessionRepository
from metis_app.services.trace_store import TraceStore
from metis_app.services.runtime_resolution import (
    build_assistant_reflection_prompt,
    resolve_assistant_identity,
    resolve_assistant_policy,
    resolve_assistant_runtime,
)
from metis_app.utils.dependency_bootstrap import install_packages
from metis_app.utils.llm_providers import create_llm

log = logging.getLogger(__name__)


def _parse_iso(value: str) -> datetime | None:
    candidate = str(value or "").strip()
    if not candidate:
        return None
    try:
        return datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError:
        return None


class AssistantCompanionService:
    """Own the local-first companion state and reflection loop."""

    _computing_nourishment: bool = False  # recursion guard

    def __init__(
        self,
        *,
        repository: AssistantRepository | None = None,
        recommender: LocalLlmRecommenderService | None = None,
        model_registry: LocalModelRegistryService | None = None,
        session_repo: SessionRepository | None = None,
        trace_store: TraceStore | None = None,
        skill_repo: SkillRepository | None = None,
        candidates_db_path: pathlib.Path | None = None,
    ) -> None:
        self.repository = repository or AssistantRepository()
        self.recommender = recommender or LocalLlmRecommenderService()
        self.model_registry = model_registry or LocalModelRegistryService()
        self.session_repo = session_repo
        self.trace_store = trace_store or TraceStore()
        self._skill_repo = skill_repo or SkillRepository()
        self._candidates_db_path = candidates_db_path or _DEFAULT_CANDIDATES_DB_PATH

    def get_snapshot(self, settings: dict[str, Any] | None = None) -> dict[str, Any]:
        active_settings = dict(settings or settings_store.load_settings())
        identity = resolve_assistant_identity(active_settings)
        runtime = resolve_assistant_runtime(active_settings)
        policy = resolve_assistant_policy(active_settings)
        status = self._resolve_status(active_settings, identity=identity, runtime=runtime)
        nourishment = self._compute_nourishment(active_settings)
        return {
            "identity": identity.to_payload(),
            "runtime": runtime.to_payload(),
            "policy": policy.to_payload(),
            "status": status.to_payload(),
            "nourishment": nourishment.to_payload(),
            "memory": [item.to_payload() for item in self.repository.list_memory(limit=8)],
            "playbooks": [item.to_payload() for item in self.repository.list_playbooks(limit=6)],
            "brain_links": [item.to_payload() for item in self.repository.list_brain_links(limit=64)],
        }

    def update_config(
        self,
        *,
        identity: dict[str, Any] | None = None,
        runtime: dict[str, Any] | None = None,
        policy: dict[str, Any] | None = None,
        status: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        current = settings_store.load_settings()
        if identity is not None:
            merged_identity = resolve_assistant_identity(current).to_payload()
            merged_identity.update(dict(identity or {}))
            current["assistant_identity"] = merged_identity
        if runtime is not None:
            merged_runtime = resolve_assistant_runtime(current).to_payload()
            merged_runtime.update(dict(runtime or {}))
            current["assistant_runtime"] = merged_runtime
        if policy is not None:
            merged_policy = resolve_assistant_policy(current).to_payload()
            merged_policy.update(dict(policy or {}))
            current["assistant_policy"] = merged_policy
        settings_store.save_settings(
            {
                "assistant_identity": current.get("assistant_identity", {}),
                "assistant_runtime": current.get("assistant_runtime", {}),
                "assistant_policy": current.get("assistant_policy", {}),
            }
        )
        if status is not None:
            self.repository.update_status(dict(status or {}))
        return self.get_snapshot(settings_store.load_settings())

    def clear_recent_memory(self, *, limit: int = 10) -> dict[str, Any]:
        removed = self.repository.clear_recent_memory(limit=limit)
        status = self.repository.get_status()
        status.latest_summary = ""
        status.latest_why = ""
        self.repository.update_status(status)
        snapshot = self.get_snapshot()
        snapshot["removed_count"] = removed
        return snapshot

    def bootstrap_runtime(
        self,
        *,
        install_local_model: bool = False,
        settings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        active_settings = dict(settings or settings_store.load_settings())
        identity = resolve_assistant_identity(active_settings)
        runtime = resolve_assistant_runtime(active_settings)
        status = self._ensure_status(active_settings, identity=identity, runtime=runtime)
        recommendations = self.recommender.recommend_models(use_case="chat", settings=active_settings, current_mode="Tutor")
        top = self._pick_recommendation(recommendations)
        if top is not None:
            runtime.recommended_model_name = str(top.get("model_name") or "")
            runtime.recommended_quant = str(top.get("best_quant") or "")
            runtime.recommended_use_case = str(top.get("use_case") or "chat")
            status.recommended_model_name = runtime.recommended_model_name
            status.recommended_quant = runtime.recommended_quant
            status.recommended_use_case = runtime.recommended_use_case

        if install_local_model and top is not None:
            self._install_companion_model(active_settings, runtime, top)
            settings_store.save_settings({"assistant_runtime": runtime.to_payload()})
            active_settings = settings_store.load_settings()
            status = self._ensure_status(active_settings, identity=identity, runtime=runtime)
        else:
            status.bootstrap_state = status.bootstrap_state or "recommended"
            if not status.bootstrap_message and top is not None:
                status.bootstrap_message = (
                    f"Recommended local companion model: {runtime.recommended_model_name} ({runtime.recommended_quant})."
                )
            self.repository.update_status(status)
            settings_store.save_settings({"assistant_runtime": runtime.to_payload()})

        return self.get_snapshot(active_settings)

    def reflect(
        self,
        *,
        trigger: str,
        settings: dict[str, Any] | None = None,
        context_id: str = "",
        session_id: str = "",
        run_id: str = "",
        force: bool = False,
        _orchestrator: Any | None = None,
    ) -> dict[str, Any]:
        active_settings = dict(settings or settings_store.load_settings())
        identity = resolve_assistant_identity(active_settings)
        policy = resolve_assistant_policy(active_settings)
        if not identity.companion_enabled or not policy.reflection_enabled:
            return {
                "ok": False,
                "status": self.repository.get_status().to_payload(),
                "reason": "assistant_disabled",
            }
        if not force and not self._trigger_enabled(policy, trigger):
            return {
                "ok": False,
                "status": self.repository.get_status().to_payload(),
                "reason": "trigger_disabled",
            }
        if (
            not force
            and trigger != "manual"
            and not policy.allow_automatic_writes
        ):
            return {
                "ok": False,
                "status": self.repository.get_status().to_payload(),
                "reason": "writes_disabled",
            }

        status = self._ensure_status(active_settings, identity=identity, runtime=resolve_assistant_runtime(active_settings))
        if status.paused and not force:
            return {"ok": False, "status": status.to_payload(), "reason": "assistant_paused"}

        last_reflection_at = _parse_iso(status.last_reflection_at)
        if (
            last_reflection_at is not None
            and not force
            and policy.reflection_cooldown_seconds > 0
        ):
            elapsed = (datetime.now(timezone.utc) - last_reflection_at).total_seconds()
            if elapsed < policy.reflection_cooldown_seconds and trigger != "manual":
                return {"ok": False, "status": status.to_payload(), "reason": "cooldown"}
        if not force and self._is_duplicate_reflection(
            trigger=trigger,
            context_id=context_id,
            session_id=session_id,
            run_id=run_id,
        ):
            return {"ok": False, "status": status.to_payload(), "reason": "duplicate"}

        detail = None
        if self.session_repo is not None and session_id:
            detail = self.session_repo.get_session(session_id)
        trace_events = self.trace_store.read_run_events(run_id) if run_id else []
        reflection = self._generate_reflection(
            active_settings,
            trigger=trigger,
            session_id=session_id,
            run_id=run_id,
            session_detail=detail,
            trace_events=trace_events,
        )

        memory_entry = AssistantMemoryEntry.create(
            kind="reflection",
            title=reflection["title"],
            summary=reflection["summary"],
            details=reflection["details"],
            why=reflection["why"],
            confidence=reflection["confidence"],
            trigger=trigger,
            context_id=context_id,
            session_id=session_id,
            run_id=run_id,
            tags=list(reflection.get("tags") or []),
            related_node_ids=list(reflection.get("related_node_ids") or []),
        )
        self.repository.add_memory_entry(memory_entry, max_entries=policy.max_memory_entries)

        bullets = [str(item).strip() for item in (reflection.get("playbook_bullets") or []) if str(item).strip()]
        playbook = None
        if bullets:
            playbook = AssistantPlaybook.create(
                title=str(reflection.get("playbook_title") or "Companion Playbook"),
                bullets=bullets,
                source_session_id=session_id,
                source_run_id=run_id,
                confidence=reflection["confidence"],
            )
            self.repository.add_playbook(playbook, max_items=policy.max_playbooks)

        links: list[AssistantBrainLink] = [
            AssistantBrainLink.create(
                source_node_id="assistant:metis",
                target_node_id=f"session:{session_id}" if session_id else f"memory:{memory_entry.entry_id}",
                relation="learned_from_session" if session_id else "reflection_anchor",
                label="Learned From",
                summary=memory_entry.summary,
                confidence=reflection["confidence"],
                session_id=session_id,
                run_id=run_id,
                metadata={"scope": "assistant_learned", "why": memory_entry.why},
            ),
            AssistantBrainLink.create(
                source_node_id=f"memory:{memory_entry.entry_id}",
                target_node_id="assistant:metis",
                relation="belongs_to",
                label="Belongs To",
                summary=memory_entry.title,
                confidence=reflection["confidence"],
                session_id=session_id,
                run_id=run_id,
                metadata={"scope": "assistant_self"},
            ),
        ]
        if detail is not None and detail.summary.index_id:
            links.append(
                AssistantBrainLink.create(
                    source_node_id=f"memory:{memory_entry.entry_id}",
                    target_node_id=f"index:{detail.summary.index_id}",
                    relation="about_index",
                    label="About Index",
                    summary=reflection["summary"],
                    confidence=reflection["confidence"],
                    session_id=session_id,
                    run_id=run_id,
                    metadata={"scope": "assistant_learned"},
                )
            )
        if playbook is not None:
            links.append(
                AssistantBrainLink.create(
                    source_node_id=f"playbook:{playbook.playbook_id}",
                    target_node_id="assistant:metis",
                    relation="belongs_to",
                    label="Belongs To",
                    summary=playbook.title,
                    confidence=playbook.confidence,
                    session_id=session_id,
                    run_id=run_id,
                    metadata={"scope": "assistant_self"},
                )
            )
        self.repository.add_brain_links(links, max_items=policy.max_brain_links)

        status.state = "reflected"
        status.last_reflection_at = memory_entry.created_at
        status.last_reflection_trigger = trigger
        status.latest_summary = memory_entry.summary
        status.latest_why = memory_entry.why
        self.repository.update_status(status)

        import threading

        # Spawn autonomous research in background daemon thread if enabled
        if policy.autonomous_research_enabled and _orchestrator is not None:
            def _research_task() -> None:
                try:
                    result = _orchestrator.run_autonomous_research(active_settings)
                    if result:
                        research_entry = AssistantMemoryEntry.create(
                            kind="autonomous_research",
                            title=f"Added star: {result['title']}",
                            summary=(
                                f"I noticed the {result['faculty_id']} constellation was thin. "
                                f"I researched and added a new star: {result['title']}."
                            ),
                            details=f"Sources: {', '.join(result.get('sources', [])[:3])}",
                            why="Autonomous research cycle detected sparse faculty coverage.",
                            confidence=0.7,
                            trigger="autonomous_research",
                            tags=[result["faculty_id"], "autonomous"],
                        )
                        self.repository.add_memory_entry(
                            research_entry, max_entries=policy.max_memory_entries
                        )
                except Exception as _exc:
                    log.warning("autonomous_research background task failed: %s", _exc)

            threading.Thread(target=_research_task, daemon=True).start()

        # Spawn skill candidate promotion in background daemon thread
        if trigger == "completed_run" and policy.allow_automatic_writes:
            def _promote_task() -> None:
                try:
                    count = self._promote_skill_candidates(active_settings)
                    if count:
                        log.debug("Promoted %d skill candidate(s).", count)
                except Exception as _exc:
                    log.warning("_promote_skill_candidates background task failed: %s", _exc)
            threading.Thread(target=_promote_task, daemon=True).start()

        return {
            "ok": True,
            "status": status.to_payload(),
            "memory_entry": memory_entry.to_payload(),
            "playbook": playbook.to_payload() if playbook is not None else None,
            "brain_links": [item.to_payload() for item in links],
            "snapshot": self.get_snapshot(active_settings),
        }

    # Map the public ``kind`` argument onto the persisted memory-entry
    # ``kind`` field. Splitting the storage kinds (rather than tagging a
    # single one) so Phase 4b's overnight reflections are distinguishable
    # from while-you-work ones via a real column, not a tag-list lookup.
    # Adding a new ``kind`` literal here is the only place to wire it.
    _EXTERNAL_REFLECTION_KIND_MAP: dict[str, str] = {
        "while_you_work": "bonsai_reflection",
        "overnight": "overnight_reflection",
    }
    _EXTERNAL_REFLECTION_KINDS: frozenset[str] = frozenset(
        _EXTERNAL_REFLECTION_KIND_MAP.values()
    )

    def record_external_reflection(
        self,
        *,
        summary: str,
        why: str = "",
        trigger: str = "while_you_work",
        kind: str = "while_you_work",
        confidence: float = 0.55,
        source_event: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        settings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record a reflection whose text was generated outside the backend.

        Phase 4a (M13) uses this to persist Bonsai-1.7B WebGPU
        reflections — short, event-driven notes the in-browser
        companion produces while the user works. The Bonsai pipeline
        owns generation; this method owns persistence, the cooldown
        guard, and the status update.

        Phase 4b reuses this entry point with ``kind="overnight"``
        when the backend GGUF reflection toggle ships. Each
        public ``kind`` literal maps to a distinct memory-entry
        ``kind`` field via :attr:`_EXTERNAL_REFLECTION_KIND_MAP`,
        so downstream filtering is by column not by tag.

        Behaviour notes:

        - The persisted ``summary``/``why`` are truncated at 800
          characters with an ellipsis. The Pydantic route accepts up
          to 4000 characters at the boundary so legitimate prompt
          stuffing is not rejected outright; the service trims at
          read-time before write.
        - The cooldown gates on (kind, trigger) so a *while_you_work*
          reflection and an *overnight* reflection do not block each
          other, but two *while_you_work* reflections with the same
          trigger inside the cooldown window do. The trigger string
          is normalised with ``.strip()``; an empty trigger is its
          own valid bucket.
        - ``status.latest_summary``/``status.latest_why`` follow
          last-writer-wins across all reflection kinds. Phase 4b may
          revisit (per-kind summaries) once usage data exists.

        Returns a payload with the same outer shape as
        :meth:`reflect` (``ok``, ``status``, ``memory_entry``,
        ``snapshot``) plus a ``reason`` field on the failure path.
        """
        active_settings = dict(settings or settings_store.load_settings())
        identity = resolve_assistant_identity(active_settings)
        policy = resolve_assistant_policy(active_settings)
        if not identity.companion_enabled or not policy.reflection_enabled:
            return {
                "ok": False,
                "status": self.repository.get_status().to_payload(),
                "reason": "assistant_disabled",
            }
        # Mirror the ``reflect()`` write gate. Bonsai's always-on dock
        # callback (and Phase 4b's overnight cycle) fires automatically
        # without explicit user confirmation, so the same
        # ``allow_automatic_writes`` policy that governs auto-reflect
        # must also gate this writer. Manual triggers — e.g. a future
        # "save this thought" button — bypass the gate.
        if trigger != "manual" and not policy.allow_automatic_writes:
            return {
                "ok": False,
                "status": self.repository.get_status().to_payload(),
                "reason": "writes_disabled",
            }

        text = (summary or "").strip()
        if not text:
            return {
                "ok": False,
                "status": self.repository.get_status().to_payload(),
                "reason": "empty_summary",
            }
        # Bound the persisted text. Bonsai's max_new_tokens is 512 but
        # the dock prompt asks for one or two sentences; an over-long
        # response usually means the model rambled — keep it readable
        # in the memory list and don't bloat the SQLite row.
        if len(text) > 800:
            text = text[:800].rstrip() + "…"
        reason_text = (why or "").strip()
        if len(reason_text) > 800:
            reason_text = reason_text[:800].rstrip() + "…"

        runtime = resolve_assistant_runtime(active_settings)
        status = self._ensure_status(active_settings, identity=identity, runtime=runtime)
        if status.paused:
            return {
                "ok": False,
                "status": status.to_payload(),
                "reason": "assistant_paused",
            }

        normalized_trigger = (trigger or "").strip()
        memory_kind = self._EXTERNAL_REFLECTION_KIND_MAP.get(
            kind, "bonsai_reflection"
        )

        # Per-(kind, trigger) cooldown. ADR 0013 §Open Questions calls
        # for ~30s between Bonsai reflections so a busy session does
        # not stamp a memory entry per event. The lookback is sized
        # generously so unrelated entries between two same-bucket
        # reflections do not push the previous one out of view.
        cooldown_seconds = float(
            active_settings.get(
                "seedling_external_reflection_cooldown_seconds",
                30.0,
            )
        )
        if cooldown_seconds > 0:
            cooldown_lookback = max(
                64,
                int(active_settings.get(
                    "seedling_external_reflection_cooldown_lookback",
                    64,
                )),
            )
            recent = self.repository.list_memory(limit=cooldown_lookback)
            cutoff = datetime.now(timezone.utc).timestamp() - cooldown_seconds
            for item in recent:
                if item.kind != memory_kind:
                    continue
                if item.trigger != normalized_trigger:
                    continue
                created = _parse_iso(item.created_at)
                if created is None:
                    continue
                if created.timestamp() >= cutoff:
                    return {
                        "ok": False,
                        "status": status.to_payload(),
                        "reason": "cooldown",
                    }

        source_payload = source_event if isinstance(source_event, dict) else {}
        related_node_ids: list[str] = []
        if isinstance(source_payload.get("comet_id"), str) and source_payload["comet_id"]:
            related_node_ids.append(f"comet:{source_payload['comet_id']}")
        if isinstance(source_payload.get("source"), str) and source_payload["source"]:
            related_node_ids.append(f"source:{source_payload['source']}")

        default_title = (
            "Overnight reflection"
            if memory_kind == "overnight_reflection"
            else "Bonsai reflection"
        )
        title = default_title
        bullet = text.splitlines()[0] if text else ""
        if bullet and len(bullet) < 120:
            title = bullet

        memory_entry = AssistantMemoryEntry.create(
            kind=memory_kind,
            title=title,
            summary=text,
            details=text,
            why=reason_text,
            confidence=max(0.0, min(1.0, float(confidence))),
            trigger=normalized_trigger,
            tags=list(tags or []) + [kind],
            related_node_ids=related_node_ids,
        )
        self.repository.add_memory_entry(memory_entry, max_entries=policy.max_memory_entries)

        status.state = "reflected"
        status.last_reflection_at = memory_entry.created_at
        status.last_reflection_trigger = normalized_trigger
        # Last-writer-wins across reflection kinds: a Bonsai burst will
        # overwrite a prior full ``reflect()`` summary, and Phase 4b's
        # overnight write will likewise overwrite this one. The dock's
        # behaviour is "show the most recent reflection of any kind"
        # — see :meth:`record_external_reflection` docstring.
        status.latest_summary = memory_entry.summary
        status.latest_why = memory_entry.why
        self.repository.update_status(status)

        return {
            "ok": True,
            "kind": kind,
            "status": status.to_payload(),
            "memory_entry": memory_entry.to_payload(),
            "snapshot": self.get_snapshot(active_settings),
        }

    def _trigger_enabled(self, policy: AssistantPolicy, trigger: str) -> bool:
        normalized = str(trigger or "").strip().lower()
        if normalized in {"", "manual"}:
            return True
        trigger_flags = {
            "onboarding": bool(policy.trigger_on_onboarding),
            "index_build": bool(policy.trigger_on_index_build),
            "completed_run": bool(policy.trigger_on_completed_run),
            "autonomous_research": bool(policy.autonomous_research_enabled),
        }
        return trigger_flags.get(normalized, True)

    def _is_duplicate_reflection(
        self,
        *,
        trigger: str,
        context_id: str,
        session_id: str,
        run_id: str,
    ) -> bool:
        recent = self.repository.list_memory(limit=6)
        for item in recent:
            if (
                item.trigger == trigger
                and item.context_id == context_id
                and item.session_id == session_id
                and item.run_id == run_id
            ):
                return True
        return False

    def _ensure_status(
        self,
        settings: dict[str, Any],
        *,
        identity: AssistantIdentity,
        runtime: AssistantRuntime,
    ) -> AssistantStatus:
        persisted = self.repository.get_status()
        current = self._resolve_status(
            settings,
            identity=identity,
            runtime=runtime,
            current=persisted,
        )
        if current.to_payload() != persisted.to_payload():
            self.repository.update_status(current)
        return current

    def _resolve_status(
        self,
        settings: dict[str, Any],
        *,
        identity: AssistantIdentity,
        runtime: AssistantRuntime,
        current: AssistantStatus | None = None,
    ) -> AssistantStatus:
        current = AssistantStatus.from_payload(
            (current or self.repository.get_status()).to_payload()
        )
        current.bootstrap_state = runtime.bootstrap_state or current.bootstrap_state
        current.recommended_model_name = runtime.recommended_model_name or current.recommended_model_name
        current.recommended_quant = runtime.recommended_quant or current.recommended_quant
        current.recommended_use_case = runtime.recommended_use_case or current.recommended_use_case

        local_path = pathlib.Path(runtime.local_gguf_model_path).expanduser() if runtime.local_gguf_model_path else None
        if runtime.provider == "local_gguf" and local_path is not None and local_path.is_file():
            current.runtime_ready = True
            current.runtime_source = "dedicated_local"
            current.runtime_provider = "local_gguf"
            current.runtime_model = runtime.model or local_path.name
            current.bootstrap_state = "ready"
            current.bootstrap_message = "Companion is running on a dedicated local model."
        elif runtime.fallback_to_primary:
            current.runtime_ready = True
            current.runtime_source = "primary_fallback"
            current.runtime_provider = str(settings.get("llm_provider") or "")
            current.runtime_model = str(settings.get("llm_model_custom") or settings.get("llm_model") or "")
            if not current.bootstrap_state or current.bootstrap_state == "pending":
                current.bootstrap_state = "fallback"
            if not current.bootstrap_message:
                current.bootstrap_message = "Companion is using the primary chat runtime until a local companion model is configured."
        else:
            current.runtime_ready = False
            current.runtime_source = ""
            current.runtime_provider = ""
            current.runtime_model = ""
            current.bootstrap_state = current.bootstrap_state or "recommended"
            if not current.bootstrap_message:
                current.bootstrap_message = "Companion runtime is not configured yet."
        current.state = "ready" if identity.companion_enabled else "disabled"
        return current

    def _pick_recommendation(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        rows = [dict(item) for item in (payload.get("rows") or []) if isinstance(item, dict)]
        for fit_level in ("perfect", "good", "marginal"):
            for row in rows:
                if str(row.get("fit_level") or "") == fit_level:
                    return row
        return rows[0] if rows else None

    # ------------------------------------------------------------------
    # Star nourishment computation
    # ------------------------------------------------------------------

    # Default faculties used when the constellation hasn't declared its own
    _DEFAULT_FACULTIES: list[dict[str, str]] = [
        {"id": "mathematics", "name": "Mathematics"},
        {"id": "physics", "name": "Physics"},
        {"id": "literature", "name": "Literature"},
        {"id": "history", "name": "History"},
        {"id": "biology", "name": "Biology"},
        {"id": "philosophy", "name": "Philosophy"},
        {"id": "computer-science", "name": "Computer Science"},
        {"id": "economics", "name": "Economics"},
        {"id": "chemistry", "name": "Chemistry"},
        {"id": "engineering", "name": "Engineering"},
        {"id": "arts", "name": "Arts"},
    ]

    def _compute_nourishment(
        self,
        settings: dict[str, Any],
        events: list[StarEvent] | None = None,
    ) -> NourishmentState:
        """Compute current nourishment state from settings star data."""
        # Guard against infinite recursion:
        # WorkspaceOrchestrator.get_workspace_graph() → get_snapshot() → here
        if AssistantCompanionService._computing_nourishment:
            return compute_nourishment(
                stars=list(settings.get("landing_constellation_user_stars") or []),
                faculties=list(
                    settings.get("constellation_faculties") or self._DEFAULT_FACULTIES
                ),
            )
        AssistantCompanionService._computing_nourishment = True
        try:
            return self.__compute_nourishment_inner(settings, events)
        finally:
            AssistantCompanionService._computing_nourishment = False

    def __compute_nourishment_inner(
        self,
        settings: dict[str, Any],
        events: list[StarEvent] | None = None,
    ) -> NourishmentState:
        """Inner implementation, called only when recursion guard allows."""
        stars = list(settings.get("landing_constellation_user_stars") or [])
        faculties = list(
            settings.get("constellation_faculties") or self._DEFAULT_FACULTIES
        )
        # Load previous nourishment state if persisted
        previous_raw = settings.get("_nourishment_state")
        previous = (
            NourishmentState.from_payload(previous_raw)
            if isinstance(previous_raw, dict) else None
        )

        # Build TopologySignal when scaffold is available
        topo_signal: TopologySignal | None = None
        try:
            from metis_app.utils.feature_flags import FeatureFlag, get_feature_statuses
            topo_enabled = any(
                s.enabled and s.name == FeatureFlag.TOPO_SCAFFOLD_ENABLED
                for s in get_feature_statuses(settings)
            )
            if topo_enabled:
                from metis_app.services.topo_scaffold import compute_scaffold
                from metis_app.services.workspace_orchestrator import WorkspaceOrchestrator
                graph = WorkspaceOrchestrator().get_workspace_graph(skip_layout=True)
                scaffold = compute_scaffold(graph)
                # Derive isolated faculties: faculties with no scaffold edge
                connected_ids: set[str] = set()
                for edge in (scaffold.scaffold_edges or []):
                    connected_ids.add(str(edge[0]))
                    connected_ids.add(str(edge[1]))
                faculty_ids = {f.get("id", f.get("name", "")) for f in faculties}
                isolated = sorted(faculty_ids - connected_ids) if connected_ids else []
                topo_signal = TopologySignal(
                    betti_0=scaffold.betti_0,
                    betti_1=scaffold.betti_1,
                    scaffold_edge_count=len(scaffold.scaffold_edges or []),
                    strongest_persistence=(
                        scaffold.scaffold_edges[0][2]
                        if scaffold.scaffold_edges else 0.0
                    ),
                    isolated_faculties=isolated,
                    summary=scaffold.summary or "",
                )
        except Exception:  # noqa: BLE001
            log.debug("Topology signal unavailable for nourishment", exc_info=True)

        return compute_nourishment(
            stars=stars,
            faculties=faculties,
            previous=previous,
            events=events,
            topology=topo_signal,
            personality=previous.personality if previous else None,
        )

    def _install_companion_model(
        self,
        settings: dict[str, Any],
        runtime: AssistantRuntime,
        recommendation: dict[str, Any],
    ) -> None:
        log.info("Installing companion model from recommendation: %s", recommendation.get("model_name"))
        install_packages(["llama-cpp-python"], logger=log)
        plan = self.recommender.plan_import(
            model_name=str(recommendation.get("model_name") or ""),
            best_quant=str(recommendation.get("best_quant") or ""),
            fit_level=str(recommendation.get("fit_level") or ""),
            recommended_context_length=int(recommendation.get("recommended_context_length") or 2048),
            settings=settings,
        )
        imported_path = self.recommender.download_import(plan)
        registry = dict(settings.get("local_model_registry") or {})
        updated_registry = self.model_registry.add_gguf(
            registry,
            name=str(recommendation.get("model_name") or imported_path.stem),
            path=str(imported_path),
            metadata=dict(plan.registry_metadata or {}),
        )
        settings_store.save_settings({"local_model_registry": updated_registry})
        runtime.provider = "local_gguf"
        runtime.model = str(recommendation.get("model_name") or imported_path.stem)
        runtime.local_gguf_model_path = str(imported_path)
        runtime.local_gguf_context_length = max(int(recommendation.get("recommended_context_length") or 2048), 512)
        runtime.recommended_model_name = str(recommendation.get("model_name") or "")
        runtime.recommended_quant = str(recommendation.get("best_quant") or "")
        runtime.recommended_use_case = str(recommendation.get("use_case") or "chat")
        runtime.bootstrap_state = "ready"

    def _generate_reflection(
        self,
        settings: dict[str, Any],
        *,
        trigger: str,
        session_id: str,
        run_id: str,
        session_detail: Any | None,
        trace_events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        reflection = self._heuristic_reflection(
            trigger=trigger,
            session_id=session_id,
            run_id=run_id,
            session_detail=session_detail,
            trace_events=trace_events,
        )

        # -- Topology scaffold awareness (Step 5) --------------------------
        from metis_app.utils.feature_flags import FeatureFlag, get_feature_statuses
        topo_enabled = any(
            s.enabled and s.name == FeatureFlag.TOPO_SCAFFOLD_ENABLED
            for s in get_feature_statuses(settings)
        )
        if topo_enabled:
            try:
                from metis_app.services.topo_scaffold import compute_scaffold
                from metis_app.services.workspace_orchestrator import WorkspaceOrchestrator
                graph = WorkspaceOrchestrator().get_workspace_graph(skip_layout=True)
                scaffold = compute_scaffold(graph)
                topo_lines = [
                    f"Topology: {scaffold.betti_0} connected region(s), {scaffold.betti_1} integration loop(s).",
                ]
                if scaffold.scaffold_edges:
                    top_edge = scaffold.scaffold_edges[0]
                    topo_lines.append(
                        f"Strongest scaffold edge: {top_edge[0]} — {top_edge[1]} "
                        f"(persistence {top_edge[2]:.2f}, frequency {top_edge[3]})."
                    )
                if scaffold.summary:
                    topo_lines.append(f"Scaffold summary: {scaffold.summary}")
                context_lines = list(reflection.get("context_lines") or [])
                context_lines.extend(topo_lines)
                reflection["context_lines"] = context_lines
            except Exception:  # noqa: BLE001
                log.debug("Topology scaffold unavailable for reflection", exc_info=True)

        policy = resolve_assistant_policy(settings)
        if policy.reflection_backend == "heuristic":
            return reflection
        llm_reflection = self._llm_reflection(settings, reflection, session_detail=session_detail, trace_events=trace_events)
        return llm_reflection or reflection

    def _llm_reflection(
        self,
        settings: dict[str, Any],
        heuristic: dict[str, Any],
        *,
        session_detail: Any | None,
        trace_events: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        llm_settings = self._resolve_runtime_llm_settings(settings)
        if llm_settings is None:
            return None
        try:
            llm = create_llm(llm_settings)
        except Exception as exc:  # noqa: BLE001
            log.debug("Companion reflection falling back to heuristic: %s", exc)
            return None

        summary_lines = list(heuristic.get("context_lines") or [])
        nourishment = self._compute_nourishment(settings)
        from metis_app.services.star_nourishment_gen import generate_hunger_block  # noqa: PLC0415
        nourishment_block = generate_hunger_block(nourishment)
        prompt = build_assistant_reflection_prompt(
            resolve_assistant_identity(settings),
            context_lines=summary_lines,
            trace_events=trace_events,
            seed_summary=str(heuristic.get("summary") or ""),
            nourishment_block=nourishment_block,
        )
        try:
            raw = llm.invoke(
                [
                    {"type": "system", "content": prompt},
                    {"type": "human", "content": "Return compact JSON with title, summary, details, why, playbook_title, playbook_bullets, tags, confidence."},
                ]
            )
            text = str(getattr(raw, "content", raw) or "")
            start = text.find("{")
            end = text.rfind("}") + 1
            if start == -1 or end <= start:
                return None
            payload = json.loads(text[start:end])
            if not isinstance(payload, dict):
                return None
            return {
                "title": str(payload.get("title") or heuristic["title"]),
                "summary": str(payload.get("summary") or heuristic["summary"]),
                "details": str(payload.get("details") or heuristic["details"]),
                "why": str(payload.get("why") or heuristic["why"]),
                "playbook_title": str(payload.get("playbook_title") or heuristic["playbook_title"]),
                "playbook_bullets": [
                    str(item).strip()
                    for item in (payload.get("playbook_bullets") or heuristic["playbook_bullets"] or [])
                    if str(item).strip()
                ],
                "tags": [
                    str(item).strip()
                    for item in (payload.get("tags") or heuristic["tags"] or [])
                    if str(item).strip()
                ],
                "confidence": max(0.0, min(1.0, float(payload.get("confidence") or heuristic["confidence"]))),
                "related_node_ids": list(heuristic.get("related_node_ids") or []),
            }
        except Exception as exc:  # noqa: BLE001
            log.debug("Companion reflection JSON parse failed: %s", exc)
            return None

    def _resolve_runtime_llm_settings(self, settings: dict[str, Any]) -> dict[str, Any] | None:
        runtime = resolve_assistant_runtime(settings)
        if runtime.provider == "local_gguf" and runtime.local_gguf_model_path:
            candidate = pathlib.Path(runtime.local_gguf_model_path).expanduser()
            if candidate.is_file():
                resolved = dict(settings)
                resolved.update(
                    {
                        "llm_provider": "local_gguf",
                        "llm_model": runtime.model or candidate.stem,
                        "llm_model_custom": runtime.model or candidate.stem,
                        "local_gguf_model_path": str(candidate),
                        "local_gguf_context_length": runtime.local_gguf_context_length,
                        "local_gguf_gpu_layers": runtime.local_gguf_gpu_layers,
                        "local_gguf_threads": runtime.local_gguf_threads,
                        "llm_max_tokens": min(int(settings.get("llm_max_tokens", 512) or 512), 512),
                    }
                )
                return resolved
        if runtime.fallback_to_primary:
            return dict(settings)
        return None

    def _heuristic_reflection(
        self,
        *,
        trigger: str,
        session_id: str,
        run_id: str,
        session_detail: Any | None,
        trace_events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        title = "Companion Reflection"
        summary = "METIS recorded a new local reflection."
        details = "No detailed session context was available, so the reflection stayed lightweight."
        why = "A reflection trigger fired and the companion keeps a concise local memory for continuity."
        tags = [trigger] if trigger else []
        related_node_ids = []
        playbook_title = "Companion Playbook"
        playbook_bullets = []
        context_lines: list[str] = []

        if session_detail is not None:
            title = f"Learned from {session_detail.summary.title}"
            mode = str(session_detail.summary.mode or "Q&A")
            index_id = str(session_detail.summary.index_id or "")
            related_node_ids.append(f"session:{session_detail.summary.session_id}")
            if index_id:
                related_node_ids.append(f"index:{index_id}")
            last_user = next(
                (message.content for message in reversed(session_detail.messages) if message.role == "user"),
                "",
            )
            last_assistant = next(
                (message.content for message in reversed(session_detail.messages) if message.role == "assistant"),
                "",
            )
            source_count = len(next(
                (message.sources for message in reversed(session_detail.messages) if message.role == "assistant"),
                [],
            ))
            summary = (
                f"METIS noticed a {mode} conversation"
                f"{' grounded in an index' if index_id else ''} and saved a concise memory for future guidance."
            )
            details = (
                f"Latest user prompt: {last_user[:180] or 'n/a'}\n"
                f"Latest assistant response preview: {last_assistant[:220] or 'n/a'}\n"
                f"Grounding sources observed: {source_count}."
            )
            why = (
                "This suggestion appeared because a completed run gives the companion enough context "
                "to summarize what just happened and propose a useful next step."
            )
            playbook_title = f"{mode} Follow-up Pattern"
            playbook_bullets = [
                "Capture the user's last intent before suggesting a follow-up.",
                "Prefer short next-step suggestions over rewriting the full answer.",
            ]
            if index_id:
                playbook_bullets.append("Surface index-aware follow-up questions when grounded sources were available.")
            context_lines.extend(
                [
                    f"Session title: {session_detail.summary.title}",
                    f"Mode: {mode}",
                    f"Index: {index_id or 'none'}",
                    f"Latest user prompt: {last_user[:180] or 'n/a'}",
                    f"Latest assistant response preview: {last_assistant[:220] or 'n/a'}",
                ]
            )

        if trace_events:
            event_types = [str(item.get("event_type") or item.get("stage") or "") for item in trace_events if str(item.get("event_type") or item.get("stage") or "").strip()]
            if event_types:
                details = f"{details}\nTrace markers: {', '.join(event_types[:8])}."
                tags.extend(event_types[:4])
                context_lines.append(f"Trace markers: {', '.join(event_types[:8])}")

        if trigger == "onboarding":
            title = "Onboarding Handshake"
            summary = "METIS welcomed the user and prepared a lightweight local companion flow."
            details = "The companion recorded an onboarding memory so it can greet the user consistently across views."
            why = "The companion appears during onboarding to explain what it can do without taking over normal chat."
            playbook_title = "Onboarding Pattern"
            playbook_bullets = [
                "Greet the user with one clear sentence and one concrete next step.",
                "Keep onboarding guidance additive rather than blocking the main workspace.",
            ]
            context_lines.append("Trigger: onboarding")
        elif trigger == "index_build":
            title = "Index Build Reflection"
            summary = "METIS noticed a new index and recorded a follow-up suggestion for grounded exploration."
            details = f"{details}\nA new index became available."
            why = "Index builds are a strong moment to suggest grounded questions and brain exploration."
            playbook_title = "Index Build Pattern"
            playbook_bullets = [
                "After indexing, suggest one overview question and one evidence-heavy question.",
                "Point the user to the Brain tab when new grounded material arrives.",
            ]
            context_lines.append("Trigger: index build")

        return {
            "title": title,
            "summary": summary,
            "details": details,
            "why": why,
            "playbook_title": playbook_title,
            "playbook_bullets": playbook_bullets,
            "confidence": 0.72 if session_detail is not None or trace_events else 0.58,
            "tags": sorted({tag for tag in tags if tag}),
            "related_node_ids": sorted({node_id for node_id in related_node_ids if node_id}),
            "context_lines": context_lines,
        }

    def capture_skill_candidate(
        self,
        *,
        db_path: "pathlib.Path",
        query_text: str,
        trace_json: str,
        convergence_score: float,
        min_convergence: float = 0.90,
        min_iterations: int = 2,
        trace_iterations: int = 0,
    ) -> bool:
        """Save a successful agentic run as a skill candidate if it meets quality thresholds.

        Returns True if saved, False if below threshold.
        """
        from metis_app.services.skill_repository import SkillRepository
        if convergence_score < min_convergence or trace_iterations < min_iterations:
            return False
        repo = SkillRepository(skills_dir=None)
        repo.save_candidate(
            db_path=db_path,
            query_text=query_text,
            trace_json=trace_json,
            convergence_score=convergence_score,
        )
        return True

    def _promote_skill_candidates(
        self,
        settings: dict[str, Any],
        *,
        _db_path: "pathlib.Path | None" = None,
        _auto_gen_dir: "pathlib.Path | None" = None,
    ) -> int:
        """LLM-judge unreviewed skill candidates and promote generalizable ones to .md files.

        Returns count of newly promoted candidates. Silently skips if LLM is unavailable.
        """
        from metis_app.services.skill_repository import (
            SkillRepository,
            _DEFAULT_CANDIDATES_DB_PATH,
            _DEFAULT_SKILLS_DIR,
        )
        llm_settings = self._resolve_runtime_llm_settings(settings)
        if llm_settings is None:
            return 0
        try:
            llm = create_llm(llm_settings)
        except Exception as exc:  # noqa: BLE001
            log.debug("_promote_skill_candidates: LLM unavailable: %s", exc)
            return 0

        db_path = _db_path or getattr(self, "_candidates_db_path", None) or _DEFAULT_CANDIDATES_DB_PATH
        _self_skill_repo = getattr(self, "_skill_repo", None)
        auto_gen_dir = _auto_gen_dir or (
            (_self_skill_repo.skills_dir / "auto-generated") if _self_skill_repo else (_DEFAULT_SKILLS_DIR / "auto-generated")
        )
        repo = _self_skill_repo or SkillRepository(skills_dir=auto_gen_dir.parent)
        candidates = repo.list_candidates(db_path=db_path, limit=3)
        promoted_count = 0

        judge_prompt = (
            "You are a skill extraction assistant. Given a user query answered by "
            "multi-iteration agentic RAG, decide if it represents a generalizable, "
            "reusable skill pattern worth capturing. "
            "Return ONLY compact JSON: "
            '{"is_generalizable": bool, "skill_name": str, '
            '"skill_description": str, "confidence": float}'
        )
        for candidate in candidates:
            candidate_id = int(candidate["id"])
            query_text = str(candidate.get("query_text") or "")
            try:
                raw = llm.invoke([
                    {"type": "system", "content": judge_prompt},
                    {"type": "human", "content": f"Query: {query_text}"},
                ])
                text = str(getattr(raw, "content", raw) or "")
                start, end = text.find("{"), text.rfind("}") + 1
                if start == -1 or end <= start:
                    continue
                payload = json.loads(text[start:end])
                if not isinstance(payload, dict):
                    continue
                if not bool(payload.get("is_generalizable")) or float(payload.get("confidence") or 0) < 0.7:
                    continue
                skill_name = str(payload.get("skill_name") or "auto_skill").strip()
                skill_description = str(payload.get("skill_description") or "").strip()
            except Exception as exc:  # noqa: BLE001
                log.debug("_promote_skill_candidates: judge failed for id=%s: %s", candidate_id, exc)
                continue

            try:
                auto_gen_dir.mkdir(parents=True, exist_ok=True)
                slug = skill_name.lower().replace(" ", "-")
                md_content = (
                    f"---\nid: {slug}\nname: {skill_name}\n"
                    f"description: {skill_description}\nenabled_by_default: false\n"
                    f"priority: 0\ntriggers:\n  keywords: []\n  modes: []\n"
                    f"  file_types: []\n  output_styles: []\nruntime_overrides: {{}}\n---\n\n"
                    f"# {skill_name}\n\n{skill_description}\n\n"
                    f"*Auto-generated from query:* {query_text}\n"
                )
                (auto_gen_dir / f"{candidate_id}.md").write_text(md_content, encoding="utf-8")
                repo.mark_candidate_promoted(db_path=db_path, candidate_id=candidate_id)
                promoted_count += 1
            except Exception as exc:  # noqa: BLE001
                log.warning("_promote_skill_candidates: write failed for id=%s: %s", candidate_id, exc)

        return promoted_count
