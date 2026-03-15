from __future__ import annotations

import json

import axiom_app.models.app_model as app_model_module
from axiom_app.models.app_model import AppModel
from axiom_app.models.parity_types import SkillDefinition, SkillSessionState
from axiom_app.services.local_model_registry import LocalModelRegistryService
from axiom_app.services.runtime_resolution import resolve_runtime_settings
from axiom_app.services.skill_repository import SkillRepository, parse_skill_file


def _write_skill(
    root,
    skill_id: str,
    *,
    name: str,
    description: str,
    enabled_by_default: bool,
    priority: int,
    keywords: list[str] | None = None,
    modes: list[str] | None = None,
    file_types: list[str] | None = None,
    output_styles: list[str] | None = None,
    runtime_overrides: dict[str, object] | None = None,
    body: str = "",
) -> None:
    skill_dir = root / skill_id
    skill_dir.mkdir(parents=True, exist_ok=True)
    payload = (
        "---\n"
        f"id: {skill_id}\n"
        f"name: {name}\n"
        f"description: {description}\n"
        f"enabled_by_default: {'true' if enabled_by_default else 'false'}\n"
        f"priority: {priority}\n"
        "triggers:\n"
        f"  keywords: {json.dumps(keywords or [])}\n"
        f"  modes: {json.dumps(modes or [])}\n"
        f"  file_types: {json.dumps(file_types or [])}\n"
        f"  output_styles: {json.dumps(output_styles or [])}\n"
        "runtime_overrides:\n"
    )
    overrides = dict(runtime_overrides or {})
    if overrides:
        for key, value in overrides.items():
            payload += f"  {key}: {json.dumps(value)}\n"
    payload += f"---\n{body}\n"
    (skill_dir / "SKILL.md").write_text(payload, encoding="utf-8")


