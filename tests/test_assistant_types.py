from metis_app.models.assistant_types import (
    AssistantIdentity,
    TONE_PRESETS,
)


def test_tone_presets_dict_has_three_canonical_keys():
    assert set(TONE_PRESETS.keys()) == {"warm-curious", "concise-analyst", "playful"}
    for key, seed in TONE_PRESETS.items():
        assert seed.startswith("You are METIS"), key
        assert len(seed) > 60, key


def test_assistant_identity_default_tone_preset():
    identity = AssistantIdentity()
    assert identity.tone_preset == "warm-curious"


def test_assistant_identity_round_trip_preserves_tone_preset():
    original = AssistantIdentity(tone_preset="concise-analyst")
    payload = original.to_payload()
    restored = AssistantIdentity.from_payload(payload)
    assert restored.tone_preset == "concise-analyst"


def test_assistant_identity_from_payload_unknown_preset_falls_back():
    restored = AssistantIdentity.from_payload({"tone_preset": "menace"})
    assert restored.tone_preset == "warm-curious"
