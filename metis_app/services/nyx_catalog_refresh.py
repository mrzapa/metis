"""Build a governed Nyx snapshot from reviewer-owned metadata and upstream registry items."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from dataclasses import dataclass
from typing import Any, Callable

from metis_app.services.nyx_catalog import NYX_INSTALL_TARGET_POLICY_NAME
from metis_app.services.nyx_catalog import NYX_REGISTRY_SCHEMA_URL
from metis_app.services.nyx_catalog import NYX_REGISTRY_URL_TEMPLATE
from metis_app.services.nyx_catalog import NYX_REVIEW_STATUS_INSTALLABLE
from metis_app.services.nyx_catalog import NYX_REVIEW_STATUS_PREVIEW
from metis_app.services.nyx_catalog import NYX_SOURCE
from metis_app.services.nyx_catalog import NYX_SOURCE_REPO
from metis_app.services.nyx_catalog import _default_fetch_json
from metis_app.services.nyx_catalog import normalize_component_name

_SCHEMA_VERSION = "1.1"
_DEFAULT_ALLOWED_TARGET_PREFIXES = ("components/", "hooks/", "lib/")
_DEFAULT_ALLOWED_TARGETLESS_TYPES = ("registry:lib",)
_PACKAGE_SPECIFIER_PATTERN = re.compile(r"^(?:@[A-Za-z0-9._-]+/)?[A-Za-z0-9._-]+$")
_WINDOWS_ABSOLUTE_TARGET_PATTERN = re.compile(r"^[A-Za-z]:[\\/]")

FetchJson = Callable[[str], dict[str, Any]]

_ASSETS_DIR = pathlib.Path(__file__).resolve().parent.parent / "assets"
DEFAULT_NYX_REVIEW_MANIFEST_PATH = _ASSETS_DIR / "nyx_catalog_review.json"
DEFAULT_NYX_SNAPSHOT_PATH = _ASSETS_DIR / "nyx_catalog_snapshot.json"


@dataclass(frozen=True)
class NyxReviewComponent:
    component_name: str
    review_status: str
    description: str
    required_dependencies: tuple[str, ...]


@dataclass(frozen=True)
class NyxInstallTargetPolicy:
    policy_name: str
    allowed_target_prefixes: tuple[str, ...]
    allowed_targetless_types: tuple[str, ...]


@dataclass(frozen=True)
class NyxReviewManifest:
    source: str
    source_repo: str
    registry_url_template: str
    schema_url: str
    install_target_policy: NyxInstallTargetPolicy
    components: dict[str, NyxReviewComponent]


@dataclass(frozen=True)
class NyxSnapshotBuildResult:
    payload: dict[str, Any]
    previewable_components: tuple[str, ...]
    installable_components: tuple[str, ...]
    blocking_installable_components: tuple[str, ...]
    issues_by_component: dict[str, tuple[str, ...]]


def _load_json_object(path: pathlib.Path, *, label: str) -> dict[str, Any]:
    try:
        raw_text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise RuntimeError(f"{label} is missing: {path}") from exc

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{label} is invalid JSON: {path}") from exc

    if not isinstance(payload, dict):
        raise RuntimeError(f"{label} must be a JSON object: {path}")
    return payload


def _trim_text(value: Any, fallback: str = "") -> str:
    if not isinstance(value, str):
        return fallback
    return value.strip()


def _dedupe_strings(values: Any) -> tuple[str, ...]:
    if not isinstance(values, list):
        return ()

    deduped: list[str] = []
    seen: set[str] = set()
    for raw_value in values:
        normalized = _trim_text(raw_value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return tuple(deduped)


def _to_non_negative_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return 0


def _humanize_component_name(component_name: str) -> str:
    words = re.split(r"[-_]+", component_name.strip())
    return " ".join(word.capitalize() for word in words if word)


def _normalize_review_status(value: Any) -> str:
    normalized = _trim_text(value, fallback=NYX_REVIEW_STATUS_INSTALLABLE).lower()
    if normalized in {NYX_REVIEW_STATUS_INSTALLABLE, NYX_REVIEW_STATUS_PREVIEW}:
        return normalized
    raise RuntimeError(f"Unsupported Nyx review status: {value}")


def _normalize_file_summaries(raw_files: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_files, list):
        return []

    files: list[dict[str, Any]] = []
    for raw_file in raw_files:
        if not isinstance(raw_file, dict):
            continue
        path = _trim_text(raw_file.get("path"))
        file_type = _trim_text(raw_file.get("file_type")) or _trim_text(
            raw_file.get("type"),
            fallback="registry:file",
        )
        target = _trim_text(raw_file.get("target"))
        content_bytes = _to_non_negative_int(raw_file.get("content_bytes"))
        if content_bytes == 0:
            content = raw_file.get("content")
            content_bytes = len(content.encode("utf-8")) if isinstance(content, str) else 0
        if not path and not target:
            continue
        files.append(
            {
                "path": path,
                "file_type": file_type,
                "target": target,
                "content_bytes": content_bytes,
            }
        )
    return files


def _normalize_targets(raw_targets: Any, files: list[dict[str, Any]]) -> list[str]:
    explicit_targets = list(_dedupe_strings(raw_targets))
    if explicit_targets:
        return explicit_targets

    return list(
        _dedupe_strings(
            [file_summary["target"] for file_summary in files if file_summary["target"]]
        )
    )


def _is_package_dependency_specifier(value: Any) -> bool:
    if not isinstance(value, str):
        return False

    trimmed = value.strip()
    if not trimmed:
        return False
    if trimmed.startswith(".") or trimmed.startswith("/") or "\\" in trimmed:
        return False
    if any(character.isspace() for character in trimmed):
        return False
    return bool(_PACKAGE_SPECIFIER_PATTERN.match(trimmed))


def _audit_registry_item(
    component_name: str,
    registry_item: dict[str, Any],
    *,
    resolved_name: str,
) -> list[str]:
    issues: list[str] = []

    if resolved_name != component_name:
        issues.append(
            f"{component_name}: registry item name mismatch ({registry_item.get('name') or 'missing name'})"
        )

    if not isinstance(registry_item.get("files"), list) or not registry_item.get("files"):
        issues.append(f"{component_name}: registry item does not declare any files")

    for field_name in ("dependencies", "devDependencies"):
        field_value = registry_item.get(field_name)
        if field_value is None:
            continue
        if not isinstance(field_value, list):
            issues.append(f"{component_name}: {field_name} must be an array when present")
            continue

        invalid_specifiers = [
            specifier for specifier in field_value if not _is_package_dependency_specifier(specifier)
        ]
        if invalid_specifiers:
            issues.append(
                f"{component_name}: {field_name} contains invalid package specifiers: "
                + ", ".join(str(specifier) for specifier in invalid_specifiers)
            )

    registry_dependencies = registry_item.get("registryDependencies")
    if registry_dependencies is not None:
        if not isinstance(registry_dependencies, list):
            issues.append(f"{component_name}: registryDependencies must be an array when present")
        else:
            invalid_registry_dependencies = [
                specifier
                for specifier in registry_dependencies
                if not isinstance(specifier, str) or not specifier.strip()
            ]
            if invalid_registry_dependencies:
                issues.append(
                    f"{component_name}: registryDependencies contains blank or non-string entries"
                )

    return issues


def _audit_target_paths(
    component_name: str,
    files: list[dict[str, Any]],
    policy: NyxInstallTargetPolicy,
) -> list[str]:
    issues: list[str] = []

    for file_summary in files:
        target = file_summary["target"]
        file_type = file_summary["file_type"]
        path = file_summary["path"] or "<unknown>"
        if not target:
            if file_type in policy.allowed_targetless_types:
                continue
            issues.append(
                f"{component_name}: {path} has no install target for file type {file_type}"
            )
            continue

        normalized_target = target.replace("\\", "/")
        if normalized_target.startswith("/") or _WINDOWS_ABSOLUTE_TARGET_PATTERN.match(target):
            issues.append(f"{component_name}: {target} must remain relative to the app root")
            continue
        if "\\" in target:
            issues.append(f"{component_name}: {target} must use POSIX path separators")
            continue
        if any(segment == ".." for segment in normalized_target.split("/")):
            issues.append(f"{component_name}: {target} cannot traverse parent directories")
            continue
        if not any(
            normalized_target.startswith(prefix) for prefix in policy.allowed_target_prefixes
        ):
            issues.append(
                f"{component_name}: {target} is outside the allowed target prefixes "
                + ", ".join(policy.allowed_target_prefixes)
            )

    return issues


def load_nyx_review_manifest(
    review_manifest_path: pathlib.Path = DEFAULT_NYX_REVIEW_MANIFEST_PATH,
) -> NyxReviewManifest:
    payload = _load_json_object(review_manifest_path, label="Nyx review manifest")

    target_policy_payload = payload.get("install_target_policy")
    if target_policy_payload is not None and not isinstance(target_policy_payload, dict):
        raise RuntimeError(
            f"Nyx review manifest install_target_policy must be an object: {review_manifest_path}"
        )
    target_policy_payload = target_policy_payload or {}

    install_target_policy = NyxInstallTargetPolicy(
        policy_name=_trim_text(
            target_policy_payload.get("policy_name"),
            fallback=NYX_INSTALL_TARGET_POLICY_NAME,
        ),
        allowed_target_prefixes=_dedupe_strings(
            target_policy_payload.get("allowed_target_prefixes")
        )
        or _DEFAULT_ALLOWED_TARGET_PREFIXES,
        allowed_targetless_types=_dedupe_strings(
            target_policy_payload.get("allowed_targetless_types")
        )
        or _DEFAULT_ALLOWED_TARGETLESS_TYPES,
    )

    raw_components = payload.get("components")
    if not isinstance(raw_components, dict):
        raise RuntimeError(
            f"Nyx review manifest must expose a components object: {review_manifest_path}"
        )

    components: dict[str, NyxReviewComponent] = {}
    for raw_component_name, raw_component in raw_components.items():
        component_payload = raw_component if isinstance(raw_component, dict) else {}
        component_name = normalize_component_name(
            component_payload.get("component_name") or raw_component_name
        )
        if not component_name:
            raise RuntimeError(
                f"Nyx review manifest component names must be non-empty: {review_manifest_path}"
            )
        if component_name in components:
            raise RuntimeError(
                f"Nyx review manifest contains duplicate component entries: {component_name}"
            )

        required_dependencies = _dedupe_strings(
            component_payload.get("required_dependencies")
            if "required_dependencies" in component_payload
            else component_payload.get("requiredDependencies")
        )
        components[component_name] = NyxReviewComponent(
            component_name=component_name,
            review_status=_normalize_review_status(component_payload.get("review_status")),
            description=_trim_text(component_payload.get("description")),
            required_dependencies=required_dependencies,
        )

    return NyxReviewManifest(
        source=_trim_text(payload.get("source"), fallback=NYX_SOURCE),
        source_repo=_trim_text(payload.get("source_repo"), fallback=NYX_SOURCE_REPO),
        registry_url_template=_trim_text(
            payload.get("registry_url_template"),
            fallback=NYX_REGISTRY_URL_TEMPLATE,
        ),
        schema_url=_trim_text(payload.get("schema_url"), fallback=NYX_REGISTRY_SCHEMA_URL),
        install_target_policy=install_target_policy,
        components=components,
    )


def _build_local_registry_fetcher(source_path: pathlib.Path) -> FetchJson:
    payload = _load_json_object(source_path, label="Nyx local source catalog")
    components_payload = payload.get("components") if isinstance(payload.get("components"), dict) else payload
    if not isinstance(components_payload, dict):
        raise RuntimeError(f"Nyx local source catalog must be an object: {source_path}")

    source_items: dict[str, dict[str, Any]] = {}
    for raw_component_name, raw_component in components_payload.items():
        if not isinstance(raw_component, dict):
            continue
        component_name = normalize_component_name(
            raw_component.get("name") or raw_component.get("component_name") or raw_component_name
        )
        if not component_name:
            continue
        source_items[component_name] = raw_component

    def _fetch_json(url: str) -> dict[str, Any]:
        component_name = normalize_component_name(url.rsplit("/", 1)[-1].split("?", 1)[0])
        if component_name.endswith(".json"):
            component_name = component_name[:-5]
        if component_name not in source_items:
            raise RuntimeError(f"Nyx local source catalog is missing component: {component_name}")
        return source_items[component_name]

    return _fetch_json


def build_nyx_registry_fetcher(
    *,
    source_path: pathlib.Path | None = None,
    fetch_json: FetchJson | None = None,
) -> FetchJson:
    if source_path is not None and fetch_json is not None:
        raise ValueError("source_path and fetch_json are mutually exclusive")
    if source_path is not None:
        return _build_local_registry_fetcher(source_path)
    if fetch_json is not None:
        return fetch_json
    return _default_fetch_json


def build_nyx_catalog_snapshot(
    review_manifest: NyxReviewManifest,
    *,
    fetch_json: FetchJson,
) -> NyxSnapshotBuildResult:
    components_payload: dict[str, dict[str, Any]] = {}
    issues_by_component: dict[str, tuple[str, ...]] = {}
    previewable_components: list[str] = []
    installable_components: list[str] = []
    blocking_installable_components: list[str] = []

    for component_name in sorted(review_manifest.components):
        review_component = review_manifest.components[component_name]
        registry_url = review_manifest.registry_url_template.replace("{name}", component_name)
        registry_item = fetch_json(registry_url)
        if not isinstance(registry_item, dict):
            raise RuntimeError(f"Nyx registry item must be a JSON object: {registry_url}")

        resolved_name = (
            normalize_component_name(
                _trim_text(registry_item.get("name"), fallback=component_name)
            )
            or component_name
        )
        files = _normalize_file_summaries(registry_item.get("files"))
        targets = _normalize_targets(registry_item.get("targets"), files)
        audit_issues = tuple(
            _audit_registry_item(component_name, registry_item, resolved_name=resolved_name)
        )
        install_path_issues = tuple(
            _audit_target_paths(component_name, files, review_manifest.install_target_policy)
        )
        install_path_safe = not install_path_issues
        installable = (
            review_component.review_status == NYX_REVIEW_STATUS_INSTALLABLE
            and not audit_issues
            and install_path_safe
        )

        previewable_components.append(component_name)
        if installable:
            installable_components.append(component_name)
        elif review_component.review_status == NYX_REVIEW_STATUS_INSTALLABLE:
            blocking_installable_components.append(component_name)

        component_issues = tuple((*audit_issues, *install_path_issues))
        if component_issues:
            issues_by_component[component_name] = component_issues

        description = _trim_text(registry_item.get("description"), fallback=review_component.description)
        curated_description = review_component.description or description

        components_payload[component_name] = {
            "component_name": resolved_name,
            "title": _trim_text(
                registry_item.get("title"),
                fallback=_humanize_component_name(component_name),
            ),
            "description": description or curated_description,
            "curated_description": curated_description or description,
            "component_type": _trim_text(
                registry_item.get("type"),
                fallback="registry:ui",
            ),
            "install_target": f"@nyx/{component_name}",
            "registry_url": registry_url,
            "schema_url": _trim_text(
                registry_item.get("$schema"),
                fallback=review_manifest.schema_url,
            ),
            "source": review_manifest.source,
            "source_repo": review_manifest.source_repo,
            "review_status": review_component.review_status,
            "previewable": True,
            "installable": installable,
            "required_dependencies": list(review_component.required_dependencies),
            "dependencies": list(_dedupe_strings(registry_item.get("dependencies"))),
            "dev_dependencies": list(_dedupe_strings(registry_item.get("devDependencies"))),
            "registry_dependencies": list(
                _dedupe_strings(registry_item.get("registryDependencies"))
            ),
            "file_count": max(_to_non_negative_int(registry_item.get("file_count")), len(files)),
            "targets": targets,
            "files": files,
            "install_path_policy": review_manifest.install_target_policy.policy_name,
            "install_path_safe": install_path_safe,
            "install_path_issues": list(install_path_issues),
            "audit_issues": list(audit_issues),
        }

    payload = {
        "schema_version": _SCHEMA_VERSION,
        "source": review_manifest.source,
        "source_repo": review_manifest.source_repo,
        "registry_url_template": review_manifest.registry_url_template,
        "schema_url": review_manifest.schema_url,
        "install_target_policy": {
            "policy_name": review_manifest.install_target_policy.policy_name,
            "allowed_target_prefixes": list(
                review_manifest.install_target_policy.allowed_target_prefixes
            ),
            "allowed_targetless_types": list(
                review_manifest.install_target_policy.allowed_targetless_types
            ),
        },
        "reviewed_component_count": len(previewable_components),
        "previewable_component_count": len(previewable_components),
        "installable_component_count": len(installable_components),
        "components": components_payload,
    }

    return NyxSnapshotBuildResult(
        payload=payload,
        previewable_components=tuple(previewable_components),
        installable_components=tuple(installable_components),
        blocking_installable_components=tuple(blocking_installable_components),
        issues_by_component=issues_by_component,
    )


def refresh_nyx_catalog_snapshot(
    *,
    review_manifest_path: pathlib.Path = DEFAULT_NYX_REVIEW_MANIFEST_PATH,
    snapshot_path: pathlib.Path = DEFAULT_NYX_SNAPSHOT_PATH,
    source_path: pathlib.Path | None = None,
    fetch_json: FetchJson | None = None,
    strict: bool = True,
) -> NyxSnapshotBuildResult:
    review_manifest = load_nyx_review_manifest(review_manifest_path)
    registry_fetcher = build_nyx_registry_fetcher(source_path=source_path, fetch_json=fetch_json)
    build_result = build_nyx_catalog_snapshot(review_manifest, fetch_json=registry_fetcher)

    if strict and build_result.blocking_installable_components:
        blocking_summary = ", ".join(build_result.blocking_installable_components)
        raise RuntimeError(
            "Nyx snapshot refresh refused to write installable components with safety violations: "
            + blocking_summary
        )

    snapshot_path.write_text(json.dumps(build_result.payload, indent=2) + "\n", encoding="utf-8")
    return build_result


def _build_summary_lines(
    build_result: NyxSnapshotBuildResult,
    *,
    snapshot_path: pathlib.Path,
) -> list[str]:
    lines = [
        f"[nyx:refresh] wrote snapshot: {snapshot_path}",
        "[nyx:refresh] reviewed={} previewable={} installable={}".format(
            len(build_result.previewable_components),
            len(build_result.previewable_components),
            len(build_result.installable_components),
        ),
    ]
    preview_only_with_issues = [
        component_name
        for component_name, issues in sorted(build_result.issues_by_component.items())
        if issues and component_name not in build_result.blocking_installable_components
    ]
    if preview_only_with_issues:
        lines.append(
            "[nyx:refresh] preview-only review candidates with metadata or path findings: "
            + ", ".join(preview_only_with_issues)
        )
    return lines


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refresh the governed Nyx snapshot from the review manifest.",
    )
    parser.add_argument(
        "--review-file",
        type=pathlib.Path,
        default=DEFAULT_NYX_REVIEW_MANIFEST_PATH,
        help="Path to the reviewer-owned Nyx manifest JSON.",
    )
    parser.add_argument(
        "--snapshot-out",
        type=pathlib.Path,
        default=DEFAULT_NYX_SNAPSHOT_PATH,
        help="Path to write the generated Nyx snapshot JSON.",
    )
    parser.add_argument(
        "--source-file",
        type=pathlib.Path,
        default=None,
        help="Optional local Nyx registry source JSON for offline refreshes and tests.",
    )
    parser.add_argument(
        "--allow-installable-issues",
        action="store_true",
        help="Write the snapshot even if installable components fail metadata or target-path safety checks.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        build_result = refresh_nyx_catalog_snapshot(
            review_manifest_path=args.review_file,
            snapshot_path=args.snapshot_out,
            source_path=args.source_file,
            strict=not args.allow_installable_issues,
        )
    except RuntimeError as exc:
        print(f"[nyx:refresh] {exc}", file=sys.stderr)
        return 1

    for line in _build_summary_lines(build_result, snapshot_path=args.snapshot_out):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())