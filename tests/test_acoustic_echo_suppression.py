"""Unit tests for Acoustic Echo Suppression and Feedback Loop Prevention (Bug 5).

Verifies that:
1. Exact and partial echoes of spoken assistant responses are intercepted.
2. Phonetic variations, missing words, and fuzzy STT transcripts are rejected as echoes.
3. Legitimate user speech is preserved without false rejections.
4. VoiceConversationController discards echo turns and prevents conversational feedback loops.
"""

import time
import numpy as np
import pytest

from app.voice.conversation_state import ConversationState, VoiceActivationMode
from app.voice.echo_suppressor import AcousticEchoSuppressor, normalize_text
from app.voice.audio_player import AudioPlayer
from app.voice.microphone_manager import MicrophoneManager
from app.voice.vad_engine import VADEngine
from app.voice.voice_conversation_controller import VoiceConversationController
from app.voice.whisper_engine import TranscriptionResult, WhisperEngine


class MockWhisper(WhisperEngine):
    """Mock Whisper STT Engine for echo test harness."""

    def __init__(self, mock_text: str = "") -> None:
        super().__init__()
        self.mock_text = mock_text

    def ensure_model_loaded(self) -> bool:
        return True

    def transcribe(self, audio_data: np.ndarray, language=None, prompt=None, beam_size=1) -> TranscriptionResult:
        return TranscriptionResult(
            text=self.mock_text,
            language="en",
            language_probability=0.99,
            duration_seconds=1.0,
        )

    def transcribe_async(self, audio_data: np.ndarray, callback=None, language=None, prompt=None) -> None:
        res = self.transcribe(audio_data, language=language, prompt=prompt)
        if callback:
            callback(res)


class MockAIService:
    """Mock AI Service counting requests."""

    def __init__(self) -> None:
        self.ask_calls = []

    def ask(self, user_prompt: str, is_voice: bool = True) -> None:
        self.ask_calls.append(user_prompt)

    def cancel_generation(self) -> None:
        pass


class TestAcousticEchoSuppressor:
    """Unit tests for AcousticEchoSuppressor algorithms."""

    def test_normalize_text(self) -> None:
        assert normalize_text("Hello, World!") == "hello world"
        assert normalize_text("  What's   UP?!  ") == "what s up"
        assert normalize_text("નમસ્તે, કેમ છો?") == "નમસ્તે કેમ છો"
        assert normalize_text("नमस्ते, कैसे हैं?") == "नमस्ते कैसे हैं"

    def test_exact_substring_echo_suppressed(self) -> None:
        suppressor = AcousticEchoSuppressor()
        suppressor.record_assistant_speech("Hello! How can I help you today?")

        # Exact match
        is_echo, reason, conf = suppressor.is_echo("Hello! How can I help you today?")
        assert is_echo is True
        assert reason in ("exact_match", "substring_match", "word_overlap", "fuzzy_similarity")

        # Substring
        is_echo, reason, conf = suppressor.is_echo("How can I help you today")
        assert is_echo is True

        # Beginning fragment
        is_echo, reason, conf = suppressor.is_echo("Hello how can I help")
        assert is_echo is True

    def test_word_overlap_with_missing_words(self) -> None:
        suppressor = AcousticEchoSuppressor()
        suppressor.record_assistant_speech(
            "The weather in Ahmedabad is sunny and warm with twenty eight degrees."
        )

        # Whisper transcribes only a subset of the words due to mic clipping
        clipped_echo = "Ahmedabad sunny warm twenty eight degrees"
        is_echo, reason, conf = suppressor.is_echo(clipped_echo)
        assert is_echo is True
        assert reason in ("word_overlap", "fuzzy_similarity", "substring_match")

    def test_phonetic_typos_and_fuzzy_variations(self) -> None:
        suppressor = AcousticEchoSuppressor()
        suppressor.record_assistant_speech("Sure, let me check the weather forecast for you right now.")

        # Whisper phonetic substitution ('weather' -> 'whether')
        echo_with_typo = "sure let me check the whether forecast for you right now"
        is_echo, reason, conf = suppressor.is_echo(echo_with_typo)
        assert is_echo is True
        assert conf >= 0.65

    def test_n_gram_phrase_shingle_tail(self) -> None:
        suppressor = AcousticEchoSuppressor()
        suppressor.record_assistant_speech("I am doing great! What would you like to explore?")

        # Echo tail picked up at end of playback
        tail_echo = "what would you like to explore today"
        is_echo, reason, conf = suppressor.is_echo(tail_echo)
        assert is_echo is True

    def test_legitimate_user_speech_preserved(self) -> None:
        suppressor = AcousticEchoSuppressor()
        suppressor.record_assistant_speech("I am ready to help you with Python programming and coding.")

        # Legitimate questions should NEVER be flagged as echo
        clean_prompts = [
            "Can you write a binary search tree in Python?",
            "What is the capital of France?",
            "Tell me a joke about robots",
            "No, that's not what I asked for earlier",
            "Who created Linux?",
        ]
        for prompt in clean_prompts:
            is_echo, reason, conf = suppressor.is_echo(prompt)
            assert is_echo is False, f"False positive rejection on legitimate prompt: '{prompt}' ({reason})"

    def test_stale_history_expires(self) -> None:
        suppressor = AcousticEchoSuppressor(history_retention_sec=0.10)
        suppressor.record_assistant_speech("What is your favorite color?")
        time.sleep(0.15)

        # After retention window, user saying the same phrase is accepted
        is_echo, reason, _ = suppressor.is_echo("What is your favorite color?")
        assert is_echo is False

    def test_duplicate_user_speech_detection(self) -> None:
        suppressor = AcousticEchoSuppressor()
        suppressor.record_user_speech("Hello Buddy")

        assert suppressor.is_recent_duplicate_user("Hello Buddy", window_sec=2.0) is True
        assert suppressor.is_recent_duplicate_user("hello buddy!", window_sec=2.0) is True
        assert suppressor.is_recent_duplicate_user("Something completely different", window_sec=2.0) is False


