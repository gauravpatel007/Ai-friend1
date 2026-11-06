"""Targeted Verification Suite for Response-Time Monitoring Instrumentation (Task 2).

Verifies:
1. Monotonic timing precision via time.perf_counter().
2. Unique request IDs for text and voice conversation turns.
3. Complete 7-stage TEXT mode pipeline measurement.
4. Complete 9-stage VOICE mode pipeline measurement.
5. Privacy compliance: no raw audio buffers or sensitive prompts stored in telemetry dicts.
"""

import time
import pytest
from app.voice.conversation_state import ConversationLatencyMetrics
from app.ai.ai_service import AIService


def test_voice_latency_metrics_all_nine_stages() -> None:
    """Validate that ConversationLatencyMetrics measures all 9 voice stages and calculates deltas."""
    req_id = "vreq_test_001"
    metrics = ConversationLatencyMetrics(turn_id=1, request_id=req_id)

    # 1. User starts speaking
    metrics.mark_speech_start()
    time.sleep(0.005)

    # 2. Speech ends
    metrics.mark_speech_end()

    # 3. Speech recognition starts
    metrics.mark_stt_start()
    time.sleep(0.005)

    # 4. Final transcript becomes available
    metrics.mark_stt_done(recognized_text="Hello Buddy, how are you?")

    # 5. LLM starts generating
    metrics.mark_llm_start()
    time.sleep(0.005)

    # 6. First LLM token generated
    metrics.mark_first_token()

    # 7. First TTS audio chunk generated
    metrics.mark_first_tts_audio()
    time.sleep(0.005)

    # 8. Audio playback begins
    metrics.mark_playback_started()
    time.sleep(0.005)

    # 9. Complete response finishes playing
    metrics.mark_playback_ended()
    metrics.finish_turn(full_response="I am doing fantastic, thank you!")

    telemetry = metrics.to_telemetry_dict()

    # Verify mode and correlation ID
    assert telemetry["mode"] == "voice"
    assert telemetry["request_id"] == req_id
    assert telemetry["turn_id"] == 1

    # Verify all 9 monotonic milestones are present and monotonically increasing
    assert telemetry["t_speech_start"] > 0.0
    assert telemetry["t_speech_end"] >= telemetry["t_speech_start"]
    assert telemetry["t_stt_start"] >= telemetry["t_speech_end"]
    assert telemetry["t_transcript_ready"] >= telemetry["t_stt_start"]
    assert telemetry["t_llm_start"] >= telemetry["t_transcript_ready"]
    assert telemetry["t_first_token_gen"] >= telemetry["t_llm_start"]
    assert telemetry["t_first_tts_audio"] >= telemetry["t_first_token_gen"]
    assert telemetry["t_audio_playback_start"] >= telemetry["t_first_tts_audio"]
    assert telemetry["t_audio_playback_end"] >= telemetry["t_audio_playback_start"]

    # Verify calculated deltas
    assert telemetry["user_speech_duration_ms"] > 0.0
    assert telemetry["stt_duration_ms"] > 0.0
    assert telemetry["llm_time_to_first_token_ms"] >= 0.0
    assert telemetry["time_to_first_audible_ms"] > 0.0
    assert telemetry["total_playback_duration_ms"] > 0.0
    assert telemetry["total_voice_turn_ms"] > 0.0

    # Privacy verification: verify NO raw audio bytes or prompt text in telemetry
    telemetry_str = str(telemetry)
    assert "Hello Buddy" not in telemetry_str
    assert "raw_audio" not in telemetry_str
    assert "pcm" not in telemetry_str
    assert "audio_bytes" not in telemetry_str


def test_ai_service_text_telemetry_metrics(qapp_instance) -> None:
    """Validate that AIService tracks monotonic timestamps and exposes 7-stage text telemetry."""
    service = AIService()

    req_id = "treq_custom_999"
    t_recv = time.perf_counter()
    t_client = 123456.78

    # Manually configure active turn state to verify timing assembly
    with service._lock:
        service._current_gen_id = 42
        service._active_request_id = req_id
        service._t_backend_received = t_recv
        service._client_timestamp = t_client
        service._gen_start_time = t_recv + 0.002
        service._is_generating = True
        service._is_current_voice = False

    time.sleep(0.005)
    # Simulate chunk received
    service._on_chunk_received(42, "Hello")

    time.sleep(0.005)
    # Simulate completion
    service._on_completed(42, "Hello world!")

    timings = service.get_latest_timing_metrics()

    assert timings["request_id"] == req_id
    assert timings["t_backend_received"] == t_recv
    assert timings["client_timestamp"] == t_client
    assert timings["t_llm_start"] > t_recv
    assert timings["t_first_token"] > timings["t_llm_start"]
    assert timings["t_llm_completed"] > timings["t_first_token"]

    assert timings["backend_to_llm_start_ms"] > 0.0
    assert timings["llm_time_to_first_token_ms"] > 0.0
    assert timings["llm_generation_duration_ms"] > 0.0
    assert timings["total_backend_duration_ms"] > 0.0
    assert timings["response_length_chars"] == len("Hello world!")


def test_api_send_message_request_id_and_timing(qapp_instance) -> None:
    """Validate FastAPI route returns request_id and monotonic backend_received_time."""
    from starlette.testclient import TestClient
    from app.api.server import app
    from app.memory.conversation_repository import ConversationRepository

    repo = ConversationRepository()
    conv = repo.create_conversation("Perf Test")
    app.state.conv_repo = repo

    client = TestClient(app, base_url="http://127.0.0.1:8765")

    # 1. Provide explicit request_id
    payload = {
        "content": "Hello performance check",
        "is_voice": False,
        "request_id": "treq_client_12345",
        "client_timestamp": 98765.43,
    }
    res = client.post(f"/api/conversations/{conv.id}/messages", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["request_id"] == "treq_client_12345"
    assert "backend_received_time" in data
    assert data["backend_received_time"] > 0.0

    # 2. Omit request_id -> backend auto-generates unique ID
    payload2 = {
        "content": "Second check",
        "is_voice": False,
    }
    res2 = client.post(f"/api/conversations/{conv.id}/messages", json=payload2)
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["request_id"].startswith("req_")
    assert data2["request_id"] != "treq_client_12345"
    assert data2["backend_received_time"] > 0.0
