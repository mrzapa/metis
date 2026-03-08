"""Helpers for the monolith-compatible local-model registry."""

from __future__ import annotations

import os
import pathlib
from typing import Any

from axiom_app.models.parity_types import LocalModelEntry


class LocalModelRegistryService:
    """Normalize, mutate, and activate local-model registry entries."""

    BUCKETS = ("gguf", "sentence_transformers")

    def normalize(self, payload: Any) -> dict[str, list[LocalModelEntry]]:
        registry: dict[str, list[LocalModelEntry]] = {bucket: [] for bucket in self.BUCKETS}
        if not isinstance(payload, dict):
            return registry
        for bucket in self.BUCKETS:
            for item in payload.get(bucket, []):
                if not isinstance(item, dict):
                    continue
                entry = LocalModelEntry.from_payload(item, fallback_type=bucket)
                if entry is not None:
                    registry[bucket].append(entry)
        return registry

    def serialize(self, registry: dict[str, list[LocalModelEntry]] | Any) -> dict[str, list[dict[str, Any]]]:
        normalized = self.normalize(self._to_payload(registry))
        return {
            bucket: [entry.to_payload() for entry in entries]
            for bucket, entries in normalized.items()
        }

    def list_entries(self, registry: dict[str, list[LocalModelEntry]] | Any) -> list[LocalModelEntry]:
        normalized = self.normalize(self._to_payload(registry))
        rows: list[LocalModelEntry] = []
        for bucket in self.BUCKETS:
            rows.extend(normalized.get(bucket, []))
        return rows

    def add_gguf(
        self,
        registry: dict[str, list[LocalModelEntry]] | Any,
        *,
        name: str,
        path: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        normalized = self.normalize(self._to_payload(registry))
        entry = LocalModelEntry.new("gguf", name, path, path=path, metadata=metadata)
        normalized["gguf"] = self._upsert(normalized["gguf"], entry)
        return self.serialize(normalized)

    def add_sentence_transformer(
        self,
        registry: dict[str, list[LocalModelEntry]] | Any,
        *,
        name: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        normalized = self.normalize(self._to_payload(registry))
        entry = LocalModelEntry.new("sentence_transformers", name, name, metadata=metadata)
        normalized["sentence_transformers"] = self._upsert(
            normalized["sentence_transformers"],
            entry,
        )
        return self.serialize(normalized)

    def remove_entry(
        self,
        registry: dict[str, list[LocalModelEntry]] | Any,
        entry_id: str,
    ) -> dict[str, list[dict[str, Any]]]:
        normalized = self.normalize(self._to_payload(registry))
        for bucket in self.BUCKETS:
            normalized[bucket] = [
                entry for entry in normalized[bucket] if entry.entry_id != entry_id
            ]
        return self.serialize(normalized)

    def get_entry(
        self,
        registry: dict[str, list[LocalModelEntry]] | Any,
        entry_id: str,
    ) -> LocalModelEntry | None:
        for entry in self.list_entries(registry):
            if entry.entry_id == entry_id:
                return entry
        return None

    def activate_entry(
        self,
        settings: dict[str, Any],
        entry: LocalModelEntry,
        *,
        target: str,
    ) -> dict[str, Any]:
        updated = dict(settings or {})
        if target == "llm":
            if entry.model_type != "gguf":
                raise ValueError("Only GGUF entries can be activated as an LLM.")
            updated["llm_provider"] = "local_gguf"
            updated["local_gguf_model_path"] = entry.path or entry.value
            updated["llm_model"] = entry.name
            updated["llm_model_custom"] = entry.name
            metadata = dict(entry.metadata or {})
            context_length = metadata.get("recommended_context_length")
            try:
                context_value = int(context_length) if context_length not in (None, "") else None
            except (TypeError, ValueError):
                context_value = None
            if context_value:
                updated["local_gguf_context_length"] = max(context_value, 2048)
            updated["local_gguf_gpu_layers"] = 0
            updated["local_gguf_threads"] = 0
            return updated

        if target != "embedding":
            raise ValueError(f"Unknown activation target: {target}")
        if entry.model_type == "sentence_transformers":
            updated["embedding_provider"] = "local_sentence_transformers"
            updated["local_st_model_name"] = entry.value
            updated["sentence_transformers_model"] = entry.value
            return updated

        updated["embedding_provider"] = "local_huggingface"
        updated["embedding_model"] = entry.name
        updated["embedding_model_custom"] = entry.path or entry.value
        return updated

    def open_path_for_entry(self, settings: dict[str, Any], entry: LocalModelEntry) -> pathlib.Path:
        if entry.model_type == "gguf":
            raw = entry.path or entry.value
        else:
            raw = str(settings.get("local_st_cache_dir", "") or "").strip() or os.path.expanduser("~")
        path = pathlib.Path(raw).expanduser()
        return path if path.is_dir() else path.parent

    @staticmethod
    def _to_payload(registry: dict[str, list[LocalModelEntry]] | Any) -> dict[str, Any]:
        if isinstance(registry, dict):
            payload: dict[str, Any] = {}
            for bucket, items in registry.items():
                normalized_items: list[dict[str, Any]] = []
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, LocalModelEntry):
                            normalized_items.append(item.to_payload())
                        elif isinstance(item, dict):
                            normalized_items.append(dict(item))
                payload[str(bucket)] = normalized_items
            return payload
        return {}

    @staticmethod
    def _upsert(entries: list[LocalModelEntry], new_entry: LocalModelEntry) -> list[LocalModelEntry]:
        filtered = [
            entry
            for entry in entries
            if not (
                entry.name.lower() == new_entry.name.lower()
                and entry.model_type == new_entry.model_type
                and (entry.path or entry.value).lower() == (new_entry.path or new_entry.value).lower()
            )
        ]
        filtered.append(new_entry)
        return filtered
