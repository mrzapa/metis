"""Tests for the M14 Phase 7 ``.metis-skill`` bundle format."""

from __future__ import annotations

import pathlib
import tarfile
from io import BytesIO
from typing import Any

import pytest
import yaml

from metis_app.services import forge_bundle


_FIXTURE_FRONTMATTER: dict[str, Any] = {
    "id": "qa-core",
    "name": "Q&A Core",
    "description": "Direct grounded answers for general document questions.",
    "enabled_by_default": True,
    "priority": 100,
    "triggers": {
        "keywords": ["answer", "explain"],
        "modes": ["Q&A"],
        "file_types": [".md"],
        "output_styles": ["Default answer"],
    },
    "runtime_overrides": {
        "selected_mode": "Q&A",
        "retrieval_k": 25,
    },
}
_FIXTURE_BODY = (
    "Use this skill for standard grounded document question-answering.\n"
)


def _write_skill(
    skills_root: pathlib.Path,
    slug: str,
    *,
    frontmatter: dict[str, Any],
    body: str,
) -> pathlib.Path:
    """Write ``<skills_root>/<slug>/SKILL.md`` with frontmatter+body."""
    skill_dir = skills_root / slug
    skill_dir.mkdir(parents=True, exist_ok=True)
    fm_text = yaml.safe_dump(frontmatter, sort_keys=False)
    skill_path = skill_dir / "SKILL.md"
    skill_path.write_text(f"---\n{fm_text}---\n{body}", encoding="utf-8")
    return skill_path


def _make_manifest_yaml(**overrides: Any) -> bytes:
    payload: dict[str, Any] = {
        "bundle_format_version": 1,
        "skill_id": "qa-core",
        "name": "Q&A Core",
        "description": "Direct grounded answers.",
        "version": "0.1.0",
        "exported_at": "2026-05-01T12:00:00Z",
        "min_metis_version": "0.1.0",
    }
    payload.update(overrides)
    return yaml.safe_dump(payload, sort_keys=False).encode("utf-8")


# ── Manifest dataclass ───────────────────────────────────────────


def test_manifest_round_trips_through_yaml() -> None:
    manifest = forge_bundle.Manifest(
        bundle_format_version=1,
        skill_id="qa-core",
        name="Q&A Core",
        description="Direct grounded answers.",
        version="0.1.0",
        exported_at="2026-05-01T12:00:00Z",
        min_metis_version="0.1.0",
        author="user@example.com",
        dependencies=(
            {"id": "agent-native-bridge", "min_version": "0.0.0"},
        ),
    )
    text = manifest.to_yaml()
    round_trip = forge_bundle.Manifest.from_yaml(text)
    assert round_trip == manifest


def test_manifest_omits_optional_fields_when_none() -> None:
    manifest = forge_bundle.Manifest(
        bundle_format_version=1,
        skill_id="qa-core",
        name="Q&A Core",
        description="...",
        version="0.1.0",
        exported_at="2026-05-01T12:00:00Z",
        min_metis_version="0.1.0",
    )
    text = manifest.to_yaml()
    assert "author" not in text
    assert "dependencies" not in text


def test_manifest_from_yaml_rejects_unknown_format_version() -> None:
    text = yaml.safe_dump(
        {
            "bundle_format_version": 99,
            "skill_id": "qa-core",
            "name": "x",
            "description": "x",
            "version": "0.1.0",
            "exported_at": "2026-05-01T12:00:00Z",
            "min_metis_version": "0.1.0",
        }
    )
    with pytest.raises(ValueError, match="bundle_format_version"):
        forge_bundle.Manifest.from_yaml(text)


# ── pack_skill / inspect_bundle ──────────────────────────────────


