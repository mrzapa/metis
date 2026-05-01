"""M14 Phase 7 — `.metis-skill` bundle pack / inspect / validate / install.

A ``.metis-skill`` bundle is a POSIX tar archive (uncompressed in v1)
with this layout::

    manifest.yaml            # bundle metadata
    skill/SKILL.md           # the skill payload
    skill/<extra files>      # optional auxiliary payload files

The bundle never extracts to the live ``skills/`` root directly. The
install path stages into a tempdir, runs the explicit-prefix
traversal check (plus Python 3.12's ``data`` extraction filter when
available), and only then moves the validated ``skill/`` subtree to
``<skills_root>/<id>/``. ADR 0015 is the architectural baseline.
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import os
import pathlib
import re
import shutil
import tarfile
import tempfile
from io import BytesIO
from typing import Any, Callable

import yaml

SUPPORTED_FORMAT_VERSION = 1
"""Format version this reader/writer produces and consumes."""

MANIFEST_NAME = "manifest.yaml"
"""Name of the manifest file at the bundle root."""

PAYLOAD_PREFIX = "skill/"
"""Tar archive prefix under which the skill directory ships."""

SKILL_FILE_RELATIVE = "SKILL.md"
"""Required entry inside the payload directory."""

DEFAULT_MIN_METIS_VERSION = "0.1.0"


class BundleValidationError(ValueError):
    """Raised when a bundle fails validation on install."""


@dataclasses.dataclass(frozen=True)
class Manifest:
    """Parsed ``manifest.yaml`` payload.

    The dataclass is the single source of truth for the schema —
    ``to_yaml`` and ``from_yaml`` are paired so packers and readers
    cannot drift on field names or required-vs-optional distinction.
    """

    bundle_format_version: int
    skill_id: str
    name: str
    description: str
    version: str
    exported_at: str
    min_metis_version: str
    author: str | None = None
    dependencies: tuple[dict[str, str], ...] = ()

    def to_yaml(self) -> str:
        payload: dict[str, Any] = {
            "bundle_format_version": int(self.bundle_format_version),
            "skill_id": str(self.skill_id),
            "name": str(self.name),
            "description": str(self.description),
            "version": str(self.version),
            "exported_at": str(self.exported_at),
            "min_metis_version": str(self.min_metis_version),
        }
        if self.author is not None:
            payload["author"] = str(self.author)
        if self.dependencies:
            payload["dependencies"] = [dict(dep) for dep in self.dependencies]
        return yaml.safe_dump(payload, sort_keys=False)

    @classmethod
    def from_yaml(cls, text: str) -> Manifest:
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise ValueError(f"manifest YAML parse error: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError("manifest must be a YAML mapping")

        format_version = data.get("bundle_format_version")
        if format_version != SUPPORTED_FORMAT_VERSION:
            raise ValueError(
                f"unsupported bundle_format_version: {format_version!r} "
                f"(reader supports {SUPPORTED_FORMAT_VERSION})"
            )

        for required in (
            "skill_id",
            "name",
            "description",
            "version",
            "exported_at",
            "min_metis_version",
        ):
            if not data.get(required):
                raise ValueError(
                    f"manifest missing required field {required!r}"
                )

        deps_raw = data.get("dependencies") or []
        if not isinstance(deps_raw, list):
            raise ValueError("manifest dependencies must be a list")
        deps: list[dict[str, str]] = []
        for dep in deps_raw:
            if not isinstance(dep, dict):
                raise ValueError("manifest dependency entry must be a mapping")
            deps.append(
                {
                    "id": str(dep.get("id", "")),
                    "min_version": str(dep.get("min_version", "0.0.0")),
                }
            )

        author_raw = data.get("author")
        author = str(author_raw) if author_raw else None

        return cls(
            bundle_format_version=int(format_version),
            skill_id=str(data["skill_id"]),
            name=str(data["name"]),
            description=str(data["description"]),
            version=str(data["version"]),
            exported_at=str(data["exported_at"]),
            min_metis_version=str(data["min_metis_version"]),
            author=author,
            dependencies=tuple(deps),
        )


@dataclasses.dataclass(frozen=True)
class InspectedBundle:
    """The shape ``inspect_bundle`` returns to the preview pane."""

    manifest: Manifest
    skill_frontmatter: dict[str, Any]
    skill_body: str
    errors: list[str]


@dataclasses.dataclass(frozen=True)
class InstallResult:
    """The shape ``install_bundle`` returns on success."""

    skill_id: str
    skill_path: pathlib.Path
    replaced: bool


# ── Helpers ────────────────────────────────────────────────────────


def _utc_now_iso() -> str:
    return _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _zero_manifest() -> Manifest:
    return Manifest(
        bundle_format_version=0,
        skill_id="",
        name="",
        description="",
        version="",
        exported_at="",
        min_metis_version="",
    )


def _split_frontmatter(
    text: str,
) -> tuple[str | None, dict[str, Any], str]:
    """Return (id, frontmatter, body) parsed from a ``SKILL.md`` blob.

    Mirrors the parser in
    ``metis_app.services.skill_repository._extract_frontmatter`` but
    returns a tolerant tuple instead of raising — invalid frontmatter
    becomes ``({}, body)`` so the caller can collect the error
    message itself.
    """
    if not text.startswith("---"):
        return None, {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None, {}, text
    try:
        fm = yaml.safe_load(parts[1].strip()) or {}
    except yaml.YAMLError:
        fm = {}
    if not isinstance(fm, dict):
        fm = {}
    body = parts[2].lstrip("\r\n")
    fm_id = fm.get("id")
    return (str(fm_id) if fm_id else None), fm, body


def _is_unsafe_member(name: str) -> bool:
    """Return True if a tar member name escapes the bundle root.

    Belt-and-braces complement to Python 3.12's ``tarfile`` data
    filter. Rejects absolute paths (POSIX or Windows drive),
    backslash-bearing paths (Windows-style separators leak nothing
    safely into a POSIX-only archive), and any normalised path with
    a ``..`` component.
    """
    if not name:
        return True
    if name.startswith("/"):
        return True
    if "\\" in name:
        return True
    if re.match(r"^[A-Za-z]:[\\/]", name):
        return True
    if name == ".." or name.startswith("../"):
        return True
    norm = os.path.normpath(name).replace("\\", "/")
    if norm == ".." or norm.startswith("../"):
        return True
    if "/.." in norm:
        return True
    return False


# ── Pack ────────────────────────────────────────────────────────────


def pack_skill(
    *,
    skill_dir: pathlib.Path,
    version: str,
    dest_dir: pathlib.Path,
    author: str | None = None,
    min_metis_version: str = DEFAULT_MIN_METIS_VERSION,
    dependencies: tuple[dict[str, str], ...] = (),
    now: Callable[[], str] = _utc_now_iso,
) -> pathlib.Path:
    """Pack a ``skills/<id>/`` directory into a ``.metis-skill`` bundle.

    The bundle file is written to
    ``dest_dir/<skill_id>-<version>.metis-skill``. Returns the path
    of the written bundle. ``skill_id``, ``name``, and ``description``
    in the manifest mirror the frontmatter of the source SKILL.md so
    a reader can render the preview pane without re-parsing.
    """
    skill_dir = pathlib.Path(skill_dir)
    dest_dir = pathlib.Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    skill_md_path = skill_dir / SKILL_FILE_RELATIVE
    if not skill_md_path.is_file():
        raise FileNotFoundError(
            f"missing {SKILL_FILE_RELATIVE} under {skill_dir}"
        )

    skill_md_text = skill_md_path.read_text(encoding="utf-8")
    fm_id, frontmatter, _ = _split_frontmatter(skill_md_text)
    skill_id = fm_id or skill_dir.name
    name = str(frontmatter.get("name") or skill_id)
    description = str(frontmatter.get("description") or "")

    manifest = Manifest(
        bundle_format_version=SUPPORTED_FORMAT_VERSION,
        skill_id=skill_id,
        name=name,
        description=description,
        version=version,
        exported_at=now(),
        min_metis_version=min_metis_version,
        author=author,
        dependencies=tuple(dependencies),
    )

    bundle_path = dest_dir / f"{skill_id}-{version}.metis-skill"
    with tarfile.open(bundle_path, mode="w") as tf:
        manifest_bytes = manifest.to_yaml().encode("utf-8")
        info = tarfile.TarInfo(name=MANIFEST_NAME)
        info.size = len(manifest_bytes)
        tf.addfile(info, BytesIO(manifest_bytes))
        for path in sorted(skill_dir.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(skill_dir).as_posix()
            arcname = f"{PAYLOAD_PREFIX}{relative}"
            tf.add(path, arcname=arcname)
    return bundle_path


# ── Inspect / validate ─────────────────────────────────────────────


def inspect_bundle(bundle_path: pathlib.Path) -> InspectedBundle:
    """Parse a bundle's manifest + SKILL.md without extracting payload.

    Errors are collected into ``InspectedBundle.errors`` so the
    preview pane can render them all in one pass. The bundle file
    itself is never modified.
    """
    bundle_path = pathlib.Path(bundle_path)
    errors: list[str] = []
    manifest_text: str | None = None
    skill_md_text: str | None = None

    try:
        with tarfile.open(bundle_path, mode="r") as tf:
            for member in tf.getmembers():
                if _is_unsafe_member(member.name):
                    errors.append(f"unsafe path: {member.name!r}")
                    continue
                if member.name == MANIFEST_NAME:
                    fobj = tf.extractfile(member)
                    if fobj is not None:
                        manifest_text = fobj.read().decode("utf-8")
                elif member.name == f"{PAYLOAD_PREFIX}{SKILL_FILE_RELATIVE}":
                    fobj = tf.extractfile(member)
                    if fobj is not None:
                        skill_md_text = fobj.read().decode("utf-8")
    except tarfile.TarError as exc:
        return InspectedBundle(
            manifest=_zero_manifest(),
            skill_frontmatter={},
            skill_body="",
            errors=[f"unreadable bundle: {exc}"],
        )

    if manifest_text is None:
        errors.append("missing manifest.yaml in bundle")
        return InspectedBundle(
            manifest=_zero_manifest(),
            skill_frontmatter={},
            skill_body="",
            errors=errors,
        )
    try:
        manifest = Manifest.from_yaml(manifest_text)
    except ValueError as exc:
        errors.append(f"invalid manifest: {exc}")
        return InspectedBundle(
            manifest=_zero_manifest(),
            skill_frontmatter={},
            skill_body="",
            errors=errors,
        )

    if skill_md_text is None:
        errors.append(f"missing skill/{SKILL_FILE_RELATIVE} in bundle")
        return InspectedBundle(
            manifest=manifest,
            skill_frontmatter={},
            skill_body="",
            errors=errors,
        )

    fm_id, frontmatter, body = _split_frontmatter(skill_md_text)
    if fm_id and fm_id != manifest.skill_id:
        errors.append(
            f"skill_id mismatch: manifest={manifest.skill_id!r} "
            f"vs SKILL.md frontmatter={fm_id!r}"
        )

    return InspectedBundle(
        manifest=manifest,
        skill_frontmatter=frontmatter,
        skill_body=body,
        errors=errors,
    )


def validate_bundle(bundle_path: pathlib.Path) -> list[str]:
    """Return human-readable validation errors. Empty list = clean."""
    return inspect_bundle(bundle_path).errors


# ── Install ────────────────────────────────────────────────────────


def install_bundle(
    bundle_path: pathlib.Path,
    *,
    skills_root: pathlib.Path,
    replace: bool = False,
) -> InstallResult:
    """Extract a validated bundle into ``<skills_root>/<id>/``.

    Raises:
        BundleValidationError: bundle fails ``validate_bundle``.
        FileExistsError: target slug exists and ``replace=False``.
    """
    bundle_path = pathlib.Path(bundle_path)
    skills_root = pathlib.Path(skills_root)

    inspected = inspect_bundle(bundle_path)
    if inspected.errors:
        raise BundleValidationError("; ".join(inspected.errors))

    skill_id = inspected.manifest.skill_id
    target_dir = skills_root / skill_id

    if target_dir.exists() and not replace:
        raise FileExistsError(
            f"skill {skill_id!r} already installed at {target_dir}"
        )

    skills_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as staging:
        staging_root = pathlib.Path(staging)
        with tarfile.open(bundle_path, mode="r") as tf:
            members_to_extract: list[tarfile.TarInfo] = []
            for member in tf.getmembers():
                if _is_unsafe_member(member.name):
                    raise BundleValidationError(
                        f"unsafe tar member: {member.name!r}"
                    )
                if member.name.startswith(PAYLOAD_PREFIX):
                    members_to_extract.append(member)
            try:
                tf.extractall(  # type: ignore[call-arg]
                    staging_root,
                    members=members_to_extract,
                    filter="data",
                )
            except TypeError:
                # Python <3.12 has no `filter` kwarg; the explicit
                # ``_is_unsafe_member`` check above already rejected
                # any unsafe members.
                tf.extractall(staging_root, members=members_to_extract)

        unpacked_skill_dir = staging_root / PAYLOAD_PREFIX.rstrip("/")
        if not unpacked_skill_dir.is_dir():
            raise BundleValidationError(
                "bundle missing skill/ payload directory"
            )

        replaced = False
        if target_dir.exists():
            shutil.rmtree(target_dir)
            replaced = True

        target_dir.mkdir(parents=True, exist_ok=False)
        for child in unpacked_skill_dir.iterdir():
            if child.is_dir():
                shutil.copytree(child, target_dir / child.name)
            else:
                shutil.copy2(child, target_dir / child.name)

    return InstallResult(
        skill_id=skill_id,
        skill_path=target_dir / SKILL_FILE_RELATIVE,
        replaced=replaced,
    )