def test_app_model_merges_defaults_and_user_settings(tmp_path, monkeypatch) -> None:
    defaults = tmp_path / "default_settings.json"
    user_settings = tmp_path / "settings.json"

    defaults.write_text(
        json.dumps(
            {
                "theme": "light",
                "llm_provider": "anthropic",
                "chunk_size": 1000,
                "current_skill_id": "qa-core",
                "skills": {"enabled": {}},
            }
        ),
        encoding="utf-8",
    )
    user_settings.write_text(
        json.dumps(
            {
                "theme": "space_dust",
                "current_skill_id": "research-claims",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(app_model_module, "_DEFAULT_SETTINGS_PATH", defaults)
    monkeypatch.setattr(app_model_module, "_USER_SETTINGS_PATH", user_settings)

    model = AppModel()
    model.load_settings()

    # User overrides win
    assert model.settings["theme"] == "space_dust"
    assert model.current_skill_id == "research-claims"
    # Defaults preserved for keys absent from user
    assert model.settings["llm_provider"] == "anthropic"
    assert model.settings["chunk_size"] == 1000


def test_skill_repository_parses_and_toggles_skills(tmp_path) -> None:
    _write_skill(
        tmp_path,
        "research-claims",
        name="Research Claims",
        description="Map claims and counterclaims.",
        enabled_by_default=False,
        priority=8,
        keywords=["claim", "counterclaim"],
        modes=["Research"],
        runtime_overrides={"selected_mode": "Research", "retrieval_k": 42, "top_k": 12},
        body="Focus on evidence quality.",
    )
    repository = SkillRepository(tmp_path)

    valid = repository.list_valid_skills()
    assert [skill.skill_id for skill in valid] == ["research-claims"]
    assert repository.is_globally_enabled(valid[0], {"skills": {"enabled": {}}}) is False

    updated = repository.set_global_enabled({"skills": {"enabled": {}}}, "research-claims", True)
    assert updated["skills"]["enabled"]["research-claims"] is True
    assert repository.is_globally_enabled(valid[0], updated) is True


def test_skill_repository_reports_invalid_skill_frontmatter(tmp_path) -> None:
    skill_dir = tmp_path / "broken-skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: Broken\n---\nMissing required fields.\n",
        encoding="utf-8",
    )

    skill = parse_skill_file(skill_dir / "SKILL.md")
    repository = SkillRepository(tmp_path)

    assert skill.valid is False
    assert repository.lint_errors()


def test_runtime_resolution_uses_skill_precedence_and_conflicts() -> None:
    settings = {
        "selected_mode": "Q&A",
        "llm_provider": "openai",
        "llm_model": "gpt-5.4",
        "embedding_provider": "voyage",
        "embedding_model": "voyage-4-large",
        "retrieval_k": 10,
        "top_k": 3,
        "mmr_lambda": 0.5,
        "retrieval_mode": "flat",
        "agentic_mode": False,
        "agentic_max_iterations": 2,
        "search_type": "mmr",
        "output_style": "Structured report",
    }
    enabled_skills = [
        SkillDefinition(
            skill_id="qa-core",
            name="Q&A Core",
            description="Default grounded Q&A behavior.",
            enabled_by_default=True,
            priority=3,
            triggers={"keywords": [], "modes": ["Q&A"], "file_types": [], "output_styles": []},
            runtime_overrides={"retrieval_k": 18, "system_instructions_append": "Stay concise."},
            body="Answer directly.",
        ),
        SkillDefinition(
            skill_id="research-claims",
            name="Research Claims",
            description="Map evidence-backed claims.",
            enabled_by_default=True,
            priority=9,
            triggers={
                "keywords": ["claim", "counterclaim"],
                "modes": ["Research"],
                "file_types": [".pdf"],
                "output_styles": ["Structured report"],
            },
            runtime_overrides={
                "selected_mode": "Research",
                "retrieval_k": 42,
                "top_k": 12,
                "retrieval_mode": "hierarchical",
                "agentic_mode": True,
                "agentic_max_iterations": 3,
                "citation_policy_append": "Every factual claim needs [S#].",
            },
            body="Focus on evidence quality and disputed assertions.",
        ),
    ]

    resolved = resolve_runtime_settings(
        settings,
        enabled_skills=enabled_skills,
        session_skill_state=SkillSessionState(pinned=["qa-core"]),
        query="Map the strongest claim and counterclaim in this PDF.",
        file_types=[".pdf"],
    )

    assert resolved.mode == "Q&A"
    assert resolved.primary_skill_id == "qa-core"
    assert [skill.skill_id for skill in resolved.selected_skills] == ["qa-core", "research-claims"]
    assert resolved.runtime_override_conflicts
    assert any(conflict["key"] == "selected_mode" for conflict in resolved.runtime_override_conflicts)
    assert resolved.resolution_payload["skills"]["pinned"] == ["qa-core"]
    assert "Enabled skills:" in resolved.capability_index
    assert "Selected skill instructions:" in resolved.system_prompt


def test_local_model_registry_adds_and_activates_entries() -> None:
    service = LocalModelRegistryService()
    registry = service.add_gguf({}, name="Mistral GGUF", path="C:/models/mistral.gguf")
    registry = service.add_sentence_transformer(
        registry,
        name="sentence-transformers/all-MiniLM-L6-v2",
    )

    entries = service.list_entries(registry)
    gguf_entry = next(entry for entry in entries if entry.model_type == "gguf")
    st_entry = next(
        entry for entry in entries if entry.model_type == "sentence_transformers"
    )

    llm_settings = service.activate_entry({}, gguf_entry, target="llm")
    embedding_settings = service.activate_entry(llm_settings, st_entry, target="embedding")

    assert llm_settings["llm_provider"] == "local_gguf"
    assert llm_settings["local_gguf_model_path"] == "C:/models/mistral.gguf"
    assert embedding_settings["embedding_provider"] == "local_sentence_transformers"
    assert embedding_settings["local_st_model_name"] == "sentence-transformers/all-MiniLM-L6-v2"
