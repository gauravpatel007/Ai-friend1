"""Unit and UI tests for SetupWizard and OllamaRuntimeManager."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.ollama_installer import OllamaRuntimeManager
from app.desktop.setup_wizard import SetupWizard
from app.settings.config_manager import ConfigManager

SCRATCH_DIR = Path(__file__).parent / "_test_scratch"
SCRATCH_DIR.mkdir(parents=True, exist_ok=True)


def test_ollama_runtime_manager_methods():
    mgr = OllamaRuntimeManager(host="http://127.0.0.1:11434")

    # Mock is_running
    with patch("urllib.request.OpenerDirector.open") as mock_open:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_open.return_value.__enter__.return_value = mock_resp
        assert mgr.is_running() is True

    # Mock list_installed_models
    with patch("urllib.request.OpenerDirector.open") as mock_open:
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"models": [{"name": "qwen3:1.7b"}, {"name": "llama3.2:1b"}]}'
        mock_open.return_value.__enter__.return_value = mock_resp
        models = mgr.list_installed_models()
        assert "qwen3:1.7b" in models
        assert mgr.is_model_available("qwen3:1.7b") is True
        assert mgr.is_model_available("mistral:7b") is False


def test_setup_wizard_flow(qapp_instance):
    config_file = SCRATCH_DIR / "test_wizard_config.json"
    cfg = ConfigManager(config_path=config_file)
    cfg.set("general.setup_completed", False)

    wizard = SetupWizard(config_manager=cfg)
    assert wizard.stack.count() == 5
    assert wizard.stack.currentIndex() == 0

    # Step 1 -> Step 2
    wizard.companion_name_input.setText("Nova")
    wizard._on_next_clicked()
    assert wizard.stack.currentIndex() == 1

    # Step 2 -> Step 3
    wizard._on_next_clicked()
    assert wizard.stack.currentIndex() == 2

    # Step 3 -> Step 4
    wizard._on_next_clicked()
    assert wizard.stack.currentIndex() == 3

    # Step 4 -> Step 5
    wizard._on_next_clicked()
    assert wizard.stack.currentIndex() == 4
    assert wizard.next_btn.text().startswith("Finish")

    # Complete setup
    with patch("app.desktop.setup_wizard.enable_startup"), patch("app.desktop.setup_wizard.disable_startup"):
        wizard._save_and_finish()

    assert cfg.get("general.setup_completed") is True
    assert cfg.get("ai.companion_name") == "Nova"
