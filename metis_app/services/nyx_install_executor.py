"""Revalidate and execute approved Nyx install actions."""

from __future__ import annotations

from dataclasses import dataclass
import json
import pathlib
import shutil
import subprocess
from typing import Any, Callable

from metis_app.services.nyx_catalog import (
    NYX_REVIEW_STATUS_INSTALLABLE,
    NYX_REVIEW_STATUS_PREVIEW,
    NyxCatalogBroker,
    NyxCatalogComponentNotFoundError,
)
from metis_app.services.nyx_runtime import NYX_INSTALL_ACTION_TYPE, build_nyx_install_actions

_HERE = pathlib.Path(__file__).resolve().parent
_PACKAGE_ROOT = _HERE.parent
_REPO_ROOT = _PACKAGE_ROOT.parent
_DEFAULT_WEB_APP_DIR = _REPO_ROOT / "apps" / "metis-web"
_INSTALLER_PACKAGE_SCRIPT = "ui:add:nyx"
_EXPECTED_INSTALLER_SCRIPT = "node ./scripts/add-nyx-component.mjs"
_INSTALLER_SCRIPT_PATH = pathlib.Path("scripts") / "add-nyx-component.mjs"
_INSTALL_TIMEOUT_SECONDS = 300
_MAX_OUTPUT_EXCERPT_CHARS = 4_000
_INSTALLER_AUTO_DECLINE_INPUT = "n\n" * 64


