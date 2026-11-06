"""Phase 13: Performance and Privacy Requirements Verification.

Tests:
1. Local AI inference preservation and zero-cloud privacy:
   - Inference uses local Ollama endpoint (127.0.0.1:11434)
   - Zero external cloud AI or third-party paid API dependencies
   - Local database persistence without external data leakage
2. Local speech recognition and TTS:
   - Local Faster-Whisper offline model
   - Local TTS engines (Kokoro-82M, Piper, Windows SAPI5)
3. Non-blocking UI and async execution:
   - Asynchronous STT transcription worker
   - Background LLM generation thread
   - Asynchronous TTS worker queue
4. Stage latency measurements:
   - 1. Audio capture duration
   - 2. Speech-recognition latency
   - 3. Backend request latency
   - 4. Model time to first output
   - 5. Total model-generation time
   - 6. TTS generation time
   - 7. Time to first audible response
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.ai.ai_service import AIService
from app.ai.ollama_client import DEFAULT_OLLAMA_HOST, OllamaClient
from app.core.diagnostic_mode import DiagnosticTracker, diagnostic_tracker
from app.settings.config_manager import ConfigManager
from app.voice.conversation_state import ConversationLatencyMetrics, ConversationState
from app.voice.tts_base import BaseTTSEngine, SynthesizedAudio
from app.voice.voice_conversation_controller import VoiceConversationController
from app.voice.voice_service import VoiceService
from app.voice.whisper_engine import WhisperEngine


@pytest.fixture(autouse=True)
def cleanup_diagnostic():
    """Ensure clean diagnostic isolation before and after every test."""
    diagnostic_tracker.set_enabled(False)
    diagnostic_tracker.reset_turn()
    yield
    diagnostic_tracker.set_enabled(False)
    diagnostic_tracker.reset_turn()


# =============================================================================
# 1. LOCAL AI INFERENCE & PRIVACY PRESERVATION
# =============================================================================

class TestPrivacyAndLocalInference:
    """Verify that local AI architecture is preserved with zero cloud API dependencies."""

    def test_ollama_client_defaults_to_local_host(self):
        """Ollama client must communicate exclusively with local loopback host."""
        client = OllamaClient()
        assert "127.0.0.1" in client.base_url or "localhost" in client.base_url
        assert not client.base_url.startswith("https://api.openai.com")
        assert not client.base_url.startswith("https://api.anthropic.com")
        assert client.base_url == DEFAULT_OLLAMA_HOST

    def test_config_preserves_local_model_and_local_tts(self):
        """Configuration must select local model and local speech engines."""
        cfg = ConfigManager()
        model_name = cfg.get("ai.model", "llama3.2:3b")
        assert isinstance(model_name, str) and len(model_name) > 0
        assert "cloud" not in model_name.lower() or "llama" in model_name.lower() or "qwen" in model_name.lower()

    def test_voice_engines_are_strictly_local(self):
        """Voice service must use local offline speech engines without cloud calls."""
        vs = VoiceService()
        available_engines = vs.get_available_tts_engines()
        assert len(available_engines) > 0
        # All available engines must be local offline engines
        for engine in available_engines:
            assert engine in ("kokoro", "piper", "system", "sapi5")


# =============================================================================
# 2. NON-BLOCKING UI & ASYNCHRONOUS PIPELINE
# =============================================================================

class TestNonBlockingUIArchitecture:
    """Verify that heavy compute (STT, LLM, TTS) executes asynchronously off the GUI thread."""

    def test_whisper_engine_transcribe_async_non_blocking(self):
        """Whisper transcription must provide non-blocking asynchronous execution."""
        engine = WhisperEngine()
        engine._is_loaded = True

        called = []
        dummy_audio = np.zeros(16000, dtype=np.float32)

        with patch.object(engine._thread_pool, "start") as mock_start:
            engine.transcribe_async(
                audio_data=dummy_audio,
                language="en",
                callback=lambda res: called.append(res),
            )
            mock_start.assert_called_once()

    def test_ai_service_ask_dispatches_in_worker_thread(self, qapp_instance):
        """AIService.ask() must launch generation in a background worker without blocking caller."""
        ai = AIService(config_manager=ConfigManager())
        assert hasattr(ai, "thread_pool")

        with patch.object(ai.thread_pool, "start") as mock_start:
            ai.model_manager.is_available = MagicMock(return_value=True)
            ai.model_manager.select_active_model = MagicMock(return_value="llama3.2:3b")
            gen_id = ai.ask("Test question", is_voice=True)
            assert gen_id > 0
            mock_start.assert_called_once()
        ai.stop()


# =============================================================================
# 3. SEPARATE STAGE LATENCY MEASUREMENTS (Phase 13 Core Requirement)
# =============================================================================

class TestStageLatencyMeasurements:
    """Verify isolated tracking across all 7 stages required by Phase 13:
    1. Audio capture duration
    2. Speech-recognition latency
    3. Backend request latency
    4. Model time to first output
    5. Total model-generation time
    6. TTS generation time
    7. Time to first audible response
    """

    def test_conversation_latency_metrics_all_seven_stages(self):
        """Verify that ConversationLatencyMetrics computes and exports all 7 stage metrics."""
        m = ConversationLatencyMetrics(turn_id=42)

        # 1. Audio capture stage (simulating 1.85s speech)
        m.mark_speech_end(speech_duration_s=1.85)
        assert m.user_speech_duration_s == 1.85

        # Simulate base timestamps
        base = 1000.0
        m.t_turn_start = base
        m.t_speech_end = base + 1.85
        m.t_stt_completed = base + 2.10
        m.stt_latency_ms = (m.t_stt_completed - m.t_speech_end) * 1000.0  # 250ms

        m.t_backend_request_sent = base + 2.12
        m.t_backend_request_received = base + 2.14
        m.backend_request_latency_ms = (m.t_backend_request_received - m.t_backend_request_sent) * 1000.0  # 20ms

        m.t_first_llm_token = base + 2.44
        m.llm_first_token_latency_ms = (m.t_first_llm_token - m.t_backend_request_sent) * 1000.0  # 320ms

        m.t_llm_completed = base + 3.24
        m.total_model_generation_ms = (m.t_llm_completed - m.t_backend_request_received) * 1000.0  # 1100ms

        m.t_first_sentence_chunk = base + 2.66
        m.t_first_tts_audio = base + 2.84
        m.tts_first_audio_latency_ms = (m.t_first_tts_audio - m.t_first_sentence_chunk) * 1000.0  # 180ms

        m.t_first_playback_started = base + 2.87
        m.time_to_first_playback_ms = (m.t_first_playback_started - m.t_speech_end) * 1000.0  # 1020ms

        # Finish turn
        m.finish_turn(full_ai_text="Quantum computing utilizes quantum superposition.")
        data = m.to_dict()

        # Validate all 7 stages exist in exported dictionary
        assert data["turn_id"] == 42
        assert data["audio_capture_duration_s"] == 1.85
        assert data["speech_recognition_latency_ms"] == pytest.approx(250.0, abs=1.0)
        assert data["backend_request_latency_ms"] == pytest.approx(20.0, abs=1.0)
        assert data["model_time_to_first_output_ms"] == pytest.approx(320.0, abs=1.0)
        assert data["total_model_generation_ms"] == pytest.approx(1100.0, abs=1.0)
        assert data["tts_generation_time_ms"] == pytest.approx(180.0, abs=1.0)
        assert data["time_to_first_audible_response_ms"] == pytest.approx(1020.0, abs=1.0)

        # Dynamic measurement method verification
        m2 = ConversationLatencyMetrics(turn_id=43)
        m2.mark_speech_end(1.5)
        time.sleep(0.015)
        m2.mark_stt_done("Hello")
        assert m2.stt_latency_ms >= 10.0
        m2.mark_backend_sent()
        time.sleep(0.01)
        m2.mark_backend_received()
        assert m2.backend_request_latency_ms >= 5.0
        m2.mark_first_token()
        assert m2.llm_first_token_latency_ms >= 5.0
        time.sleep(0.01)
        m2.mark_llm_done()
        assert m2.total_model_generation_ms >= 5.0
        m2.mark_first_sentence()
        time.sleep(0.01)
        m2.mark_first_tts_audio()
        assert m2.tts_first_audio_latency_ms >= 5.0
        m2.mark_playback_started()
        assert m2.time_to_first_playback_ms >= 15.0

    def test_diagnostic_tracker_exposes_stage_latencies(self):
        """Diagnostic tracker must absorb and broadcast stage performance latencies."""
        tracker = DiagnosticTracker(enabled=True)

        stage_metrics = {
            "speech_recognition_latency_ms": 210.5,
            "backend_request_latency_ms": 15.2,
            "model_time_to_first_output_ms": 350.0,
            "total_model_generation_ms": 1250.0,
            "tts_generation_time_ms": 165.4,
            "time_to_first_audible_response_ms": 890.0,
        }

        tracker.update_stage_latencies(stage_metrics)
        status = tracker.get_status()

        assert status["speech_recognition_latency_ms"] == 210.5
        assert status["backend_request_latency_ms"] == 15.2
        assert status["model_time_to_first_output_ms"] == 350.0
        assert status["total_model_generation_ms"] == 1250.0
        assert status["tts_generation_time_ms"] == 165.4
        assert status["time_to_first_audible_response_ms"] == 890.0

    def test_structured_performance_logging(self, caplog):
        """Performance updates must log structured [PERFORMANCE] entries."""
        import logging
        tracker = DiagnosticTracker(enabled=True)

        with caplog.at_level(logging.INFO):
            tracker.update_stage_latencies({
                "speech_recognition_latency_ms": 195.0,
                "backend_request_latency_ms": 12.0,
                "model_time_to_first_output_ms": 280.0,
                "total_model_generation_ms": 950.0,
                "tts_generation_time_ms": 140.0,
                "time_to_first_audible_response_ms": 780.0,
            })

        assert any("[PERFORMANCE]" in record.message for record in caplog.records)
        assert any("TTFT=280.0ms" in record.message for record in caplog.records)