def test_pack_then_inspect_round_trips(tmp_path: pathlib.Path) -> None:
    skills_root = tmp_path / "skills"
    _write_skill(
        skills_root, "qa-core",
        frontmatter=_FIXTURE_FRONTMATTER, body=_FIXTURE_BODY,
    )
    bundle_path = forge_bundle.pack_skill(
        skill_dir=skills_root / "qa-core",
        version="0.1.0",
        dest_dir=tmp_path,
        now=lambda: "2026-05-01T12:00:00Z",
    )
    assert bundle_path.exists()
    assert bundle_path.suffix == ".metis-skill" or str(bundle_path).endswith(
        ".metis-skill"
    )

    inspected = forge_bundle.inspect_bundle(bundle_path)
    assert inspected.manifest.skill_id == "qa-core"
    assert inspected.manifest.version == "0.1.0"
    assert inspected.manifest.bundle_format_version == 1
    assert inspected.manifest.exported_at == "2026-05-01T12:00:00Z"
    assert inspected.skill_frontmatter["id"] == "qa-core"
    assert inspected.skill_body.strip() == _FIXTURE_BODY.strip()
    assert inspected.errors == []


def test_pack_writes_filename_with_id_and_version(tmp_path: pathlib.Path) -> None:
    skills_root = tmp_path / "skills"
    _write_skill(
        skills_root, "qa-core",
        frontmatter=_FIXTURE_FRONTMATTER, body=_FIXTURE_BODY,
    )
    bundle_path = forge_bundle.pack_skill(
        skill_dir=skills_root / "qa-core",
        version="0.1.0",
        dest_dir=tmp_path,
    )
    assert "qa-core" in bundle_path.name
    assert "0.1.0" in bundle_path.name


def test_pack_includes_extra_payload_files(tmp_path: pathlib.Path) -> None:
    skills_root = tmp_path / "skills"
    skill_dir = skills_root / "qa-core"
    _write_skill(
        skills_root, "qa-core",
        frontmatter=_FIXTURE_FRONTMATTER, body=_FIXTURE_BODY,
    )
    (skill_dir / "fixture.json").write_text('{"ok": true}', encoding="utf-8")

    bundle_path = forge_bundle.pack_skill(
        skill_dir=skill_dir, version="0.1.0", dest_dir=tmp_path,
    )
    with tarfile.open(bundle_path, mode="r") as tf:
        names = sorted(tf.getnames())
    assert "manifest.yaml" in names
    assert "skill/SKILL.md" in names
    assert "skill/fixture.json" in names


def test_pack_skill_records_optional_author(tmp_path: pathlib.Path) -> None:
    skills_root = tmp_path / "skills"
    _write_skill(
        skills_root, "qa-core",
        frontmatter=_FIXTURE_FRONTMATTER, body=_FIXTURE_BODY,
    )
    bundle_path = forge_bundle.pack_skill(
        skill_dir=skills_root / "qa-core",
        version="0.2.0",
        dest_dir=tmp_path,
        author="user@example.com",
    )
    inspected = forge_bundle.inspect_bundle(bundle_path)
    assert inspected.manifest.author == "user@example.com"


# ── validate_bundle ──────────────────────────────────────────────


def test_validate_clean_bundle_returns_empty_list(tmp_path: pathlib.Path) -> None:
    skills_root = tmp_path / "skills"
    _write_skill(
        skills_root, "qa-core",
        frontmatter=_FIXTURE_FRONTMATTER, body=_FIXTURE_BODY,
    )
    bundle_path = forge_bundle.pack_skill(
        skill_dir=skills_root / "qa-core", version="0.1.0", dest_dir=tmp_path,
    )
    assert forge_bundle.validate_bundle(bundle_path) == []


def test_validate_missing_manifest_reports_error(tmp_path: pathlib.Path) -> None:
    bad = tmp_path / "no-manifest.metis-skill"
    with tarfile.open(bad, mode="w") as tf:
        data = b"---\nid: qa-core\n---\nbody\n"
        info = tarfile.TarInfo(name="skill/SKILL.md")
        info.size = len(data)
        tf.addfile(info, BytesIO(data))
    errors = forge_bundle.validate_bundle(bad)
    assert any("manifest" in e.lower() for e in errors)


