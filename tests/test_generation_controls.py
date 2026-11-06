"""Tests for GenerationConfig controls and presets."""

from app.ai.generation_controls import GenerationConfig


def test_generation_config_defaults():
    """Verify default generation parameters."""
    cfg = GenerationConfig()
    assert cfg.model == "llama3.2:latest"
    assert cfg.temperature == 0.7
    assert cfg.max_tokens == 250
    assert cfg.context_size == 2048


def test_generation_config_to_ollama_options():
    """Verify mapping from GenerationConfig to Ollama options dictionary."""
    cfg = GenerationConfig(temperature=0.8, max_tokens=150, context_size=4096, top_p=0.95)
    opts = cfg.to_ollama_options()
    assert opts["temperature"] == 0.8
    assert opts["num_predict"] == 150
    assert opts["num_ctx"] == 4096
    assert opts["top_p"] == 0.95


def test_generation_config_voice_preset():
    """Verify voice preset defaults to concise mode and small token limit."""
    cfg = GenerationConfig.for_voice("qwen3:4b")
    assert cfg.response_style == "concise"
    assert cfg.max_tokens <= 100
    assert cfg.temperature <= 0.7


def test_generation_config_chat_preset():
    """Verify chat preset configures appropriate tokens and style."""
    cfg = GenerationConfig.for_chat("qwen3:4b")
    assert cfg.response_style == "casual"
    assert cfg.max_tokens >= 250


def test_generation_config_serialization():
    """Verify roundtrip dictionary serialization."""
    orig = GenerationConfig(model="llama3.2", temperature=0.5, max_tokens=120)
    data = orig.to_dict()
    restored = GenerationConfig.from_dict(data)
    assert restored.model == "llama3.2"
    assert restored.temperature == 0.5
    assert restored.max_tokens == 120
