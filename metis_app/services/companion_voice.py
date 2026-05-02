"""Resolve effective prompt seed from AssistantIdentity tone preset."""

from __future__ import annotations

from metis_app.models.assistant_types import AssistantIdentity, TONE_PRESETS


def resolve_prompt_seed(identity: AssistantIdentity) -> str:
    """Return the seed METIS should use given the identity's preset and override.

    Rules:
      - tone_preset == "custom" -> use prompt_seed verbatim
      - tone_preset is a known key AND prompt_seed is empty -> preset's seed
      - tone_preset is a known key AND prompt_seed equals the preset -> preset's seed
      - tone_preset is a known key AND prompt_seed differs -> user override (custom)
      - tone_preset is unknown -> fall back to "warm-curious"
    """
    preset = identity.tone_preset or "warm-curious"
    seed = identity.prompt_seed or ""

    if preset == "custom":
        return seed

    if preset not in TONE_PRESETS:
        return TONE_PRESETS["warm-curious"]

    canonical = TONE_PRESETS[preset]
    if seed == "" or seed == canonical:
        return canonical

    # User typed an override - honour it
    return seed