class NyxInstallActionExecutionError(RuntimeError):
    """Raised when a Nyx install proposal cannot be safely executed."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = str(code or "nyx_install_failed").strip() or "nyx_install_failed"
        self.metadata = dict(metadata or {})


@dataclass(frozen=True)
class NyxInstallRevalidationResult:
    action_id: str
    proposal_token: str
    component_names: tuple[str, ...]
    component_count: int
    proposal: dict[str, Any]


@dataclass(frozen=True)
class NyxInstallExecutionResult:
    action_id: str
    proposal_token: str
    component_names: tuple[str, ...]
    component_count: int
    proposal: dict[str, Any]
    command: tuple[str, ...]
    cwd: str
    returncode: int
    stdout_excerpt: str
    stderr_excerpt: str
    package_script: str = _INSTALLER_PACKAGE_SCRIPT
    execution_status: str = "completed"

    def to_response_payload(self, *, run_id: str, approved: bool) -> dict[str, Any]:
        payload = {
            "run_id": run_id,
            "approved": approved,
            "status": "completed",
            "action_id": self.action_id,
            "action_type": NYX_INSTALL_ACTION_TYPE,
            "proposal_token": self.proposal_token,
            "component_names": list(self.component_names),
            "component_count": self.component_count,
            "execution_status": self.execution_status,
            "proposal": self.proposal,
            "installer": {
                "command": list(self.command),
                "cwd": self.cwd,
                "package_script": self.package_script,
                "returncode": self.returncode,
            },
        }
        if self.stdout_excerpt:
            payload["installer"]["stdout_excerpt"] = self.stdout_excerpt
        if self.stderr_excerpt:
            payload["installer"]["stderr_excerpt"] = self.stderr_excerpt
        return payload

    def to_trace_payload(self, *, approved: bool) -> dict[str, Any]:
        payload = {
            "approved": approved,
            "action_id": self.action_id,
            "action_type": NYX_INSTALL_ACTION_TYPE,
            "proposal_token": self.proposal_token,
            "component_names": list(self.component_names),
            "component_count": self.component_count,
            "status": "success",
            "execution_status": self.execution_status,
            "command": list(self.command),
            "cwd": self.cwd,
            "package_script": self.package_script,
            "returncode": self.returncode,
        }
        if self.stdout_excerpt:
            payload["stdout_excerpt"] = self.stdout_excerpt
        if self.stderr_excerpt:
            payload["stderr_excerpt"] = self.stderr_excerpt
        return payload


def _normalize_component_names(values: Any) -> tuple[str, ...]:
    if isinstance(values, str):
        candidates = [values]
    elif isinstance(values, (list, tuple, set)):
        candidates = list(values)
    else:
        candidates = []

    normalized: list[str] = []
    seen: set[str] = set()
    for value in candidates:
        text = str(value or "").strip().lower()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return tuple(normalized)


def _proposal_component_names(proposal: dict[str, Any]) -> tuple[str, ...]:
    component_names = _normalize_component_names(proposal.get("component_names"))
    if component_names:
        return component_names

    names: list[str] = []
    for component in list(proposal.get("components") or []):
        if not isinstance(component, dict):
            continue
        component_name = str(component.get("component_name") or "").strip().lower()
        if component_name:
            names.append(component_name)
    return _normalize_component_names(names)


def _proposal_token_from_action(action: dict[str, Any], proposal: dict[str, Any]) -> str:
    payload = action.get("payload") if isinstance(action.get("payload"), dict) else {}
    return str(
        payload.get("proposal_token")
        or proposal.get("proposal_token")
        or ""
    ).strip()


def _clip_output(text: str) -> str:
    normalized = str(text or "").strip()
    if len(normalized) <= _MAX_OUTPUT_EXCERPT_CHARS:
        return normalized
    return normalized[: _MAX_OUTPUT_EXCERPT_CHARS - 3] + "..."


def _load_package_manifest(web_app_dir: pathlib.Path) -> dict[str, Any]:
    package_json_path = web_app_dir / "package.json"
    try:
        raw_text = package_json_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise NyxInstallActionExecutionError(
            f"Nyx installer package manifest is missing: {package_json_path}",
            code="installer_unavailable",
            metadata={"cwd": str(web_app_dir), "package_json_path": str(package_json_path)},
        ) from exc

    try:
        package_manifest = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise NyxInstallActionExecutionError(
            f"Nyx installer package manifest is invalid JSON: {package_json_path}",
            code="installer_unavailable",
            metadata={"cwd": str(web_app_dir), "package_json_path": str(package_json_path)},
        ) from exc

    if not isinstance(package_manifest, dict):
        raise NyxInstallActionExecutionError(
            f"Nyx installer package manifest must be a JSON object: {package_json_path}",
            code="installer_unavailable",
            metadata={"cwd": str(web_app_dir), "package_json_path": str(package_json_path)},
        )

    return package_manifest


def _resolve_installer_command(
    component_names: tuple[str, ...],
    *,
    web_app_dir: pathlib.Path,
    which: Callable[[str], str | None],
) -> tuple[str, ...]:
    package_manifest = _load_package_manifest(web_app_dir)
    scripts = package_manifest.get("scripts") if isinstance(package_manifest.get("scripts"), dict) else {}
    configured_script = str(scripts.get(_INSTALLER_PACKAGE_SCRIPT) or "").strip()
    if configured_script != _EXPECTED_INSTALLER_SCRIPT:
        raise NyxInstallActionExecutionError(
            "Nyx installer package script is unavailable or has an unexpected command.",
            code="installer_unavailable",
            metadata={
                "cwd": str(web_app_dir),
                "package_script": _INSTALLER_PACKAGE_SCRIPT,
                "configured_script": configured_script,
                "expected_script": _EXPECTED_INSTALLER_SCRIPT,
            },
        )

    node_executable = which("node")
    if not node_executable:
        raise NyxInstallActionExecutionError(
            "Node.js is required to execute approved Nyx installs.",
            code="installer_unavailable",
            metadata={"cwd": str(web_app_dir), "package_script": _INSTALLER_PACKAGE_SCRIPT},
        )

    installer_script_path = web_app_dir / _INSTALLER_SCRIPT_PATH
    if not installer_script_path.is_file():
        raise NyxInstallActionExecutionError(
            f"Nyx installer script is missing: {installer_script_path}",
            code="installer_unavailable",
            metadata={
                "cwd": str(web_app_dir),
                "package_script": _INSTALLER_PACKAGE_SCRIPT,
                "installer_script_path": str(installer_script_path),
            },
        )

    return (str(node_executable), str(installer_script_path), "--", *component_names)


def _runtime_inputs_from_proposal(
    proposal: dict[str, Any],
    component_names: tuple[str, ...],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    selected_components = [
        {"component_name": component_name}
        for component_name in component_names
    ]
    settings = {
        "nyx_runtime": {
            "schema_version": str(proposal.get("schema_version") or "1.0").strip() or "1.0",
            "query": str(proposal.get("query") or "").strip(),
            "intent_type": str(proposal.get("intent_type") or "").strip(),
            "matched_signals": [
                str(signal).strip()
                for signal in list(proposal.get("matched_signals") or [])
                if str(signal).strip()
            ],
            "selected_components": selected_components,
        }
    }
    artifacts = [
        {
            "type": "nyx_component_selection",
            "payload": {"selected_components": selected_components},
        }
    ]
    return settings, artifacts


def revalidate_nyx_install_action(
    *,
    run_id: str,
    persisted_action: dict[str, Any],
    action_id: str = "",
    proposal_token: str = "",
    requested_component_names: Any = None,
    broker: NyxCatalogBroker | None = None,
) -> NyxInstallRevalidationResult:
    if str(persisted_action.get("action_type") or "").strip() != NYX_INSTALL_ACTION_TYPE:
        raise NyxInstallActionExecutionError(
            "Unsupported run action type.",
            code="unsupported_action",
            metadata={"action_type": persisted_action.get("action_type")},
        )

    proposal = dict(persisted_action.get("proposal") or {})
    resolved_action_id = str(persisted_action.get("action_id") or "").strip()
    resolved_token = _proposal_token_from_action(persisted_action, proposal)
    component_names = _proposal_component_names(proposal)

    if not resolved_action_id or not resolved_token or not component_names:
        raise NyxInstallActionExecutionError(
            "Nyx install proposal is incomplete and cannot be executed.",
            code="invalid_proposal",
            metadata={
                "action_id": resolved_action_id,
                "proposal_token": resolved_token,
                "component_names": list(component_names),
            },
        )

    requested_action_id = str(action_id or "").strip()
    if requested_action_id and requested_action_id != resolved_action_id:
        raise NyxInstallActionExecutionError(
            "Nyx install action id no longer matches the persisted proposal.",
            code="action_mismatch",
            metadata={
                "action_id": resolved_action_id,
                "requested_action_id": requested_action_id,
            },
        )

    requested_token = str(proposal_token or "").strip()
    if requested_token and requested_token != resolved_token:
        raise NyxInstallActionExecutionError(
            "Nyx install proposal token no longer matches the persisted proposal.",
            code="proposal_mismatch",
            metadata={
                "proposal_token": resolved_token,
                "requested_proposal_token": requested_token,
            },
        )

    normalized_requested_names = _normalize_component_names(requested_component_names)
    if normalized_requested_names and normalized_requested_names != component_names:
        raise NyxInstallActionExecutionError(
            "Nyx install request components do not match the persisted proposal.",
            code="component_mismatch",
            metadata={
                "component_names": list(component_names),
                "requested_component_names": list(normalized_requested_names),
            },
        )

    resolved_broker = broker or NyxCatalogBroker()
    for component_name in component_names:
        try:
            detail = resolved_broker.get_component_detail(component_name)
        except NyxCatalogComponentNotFoundError as exc:
            raise NyxInstallActionExecutionError(
                f"Nyx component '{component_name}' is no longer supported by the reviewed snapshot.",
                code="unsupported_component",
                metadata={"component_name": component_name},
            ) from exc
        except ValueError as exc:
            raise NyxInstallActionExecutionError(
                f"Nyx component '{component_name}' could not be revalidated.",
                code="invalid_proposal",
                metadata={"component_name": component_name},
            ) from exc
        except RuntimeError as exc:
            raise NyxInstallActionExecutionError(
                "Current Nyx review snapshot could not be loaded for revalidation.",
                code="revalidation_failed",
                metadata={"component_name": component_name},
            ) from exc

        if not detail.install_path_safe:
            raise NyxInstallActionExecutionError(
                f"Nyx component '{component_name}' failed install path safety revalidation.",
                code="unsafe_component",
                metadata={
                    "component_name": component_name,
                    "install_path_policy": detail.install_path_policy,
                    "install_path_issues": list(detail.install_path_issues),
                },
            )

        if detail.review_status == NYX_REVIEW_STATUS_PREVIEW or not detail.installable:
            raise NyxInstallActionExecutionError(
                f"Nyx component '{component_name}' is no longer reviewed as installable.",
                code="preview_only_component",
                metadata={
                    "component_name": component_name,
                    "review_status": detail.review_status,
                    "installable": bool(detail.installable),
                    "previewable": bool(detail.previewable),
                    "audit_issues": list(detail.audit_issues),
                },
            )

        if detail.review_status != NYX_REVIEW_STATUS_INSTALLABLE:
            raise NyxInstallActionExecutionError(
                f"Nyx component '{component_name}' failed reviewed-installable revalidation.",
                code="unsupported_component",
                metadata={
                    "component_name": component_name,
                    "review_status": detail.review_status,
                },
            )

    settings, artifacts = _runtime_inputs_from_proposal(proposal, component_names)
    current_actions = build_nyx_install_actions(
        run_id=run_id,
        settings=settings,
        artifacts=artifacts,
        broker=resolved_broker,
    )
    if len(current_actions) != 1:
        raise NyxInstallActionExecutionError(
            "Nyx install proposal is stale and must be regenerated.",
            code="stale_proposal",
            metadata={
                "action_id": resolved_action_id,
                "proposal_token": resolved_token,
                "component_names": list(component_names),
            },
        )

    current_action = dict(current_actions[0])
    current_proposal = dict(current_action.get("proposal") or {})
    current_action_id = str(current_action.get("action_id") or "").strip()
    current_token = _proposal_token_from_action(current_action, current_proposal)

    if current_action_id != resolved_action_id or current_token != resolved_token:
        raise NyxInstallActionExecutionError(
            "Nyx install proposal is stale and must be regenerated.",
            code="stale_proposal",
            metadata={
                "action_id": resolved_action_id,
                "proposal_token": resolved_token,
                "current_action_id": current_action_id,
                "current_proposal_token": current_token,
                "component_names": list(component_names),
            },
        )

    return NyxInstallRevalidationResult(
        action_id=resolved_action_id,
        proposal_token=resolved_token,
        component_names=component_names,
        component_count=int(current_proposal.get("component_count") or len(component_names)),
        proposal=current_proposal,
    )


def execute_nyx_install_action(
    *,
    run_id: str,
    persisted_action: dict[str, Any],
    action_id: str = "",
    proposal_token: str = "",
    requested_component_names: Any = None,
    broker: NyxCatalogBroker | None = None,
    web_app_dir: pathlib.Path | None = None,
    which: Callable[[str], str | None] = shutil.which,
    subprocess_run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> NyxInstallExecutionResult:
    revalidated = revalidate_nyx_install_action(
        run_id=run_id,
        persisted_action=persisted_action,
        action_id=action_id,
        proposal_token=proposal_token,
        requested_component_names=requested_component_names,
        broker=broker,
    )

    resolved_web_app_dir = pathlib.Path(web_app_dir or _DEFAULT_WEB_APP_DIR)
    command = _resolve_installer_command(
        revalidated.component_names,
        web_app_dir=resolved_web_app_dir,
        which=which,
    )

    try:
        completed = subprocess_run(
            list(command),
            cwd=str(resolved_web_app_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            input=_INSTALLER_AUTO_DECLINE_INPUT,
            timeout=_INSTALL_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise NyxInstallActionExecutionError(
            "Nyx installer timed out before completing.",
            code="installer_failed",
            metadata={
                "action_id": revalidated.action_id,
                "proposal_token": revalidated.proposal_token,
                "component_names": list(revalidated.component_names),
                "component_count": revalidated.component_count,
                "command": list(command),
                "cwd": str(resolved_web_app_dir),
                "package_script": _INSTALLER_PACKAGE_SCRIPT,
                "timeout_seconds": _INSTALL_TIMEOUT_SECONDS,
            },
        ) from exc
    except OSError as exc:
        raise NyxInstallActionExecutionError(
            "Nyx installer could not be launched.",
            code="installer_unavailable",
            metadata={
                "action_id": revalidated.action_id,
                "proposal_token": revalidated.proposal_token,
                "component_names": list(revalidated.component_names),
                "component_count": revalidated.component_count,
                "command": list(command),
                "cwd": str(resolved_web_app_dir),
                "package_script": _INSTALLER_PACKAGE_SCRIPT,
            },
        ) from exc

    stdout_excerpt = _clip_output(getattr(completed, "stdout", ""))
    stderr_excerpt = _clip_output(getattr(completed, "stderr", ""))
    returncode = int(getattr(completed, "returncode", 1) or 0)
    if returncode != 0:
        detail = stderr_excerpt or stdout_excerpt or "Nyx installer exited with a non-zero status."
        raise NyxInstallActionExecutionError(
            f"Nyx installer failed: {detail}",
            code="installer_failed",
            metadata={
                "action_id": revalidated.action_id,
                "proposal_token": revalidated.proposal_token,
                "component_names": list(revalidated.component_names),
                "component_count": revalidated.component_count,
                "command": list(command),
                "cwd": str(resolved_web_app_dir),
                "package_script": _INSTALLER_PACKAGE_SCRIPT,
                "returncode": returncode,
                "stdout_excerpt": stdout_excerpt,
                "stderr_excerpt": stderr_excerpt,
            },
        )

    return NyxInstallExecutionResult(
        action_id=revalidated.action_id,
        proposal_token=revalidated.proposal_token,
        component_names=revalidated.component_names,
        component_count=revalidated.component_count,
        proposal=revalidated.proposal,
        command=command,
        cwd=str(resolved_web_app_dir),
        returncode=returncode,
        stdout_excerpt=stdout_excerpt,
        stderr_excerpt=stderr_excerpt,
    )