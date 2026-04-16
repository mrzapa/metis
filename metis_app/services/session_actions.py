"""Framework-neutral helpers for hydrating NYX install action results onto sessions.

Extracted from the retired ``metis_app.api.sessions`` FastAPI module so the
Litestar API layer (and any future caller) can hydrate session details without
pulling in a FastAPI dependency.
"""

from __future__ import annotations

from typing import Any

from metis_app.models.session_types import SessionDetail
from metis_app.services.nyx_runtime import NYX_INSTALL_ACTION_TYPE
from metis_app.services.trace_store import TraceStore


def _list_string_values(value: object) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _session_run_ids(detail: SessionDetail) -> list[str]:
    run_ids: list[str] = []
    for message in detail.messages:
        run_id = str(message.run_id or "").strip()
        if run_id and run_id not in run_ids:
            run_ids.append(run_id)
    return run_ids


def _action_identity(action: dict[str, object]) -> tuple[str, str]:
    payload = action.get("payload") if isinstance(action.get("payload"), dict) else {}
    proposal = action.get("proposal") if isinstance(action.get("proposal"), dict) else {}
    action_id = str(action.get("action_id") or payload.get("action_id") or "").strip()
    proposal_token = str(
        payload.get("proposal_token") or proposal.get("proposal_token") or ""
    ).strip()
    return action_id, proposal_token


def _build_action_result(
    *,
    run_id: str,
    action: dict[str, object],
    payload: dict[str, object],
) -> dict[str, object]:
    action_payload = action.get("payload") if isinstance(action.get("payload"), dict) else {}
    proposal = action.get("proposal") if isinstance(action.get("proposal"), dict) else {}
    component_names = _list_string_values(
        payload.get("component_names")
        or action_payload.get("component_names")
        or proposal.get("component_names")
    )
    installer_fields = {
        "command": _list_string_values(payload.get("command")),
        "cwd": str(payload.get("cwd") or "").strip(),
        "package_script": str(payload.get("package_script") or "").strip(),
        "returncode": int(payload.get("returncode") or 0),
        "stdout_excerpt": str(payload.get("stdout_excerpt") or "").strip(),
        "stderr_excerpt": str(payload.get("stderr_excerpt") or "").strip(),
    }
    installer: dict[str, Any] | None = None
    if any(
        installer_fields[key]
        for key in (
            "command",
            "cwd",
            "package_script",
            "returncode",
            "stdout_excerpt",
            "stderr_excerpt",
        )
    ):
        installer = installer_fields

    result: dict[str, object] = {
        "run_id": run_id,
        "approved": bool(payload.get("approved")),
        "status": str(payload.get("status") or "").strip(),
        "action_id": str(payload.get("action_id") or action.get("action_id") or "").strip(),
        "action_type": NYX_INSTALL_ACTION_TYPE,
        "proposal_token": str(
            payload.get("proposal_token")
            or action_payload.get("proposal_token")
            or proposal.get("proposal_token")
            or ""
        ).strip(),
        "component_names": component_names,
        "component_count": int(
            payload.get("component_count")
            or action_payload.get("component_count")
            or proposal.get("component_count")
            or len(component_names)
            or 0
        ),
        "execution_status": str(payload.get("execution_status") or "").strip(),
        "proposal": proposal or None,
    }
    if installer is not None:
        result["installer"] = installer
    failure_code = str(payload.get("failure_code") or "").strip()
    if failure_code:
        result["failure_code"] = failure_code
    return result


def hydrate_session_actions(detail: SessionDetail) -> SessionDetail:
    """Attach action_result payloads to messages whose actions have executed."""
    run_ids = _session_run_ids(detail)
    if not run_ids:
        return detail

    run_traces = TraceStore().read_runs(run_ids)
    detail.traces = run_traces

    for message in detail.messages:
        run_id = str(message.run_id or "").strip()
        if not run_id or not message.actions:
            continue

        expected_actions = [
            action
            for action in message.actions
            if isinstance(action, dict)
            and str(action.get("action_type") or "").strip() == NYX_INSTALL_ACTION_TYPE
        ]
        if not expected_actions:
            continue

        run_events = list(run_traces.get(run_id) or [])
        for action in expected_actions:
            expected_action_id, expected_token = _action_identity(action)
            for event in reversed(run_events):
                if str(event.get("event_type") or "").strip() != "nyx_install_action_submitted":
                    continue
                payload = event.get("payload")
                if not isinstance(payload, dict):
                    continue
                if str(payload.get("action_type") or NYX_INSTALL_ACTION_TYPE).strip() != NYX_INSTALL_ACTION_TYPE:
                    continue

                candidate_action_id = str(payload.get("action_id") or "").strip()
                candidate_token = str(payload.get("proposal_token") or "").strip()
                if expected_action_id and candidate_action_id != expected_action_id:
                    continue
                if expected_token and candidate_token != expected_token:
                    continue

                message.action_result = _build_action_result(
                    run_id=run_id,
                    action=action,
                    payload=payload,
                )
                break
            if message.action_result is not None:
                break

    return detail
