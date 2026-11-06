"""Tests for PersonalityManager."""

from app.ai.personality_manager import PersonalityManager


def test_personality_manager_default_prompt():
    """Verify default friendly prompt formatting with companion name."""
    pm = PersonalityManager(companion_name="RoboFriend")
    prompt = pm.build_system_prompt()
    assert "RoboFriend" in prompt
    assert "friendly" in prompt.lower()
    assert "desktop AI companion" in prompt


def test_personality_manager_switch_preset():
    """Verify switching personality presets changes the base prompt."""
    pm = PersonalityManager()
    assert pm.set_personality("playful") is True
    prompt_playful = pm.build_system_prompt()
    assert "playful" in prompt_playful.lower()

    assert pm.set_personality("concise") is True
    prompt_concise = pm.build_system_prompt()
    assert "concise" in prompt_concise.lower()


def test_personality_manager_custom_prompt():
    """Verify setting a custom personality prompt."""
    pm = PersonalityManager()
    pm.set_custom_prompt("You are {name}, a cybersecurity analyst mentor.")
    prompt = pm.build_system_prompt()
    assert "cybersecurity analyst mentor" in prompt
    assert "Buddy" in prompt


def test_personality_manager_voice_mode_adaptation():
    """Verify voice mode prompts include strict brevity instructions."""
    pm = PersonalityManager()
    prompt_voice = pm.build_system_prompt(is_voice=True)
    assert "VOICE MODE" in prompt_voice
    assert "concise" in prompt_voice.lower()


def test_personality_manager_user_name_and_custom_rules():
    """Verify user name and custom rules are included in prompt."""
    pm = PersonalityManager(user_name="Alice")
    pm.add_custom_rule("Always use metric units.")
    prompt = pm.build_system_prompt()
    assert "Alice" in prompt
    assert "metric units" in prompt


from typing import Any, Dict, Optional


class MockConfigManager:
    """Mock config manager for testing dynamic personality settings persistence."""

    def __init__(self, initial: Optional[Dict[str, Any]] = None) -> None:
        self.store: Dict[str, Any] = initial or {}

    def get(self, key: str, default: Any = None) -> Any:
        return self.store.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.store[key] = value


def test_personality_manager_with_config_manager_keyword_arg():
    """Verify initializing PersonalityManager(config_manager=cm) succeeds without TypeError (Bug 9)."""
    cfg = MockConfigManager({
        "ai.personality": "energetic",
        "companion.name": "Sparky",
        "user.name": "Dave",
    })
    pm = PersonalityManager(config_manager=cfg)

    assert pm.personality == "energetic"
    assert pm.companion_name == "Sparky"
    assert pm.user_name == "Dave"
    prompt = pm.build_system_prompt()
    assert "Sparky" in prompt
    assert "Dave" in prompt
    assert "enthusiastic" in prompt.lower() or "energetic" in prompt.lower()


def test_personality_manager_config_manager_sync_on_updates():
    """Verify updating personality attributes persists them back to the config manager."""
    cfg = MockConfigManager({
        "ai.personality": "friendly",
        "companion.name": "Buddy",
    })
    pm = PersonalityManager(config_manager=cfg)

    # Change personality
    pm.set_personality("calm")
    assert cfg.get("ai.personality") == "calm"

    # Change companion name
    pm.set_companion_name("Luna")
    assert cfg.get("companion.name") == "Luna"
    assert "Luna" in pm.build_system_prompt()

    # Set user name
    pm.set_user_name("Sarah")
    assert cfg.get("user.name") == "Sarah"
    assert "Sarah" in pm.build_system_prompt()

    # Custom prompt
    pm.set_custom_prompt("You are {name}, a space explorer.")
    assert cfg.get("ai.personality") == "custom"
    assert "space explorer" in pm.build_system_prompt()


def test_personality_manager_positional_config_manager_and_kwargs():
    """Verify PersonalityManager accepts positional config manager and unexpected kwargs safely."""
    cfg = MockConfigManager({
        "ai.personality": "professional",
        "companion.name": "Alfred",
    })
    # Positional config manager + extra kwargs
    pm = PersonalityManager(cfg, extra_future_param="ignore_safely")
    assert pm.personality == "professional"
    assert pm.companion_name == "Alfred"

    # Explicit override takes precedence over config
    pm2 = PersonalityManager(
        default_personality="funny",
        companion_name="Joker",
        config_manager=cfg,
    )
    assert pm2.personality == "funny"
    assert pm2.companion_name == "Joker"

