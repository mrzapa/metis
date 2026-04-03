"""Load, validate, and persist contextual skill definitions."""

from __future__ import annotations

from dataclasses import replace
import pathlib
from typing import Any

import yaml

from metis_app.models.parity_types import SkillDefinition

_HERE = pathlib.Path(__file__).resolve().parent
_PACKAGE_ROOT = _HERE.parent
_REPO_ROOT = _PACKAGE_ROOT.parent
_DEFAULT_SKILLS_DIR = _REPO_ROOT / "skills"
_DEFAULT_CANDIDATES_DB_PATH = _REPO_ROOT / "skill_candidates.db"

FRONTMATTER_REQUIRED_KEYS = {
    "id",
    "name",
    "description",
    "enabled_by_default",
    "priority",
    "triggers",
    "runtime_overrides",
}
FRONTMATTER_OPTIONAL_KEYS = {"metadata"}
TRIGGER_KEYS = {"keywords", "modes", "file_types", "output_styles"}
RUNTIME_OVERRIDE_KEYS = {
    "selected_mode",
    "retrieval_k",
    "top_k",
    "mmr_lambda",
    "retrieval_mode",
    "agentic_mode",
    "agentic_max_iterations",
    "output_style",
    "system_instructions_append",
    "citation_policy_append",
}
APPEND_OVERRIDE_KEYS = {"system_instructions_append", "citation_policy_append"}
SCALAR_OVERRIDE_KEYS = RUNTIME_OVERRIDE_KEYS - APPEND_OVERRIDE_KEYS


def _extract_frontmatter(raw_text: str) -> tuple[str, str]:
    text = str(raw_text or "")
    if not text.startswith("---"):
        raise ValueError("Missing YAML frontmatter opening delimiter.")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError("Missing YAML frontmatter closing delimiter.")
    return parts[1].strip(), parts[2].lstrip("\r\n")


def _normalize_string_list(value: Any, *, field_name: str, errors: list[str]) -> list[str]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        errors.append(f"'{field_name}' must be a list of strings.")
        return []
    normalized: list[str] = []
    for item in value:
        item_text = str(item or "").strip()
        if item_text:
            normalized.append(item_text)
    return normalized


