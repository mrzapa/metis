from metis_app.models.assistant_types import AssistantIdentity, TONE_PRESETS
from metis_app.services.companion_voice import resolve_prompt_seed


def test_resolve_returns_preset_seed_when_seed_matches():
    identity = AssistantIdentity(
        tone_preset="concise-analyst",
        prompt_seed=TONE_PRESETS["concise-analyst"],
    )
    assert resolve_prompt_seed(identity) == TONE_PRESETS["concise-analyst"]


def test_resolve_returns_preset_seed_when_seed_empty():
    identity = AssistantIdentity(tone_preset="playful", prompt_seed="")
    assert resolve_prompt_seed(identity) == TONE_PRESETS["playful"]


def test_resolve_returns_custom_seed_when_tone_preset_is_custom():
    identity = AssistantIdentity(
        tone_preset="custom",
        prompt_seed="You are not METIS. You are a pirate.",
    )
    assert resolve_prompt_seed(identity) == "You are not METIS. You are a pirate."


def test_resolve_returns_custom_seed_when_user_overrode_preset_seed():
    identity = AssistantIdentity(
        tone_preset="warm-curious",
        prompt_seed="My custom seed text.",
    )
    # User typed override; treat as custom for resolution
    assert resolve_prompt_seed(identity) == "My custom seed text."


def test_resolve_falls_back_to_warm_curious_for_unknown_preset():
    # Bypass __init__ to simulate corrupt persisted state
    identity = AssistantIdentity()
    object.__setattr__(identity, "tone_preset", "menace")
    object.__setattr__(identity, "prompt_seed", "")
    assert resolve_prompt_seed(identity) == TONE_PRESETS["warm-curious"]


def test_default_identity_resolves_to_warm_curious_preset():
    """A freshly constructed identity must hit the preset-match rule, not the user-override rule."""
    assert resolve_prompt_seed(AssistantIdentity()) == TONE_PRESETS["warm-curious"]


def test_resolve_treats_whitespace_only_seed_as_empty():
    identity = AssistantIdentity(tone_preset="playful", prompt_seed="   \n  ")
    assert resolve_prompt_seed(identity) == TONE_PRESETS["playful"]