def test_validate_missing_skill_md_reports_error(tmp_path: pathlib.Path) -> None:
    bad = tmp_path / "no-skill.metis-skill"
    with tarfile.open(bad, mode="w") as tf:
        m = _make_manifest_yaml()
        info = tarfile.TarInfo(name="manifest.yaml")
        info.size = len(m)
        tf.addfile(info, BytesIO(m))
    errors = forge_bundle.validate_bundle(bad)
    assert any("SKILL.md" in e for e in errors)


def test_validate_skill_id_mismatch_reports_error(
    tmp_path: pathlib.Path,
) -> None:
    bad = tmp_path / "mismatch.metis-skill"
    with tarfile.open(bad, mode="w") as tf:
        m = _make_manifest_yaml(skill_id="qa-core")
        info = tarfile.TarInfo(name="manifest.yaml")
        info.size = len(m)
        tf.addfile(info, BytesIO(m))
        skill_payload = (
            b"---\nid: different-id\nname: x\ndescription: x\n"
            b"enabled_by_default: false\npriority: 0\n"
            b"triggers:\n  keywords: []\n  modes: []\n"
            b"  file_types: []\n  output_styles: []\n"
            b"runtime_overrides: {}\n---\nbody\n"
        )
        info2 = tarfile.TarInfo(name="skill/SKILL.md")
        info2.size = len(skill_payload)
        tf.addfile(info2, BytesIO(skill_payload))
    errors = forge_bundle.validate_bundle(bad)
    assert any(
        "skill_id" in e or "mismatch" in e.lower() for e in errors
    )


def test_validate_unsafe_traversal_path_rejected(
    tmp_path: pathlib.Path,
) -> None:
    bad = tmp_path / "evil.metis-skill"
    with tarfile.open(bad, mode="w") as tf:
        m = _make_manifest_yaml()
        info = tarfile.TarInfo(name="manifest.yaml")
        info.size = len(m)
        tf.addfile(info, BytesIO(m))
        evil = b"oops"
        info2 = tarfile.TarInfo(name="../../etc/passwd")
        info2.size = len(evil)
        tf.addfile(info2, BytesIO(evil))
    errors = forge_bundle.validate_bundle(bad)
    assert any(
        "unsafe" in e.lower() or "traversal" in e.lower() or ".." in e
        for e in errors
    )


def test_validate_absolute_path_member_rejected(
    tmp_path: pathlib.Path,
) -> None:
    bad = tmp_path / "absolute.metis-skill"
    with tarfile.open(bad, mode="w") as tf:
        m = _make_manifest_yaml()
        info = tarfile.TarInfo(name="manifest.yaml")
        info.size = len(m)
        tf.addfile(info, BytesIO(m))
        evil = b"oops"
        info2 = tarfile.TarInfo(name="/etc/shadow")
        info2.size = len(evil)
        tf.addfile(info2, BytesIO(evil))
    errors = forge_bundle.validate_bundle(bad)
    assert any(
        "unsafe" in e.lower() or "absolute" in e.lower()
        for e in errors
    )


def test_validate_unsupported_format_version_rejected(
    tmp_path: pathlib.Path,
) -> None:
    bad = tmp_path / "v99.metis-skill"
    with tarfile.open(bad, mode="w") as tf:
        m = _make_manifest_yaml(bundle_format_version=99)
        info = tarfile.TarInfo(name="manifest.yaml")
        info.size = len(m)
        tf.addfile(info, BytesIO(m))
    errors = forge_bundle.validate_bundle(bad)
    assert any("bundle_format_version" in e for e in errors)


# ── install_bundle ───────────────────────────────────────────────