class TestControllerEchoSuppression:
    """Integration test verifying VoiceConversationController breaks echo loops."""

    def test_controller_discards_echo_transcription(self, qtbot) -> None:
        mic = MicrophoneManager()
        vad = VADEngine()
        whisper = MockWhisper()
        player = AudioPlayer()
        ai = MockAIService()

        from app.voice.piper_engine import PiperTTSEngine
        tts = PiperTTSEngine()

        controller = VoiceConversationController(
            mic_manager=mic,
            vad_engine=vad,
            whisper_engine=whisper,
            audio_player=player,
            tts_engine=tts,
            ai_service=ai,
            activation_mode=VoiceActivationMode.CONTINUOUS,
        )
        controller._state = ConversationState.TRANSCRIBING
        controller._turn_id = 1

        # Simulate assistant having just spoken
        assistant_utterance = "I can definitely help you configure your desktop companion!"
        controller.echo_suppressor.record_assistant_speech(assistant_utterance)

        # 1. Feed echo transcription to controller
        echo_transcript = "definitely help you configure your desktop companion"
        result = TranscriptionResult(
            text=echo_transcript,
            language="en",
            language_probability=0.99,
            duration_seconds=1.0,
        )

        controller._on_transcription_completed(result, turn_id=1)

        # Verifications:
        # - AI ask() was NOT called with the echo
        assert len(ai.ask_calls) == 0
        # - Controller returned safely to LISTENING without crashing or looping
        assert controller.state == ConversationState.LISTENING

        # 2. Feed legitimate user speech
        controller._state = ConversationState.TRANSCRIBING
        controller._turn_id = 2
        clean_result = TranscriptionResult(
            text="Open the browser and show me Python documentation",
            language="en",
            language_probability=0.99,
            duration_seconds=1.0,
        )
        controller._on_transcription_completed(clean_result, turn_id=2)

        # AI ask() was called with clean user query!
        assert len(ai.ask_calls) == 1
        assert ai.ask_calls[0] == "Open the browser and show me Python documentation"

        controller.cleanup()
