from __future__ import annotations

import json

from axiom_app.models.app_model import AppModel
from axiom_app.models.parity_types import AgentProfile
from axiom_app.services.local_model_registry import LocalModelRegistryService
from axiom_app.services.profile_repository import ProfileRepository
from axiom_app.services.runtime_resolution import resolve_runtime_settings
import axiom_app.models.app_model as app_model_module


def test_app_model_imports_legacy_config_without_overriding_user_settings(
    tmp_path,
    monkeypatch,
) -> None:
    defaults = tmp_path / "default_settings.json"
    user_settings = tmp_path / "settings.json"
    legacy_settings = tmp_path / "agentic_rag_config.json"

    defaults.write_text(
        json.dumps(
            {
                "theme": "light",
                "llm_provider": "anthropic",
                "chunk_size": 1000,
                "selected_profile": "Built-in: Default",
            }
        ),
        encoding="utf-8",
    )
    legacy_settings.write_text(
        json.dumps(
            {
                "theme": "dark",
                "llm_provider": "openai",
                "chunk_size": 222,
            }
        ),
        encoding="utf-8",
    )
    user_settings.write_text(
        json.dumps(
            {
                "theme": "space_dust",
                "selected_profile": "File: custom.json",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(app_model_module, "_DEFAULT_SETTINGS_PATH", defaults)
    monkeypatch.setattr(app_model_module, "_USER_SETTINGS_PATH", user_settings)
    monkeypatch.setattr(app_model_module, "_LEGACY_CONFIG_PATH", legacy_settings)

    model = AppModel()
    model.load_settings()

    assert model.settings["theme"] == "space_dust"
    assert model.settings["llm_provider"] == "openai"
    assert model.settings["chunk_size"] == 222
    assert model.current_profile_label == "File: custom.json"


def test_profile_repository_round_trips_and_duplicates_profiles(tmp_path) -> None:
    repo = ProfileRepository(tmp_path)
    source = AgentProfile(
        name="Research Analyst",
        system_instructions="Cite everything.",
        retrieval_strategy={"retrieve_k": 40, "final_k": 8},
        mode_default="Research",
        provider="mock",
        model="mock-v2",
    )

    saved_path = repo.save_profile(source)
    saved_label = repo.label_for_path(saved_path)
    loaded = repo.get_profile(saved_label)
    duplicate_path = repo.duplicate_profile(saved_label, new_name="Research Analyst Copy")
    duplicate_label = repo.label_for_path(duplicate_path)

    assert loaded.name == "Research Analyst"
    assert loaded.retrieval_strategy["retrieve_k"] == 40
    assert duplicate_label in repo.list_labels()
    assert repo.get_profile(duplicate_label).name == "Research Analyst Copy"


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
    assert (
        embedding_settings["local_st_model_name"]
        == "sentence-transformers/all-MiniLM-L6-v2"
    )


def test_runtime_resolution_matches_monolith_mode_prompt_and_precedence() -> None:
    profile = AgentProfile(
        name="Research Analyst",
        mode_default="Research",
        provider="anthropic",
        model="claude-opus-4-6",
        system_instructions="Demand evidentiary grounding.",
        style_template="Claims, counterclaims, and gaps.",
        citation_policy="Every factual claim needs [S#].",
        retrieval_strategy={"retrieve_k": 30, "final_k": 7, "mmr_lambda": 0.4},
        iteration_strategy={"agentic_mode": True, "max_iterations": 3},
        retrieval_mode="hierarchical",
    )
    settings = {
        "selected_mode": "Research",
        "llm_provider": "openai",
        "llm_model": "gpt-5.4",
        "embedding_provider": "voyage",
        "embedding_model": "voyage-4-large",
        "search_type": "mmr",
        "output_style": "Structured report",
    }

    resolved = resolve_runtime_settings(
        settings,
        profile,
        profile_label="File: research.json",
        query="Map the strongest claims and counterclaims.",
    )

    assert resolved.mode == "Research"
    assert resolved.prompt_pack_id == "Research"
    assert resolved.retrieve_k == 30
    assert resolved.final_k == 7
    assert resolved.agentic_mode is True
    assert resolved.agentic_max_iterations == 3
    assert resolved.llm_provider == "anthropic"
    assert "Mode: Research." in resolved.mode_prompt_pack
    assert "Profile overlay:" in resolved.system_prompt
    assert resolved.resolution_payload["prompt_pack_id"] == "Research"
