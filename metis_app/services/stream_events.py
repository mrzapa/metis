"""Helpers for additive normalization of streamed chat events.

The normalization is intentionally additive: existing top-level event keys are
preserved so legacy clients continue to work, while AG-UI-inspired envelope
metadata is added for newer consumers.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

_STATUS_BY_EVENT_TYPE = {
    "run_started": "started",
    "retrieval_complete": "in_progress",
    "retrieval_augmented": "in_progress",
    "subqueries": "in_progress",
    "iteration_start": "in_progress",
    "gaps_identified": "in_progress",
    "refinement_retrieval": "in_progress",
    "fallback_decision": "in_progress",
    "token": "in_progress",
    "final": "completed",
    "action_required": "action_required",
    "error": "failed",
    "persona_created": "in_progress",
    "simulation_round_start": "in_progress",
    "belief_shift": "in_progress",
    "simulation_round": "in_progress",
    "simulation_complete": "completed",
    "topics_extracted": "in_progress",
    "swarm_start": "in_progress",
    "swarm_round_start": "in_progress",
    "swarm_persona_vote": "in_progress",
    "swarm_round_end": "in_progress",
    "swarm_synthesis": "in_progress",
    "swarm_complete": "completed",
}

_LIFECYCLE_BY_EVENT_TYPE = {
    "run_started": "run",
    "retrieval_complete": "retrieval",
    "retrieval_augmented": "retrieval",
    "subqueries": "retrieval",
    "iteration_start": "reflection",
    "gaps_identified": "reflection",
    "refinement_retrieval": "retrieval",
    "fallback_decision": "fallback",
    "token": "generation",
    "final": "run",
    "action_required": "action",
    "error": "error",
    "persona_created": "simulation",
    "simulation_round_start": "simulation",
    "belief_shift": "simulation",
    "simulation_round": "simulation",
    "simulation_complete": "simulation",
    "topics_extracted": "simulation",
    "swarm_start": "simulation",
    "swarm_round_start": "simulation",
    "swarm_persona_vote": "simulation",
    "swarm_round_end": "simulation",
    "swarm_synthesis": "simulation",
    "swarm_complete": "simulation",
}

# Scion-inspired three-axis agent state model
# agent_phase: coarse lifecycle phase visible to orchestrators
_PHASE_BY_EVENT_TYPE = {
    "run_started": "initializing",
    "retrieval_complete": "running",
    "retrieval_augmented": "running",
    "subqueries": "running",
    "iteration_start": "running",
    "gaps_identified": "running",
    "refinement_retrieval": "running",
    "fallback_decision": "running",
    "token": "running",
    "iteration_converged": "running",
    "iteration_complete": "running",
    "final": "stopped",
    "action_required": "stopped",
    "error": "error",
    "persona_created": "running",
    "simulation_round_start": "running",
    "belief_shift": "running",
    "simulation_round": "running",
    "simulation_complete": "stopped",
    "topics_extracted": "running",
    "swarm_start": "running",
    "swarm_round_start": "running",
    "swarm_persona_vote": "running",
    "swarm_round_end": "running",
    "swarm_synthesis": "running",
    "swarm_complete": "stopped",
}

# agent_activity: fine-grained current activity within the phase
_ACTIVITY_BY_EVENT_TYPE = {
    "run_started": "idle",
    "retrieval_complete": "executing",
    "retrieval_augmented": "executing",
    "subqueries": "executing",
    "iteration_start": "thinking",
    "gaps_identified": "thinking",
    "refinement_retrieval": "executing",
    "fallback_decision": "thinking",
    "token": "executing",
    "iteration_converged": "thinking",
    "iteration_complete": "thinking",
    "final": "completed",
    "action_required": "waiting_for_input",
    "error": "idle",
    "persona_created": "executing",
    "simulation_round_start": "executing",
    "belief_shift": "thinking",
    "simulation_round": "executing",
    "simulation_complete": "completed",
    "topics_extracted": "thinking",
    "swarm_start": "executing",
    "swarm_round_start": "executing",
    "swarm_persona_vote": "thinking",
    "swarm_round_end": "thinking",
    "swarm_synthesis": "thinking",
    "swarm_complete": "completed",
}

_META_KEYS = {
    "type",
    "event_type",
    "run_id",
    "event_id",
    "timestamp",
    "status",
    "lifecycle",
    "agent_phase",
    "agent_activity",
    "detail",
    "ancestry",
    "subject",
    "payload",
    "context",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _deterministic_event_id(run_id: str, event_type: str, payload: dict[str, Any]) -> str:
    stable_payload = {
        str(key): value
        for key, value in sorted(payload.items(), key=lambda item: str(item[0]))
        if str(key) not in {"event_id", "timestamp"}
    }
    digest = hashlib.sha1(
        json.dumps(stable_payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:12]
    prefix = f"{run_id}:{event_type}" if run_id else event_type
    return f"{prefix}:{digest}"


def normalize_stream_event(
    event: dict[str, Any],
    *,
    sequence: int | None = None,
    source: str = "rag_stream",
) -> dict[str, Any]:
    """Return *event* with additive normalized envelope metadata.

    Existing fields are preserved for compatibility.
    """
    normalized = dict(event or {})

    event_type = str(normalized.get("event_type") or normalized.get("type") or "").strip()
    run_id = str(normalized.get("run_id") or "").strip()

    if event_type:
        normalized["type"] = event_type
        normalized["event_type"] = event_type
    if run_id:
        normalized["run_id"] = run_id

    existing_payload = normalized.get("payload")
    if isinstance(existing_payload, dict):
        payload_wrapper = dict(existing_payload)
    else:
        payload_wrapper = {
            key: value
            for key, value in normalized.items()
            if key not in _META_KEYS
        }
    normalized["payload"] = payload_wrapper

    event_id = str(normalized.get("event_id") or "").strip()
    if not event_id:
        if sequence is not None and sequence > 0:
            event_id = f"{run_id}:{sequence}" if run_id else f"event:{sequence}"
        else:
            event_id = _deterministic_event_id(run_id, event_type, payload_wrapper)
    normalized["event_id"] = event_id

    normalized["timestamp"] = str(normalized.get("timestamp") or _utc_now_iso())
    normalized["status"] = str(
        normalized.get("status")
        or _STATUS_BY_EVENT_TYPE.get(event_type, "in_progress")
    )
    normalized["lifecycle"] = str(
        normalized.get("lifecycle")
        or _LIFECYCLE_BY_EVENT_TYPE.get(event_type, "event")
    )

    existing_context = normalized.get("context")
    context_wrapper = dict(existing_context) if isinstance(existing_context, dict) else {}
    context_wrapper.setdefault("run_id", run_id)
    context_wrapper.setdefault("source", source)
    normalized["context"] = context_wrapper

    # Three-axis agent state (additive — not overriding if already set)
    normalized["agent_phase"] = str(
        normalized.get("agent_phase")
        or _PHASE_BY_EVENT_TYPE.get(event_type, "running")
    )
    normalized["agent_activity"] = str(
        normalized.get("agent_activity")
        or _ACTIVITY_BY_EVENT_TYPE.get(event_type, "executing")
    )
    if run_id and "subject" not in normalized:
        normalized["subject"] = f"session.{run_id}.events"

    return normalized


__all__ = ["normalize_stream_event"]