def parse_skill_file(path: str | pathlib.Path) -> SkillDefinition:
    skill_path = pathlib.Path(path)
    raw = skill_path.read_text(encoding="utf-8")
    errors: list[str] = []
    try:
        frontmatter_text, body = _extract_frontmatter(raw)
    except ValueError as exc:
        return SkillDefinition(
            skill_id=skill_path.parent.name or skill_path.stem,
            name=skill_path.stem,
            description="",
            enabled_by_default=False,
            priority=0,
            body="",
            path=str(skill_path),
            errors=[str(exc)],
        )

    try:
        payload = yaml.safe_load(frontmatter_text)
    except yaml.YAMLError as exc:
        payload = None
        errors.append(f"Invalid YAML frontmatter: {exc}")

    if not isinstance(payload, dict):
        errors.append("Frontmatter must be a mapping.")
        payload = {}

    payload = dict(payload or {})
    metadata_raw = payload.get("metadata") or {}
    if metadata_raw and not isinstance(metadata_raw, dict):
        errors.append("'metadata' must be a mapping when provided.")
        metadata_raw = {}

    payload_keys = set(payload)
    unknown = sorted(payload_keys - FRONTMATTER_REQUIRED_KEYS - FRONTMATTER_OPTIONAL_KEYS)
    if unknown:
        errors.append("Unknown frontmatter keys: " + ", ".join(unknown))

    metadata_keys = set(metadata_raw)
    unknown_metadata_keys = sorted(metadata_keys - FRONTMATTER_REQUIRED_KEYS)
    if unknown_metadata_keys:
        errors.append("Unknown metadata keys: " + ", ".join(unknown_metadata_keys))

    effective_payload = dict(metadata_raw)
    for key, value in payload.items():
        if key == "metadata":
            continue
        effective_payload[key] = value

    effective_keys = set(effective_payload)
    missing = sorted(FRONTMATTER_REQUIRED_KEYS - effective_keys)
    if missing:
        errors.append("Missing frontmatter keys: " + ", ".join(missing))

    triggers_raw = effective_payload.get("triggers") or {}
    if not isinstance(triggers_raw, dict):
        errors.append("'triggers' must be a mapping.")
        triggers_raw = {}
    trigger_keys = set(triggers_raw)
    missing_trigger_keys = sorted(TRIGGER_KEYS - trigger_keys)
    unknown_trigger_keys = sorted(trigger_keys - TRIGGER_KEYS)
    if missing_trigger_keys:
        errors.append("Missing trigger keys: " + ", ".join(missing_trigger_keys))
    if unknown_trigger_keys:
        errors.append("Unknown trigger keys: " + ", ".join(unknown_trigger_keys))
    triggers = {
        key: _normalize_string_list(triggers_raw.get(key), field_name=f"triggers.{key}", errors=errors)
        for key in sorted(TRIGGER_KEYS)
    }

    overrides_raw = effective_payload.get("runtime_overrides") or {}
    if not isinstance(overrides_raw, dict):
        errors.append("'runtime_overrides' must be a mapping.")
        overrides_raw = {}
    unknown_override_keys = sorted(set(overrides_raw) - RUNTIME_OVERRIDE_KEYS)
    if unknown_override_keys:
        errors.append("Unknown runtime override keys: " + ", ".join(unknown_override_keys))

    runtime_overrides: dict[str, Any] = {}
    for key, value in dict(overrides_raw).items():
        if key not in RUNTIME_OVERRIDE_KEYS:
            continue
        if key in {"retrieval_k", "top_k", "agentic_max_iterations"}:
            try:
                runtime_overrides[key] = int(value)
            except (TypeError, ValueError):
                errors.append(f"'{key}' must be an integer.")
        elif key == "mmr_lambda":
            try:
                runtime_overrides[key] = float(value)
            except (TypeError, ValueError):
                errors.append(f"'{key}' must be a float.")
        elif key == "agentic_mode":
            runtime_overrides[key] = bool(value)
        else:
            runtime_overrides[key] = str(value or "").strip()

    skill_id = str(effective_payload.get("id") or "").strip()
    if not skill_id:
        errors.append("'id' must be a non-empty string.")
        skill_id = skill_path.parent.name or skill_path.stem
    if skill_path.parent.name and skill_path.parent.name != skill_id:
        errors.append(f"Skill id '{skill_id}' must match parent directory '{skill_path.parent.name}'.")

    name = str(effective_payload.get("name") or "").strip()
    if not name:
        errors.append("'name' must be a non-empty string.")
    description = str(effective_payload.get("description") or "").strip()
    enabled_by_default = bool(effective_payload.get("enabled_by_default", False))
    try:
        priority = int(effective_payload.get("priority", 0) or 0)
    except (TypeError, ValueError):
        priority = 0
        errors.append("'priority' must be an integer.")

    return SkillDefinition(
        skill_id=skill_id or skill_path.parent.name or skill_path.stem,
        name=name or skill_path.stem,
        description=description,
        enabled_by_default=enabled_by_default,
        priority=priority,
        triggers=triggers,
        runtime_overrides=runtime_overrides,
        body=str(body or "").strip(),
        path=str(skill_path),
        errors=errors,
    )


