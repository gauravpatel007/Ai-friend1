"""Unit tests for Ollama Process Supervisor & Chat Auto-Launch (Bug 7).

Verifies that:
1. Ollama executable is discovered via config, PATH, or standard install locations.
2. Background daemon ('ollama serve') is automatically launched when offline.
3. Clean shutdown terminates supervisor-spawned daemon instances.
4. AIService auto-recovers via supervisor and provides helpful in-stream chat guidance
   when Ollama cannot be reached and offline fallback is disabled.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from app.ai.ai_service import AIService
from app.ai.model_manager import ModelManager
from app.ai.ollama_client import OllamaClient
from app.ai.ollama_supervisor import OllamaSupervisor
from app.core.signals import signals


class TestOllamaSupervisor:
    """Unit tests for OllamaSupervisor discovery and lifecycle."""

    def test_find_executable_custom_path(self, tmp_path) -> None:
        fake_exe = tmp_path / "ollama.exe"
        fake_exe.write_text("dummy binary")

        supervisor = OllamaSupervisor()
        supervisor.set_executable_path(fake_exe)
        found = supervisor.find_ollama_executable()
        assert found == fake_exe

    def test_find_executable_from_path(self, monkeypatch, tmp_path) -> None:
        fake_exe = tmp_path / "bin" / "ollama"
        fake_exe.parent.mkdir(parents=True, exist_ok=True)
        fake_exe.write_text("binary")

        monkeypatch.setattr("shutil.which", lambda cmd: str(fake_exe) if "ollama" in cmd else None)

        supervisor = OllamaSupervisor()
        found = supervisor.find_ollama_executable()
        assert found == fake_exe

    def test_find_executable_missing(self, monkeypatch) -> None:
        monkeypatch.setattr("shutil.which", lambda cmd: None)
        monkeypatch.setenv("OLLAMA_EXE_PATH", "")

        supervisor = OllamaSupervisor()
        # Mock Path.is_file to always return False for candidate lookups
        with patch.object(Path, "is_file", return_value=False):
            found = supervisor.find_ollama_executable()
            assert found is None

    def test_is_server_reachable(self) -> None:
        supervisor = OllamaSupervisor()
        # Offline port should return False
        assert supervisor.is_server_reachable("http://127.0.0.1:59998", timeout=0.2) is False

    def test_ensure_server_running_when_already_reachable(self, monkeypatch) -> None:
        supervisor = OllamaSupervisor()
        monkeypatch.setattr(supervisor, "is_server_reachable", lambda url, timeout=1.0: True)

        assert supervisor.ensure_server_running("http://127.0.0.1:11434") is True
        assert supervisor._process is None

    def test_ensure_server_running_auto_spawns_process(self, monkeypatch, tmp_path) -> None:
        fake_exe = tmp_path / "ollama.exe"
        fake_exe.write_text("exe")

        supervisor = OllamaSupervisor()
        supervisor.set_executable_path(fake_exe)

        reachability_checks = [False, False, True]

        def mock_reachable(url, timeout=1.0):
            if reachability_checks:
                return reachability_checks.pop(0)
            return True

        monkeypatch.setattr(supervisor, "is_server_reachable", mock_reachable)

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None

        with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
            success = supervisor.ensure_server_running("http://127.0.0.1:11434", timeout=3.0)
            assert success is True
            assert mock_popen.called
            cmd_args = mock_popen.call_args[0][0]
            assert cmd_args == [str(fake_exe), "serve"]
            assert supervisor._started_by_supervisor is True

        # Stop server should terminate process
        supervisor.stop_server()
        mock_proc.terminate.assert_called_once()
        assert supervisor._started_by_supervisor is False

    def test_model_manager_is_available_auto_starts(self, monkeypatch) -> None:
        mock_client = MagicMock()
        mock_client.is_server_reachable.return_value = False
        mock_client.base_url = "http://127.0.0.1:11434"

        mock_supervisor = MagicMock()
        mock_supervisor.ensure_server_running.return_value = True

        mgr = ModelManager(client=mock_client, supervisor=mock_supervisor)
        # Without auto_start -> False
        assert mgr.is_available(auto_start=False) is False
        assert not mock_supervisor.ensure_server_running.called

        # With auto_start -> True
        assert mgr.is_available(auto_start=True) is True
        mock_supervisor.ensure_server_running.assert_called_once_with("http://127.0.0.1:11434")


class TestAIServiceOllamaRecovery:
    """Tests for AIService auto-launch and in-stream chat fallback."""

    def test_ai_service_auto_launches_ollama_on_prompt(self, qapp_instance, monkeypatch) -> None:
        client = OllamaClient(base_url="http://127.0.0.1:59996")
        service = AIService(client=client)

        supervisor_called = []

        def mock_ensure_running(base_url, timeout=5.0):
            supervisor_called.append(base_url)
            # Simulate Ollama waking up
            monkeypatch.setattr(service.model_manager, "is_available", lambda auto_start=False: True)
            return True

        monkeypatch.setattr(service.model_manager.supervisor, "ensure_server_running", mock_ensure_running)
        monkeypatch.setattr(service.model_manager, "is_available", lambda auto_start=False: False)
        monkeypatch.setattr(service.model_manager, "select_active_model", lambda: "llama3.2")

        # Mock Ollama streaming
        mock_chunks = [{"message": {"content": "Hello! I was auto-started!"}}]
        monkeypatch.setattr(service.client, "chat_stream", lambda *args, **kwargs: iter(mock_chunks))

        received_chunks = []
        signals.ai_response_chunk.connect(received_chunks.append)

        gen_id = service.ask("Hi buddy!")
        qapp_instance.processEvents()

        assert len(supervisor_called) == 1
        assert supervisor_called[0] == "http://127.0.0.1:59996"
        service.stop()

    def test_ai_service_streams_guidance_when_ollama_offline_and_no_fallback(self, qapp_instance, monkeypatch) -> None:
        """Bug 7: When Ollama is offline and offline fallback is disabled, guidance renders in chat."""
        client = OllamaClient(base_url="http://127.0.0.1:59995", timeout=0.1)
        service = AIService(client=client)
        service.offline_fallback = False

        # Ensure supervisor cannot start it
        monkeypatch.setattr(service.model_manager.supervisor, "ensure_server_running", lambda *a, **k: False)
        monkeypatch.setattr(service.model_manager, "is_available", lambda auto_start=False: False)

        started_events = []
        completed_signals = []
        chunk_signals = []
        error_events = []

        service.generation_started.connect(lambda gid, prompt: started_events.append(prompt))
        signals.ai_response_chunk.connect(chunk_signals.append)
        signals.ai_response_complete.connect(completed_signals.append)
        service.error_occurred.connect(error_events.append)

        gen_id = service.ask("What is quantum computing?")
        qapp_instance.processEvents()

        # Check that generation started was emitted for UI
        assert len(started_events) == 1
        assert started_events[0] == "What is quantum computing?"

        # Check that actionable guidance was emitted directly into chat stream
        assert len(chunk_signals) >= 1
        assert "Ollama is offline" in chunk_signals[0]
        assert "ollama.com" in chunk_signals[0]
        assert len(completed_signals) == 1

        # Check that error event was also logged
        assert len(error_events) == 1
        assert "offline" in error_events[0].lower()

        service.stop()
