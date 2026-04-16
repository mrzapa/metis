"""Tests for SkillRepository.load_skill_index()."""
from __future__ import annotations
import pathlib
from metis_app.services.runtime_resolution import resolve_runtime_settings
from metis_app.services.skill_repository import SkillRepository, SkillSummary

_SKILL_FM = """\
---
id: demo
name: Demo Skill
description: A skill for testing skill discovery.
enabled_by_default: true
priority: 1
triggers:
  keywords: [demo, test]
  modes: []
  file_types: []
  output_styles: []
runtime_overrides: {}
---

# Demo Skill
Do the demo thing.
"""


def _make_skill(tmp_path: pathlib.Path, skill_id: str, fm: str) -> None:
    d = tmp_path / skill_id
    d.mkdir()
    (d / "SKILL.md").write_text(fm, encoding="utf-8")


def test_load_skill_index_returns_summaries(tmp_path):
    _make_skill(tmp_path, "demo", _SKILL_FM)
    repo = SkillRepository(skills_dir=tmp_path)
    index = repo.load_skill_index()
    assert len(index) == 1
    s = index[0]
    assert isinstance(s, SkillSummary)
    assert s.skill_id == "demo"
    assert s.name == "Demo Skill"
    assert "A skill for testing" in s.description
    assert "demo" in s.keywords


def test_load_skill_index_excludes_invalid_skills(tmp_path):
    _make_skill(tmp_path, "demo", _SKILL_FM)
    bad_dir = tmp_path / "broken"
    bad_dir.mkdir()
    (bad_dir / "SKILL.md").write_text("not yaml frontmatter", encoding="utf-8")
    repo = SkillRepository(skills_dir=tmp_path)
    index = repo.load_skill_index()
    assert len(index) == 1  # only valid skill


def test_skill_summary_format_line():
    s = SkillSummary(skill_id="demo", name="Demo", description="Does demo.", keywords=["demo"])
    line = s.format_index_line()
    assert "demo" in line
    assert "Demo" in line
    assert "Does demo." in line


# ---------------------------------------------------------------------------
# Task 2: system prompt includes skill discovery index
# ---------------------------------------------------------------------------


def test_system_prompt_includes_skill_index(tmp_path):
    _make_skill(tmp_path, "demo", _SKILL_FM)
    repo = SkillRepository(skills_dir=tmp_path)
    enabled = repo.list_valid_skills()

    result = resolve_runtime_settings(
        {"llm_provider": "mock", "selected_mode": "Q&A"},
        enabled_skills=enabled,
        session_skill_state=None,
        query="what is the weather today",  # does not match skill keywords
        file_types=[],
    )
    prompt = result.system_prompt
    assert "Available skills:" in prompt
    assert "demo" in prompt
    assert "A skill for testing" in prompt
    # Full body should NOT appear since skill was not triggered/selected
    assert "Do the demo thing." not in prompt