def test_install_writes_skill_under_skills_root(tmp_path: pathlib.Path) -> None:
    src_root = tmp_path / "src"
    _write_skill(
        src_root, "qa-core",
        frontmatter=_FIXTURE_FRONTMATTER, body=_FIXTURE_BODY,
    )
    bundle_path = forge_bundle.pack_skill(
        skill_dir=src_root / "qa-core", version="0.1.0", dest_dir=tmp_path,
    )
    target = tmp_path / "target"
    target.mkdir()
    result = forge_bundle.install_bundle(bundle_path, skills_root=target)
    assert result.skill_id == "qa-core"
    assert result.replaced is False
    skill_path = target / "qa-core" / "SKILL.md"
    assert skill_path.exists()
    assert "Q&A" in skill_path.read_text(encoding="utf-8")


def test_install_raises_when_slug_exists_without_replace(
    tmp_path: pathlib.Path,
) -> None:
    src_root = tmp_path / "src"
    target = tmp_path / "target"
    _write_skill(
        src_root, "qa-core",
        frontmatter=_FIXTURE_FRONTMATTER, body=_FIXTURE_BODY,
    )
    _write_skill(
        target, "qa-core",
        frontmatter=_FIXTURE_FRONTMATTER, body="existing local edits\n",
    )
    bundle_path = forge_bundle.pack_skill(
        skill_dir=src_root / "qa-core", version="0.1.0", dest_dir=tmp_path,
    )
    with pytest.raises(FileExistsError):
        forge_bundle.install_bundle(bundle_path, skills_root=target)
    # Existing content untouched on conflict.
    assert (
        "existing local edits"
        in (target / "qa-core" / "SKILL.md").read_text(encoding="utf-8")
    )


def test_install_replace_true_overwrites_and_flags_replaced(
    tmp_path: pathlib.Path,
) -> None:
    src_root = tmp_path / "src"
    target = tmp_path / "target"
    _write_skill(
        src_root, "qa-core",
        frontmatter=_FIXTURE_FRONTMATTER, body="new payload from bundle\n",
    )
    _write_skill(
        target, "qa-core",
        frontmatter=_FIXTURE_FRONTMATTER, body="existing local edits\n",
    )
    bundle_path = forge_bundle.pack_skill(
        skill_dir=src_root / "qa-core", version="0.1.0", dest_dir=tmp_path,
    )
    result = forge_bundle.install_bundle(
        bundle_path, skills_root=target, replace=True,
    )
    assert result.replaced is True
    on_disk = (target / "qa-core" / "SKILL.md").read_text(encoding="utf-8")
    assert "new payload from bundle" in on_disk
    assert "existing local edits" not in on_disk


def test_install_refuses_invalid_bundle(tmp_path: pathlib.Path) -> None:
    bad = tmp_path / "bad.metis-skill"
    with tarfile.open(bad, mode="w") as tf:
        # Manifest only — no skill payload.
        m = _make_manifest_yaml()
        info = tarfile.TarInfo(name="manifest.yaml")
        info.size = len(m)
        tf.addfile(info, BytesIO(m))
    target = tmp_path / "target"
    target.mkdir()
    with pytest.raises(forge_bundle.BundleValidationError):
        forge_bundle.install_bundle(bad, skills_root=target)


# ── round-trip parity over every shipped skill ───────────────────


def _list_shipped_skill_dirs() -> list[pathlib.Path]:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    skills = repo_root / "skills"
    if not skills.is_dir():
        return []
    return sorted(p for p in skills.iterdir() if p.is_dir())


@pytest.mark.parametrize("skill_dir", _list_shipped_skill_dirs(), ids=lambda p: p.name)
def test_shipped_skill_round_trips_byte_identical(
    tmp_path: pathlib.Path, skill_dir: pathlib.Path,
) -> None:
    """Pack → install over every shipped skill must reproduce SKILL.md."""
    bundle_path = forge_bundle.pack_skill(
        skill_dir=skill_dir, version="0.1.0", dest_dir=tmp_path,
    )
    target = tmp_path / "target"
    target.mkdir()
    forge_bundle.install_bundle(bundle_path, skills_root=target)

    src_text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    dst_text = (target / skill_dir.name / "SKILL.md").read_text(encoding="utf-8")
    assert src_text == dst_text
