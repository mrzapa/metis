"""Broker and normalization layer for the curated NyxUI registry subset."""

from __future__ import annotations

import json
import os
import pathlib
import re
import threading
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

NYX_SOURCE = "nyx_registry"
NYX_SOURCE_REPO = "https://github.com/MihirJaiswal/nyxui"
NYX_REGISTRY_URL_TEMPLATE = "https://nyxui.com/r/{name}.json"
NYX_REGISTRY_SCHEMA_URL = "https://ui.shadcn.com/schema/registry-item.json"
NYX_REVIEW_STATUS_INSTALLABLE = "installable"
NYX_REVIEW_STATUS_PREVIEW = "preview"
NYX_INSTALL_TARGET_POLICY_NAME = "metis_nyx_targets_v1"
_NYX_REGISTRY_BASE_URL = "https://nyxui.com/r/"
_NYX_ASSET_PACKAGE = "metis_app.assets"
_NYX_SNAPSHOT_NAME = "nyx_catalog_snapshot.json"
_CURATED_CATALOG_ENV_VAR = "METIS_NYX_CATALOG_PATH"

JsonFetcher = callable


@dataclass(frozen=True)
class CuratedNyxComponent:
    description: str
    required_dependencies: tuple[str, ...]


@dataclass(frozen=True)
class NyxCatalogFileSummary:
    path: str
    file_type: str
    target: str
    content_bytes: int


@dataclass(frozen=True)
class NyxCatalogComponentSummary:
    component_name: str
    title: str
    description: str
    curated_description: str
    component_type: str
    install_target: str
    registry_url: str
    schema_url: str
    source: str
    source_repo: str
    required_dependencies: tuple[str, ...]
    dependencies: tuple[str, ...]
    dev_dependencies: tuple[str, ...]
    registry_dependencies: tuple[str, ...]
    file_count: int
    targets: tuple[str, ...]
    review_status: str = NYX_REVIEW_STATUS_INSTALLABLE
    previewable: bool = True
    installable: bool = True
    install_path_policy: str = NYX_INSTALL_TARGET_POLICY_NAME
    install_path_safe: bool = True
    install_path_issues: tuple[str, ...] = ()
    audit_issues: tuple[str, ...] = ()


@dataclass(frozen=True)
class NyxCatalogComponentDetail:
    component_name: str
    title: str
    description: str
    curated_description: str
    component_type: str
    install_target: str
    registry_url: str
    schema_url: str
    source: str
    source_repo: str
    required_dependencies: tuple[str, ...]
    dependencies: tuple[str, ...]
    dev_dependencies: tuple[str, ...]
    registry_dependencies: tuple[str, ...]
    file_count: int
    targets: tuple[str, ...]
    files: tuple[NyxCatalogFileSummary, ...]
    review_status: str = NYX_REVIEW_STATUS_INSTALLABLE
    previewable: bool = True
    installable: bool = True
    install_path_policy: str = NYX_INSTALL_TARGET_POLICY_NAME
    install_path_safe: bool = True
    install_path_issues: tuple[str, ...] = ()
    audit_issues: tuple[str, ...] = ()

    def to_summary(self) -> NyxCatalogComponentSummary:
        return NyxCatalogComponentSummary(
            component_name=self.component_name,
            title=self.title,
            description=self.description,
            curated_description=self.curated_description,
            component_type=self.component_type,
            install_target=self.install_target,
            registry_url=self.registry_url,
            schema_url=self.schema_url,
            source=self.source,
            source_repo=self.source_repo,
            required_dependencies=self.required_dependencies,
            dependencies=self.dependencies,
            dev_dependencies=self.dev_dependencies,
            registry_dependencies=self.registry_dependencies,
            file_count=self.file_count,
            targets=self.targets,
            review_status=self.review_status,
            previewable=self.previewable,
            installable=self.installable,
            install_path_policy=self.install_path_policy,
            install_path_safe=self.install_path_safe,
            install_path_issues=self.install_path_issues,
            audit_issues=self.audit_issues,
        )


@dataclass(frozen=True)
class NyxCatalogSearchResult:
    query: str
    total: int
    matched: int
    curated_only: bool
    source: str
    items: tuple[NyxCatalogComponentSummary, ...]