class SkillRepository:
    """Repository for repo-local contextual skills."""

    def __init__(self, skills_dir: str | pathlib.Path | None = None) -> None:
        self.skills_dir = pathlib.Path(skills_dir or _DEFAULT_SKILLS_DIR)

    def ensure_skills_dir(self) -> pathlib.Path:
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        return self.skills_dir

    def load_all(self) -> tuple[list[SkillDefinition], list[SkillDefinition]]:
        valid: list[SkillDefinition] = []
        invalid: list[SkillDefinition] = []
        for path in sorted(self.ensure_skills_dir().glob("*/SKILL.md")):
            skill = parse_skill_file(path)
            if skill.valid:
                valid.append(skill)
            else:
                invalid.append(skill)
        valid.sort(key=lambda item: (item.skill_id.casefold(), item.name.casefold()))
        invalid.sort(key=lambda item: item.skill_id.casefold())
        return valid, invalid

    def list_valid_skills(self) -> list[SkillDefinition]:
        valid, _invalid = self.load_all()
        return valid

    def list_invalid_skills(self) -> list[SkillDefinition]:
        _valid, invalid = self.load_all()
        return invalid

    def get_skill(self, skill_id: str) -> SkillDefinition | None:
        normalized = str(skill_id or "").strip()
        if not normalized:
            return None
        for skill in self.list_valid_skills():
            if skill.skill_id == normalized:
                return replace(skill)
        return None

    def lint_errors(self) -> list[str]:
        errors: list[str] = []
        for skill in self.list_invalid_skills():
            prefix = f"{skill.path}: "
            errors.extend(prefix + item for item in skill.errors)
        return errors

    @staticmethod
    def _settings_enabled_map(settings: dict[str, Any]) -> dict[str, bool]:
        skills = dict((settings or {}).get("skills") or {})
        enabled = dict(skills.get("enabled") or {})
        return {str(key): bool(value) for key, value in enabled.items() if str(key).strip()}

    def is_globally_enabled(self, skill: SkillDefinition, settings: dict[str, Any]) -> bool:
        enabled_map = self._settings_enabled_map(settings)
        if skill.skill_id in enabled_map:
            return bool(enabled_map[skill.skill_id])
        return bool(skill.enabled_by_default)

    def enabled_skills(self, settings: dict[str, Any]) -> list[SkillDefinition]:
        return [replace(skill) for skill in self.list_valid_skills() if self.is_globally_enabled(skill, settings)]

    def set_global_enabled(self, settings: dict[str, Any], skill_id: str, enabled: bool) -> dict[str, Any]:
        normalized = str(skill_id or "").strip()
        next_settings = dict(settings or {})
        skills = dict(next_settings.get("skills") or {})
        enabled_map = dict(skills.get("enabled") or {})
        enabled_map[normalized] = bool(enabled)
        skills["enabled"] = enabled_map
        next_settings["skills"] = skills
        return next_settings

    def skill_rows(self, settings: dict[str, Any], *, pinned: list[str] | None = None, muted: list[str] | None = None) -> list[dict[str, Any]]:
        pinned_set = {str(item).strip() for item in (pinned or []) if str(item).strip()}
        muted_set = {str(item).strip() for item in (muted or []) if str(item).strip()}
        rows: list[dict[str, Any]] = []
        for skill in self.list_valid_skills():
            rows.append(
                {
                    "skill_id": skill.skill_id,
                    "name": skill.name,
                    "description": skill.description,
                    "enabled": self.is_globally_enabled(skill, settings),
                    "enabled_by_default": skill.enabled_by_default,
                    "priority": int(skill.priority),
                    "pinned": skill.skill_id in pinned_set,
                    "muted": skill.skill_id in muted_set,
                    "path": skill.path,
                }
            )
        return rows

    # ------------------------------------------------------------------
    # Skill candidate capture (Phase 3: Skill Evolution)
    # ------------------------------------------------------------------

    @staticmethod
    def _init_candidates_db(db_path: pathlib.Path) -> sqlite3.Connection:
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS skill_candidates (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                query_text TEXT NOT NULL,
                trace_json TEXT NOT NULL,
                convergence_score REAL NOT NULL DEFAULT 0.0,
                created_at REAL NOT NULL,
                promoted  INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.commit()
        return conn

    def save_candidate(
        self,
        *,
        db_path: pathlib.Path,
        query_text: str,
        trace_json: str,
        convergence_score: float,
    ) -> None:
        import sqlite3
        import time
        conn = self._init_candidates_db(db_path)
        with conn:
            conn.execute(
                "INSERT INTO skill_candidates (query_text, trace_json, convergence_score, created_at) VALUES (?, ?, ?, ?)",
                (str(query_text), str(trace_json), float(convergence_score), time.time()),
            )

    def list_candidates(
        self,
        *,
        db_path: pathlib.Path,
        limit: int = 5,
    ) -> list[dict]:
        import sqlite3
        conn = self._init_candidates_db(db_path)
        rows = conn.execute(
            "SELECT id, query_text, trace_json, convergence_score, created_at FROM skill_candidates "
            "WHERE promoted = 0 ORDER BY convergence_score DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {"id": r[0], "query_text": r[1], "trace_json": r[2], "convergence_score": r[3], "created_at": r[4]}
            for r in rows
        ]

    def mark_candidate_promoted(self, *, db_path: pathlib.Path, candidate_id: int) -> None:
        import sqlite3
        conn = self._init_candidates_db(db_path)
        with conn:
            conn.execute("UPDATE skill_candidates SET promoted = 1 WHERE id = ?", (candidate_id,))
