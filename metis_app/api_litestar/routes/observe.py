"""Semantic Observability API — observe, label, and export trace runs."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from litestar import Router, get, post
from litestar.exceptions import HTTPException as LitestarHTTPException
from pydantic import BaseModel

import metis_app.settings_store as _store
from metis_app.api_litestar.common import get_session_repo
from metis_app.services.artifact_converter import ArtifactConverter
from metis_app.services.behavior_discovery import BehaviorDiscoveryService

_DEFAULT_LIMIT = 50


class FeedbackBody(BaseModel):
    label: str  # "reinforce" | "suppress" | "investigate"
    note: str = ""
    segment: str = ""  # optional trace segment identifier


def _validate_label(label: str) -> None:
    allowed = {"reinforce", "suppress", "investigate"}
    if label not in allowed:
        raise LitestarHTTPException(
            status_code=422,
            detail=f"label must be one of: {sorted(allowed)!r}",
        )


def _get_profile_or_404(svc: BehaviorDiscoveryService, run_id: str) -> dict[str, Any]:
    profile = svc.get_run_profile(run_id)
    if profile is None:
        raise LitestarHTTPException(status_code=404, detail=f"Run not found: {run_id}")
    return profile.to_dict() if hasattr(profile, "to_dict") else dict(profile)


def _latest_feedback_note(run_id: str, label: str = "") -> str:
    try:
        with get_session_repo()._connect() as conn:
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
    try:
        with get_session_repo()._connect() as conn:
            row = conn.execute(
                "SELECT label FROM trace_feedback WHERE run_id = ? ORDER BY created_at DESC LIMIT 1",
                (run_id,),
            ).fetchone()
            return str(row["label"] or "reinforce") if row else "reinforce"
    except Exception:
        return "reinforce"


@get("/v1/traces/discover")
def get_discover(limit: int = _DEFAULT_LIMIT) -> dict[str, Any]:
    """Return clustered + ranked behavioral profiles for recent runs."""
    result = BehaviorDiscoveryService().discover(limit=limit)
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


@get("/v1/traces/{run_id:str}/semantic")
def get_run_semantic(run_id: str) -> dict[str, Any]:
    """Deep behavioral profile for a single run, with optional LLM narrative."""
    settings = _store.load_settings()
    result = BehaviorDiscoveryService().describe_run(run_id, settings=settings)
    if not result:
        raise LitestarHTTPException(status_code=404, detail=f"Run not found: {run_id}")
    return result


@post("/v1/traces/{run_id:str}/feedback", status_code=200)
def post_trace_feedback(run_id: str, data: FeedbackBody) -> dict[str, Any]:
    """Attach a human label to a trace run."""
    _validate_label(data.label)
    feedback_id = str(uuid.uuid4())
    ts = datetime.now(timezone.utc).isoformat()
    try:
        with get_session_repo()._connect() as conn:
            conn.execute(
                """
                INSERT INTO trace_feedback(feedback_id, run_id, segment, label, note, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (feedback_id, run_id, data.segment, data.label, data.note, ts),
            )
    except Exception as exc:
        raise LitestarHTTPException(status_code=500, detail=str(exc)) from exc
    return {"feedback_id": feedback_id, "run_id": run_id, "label": data.label, "created_at": ts}


@get("/v1/traces/feedback")
def get_trace_feedback(
    label: str = "",
    run_id: str = "",
    limit: int = 50,
) -> dict[str, Any]:
    """List trace feedback records, optionally filtered by label or run_id."""
    try:
        with get_session_repo()._connect() as conn:
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
        if "no such table" in str(exc).lower():
            records = []
        else:
            raise LitestarHTTPException(status_code=500, detail=str(exc)) from exc
    return {"records": records, "count": len(records)}


@post("/v1/traces/{run_id:str}/export/skill", status_code=200)
def export_run_as_skill(run_id: str, skill_id: str = "") -> dict[str, Any]:
    """Convert a trace run into a SKILL.md in the skills/ directory."""
    svc = BehaviorDiscoveryService()
    profile_data = _get_profile_or_404(svc, run_id)
    note = _latest_feedback_note(run_id, label="reinforce")
    return ArtifactConverter().export_as_skill(
        run_id, profile_data, skill_id=skill_id, feedback_note=note
    )


@post("/v1/traces/{run_id:str}/export/eval", status_code=200)
def export_run_as_eval(run_id: str) -> dict[str, Any]:
    """Append a trace run to evals/golden_dataset.jsonl as a golden eval case."""
    svc = BehaviorDiscoveryService()
    profile_data = _get_profile_or_404(svc, run_id)
    events = svc._read_run_events(run_id)
    note = _latest_feedback_note(run_id, label="reinforce")
    label = _latest_label(run_id)
    return ArtifactConverter().export_as_eval(
        run_id, profile_data, events, feedback_note=note, label=label
    )


router = Router(
    path="",
    route_handlers=[
        get_discover,
        get_trace_feedback,
        get_run_semantic,
        post_trace_feedback,
        export_run_as_skill,
        export_run_as_eval,
    ],
    tags=["observe"],
)
