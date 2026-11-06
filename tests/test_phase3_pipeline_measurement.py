"""Phase 3 Automated Test Suite: Voice Pipeline Performance and Baseline Measurement.

Verifies:
1. Metrics Model & 10 Voice Pipeline Stages:
   - Speech detection time (onset)
   - VAD endpoint detection time (silence hangover)
   - Faster-Whisper transcription time (STT)
   - Ollama first-token latency (TTFT)
   - Complete LLM response time
   - First TTS audio latency
   - Total speech generation time
   - Audio playback completion time
   - Barge-in detection time
   - Audio cancellation time
2. Structured Timing Logs:
   - Contains session_id, input_language, transcription, stt_duration_ms, llm_duration_ms,
     tts_duration_ms, total_response_duration_ms, interruption_events, errors.
   - Privacy guarantee: No raw audio buffers or private memory data exposed.
3. Sentence Chunking Invariants:
   - Chunk 0 yields immediately upon first sentence completion (prior to full generation).
   - Sequential ordering: chunks maintain strictly ordered playback indexes.
   - No duplicated sentences, no missing words, no erroneous splits on abbreviations/decimals.
4. Interruption & Cancellation Tracking:
   - Recording barge-in detection time and audio cancellation time.
"""

from __future__ import annotations

import json
import time
import unittest
from unittest.mock import MagicMock

from PySide6.QtCore import QCoreApplication

from app.voice.conversation_state import ConversationLatencyMetrics, ConversationState
from app.voice.sentence_chunker import SentenceChunker
from app.voice.streaming_audio_queue import QueuedAudio, QueuedSentence, StreamingAudioQueue
from app.voice.tts_base import SynthesizedAudio
import numpy as np


