"""Semantic Observability API  — observe, label, and export trace runs.

Endpoints:

    GET  /v1/traces/discover                 — cluster and rank recent runs by interestingness
    GET  /v1/traces/{run_id}/semantic        — deep profile + optional LLM narrative for one run
    POST /v1/traces/{run_id}/feedback        — attach a reinforce / suppress / investigate label
    GET  /v1/traces/feedback                 — list feedback records (filterable by label)
    POST /v1/traces/{run_id}/export/skill    — convert a run into a skills/ SKILL.md
    POST /v1/traces/{run_id}/export/eval     — add a run as a golden eval case
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import metis_app.settings_store as _store
from metis_app.services.behavior_discovery import BehaviorDiscoveryService
from metis_app.services.artifact_converter import ArtifactConverter
from metis_app.services.session_repository import SessionRepository

router = APIRouter()

_DEFAULT_LIMIT = 50


# ---------------------------------------------------------------------------
# Request / response helpers
# ---------------------------------------------------------------------------


class FeedbackBody(BaseModel):
    label: str            # "reinforce" | "suppress" | "investigate"
    note: str = ""
    segment: str = ""     # optional trace segment identifier


def _db() -> SessionRepository:
    return SessionRepository()


def _svc() -> BehaviorDiscoveryService:
    return BehaviorDiscoveryService()


def _conv() -> ArtifactConverter:
    return ArtifactConverter()


# ---------------------------------------------------------------------------
# Discovery endpoints
# ---------------------------------------------------------------------------


@router.get("/v1/traces/discover")
def get_discover(limit: int = _DEFAULT_LIMIT) -> dict[str, Any]:
    """Return clustered + ranked behavioral profiles for recent runs."""
    result = _svc().discover(limit=limit)
    profiles_sorted = sorted(
        result.profiles,
        key=lambda p: p.interestingness_score,
        reverse=True,
    )
    return {
        "profiles": [p.to_dict() for p in profiles_sorted],
        "clusters": result.clusters,
        "anomalous_run_ids": result.anomalous_run_ids,
        "strategy_histogram": result.strategy_histogram,
        "total_runs_scanned": result.total_runs_scanned,
    }


@router.get("/v1/traces/{run_id}/semantic")
def get_run_semantic(run_id: str) -> dict[str, Any]:
    """Deep behavioral profile for a single run, with optional LLM narrative."""
    settings = _store.load_settings()
    result = _svc().describe_run(run_id, settings=settings)
    if not result:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    return result


# ---------------------------------------------------------------------------
# Feedback endpoints
# ---------------------------------------------------------------------------


@router.post("/v1/traces/{run_id}/feedback")
def post_trace_feedback(run_id: str, body: FeedbackBody) -> dict[str, Any]:
    """Attach a human label to a trace run."""
    _validate_label(body.label)
    feedback_id = str(uuid.uuid4())
    ts = datetime.now(timezone.utc).isoformat()
    db = _db()
    try:
        with db._connect() as conn:
            conn.execute(
                """
                INSERT INTO trace_feedback(feedback_id, run_id, segment, label, note, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (feedback_id, run_id, body.segment, body.label, body.note, ts),
            )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"feedback_id": feedback_id, "run_id": run_id, "label": body.label, "created_at": ts}


@router.get("/v1/traces/feedback")
def get_trace_feedback(
    label: str = "",
    run_id: str = "",
    limit: int = 50,
) -> dict[str, Any]:
    """List trace feedback records, optionally filtered by label or run_id."""
    db = _db()
    try:
        with db._connect() as conn:
            clauses: list[str] = []
            params: list[Any] = []
            if label:
                clauses.append("label = ?")
                params.append(label)
            if run_id:
                clauses.append("run_id = ?")
                params.append(run_id)
            where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
            params.append(max(1, min(limit, 500)))
            rows = conn.execute(
                f"SELECT * FROM trace_feedback {where} ORDER BY created_at DESC LIMIT ?",
                params,
            ).fetchall()
            records = [dict(r) for r in rows]
    except sqlite3.OperationalError as exc:
        # Table may not exist on first call before server restart
        if "no such table" in str(exc).lower():
            records = []
        else:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"records": records, "count": len(records)}


# ---------------------------------------------------------------------------
# Export endpoints
# ---------------------------------------------------------------------------


@router.post("/v1/traces/{run_id}/export/skill")
def export_run_as_skill(run_id: str, skill_id: str = "") -> dict[str, Any]:
    """Convert a trace run into a SKILL.md in the skills/ directory."""
    profile_data = _get_profile_or_404(run_id)
    # Pull the most recent reinforce note for description
    note = _latest_feedback_note(run_id, label="reinforce")
    result = _conv().export_as_skill(run_id, profile_data, skill_id=skill_id, feedback_note=note)
    return result


@router.post("/v1/traces/{run_id}/export/eval")
def export_run_as_eval(run_id: str) -> dict[str, Any]:
    """Append a trace run to evals/golden_dataset.jsonl as a golden eval case."""
    profile_data = _get_profile_or_404(run_id)
    events = _svc()._read_run_events(run_id)
    note = _latest_feedback_note(run_id, label="reinforce")
    label = _latest_label(run_id)
    result = _conv().export_as_eval(
        run_id, profile_data, events, feedback_note=note, label=label
    )
    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _validate_label(label: str) -> None:
    allowed = {"reinforce", "suppress", "investigate"}
    if label not in allowed:
        raise HTTPException(
            status_code=422,
            detail=f"label must be one of: {sorted(allowed)!r}",
        )


def _get_profile_or_404(run_id: str) -> dict[str, Any]:
    profile = _svc().get_run_profile(run_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    return profile.to_dict() if hasattr(profile, "to_dict") else dict(profile)


def _latest_feedback_note(run_id: str, label: str = "") -> str:
    """Return the most recent human note for this run, or empty string."""
    try:
        db = _db()
        with db._connect() as conn:
            params: list[Any] = [run_id]
            where_label = ""
            if label:
                where_label = " AND label = ?"
                params.append(label)
            row = conn.execute(
                f"SELECT note FROM trace_feedback WHERE run_id = ?{where_label} ORDER BY created_at DESC LIMIT 1",
                params,
            ).fetchone()
            return str(row["note"] or "") if row else ""
    except Exception:
        return ""


def _latest_label(run_id: str) -> str:
    """Return the most recent label for this run."""
    try:
        db = _db()
        with db._connect() as conn:
            row = conn.execute(
                "SELECT label FROM trace_feedback WHERE run_id = ? ORDER BY created_at DESC LIMIT 1",
                (run_id,),
            ).fetchone()
            return str(row["label"] or "reinforce") if row else "reinforce"
    except Exception:
        return "reinforce"