class NyxCatalogComponentNotFoundError(ValueError):
    """Raised when a requested Nyx component is not part of the curated catalog."""


def _configured_curated_catalog_path() -> pathlib.Path | None:
    configured = os.getenv(_CURATED_CATALOG_ENV_VAR, "").strip()
    if not configured:
        return None
    return pathlib.Path(configured).expanduser().resolve()


def _load_json_object_from_path(
    path: pathlib.Path,
    *,
    missing_message: str,
    invalid_message: str,
) -> Any:
    try:
        raw_text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise RuntimeError(missing_message) from exc

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(invalid_message) from exc


def _load_packaged_snapshot_payload() -> Any:
    try:
        raw_text = resources.files(_NYX_ASSET_PACKAGE).joinpath(_NYX_SNAPSHOT_NAME).read_text(
            encoding="utf-8"
        )
    except (FileNotFoundError, ModuleNotFoundError) as exc:
        raise RuntimeError(
            f"Packaged Nyx snapshot is missing: {_NYX_ASSET_PACKAGE}/{_NYX_SNAPSHOT_NAME}"
        ) from exc

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Packaged Nyx snapshot is invalid JSON: {_NYX_ASSET_PACKAGE}/{_NYX_SNAPSHOT_NAME}"
        ) from exc


def _is_snapshot_payload(raw_payload: Any) -> bool:
    return isinstance(raw_payload, dict) and isinstance(raw_payload.get("components"), dict)


def _curated_components_from_snapshot(
    snapshot_details: dict[str, NyxCatalogComponentDetail],
) -> dict[str, CuratedNyxComponent]:
    return {
        component_name: CuratedNyxComponent(
            description=detail.curated_description or detail.description,
            required_dependencies=detail.required_dependencies,
        )
        for component_name, detail in snapshot_details.items()
        if detail.installable
    }


@lru_cache(maxsize=None)
def load_curated_nyx_components(
    curated_catalog_path: pathlib.Path | None = None,
) -> dict[str, CuratedNyxComponent]:
    path = curated_catalog_path or _configured_curated_catalog_path()
    if path is None:
        return _curated_components_from_snapshot(load_nyx_snapshot_component_details())

    raw_payload = _load_json_object_from_path(
        path,
        missing_message=f"Nyx catalog definition is missing: {path}",
        invalid_message=f"Nyx catalog definition is invalid JSON: {path}",
    )

    if _is_snapshot_payload(raw_payload):
        return _curated_components_from_snapshot(
            _normalize_snapshot_component_details(raw_payload, source_label=str(path))
        )

    if not isinstance(raw_payload, dict):
        raise RuntimeError(f"Nyx catalog definition must be a JSON object: {path}")

    curated_components: dict[str, CuratedNyxComponent] = {}
    for component_name, component_payload in raw_payload.items():
        normalized_name = normalize_component_name(str(component_name))
        payload = component_payload if isinstance(component_payload, dict) else {}
        curated_components[normalized_name] = CuratedNyxComponent(
            description=_normalize_text(payload.get("description")),
            required_dependencies=tuple(
                _dedupe_strings(payload.get("requiredDependencies"))
            ),
        )
    return curated_components


def normalize_component_name(component_name: str) -> str:
    candidate = str(component_name or "").strip()
    if not candidate:
        return ""

    lowered_candidate = candidate.lower()

    if lowered_candidate.startswith(_NYX_REGISTRY_BASE_URL):
        resource_name = lowered_candidate[len(_NYX_REGISTRY_BASE_URL) :].split("?", 1)[0]
        return resource_name[:-5] if resource_name.endswith(".json") else resource_name

    if lowered_candidate.startswith("@nyx/"):
        return lowered_candidate[len("@nyx/") :]

    if lowered_candidate.startswith("nyx/"):
        return lowered_candidate[len("nyx/") :]

    return lowered_candidate