class TestPhase3VoicePipelineMeasurement(unittest.TestCase):
    """Automated test suite for Phase 3 latency tracking, telemetry, and chunking."""

    @classmethod
    def setUpClass(cls) -> None:
        if QCoreApplication.instance() is None:
            cls.app = QCoreApplication([])
        else:
            cls.app = QCoreApplication.instance()

    def test_latency_metrics_all_ten_stages_tracked(self) -> None:
        """Verify that all 10 voice pipeline stages are tracked and serializable."""
        m = ConversationLatencyMetrics(turn_id=101)
        m.session_id = "session_test_123"
        m.input_language = "en"
        m.transcription = "Hello, how are you?"

        # 1. Speech detection time
        m.speech_detection_latency_ms = 96.0
        # 2. VAD endpoint detection time
        m.vad_endpoint_latency_ms = 400.0
        # 3. Whisper STT duration
        m.stt_duration_ms = 350.0
        # 4. Ollama first-token latency
        m.first_token_latency_ms = 420.0
        # 5. Complete LLM response time
        m.llm_duration_ms = 1200.0
        # 6. First TTS audio latency
        m.first_audio_latency_ms = 180.0
        # 7. Total speech generation time
        m.total_tts_duration_ms = 650.0
        # 8. Audio playback completion time
        m.audio_playback_completion_ms = 2100.0
        # 9. Barge-in detection time
        m.barge_in_detection_ms = 405.0
        # 10. Audio cancellation time
        m.audio_cancellation_ms = 2.5

        d = m.to_dict()

        self.assertEqual(d["session_id"], "session_test_123")
        self.assertEqual(d["input_language"], "en")
        self.assertEqual(d["transcription"], "Hello, how are you?")
        self.assertEqual(d["speech_detection_latency_ms"], 96.0)
        self.assertEqual(d["vad_endpoint_latency_ms"], 400.0)
        self.assertEqual(d["stt_duration_ms"], 350.0)
        self.assertEqual(d["first_token_latency_ms"], 420.0)
        self.assertEqual(d["llm_duration_ms"], 1200.0)
        self.assertEqual(d["first_audio_latency_ms"], 180.0)
        self.assertEqual(d["total_tts_duration_ms"], 650.0)
        self.assertEqual(d["audio_playback_completion_ms"], 2100.0)
        self.assertEqual(d["barge_in_detection_ms"], 405.0)
        self.assertEqual(d["audio_cancellation_ms"], 2.5)

    def test_structured_timing_log_format_and_privacy(self) -> None:
        """Verify structured log contains all required fields and no private memory/audio buffers."""
        m = ConversationLatencyMetrics(turn_id=102)
        m.session_id = "session_privacy_check"
        m.input_language = "gu"
        m.transcription = "Kem cho?"
        m.stt_duration_ms = 320.5
        m.first_token_latency_ms = 410.0
        m.llm_duration_ms = 950.0
        m.total_tts_duration_ms = 520.0
        m.first_audio_latency_ms = 210.0
        m.total_turn_duration_ms = 1850.0
        m.error = None

        log = m.to_structured_log()

        # Check required fields
        required_keys = [
            "session_id",
            "input_language",
            "transcription",
            "stt_duration_ms",
            "llm_duration_ms",
            "tts_duration_ms",
            "total_response_duration_ms",
            "interruption_events",
            "errors",
        ]
        for key in required_keys:
            self.assertIn(key, log, f"Missing required key '{key}' in structured log")

        self.assertEqual(log["session_id"], "session_privacy_check")
        self.assertEqual(log["input_language"], "gu")
        self.assertEqual(log["transcription"], "Kem cho?")
        self.assertEqual(log["stt_duration_ms"], 320.5)
        self.assertEqual(log["llm_duration_ms"], 950.0)
        self.assertEqual(log["tts_duration_ms"], 520.0)
        self.assertEqual(log["total_response_duration_ms"], 1850.0)
        self.assertEqual(log["interruption_events"], [])
        self.assertIsNone(log["errors"])

        # Check Privacy constraint: no raw audio frames, no prompt templates, no memory objects
        log_json = json.dumps(log)
        self.assertNotIn("audio_buffer", log_json)
        self.assertNotIn("raw_pcm", log_json)
        self.assertNotIn("system_prompt", log_json)
        self.assertNotIn("conversation_context", log_json)

    def test_interruption_recording(self) -> None:
        """Verify barge-in detection and audio cancellation are recorded."""
        m = ConversationLatencyMetrics(turn_id=103)
        self.assertEqual(m.interruption_count, 0)
        self.assertEqual(len(m.interruption_events), 0)

        m.record_interruption("user_speech", barge_in_ms=412.0, cancellation_ms=3.2)

        self.assertEqual(m.interruption_count, 1)
        self.assertEqual(len(m.interruption_events), 1)
        event = m.interruption_events[0]
        self.assertEqual(event["trigger"], "user_speech")
        self.assertEqual(event["barge_in_ms"], 412.0)
        self.assertEqual(event["cancellation_ms"], 3.2)
        self.assertIn("timestamp", event)
        self.assertEqual(m.barge_in_detection_ms, 412.0)
        self.assertEqual(m.audio_cancellation_ms, 3.2)

    def test_sentence_chunking_early_speaking(self) -> None:
        """Verify first sentence emits early before entire stream is finished."""
        chunker = SentenceChunker(min_chars=6, max_chars=140)
        emitted_chunks = []

        tokens = ["Hello", " there", "!", " How", " can", " I", " help", " you", " today", "?"]

        for i, token in enumerate(tokens):
            sentences = chunker.add_chunk(token)
            for s in sentences:
                emitted_chunks.append((i, s))

        for s in chunker.flush():
            emitted_chunks.append((len(tokens) - 1, s))

        self.assertGreaterEqual(len(emitted_chunks), 2)
        # First chunk emitted at or right after "!" token (token index 2)
        first_emit_token_idx, first_chunk = emitted_chunks[0]
        self.assertEqual(first_emit_token_idx, 2)
        self.assertEqual(first_chunk.strip(), "Hello there!")
        # Second chunk emitted later
        self.assertIn("today?", emitted_chunks[1][1])

    def test_sentence_chunking_word_integrity_and_no_duplication(self) -> None:
        """Verify no duplicated sentences and no missing words."""
        chunker = SentenceChunker(min_chars=6, max_chars=140)
        text = "This is the first sentence. Here is the second sentence! And this is the third."
        tokens = text.split(" ")

        collected_chunks = []
        for token in tokens:
            for s in chunker.add_chunk(token + " "):
                collected_chunks.append(s)
        for s in chunker.flush():
            collected_chunks.append(s)

        reconstructed = " ".join(" ".join(collected_chunks).split())
        expected = " ".join(text.split())
        self.assertEqual(reconstructed, expected)

        # Verify no duplicate sentences
        self.assertEqual(len(collected_chunks), 3)
        self.assertEqual(len(set(collected_chunks)), len(collected_chunks))

    def test_sentence_chunking_abbreviations_and_decimals_protected(self) -> None:
        """Verify abbreviations (Dr., e.g., etc.) and decimals (3.14) are not split."""
        chunker = SentenceChunker(min_chars=6, max_chars=140)
        text = "Dr. Smith bought 3.14 kg of apples e.g. Honeycrisp etc. yesterday."
        tokens = text.split(" ")

        chunks = []
        for token in tokens:
            for s in chunker.add_chunk(token + " "):
                chunks.append(s)
        for s in chunker.flush():
            chunks.append(s)

        # It should not split on "Dr.", "3.14", "e.g.", "etc."
        # Everything should be in a single chunk until the final "."
        self.assertEqual(len(chunks), 1)
        self.assertIn("Dr. Smith bought 3.14 kg", chunks[0])

    def test_streaming_queue_strict_sequential_order(self) -> None:
        """Verify StreamingAudioQueue plays audio strictly in sequence (Chunk 0 -> 1 -> 2)."""
        mock_player = MagicMock()
        mock_tts = MagicMock()
        queue = StreamingAudioQueue(audio_player=mock_player, tts_engine=mock_tts)

        queue.start_new_turn(turn_id=1)

        chunk0_audio = SynthesizedAudio(
            samples=np.zeros(1600, dtype=np.float32),
            sample_rate=16000,
            duration_seconds=0.1,
            text="First sentence.",
            voice_name="test",
        )
        chunk1_audio = SynthesizedAudio(
            samples=np.zeros(1600, dtype=np.float32),
            sample_rate=16000,
            duration_seconds=0.1,
            text="Second sentence.",
            voice_name="test",
        )

        item0 = QueuedSentence(turn_id=1, chunk_index=0, text="First sentence.")
        item1 = QueuedSentence(turn_id=1, chunk_index=1, text="Second sentence.")

        # Deliver synthesized audio for chunk 1 FIRST
        queue._on_sentence_synthesized(item1, chunk1_audio)

        # In sequential playback: _play_next_audio_chunk checks _next_playback_index (0)
        # Since chunk 0 is missing, it should NOT play chunk 1 yet!
        self.assertFalse(queue._is_playing_chunk)
        self.assertEqual(queue._next_playback_index, 0)
        mock_player.play.assert_not_called()

        # Now deliver chunk 0
        queue._on_sentence_synthesized(item0, chunk0_audio)

        # Now chunk 0 must be playing
        self.assertTrue(queue._is_playing_chunk)
        self.assertEqual(queue._next_playback_index, 1)
        mock_player.play.assert_called_once()
        self.assertEqual(queue._current_playing_item.chunk_index, 0)

        # Mark chunk 0 finished
        queue._on_player_chunk_finished()

        # Now chunk 1 should be playing
        self.assertEqual(queue._next_playback_index, 2)
        self.assertEqual(queue._current_playing_item.chunk_index, 1)
        self.assertEqual(mock_player.play.call_count, 2)


if __name__ == "__main__":
    unittest.main()