def _default_fetch_json(url: str) -> dict[str, Any]:
    request = urllib_request.Request(
        url,
        headers={"accept": "application/json", "user-agent": "metis-nyx-broker/1.0"},
    )
    try:
        with urllib_request.urlopen(request, timeout=10) as response:
            payload = json.load(response)
    except urllib_error.HTTPError as exc:
        raise RuntimeError(
            f"Nyx registry request failed: {url} ({exc.code} {exc.reason})"
        ) from exc
    except urllib_error.URLError as exc:
        raise RuntimeError(f"Nyx registry request failed: {url} ({exc.reason})") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Nyx registry returned invalid JSON: {url}") from exc

    if not isinstance(payload, dict):
        raise RuntimeError(f"Nyx registry returned an unexpected payload: {url}")
    return payload


def _normalize_text(value: Any, fallback: str = "") -> str:
    if not isinstance(value, str):
        return fallback
    return value.strip()


def _dedupe_strings(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []

    deduped: list[str] = []
    seen: set[str] = set()
    for raw_value in values:
        normalized = _normalize_text(raw_value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _to_non_negative_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return 0


def _normalize_bool(value: Any, *, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y", "on"}:
            return True
        if normalized in {"false", "0", "no", "n", "off"}:
            return False
    return fallback


def _normalize_review_status(
    value: Any,
    *,
    fallback: str = NYX_REVIEW_STATUS_INSTALLABLE,
) -> str:
    normalized = _normalize_text(value, fallback=fallback).lower()
    if normalized in {
        NYX_REVIEW_STATUS_INSTALLABLE,
        NYX_REVIEW_STATUS_PREVIEW,
    }:
        return normalized
    return fallback


def _humanize_component_name(component_name: str) -> str:
    words = re.split(r"[-_]+", component_name.strip())
    return " ".join(word.capitalize() for word in words if word)


def _normalize_file_summaries(raw_files: Any) -> tuple[NyxCatalogFileSummary, ...]:
    if not isinstance(raw_files, list):
        return ()

    files: list[NyxCatalogFileSummary] = []
    for raw_file in raw_files:
        if not isinstance(raw_file, dict):
            continue
        path = _normalize_text(raw_file.get("path"))
        file_type = _normalize_text(raw_file.get("file_type")) or _normalize_text(
            raw_file.get("type"),
            fallback="registry:file",
        )
        target = _normalize_text(raw_file.get("target"))
        content_bytes = _to_non_negative_int(raw_file.get("content_bytes"))
        if content_bytes == 0:
            content = raw_file.get("content")
            content_bytes = len(content.encode("utf-8")) if isinstance(content, str) else 0
        if not path and not target:
            continue
        files.append(
            NyxCatalogFileSummary(
                path=path,
                file_type=file_type,
                target=target,
                content_bytes=content_bytes,
            )
        )
    return tuple(files)


def _normalize_targets(
    raw_targets: Any,
    files: tuple[NyxCatalogFileSummary, ...],
) -> tuple[str, ...]:
    explicit_targets = tuple(_dedupe_strings(raw_targets))
    if explicit_targets:
        return explicit_targets
    return tuple(
        _dedupe_strings([file_summary.target for file_summary in files if file_summary.target])
    )


def _normalize_snapshot_component_detail(
    component_name: str,
    raw_component: Any,
) -> NyxCatalogComponentDetail:
    payload = raw_component if isinstance(raw_component, dict) else {}
    resolved_name = (
        normalize_component_name(
            _normalize_text(payload.get("component_name"), fallback=component_name)
        )
        or component_name
    )
    files = _normalize_file_summaries(payload.get("files"))
    targets = _normalize_targets(payload.get("targets"), files)
    description = _normalize_text(payload.get("description"))
    curated_description = _normalize_text(
        payload.get("curated_description"),
        fallback=description,
    )
    review_status = _normalize_review_status(payload.get("review_status"))
    install_path_safe = _normalize_bool(
        payload.get("install_path_safe"),
        fallback=True,
    )
    install_path_issues = tuple(_dedupe_strings(payload.get("install_path_issues")))
    audit_issues = tuple(_dedupe_strings(payload.get("audit_issues")))
    default_installable = (
        review_status == NYX_REVIEW_STATUS_INSTALLABLE
        and install_path_safe
        and not install_path_issues
        and not audit_issues
    )

    return NyxCatalogComponentDetail(
        component_name=resolved_name,
        title=_normalize_text(
            payload.get("title"),
            fallback=_humanize_component_name(resolved_name),
        ),
        description=description or curated_description,
        curated_description=curated_description or description,
        component_type=_normalize_text(
            payload.get("component_type"),
            fallback=_normalize_text(payload.get("type"), fallback="registry:ui"),
        ),
        install_target=_normalize_text(
            payload.get("install_target"),
            fallback=f"@nyx/{resolved_name}",
        ),
        registry_url=_normalize_text(
            payload.get("registry_url"),
            fallback=NYX_REGISTRY_URL_TEMPLATE.replace("{name}", resolved_name),
        ),
        schema_url=(
            _normalize_text(payload.get("schema_url"))
            or _normalize_text(payload.get("$schema"), fallback=NYX_REGISTRY_SCHEMA_URL)
        ),
        source=_normalize_text(payload.get("source"), fallback=NYX_SOURCE),
        source_repo=_normalize_text(payload.get("source_repo"), fallback=NYX_SOURCE_REPO),
        required_dependencies=tuple(
            _dedupe_strings(
                payload.get("required_dependencies")
                if "required_dependencies" in payload
                else payload.get("requiredDependencies")
            )
        ),
        dependencies=tuple(_dedupe_strings(payload.get("dependencies"))),
        dev_dependencies=tuple(
            _dedupe_strings(
                payload.get("dev_dependencies")
                if "dev_dependencies" in payload
                else payload.get("devDependencies")
            )
        ),
        registry_dependencies=tuple(
            _dedupe_strings(
                payload.get("registry_dependencies")
                if "registry_dependencies" in payload
                else payload.get("registryDependencies")
            )
        ),
        file_count=max(_to_non_negative_int(payload.get("file_count")), len(files)),
        targets=targets,
        files=files,
        review_status=review_status,
        previewable=_normalize_bool(payload.get("previewable"), fallback=True),
        installable=_normalize_bool(payload.get("installable"), fallback=default_installable),
        install_path_policy=_normalize_text(
            payload.get("install_path_policy"),
            fallback=NYX_INSTALL_TARGET_POLICY_NAME,
        ),
        install_path_safe=install_path_safe,
        install_path_issues=install_path_issues,
        audit_issues=audit_issues,
    )


def _normalize_snapshot_component_details(
    raw_payload: Any,
    *,
    source_label: str,
) -> dict[str, NyxCatalogComponentDetail]:
    if not _is_snapshot_payload(raw_payload):
        raise RuntimeError(f"Nyx snapshot must expose a components object: {source_label}")

    components_payload = raw_payload.get("components") or {}
    snapshot_details: dict[str, NyxCatalogComponentDetail] = {}
    for raw_component_name, raw_component in components_payload.items():
        component_name = normalize_component_name(str(raw_component_name or ""))
        if not component_name:
            continue
        snapshot_details[component_name] = _normalize_snapshot_component_detail(
            component_name,
            raw_component,
        )
    return snapshot_details


@lru_cache(maxsize=None)
def load_nyx_snapshot_component_details(
    snapshot_path: pathlib.Path | None = None,
) -> dict[str, NyxCatalogComponentDetail]:
    if snapshot_path is None:
        raw_payload = _load_packaged_snapshot_payload()
        source_label = f"{_NYX_ASSET_PACKAGE}/{_NYX_SNAPSHOT_NAME}"
    else:
        raw_payload = _load_json_object_from_path(
            snapshot_path,
            missing_message=f"Nyx snapshot is missing: {snapshot_path}",
            invalid_message=f"Nyx snapshot is invalid JSON: {snapshot_path}",
        )
        source_label = str(snapshot_path)

    return _normalize_snapshot_component_details(raw_payload, source_label=source_label)


@lru_cache(maxsize=None)
def load_optional_nyx_snapshot_component_details(
    snapshot_path: pathlib.Path,
) -> dict[str, NyxCatalogComponentDetail]:
    raw_payload = _load_json_object_from_path(
        snapshot_path,
        missing_message=f"Nyx catalog definition is missing: {snapshot_path}",
        invalid_message=f"Nyx catalog definition is invalid JSON: {snapshot_path}",
    )
    if not _is_snapshot_payload(raw_payload):
        return {}
    return _normalize_snapshot_component_details(raw_payload, source_label=str(snapshot_path))


def _apply_curated_component_overrides(
    detail: NyxCatalogComponentDetail,
    curated: CuratedNyxComponent,
) -> NyxCatalogComponentDetail:
    curated_description = curated.description or detail.curated_description or detail.description
    required_dependencies = curated.required_dependencies or detail.required_dependencies
    description = detail.description or curated_description
    return NyxCatalogComponentDetail(
        component_name=detail.component_name,
        title=detail.title,
        description=description,
        curated_description=curated_description,
        component_type=detail.component_type,
        install_target=detail.install_target,
        registry_url=detail.registry_url,
        schema_url=detail.schema_url,
        source=detail.source,
        source_repo=detail.source_repo,
        required_dependencies=required_dependencies,
        dependencies=detail.dependencies,
        dev_dependencies=detail.dev_dependencies,
        registry_dependencies=detail.registry_dependencies,
        file_count=detail.file_count,
        targets=detail.targets,
        files=detail.files,
        review_status=detail.review_status,
        previewable=detail.previewable,
        installable=detail.installable,
        install_path_policy=detail.install_path_policy,
        install_path_safe=detail.install_path_safe,
        install_path_issues=detail.install_path_issues,
        audit_issues=detail.audit_issues,
    )


def _search_score(component: NyxCatalogComponentSummary, query: str) -> int:
    normalized_query = query.strip().lower()
    if not normalized_query:
        return 0

    name = component.component_name.lower()
    title = component.title.lower()
    haystack = " ".join(
        [
            name,
            title,
            component.description.lower(),
            component.curated_description.lower(),
            " ".join(component.required_dependencies).lower(),
            " ".join(component.dependencies).lower(),
            " ".join(component.registry_dependencies).lower(),
        ]
    )

    score = 0
    if name == normalized_query:
        score += 100
    elif name.startswith(normalized_query):
        score += 80
    elif normalized_query in name:
        score += 60

    if title == normalized_query:
        score += 40
    elif title.startswith(normalized_query):
        score += 30
    elif normalized_query in title:
        score += 20

    query_terms = [term for term in re.split(r"\s+", normalized_query) if term]
    if query_terms and all(term in haystack for term in query_terms):
        score += 10 * len(query_terms)

    return score


class NyxCatalogBroker:
    """Fetch and normalize component metadata for METIS's curated NyxUI subset."""

    def __init__(
        self,
        *,
        curated_components: dict[str, CuratedNyxComponent] | None = None,
        fetch_json: Any | None = None,
    ) -> None:
        self._curated_components = dict(
            curated_components or load_curated_nyx_components()
        )
        self._fetch_json = fetch_json or _default_fetch_json
        self._snapshot_details: dict[str, NyxCatalogComponentDetail] = {}
        if fetch_json is None:
            configured_catalog_path = _configured_curated_catalog_path()
            if configured_catalog_path is not None:
                self._snapshot_details = load_optional_nyx_snapshot_component_details(
                    configured_catalog_path
                )
            if not self._snapshot_details:
                self._snapshot_details = load_nyx_snapshot_component_details()
        self._detail_cache: dict[str, NyxCatalogComponentDetail] = {}
        self._lock = threading.Lock()

    def iter_curated_components(self) -> tuple[tuple[str, CuratedNyxComponent], ...]:
        return tuple(
            (component_name, self._curated_components[component_name])
            for component_name in sorted(self._curated_components)
        )

    def _catalog_component_names(self) -> tuple[str, ...]:
        if self._snapshot_details:
            return tuple(
                component_name
                for component_name in sorted(self._snapshot_details)
                if self._snapshot_details[component_name].previewable
            )

        return tuple(sorted(self._curated_components))

    def search_catalog(
        self,
        *,
        query: str = "",
        limit: int | None = None,
    ) -> NyxCatalogSearchResult:
        summaries = [
            self.get_component_detail(component_name).to_summary()
            for component_name in self._catalog_component_names()
        ]
        normalized_query = query.strip()
        if normalized_query:
            ranked = [
                (_search_score(summary, normalized_query), summary)
                for summary in summaries
            ]
            filtered = [item for item in ranked if item[0] > 0]
            filtered.sort(
                key=lambda item: (
                    -item[0],
                    item[1].title.lower(),
                    item[1].component_name.lower(),
                )
            )
            matched_items = [summary for _, summary in filtered]
        else:
            matched_items = sorted(
                summaries,
                key=lambda summary: (summary.title.lower(), summary.component_name.lower()),
            )

        matched_count = len(matched_items)
        if limit is not None and limit > 0:
            matched_items = matched_items[:limit]

        return NyxCatalogSearchResult(
            query=normalized_query,
            total=len(summaries),
            matched=matched_count,
            curated_only=True,
            source=NYX_SOURCE,
            items=tuple(matched_items),
        )

    def get_component_detail(self, component_name: str) -> NyxCatalogComponentDetail:
        normalized_name = normalize_component_name(component_name)
        if not normalized_name:
            raise ValueError("Nyx component name is required")
        snapshot_detail = self._snapshot_details.get(normalized_name)
        if (
            normalized_name not in self._curated_components
            and (snapshot_detail is None or not snapshot_detail.previewable)
        ):
            raise NyxCatalogComponentNotFoundError(
                f"Unsupported NyxUI component: {component_name}"
            )

        with self._lock:
            cached = self._detail_cache.get(normalized_name)
        if cached is not None:
            return cached

        detail = self._fetch_component_detail(normalized_name)
        with self._lock:
            existing = self._detail_cache.get(normalized_name)
            if existing is not None:
                return existing
            self._detail_cache[normalized_name] = detail
        return detail

    def _fetch_component_detail(self, component_name: str) -> NyxCatalogComponentDetail:
        curated = self._curated_components.get(component_name)
        snapshot_detail = self._snapshot_details.get(component_name)
        if snapshot_detail is not None:
            if curated is None:
                return snapshot_detail
            return _apply_curated_component_overrides(snapshot_detail, curated)

        registry_url = NYX_REGISTRY_URL_TEMPLATE.replace("{name}", component_name)
        registry_item = self._fetch_json(registry_url)

        resolved_name = (
            normalize_component_name(
                _normalize_text(registry_item.get("name"), fallback=component_name)
            )
            or component_name
        )
        files = _normalize_file_summaries(registry_item.get("files"))
        targets = tuple(
            _dedupe_strings([file_summary.target for file_summary in files if file_summary.target])
        )

        if curated is None:
            raise NyxCatalogComponentNotFoundError(
                f"Unsupported NyxUI component: {component_name}"
            )

        return NyxCatalogComponentDetail(
            component_name=resolved_name,
            title=_normalize_text(
                registry_item.get("title"),
                fallback=_humanize_component_name(component_name),
            ),
            description=_normalize_text(
                registry_item.get("description"),
                fallback=curated.description,
            ),
            curated_description=curated.description,
            component_type=_normalize_text(
                registry_item.get("type"),
                fallback="registry:ui",
            ),
            install_target=f"@nyx/{component_name}",
            registry_url=registry_url,
            schema_url=_normalize_text(
                registry_item.get("$schema"),
                fallback=NYX_REGISTRY_SCHEMA_URL,
            ),
            source=NYX_SOURCE,
            source_repo=NYX_SOURCE_REPO,
            required_dependencies=curated.required_dependencies,
            dependencies=tuple(_dedupe_strings(registry_item.get("dependencies"))),
            dev_dependencies=tuple(_dedupe_strings(registry_item.get("devDependencies"))),
            registry_dependencies=tuple(
                _dedupe_strings(registry_item.get("registryDependencies"))
            ),
            file_count=len(files),
            targets=targets,
            files=files,
            review_status=NYX_REVIEW_STATUS_INSTALLABLE,
            previewable=True,
            installable=True,
            install_path_policy=NYX_INSTALL_TARGET_POLICY_NAME,
            install_path_safe=True,
            install_path_issues=(),
            audit_issues=(),
        )


_DEFAULT_BROKER: NyxCatalogBroker | None = None
_DEFAULT_BROKER_LOCK = threading.Lock()


def get_default_nyx_catalog_broker() -> NyxCatalogBroker:
    global _DEFAULT_BROKER
    if _DEFAULT_BROKER is not None:
        return _DEFAULT_BROKER
    with _DEFAULT_BROKER_LOCK:
        if _DEFAULT_BROKER is None:
            _DEFAULT_BROKER = NyxCatalogBroker()
    return _DEFAULT_BROKER