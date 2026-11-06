"""Phase 8 Automated Test Suite: Real-Time Voice Activity Visualization.

Tests all requirements of Phase 8:
8.1 Required Voice States:
    - Display all 11 required voice states:
      Sleeping, Wake-word detected, Listening, User speaking, Processing,
      Generating response, Speaking, Interrupted, Muted, Microphone unavailable, Error.
    - Status indicator dot color, labels, and title strings match Apple HIG design.
8.2 Live Audio Activity Indicator (Microphone Activity Visualization):
    - Responds to microphone input.
    - Reflects speech intensity proportionally.
    - Remains stable and flat at 5px resting baseline during silence (level <= 0.02).
    - Avoids random oscillations during silence.
8.3 Assistant Speaking Playback Visualization:
    - Distinct speaking animation and Apple Purple/Indigo styling.
    - Reflects actual audio playback activity from AudioPlayer.
    - Immediately halts animation when playback ends or stops.
8.4 Mute Indicator and Audio Suppression:
    - Shows clearly visible mute state with Apple Red indicator.
    - Prevents microphone input from triggering conversations.
    - Completely distinct from Sleep Mode (wake-word standby vs suppressed mic).
8.5 Interruption Visualization:
    - Immediately stops speaking playback animation.
    - Shows visual indication that assistant detected interruption ("Interrupted", amber dot).
    - Clean transition into listening or processing.
8.6 Visual Design and Telemetry Synchronization:
    - StatusHUD and PetWindow reflect voice state accurately.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import numpy as np
from PySide6.QtCore import QCoreApplication, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from app.core.signals import signals
from app.desktop.status_hud import StatusHUD
from app.desktop.voice_window import AudioWaveformWidget, StatusIndicatorDot, VoicePortalWidget, VoiceWindow
from app.settings.config_manager import ConfigManager
from app.voice.conversation_state import ConversationState, VoiceActivationMode
from app.voice.microphone_manager import MicrophoneManager
from app.voice.voice_conversation_controller import VoiceConversationController
from app.voice.voice_service import VoiceMode, VoiceService


class TestPhase8VoiceVisualization(unittest.TestCase):
    """Test suite for Phase 8 Real-Time Voice Activity Visualization."""

    @classmethod
    def setUpClass(cls) -> None:
        if QApplication.instance() is None:
            cls.app = QApplication([])
        else:
            cls.app = QApplication.instance()

    def setUp(self) -> None:
        self.mock_cfg = MagicMock(spec=ConfigManager)
        self.mock_cfg.get.side_effect = lambda key, default=None: "Bond" if "name" in key else default

        # Mock VoiceService
        self.mock_voice_service = MagicMock(spec=VoiceService)
        self.mock_voice_service.speech_detected = MagicMock()
        self.mock_voice_service.transcription_started = MagicMock()
        self.mock_voice_service.speaking_started = MagicMock()
        self.mock_voice_service.speaking_finished = MagicMock()
        self.mock_voice_service.audio_level = MagicMock()
        self.mock_voice_service.audio_player = MagicMock()
        self.mock_voice_service.conversation_controller = MagicMock()

        self.window = VoiceWindow(
            config_manager=self.mock_cfg,
            voice_service=self.mock_voice_service,
        )

    def tearDown(self) -> None:
        if hasattr(self, "window") and self.window:
            self.window.close()
            self.window.deleteLater()
        if QApplication.instance():
            QApplication.processEvents()

    # ─────────────────────────────────────────────────────────────────────────
    # 8.1 Required Voice States
    # ─────────────────────────────────────────────────────────────────────────

    def test_all_11_conversation_state_enum_members_exist(self) -> None:
        """Verify all 11 required voice states exist in ConversationState enum."""
        required = [
            "sleeping",
            "wake_word_detected",
            "listening",
            "user_speaking",
            "processing",
            "generating_response",
            "speaking",
            "interrupted",
            "muted",
            "microphone_unavailable",
            "error",
        ]
        for name in required:
            st = ConversationState(name)
            self.assertIsNotNone(st, f"State '{name}' not found in ConversationState enum")

    def test_voice_window_displays_sleeping_state(self) -> None:
        """Verify Sleeping state display properties."""
        self.window.set_state("sleeping")
        self.assertEqual(self.window.status_label.text(), "Asleep")
        self.assertIn("Say wake word", self.window.hint_label.text())
        self.assertIn("Asleep", self.window.title_label.text())
        self.assertEqual(self.window.status_dot._color, QColor(142, 142, 147))  # Apple System Gray
        self.assertEqual(self.window.waveform._level, 0.0)

    def test_voice_window_displays_wake_word_detected_state(self) -> None:
        """Verify Wake-word detected state display properties."""
        self.window.set_state("wake_word_detected")
        self.assertEqual(self.window.status_label.text(), "Wake Word Detected")
        self.assertIn("command", self.window.hint_label.text().lower())
        self.assertEqual(self.window.status_dot._color, QColor(164, 198, 57))  # Lime/Yellow-Green

    def test_voice_window_displays_listening_state(self) -> None:
        """Verify Listening state display properties."""
        self.window.set_state("listening")
        self.assertEqual(self.window.status_label.text(), "I'm Listening...")
        self.assertIn("microphone", self.window.hint_label.text().lower())
        self.assertEqual(self.window.status_dot._color, QColor(52, 199, 89))  # Apple Green

    def test_voice_window_displays_user_speaking_state(self) -> None:
        """Verify User Speaking state display properties."""
        self.window.set_state("user_speaking")
        self.assertEqual(self.window.status_label.text(), "User Speaking")
        self.assertIn("Capturing", self.window.hint_label.text())
        self.assertEqual(self.window.status_dot._color, QColor(0, 229, 255))  # Electric Cyan

    def test_voice_window_displays_processing_state(self) -> None:
        """Verify Processing state display properties."""
        self.window.set_state("processing")
        self.assertEqual(self.window.status_label.text(), "Processing...")
        self.assertIn("Analyzing", self.window.hint_label.text())
        self.assertEqual(self.window.status_dot._color, QColor(10, 132, 255))  # Apple Blue
        self.assertEqual(self.window.waveform._level, 0.0)

    def test_voice_window_displays_generating_response_state(self) -> None:
        """Verify Generating response state display properties."""
        self.window.set_state("generating_response")
        self.assertEqual(self.window.status_label.text(), "Generating Response...")
        self.assertIn("Formulating", self.window.hint_label.text())
        self.assertEqual(self.window.status_dot._color, QColor(255, 159, 10))  # Apple Orange
        self.assertEqual(self.window.waveform._level, 0.0)

    def test_voice_window_displays_speaking_state(self) -> None:
        """Verify Speaking state display properties."""
        self.window.set_state("speaking")
        self.assertEqual(self.window.status_label.text(), "Speaking...")
        self.assertIn("responding", self.window.hint_label.text())
        self.assertEqual(self.window.status_dot._color, QColor(191, 90, 242))  # Apple Purple
        self.assertEqual(self.window.waveform.mode, "speaking")

    def test_voice_window_displays_interrupted_state(self) -> None:
        """Verify Interrupted state display properties."""
        self.window.set_state("interrupted")
        self.assertEqual(self.window.status_label.text(), "Interrupted")
        self.assertIn("Stopping playback", self.window.hint_label.text())
        self.assertEqual(self.window.status_dot._color, QColor(255, 149, 0))  # Apple Amber
        self.assertEqual(self.window.waveform._level, 0.0)

    def test_voice_window_displays_muted_state(self) -> None:
        """Verify Muted state display properties."""
        self.window.set_state("muted")
        self.assertEqual(self.window.status_label.text(), "Microphone Muted")
        self.assertIn("Tap microphone", self.window.hint_label.text())
        self.assertEqual(self.window.status_dot._color, QColor(255, 69, 58))  # Apple Red
        self.assertEqual(self.window.waveform._level, 0.0)

    def test_voice_window_displays_microphone_unavailable_state(self) -> None:
        """Verify Microphone unavailable state display properties."""
        self.window.set_state("microphone_unavailable")
        self.assertEqual(self.window.status_label.text(), "Microphone Unavailable")
        self.assertIn("hardware", self.window.hint_label.text().lower())
        self.assertEqual(self.window.status_dot._color, QColor(255, 59, 48))  # Warning Red
        self.assertEqual(self.window.waveform._level, 0.0)

    def test_voice_window_displays_error_state(self) -> None:
        """Verify Error state display properties."""
        self.window.set_state("error")
        self.assertEqual(self.window.status_label.text(), "Voice Error")
        self.assertIn("issue occurred", self.window.hint_label.text().lower())
        self.assertEqual(self.window.status_dot._color, QColor(215, 0, 21))  # Deep Red
        self.assertEqual(self.window.waveform._level, 0.0)

    def test_backward_compatible_state_aliases(self) -> None:
        """Verify aliases map properly to their corresponding primary state."""
        self.window.set_state("thinking")
        self.assertEqual(self.window.status_label.text(), "Generating Response...")

        self.window.set_state("transcribing")
        self.assertEqual(self.window.status_label.text(), "Processing...")

        self.window.set_state("mic_unavailable")
        self.assertEqual(self.window.status_label.text(), "Microphone Unavailable")

    # ─────────────────────────────────────────────────────────────────────────
    # 8.2 Live Audio Activity Indicator (Waveform & Silence Stability)
    # ─────────────────────────────────────────────────────────────────────────

    def test_waveform_remains_flat_and_stable_during_silence(self) -> None:
        """Verify waveform remains completely stable at 5px resting height during silence (8.2)."""
        waveform = self.window.waveform
        waveform.set_level(0.0)
        self.assertEqual(waveform._level, 0.0)

        # Level below silence threshold (0.02)
        waveform.set_level(0.01)
        self.assertEqual(waveform._level, 0.0, "Levels below silence threshold must clamp to 0.0")

        # In resting state, _anim_phase does not increment during silence
        waveform._on_tick()
        self.assertEqual(waveform._anim_phase, 0.0, "Animation phase must remain 0 during silence")

    def test_waveform_scales_proportionally_with_speech_intensity(self) -> None:
        """Verify waveform reflects active speech intensity when speech occurs (8.2)."""
        waveform = self.window.waveform
        waveform.set_level(0.5)
        self.assertGreaterEqual(waveform._level, 0.5)

        waveform._on_tick()
        self.assertGreater(waveform._anim_phase, 0.0, "Animation phase advances when speech is active")

    def test_mic_manager_mute_suppresses_level_and_frames(self) -> None:
        """Verify MicrophoneManager emits 0.0 and drops frames when muted (8.2 & 8.4)."""
        mic = MicrophoneManager()
        emitted_levels = []
        mic.audio_level.connect(emitted_levels.append)

        # Normal frame processing
        test_frame = np.ones((512, 1), dtype=np.float32) * 0.1
        mic._is_recording = True
        mic._audio_callback(test_frame, 512, None, None)
        self.assertTrue(len(emitted_levels) > 0)
        self.assertGreater(emitted_levels[-1], 0.0)

        # Mute microphone
        mic.set_muted(True)
        self.assertTrue(mic.is_muted)
        emitted_levels.clear()

        # Audio callback while muted
        mic._audio_callback(test_frame, 512, None, None)
        # Verify any emitted level during mute is 0.0
        for lvl in emitted_levels:
            self.assertEqual(lvl, 0.0)

    # ─────────────────────────────────────────────────────────────────────────
    # 8.3 Assistant Speaking Playback Visualization
    # ─────────────────────────────────────────────────────────────────────────

    def test_assistant_speaking_mode_and_amplitude_updates(self) -> None:
        """Verify speaking mode uses purple palette and reflects actual AudioPlayer amplitude (8.3)."""
        self.window.set_state("speaking")
        self.assertEqual(self.window.waveform.mode, "speaking")

        # Simulate real-time audio playback amplitude updates
        self.window._on_playback_amplitude(0.75)
        self.assertAlmostEqual(self.window.waveform._level, 0.75, places=2)
        self.assertAlmostEqual(self.window.portal._audio_level, 0.75, places=2)

    def test_speaking_finishing_immediately_halts_playback_animation(self) -> None:
        """Verify speaking animation immediately stops when playback completes (8.3)."""
        self.window.set_state("speaking")
        self.window._on_playback_amplitude(0.6)
        self.assertGreater(self.window.waveform._level, 0.0)

        # Playback finishes
        self.window._on_speaking_finished()
        self.assertEqual(self.window.waveform._level, 0.0, "Waveform level must reset to 0.0 when playback finishes")
        self.assertEqual(self.window.portal._audio_level, 0.0)
        self.assertEqual(self.window._current_state, "listening")

    # ─────────────────────────────────────────────────────────────────────────
    # 8.4 Mute Indicator and Distinct from Sleep Mode
    # ─────────────────────────────────────────────────────────────────────────

    def test_mute_toggle_visuals_and_service_notification(self) -> None:
        """Verify toggle mute displays Apple Red dot and calls voice_service.set_muted (8.4)."""
        self.assertFalse(self.window._is_muted)

        # Click Mute
        self.window._toggle_mute()
        self.assertTrue(self.window._is_muted)
        self.assertEqual(self.window.status_label.text(), "Microphone Muted")
        self.assertEqual(self.window.status_dot._color, QColor(255, 69, 58))  # Apple Red
        self.mock_voice_service.set_muted.assert_called_with(True)

        # Click Unmute
        self.window._toggle_mute()
        self.assertFalse(self.window._is_muted)
        self.assertEqual(self.window.status_label.text(), "I'm Listening...")
        self.assertEqual(self.window.status_dot._color, QColor(52, 199, 89))  # Apple Green
        self.mock_voice_service.set_muted.assert_called_with(False)

    def test_mute_is_functionally_and_visually_distinct_from_sleep(self) -> None:
        """Verify mute is clearly distinct from sleep mode in title, text, dot color, and behavior (8.4)."""
        # Sleep Mode
        self.window.set_state("sleeping")
        sleep_text = self.window.status_label.text()
        sleep_color = self.window.status_dot._color

        # Mute Mode
        self.window.set_state("muted")
        mute_text = self.window.status_label.text()
        mute_color = self.window.status_dot._color

        self.assertNotEqual(sleep_text, mute_text)
        self.assertEqual(sleep_text, "Asleep")
        self.assertEqual(mute_text, "Microphone Muted")

        self.assertNotEqual(sleep_color, mute_color)
        self.assertEqual(sleep_color, QColor(142, 142, 147))  # Apple Gray
        self.assertEqual(mute_color, QColor(255, 69, 58))    # Apple Red

    def test_voice_controller_drops_frames_when_muted(self) -> None:
        """Verify VoiceConversationController suppresses mic frames when muted (8.4)."""
        mock_player = MagicMock()
        mock_player.is_playing = False
        mock_player.is_in_cooldown.return_value = False

        ctrl = VoiceConversationController(
            mic_manager=MagicMock(),
            vad_engine=MagicMock(),
            whisper_engine=MagicMock(),
            audio_player=mock_player,
            tts_engine=MagicMock(),
        )
        ctrl.echo_canceller = MagicMock()
        ctrl.echo_canceller.is_playing = False
        ctrl.echo_canceller.is_in_cooldown.return_value = False
        ctrl.vad_engine.process_frame = MagicMock()

        chunk = np.ones(512, dtype=np.float32)
        ctrl._state = ConversationState.LISTENING

        # Not muted -> processes frame
        ctrl.process_mic_frame(chunk)
        ctrl.vad_engine.process_frame.assert_called_once_with(chunk)

        # Muted -> dropped
        ctrl.vad_engine.process_frame.reset_mock()
        ctrl.set_muted(True)
        self.assertTrue(ctrl._is_muted)
        self.assertEqual(ctrl.state, ConversationState.MUTED)
        ctrl.process_mic_frame(chunk)
        ctrl.vad_engine.process_frame.assert_not_called()

    # ─────────────────────────────────────────────────────────────────────────
    # 8.5 Interruption Visualization
    # ─────────────────────────────────────────────────────────────────────────

    def test_interruption_detection_halts_playback_animation_and_shows_interrupted(self) -> None:
        """Verify interruption detection triggers 'interrupted' state and stops playback animation (8.5)."""
        mock_player = MagicMock()
        mock_player.is_playing = True
        mock_player.stop = MagicMock()

        mock_queue = MagicMock()
        mock_queue.stop_and_capture_interruption = MagicMock(return_value=None)

        ctrl = VoiceConversationController(
            mic_manager=MagicMock(),
            vad_engine=MagicMock(),
            whisper_engine=MagicMock(),
            audio_player=mock_player,
            tts_engine=MagicMock(),
        )
        ctrl.audio_queue = mock_queue

        states_captured = []
        signals.voice_state_changed.connect(states_captured.append)

        # Set assistant speaking
        ctrl._state = ConversationState.SPEAKING
        self.window.set_state("speaking")
        self.window._on_playback_amplitude(0.8)
        self.assertGreater(self.window.waveform._level, 0.0)

        # User interrupts with barge-in speech
        interruption_chunk = np.ones(1600, dtype=np.float32) * 0.2
        ctrl._on_interruption_detected(turn_id=1, speech_samples=interruption_chunk)

        # Verify stop and capture occurred
        mock_queue.stop_and_capture_interruption.assert_called_once()
        self.assertIn("interrupted", states_captured)

        # Verify voice window handled interrupted state
        self.window.set_state("interrupted")
        self.assertEqual(self.window.status_label.text(), "Interrupted")
        self.assertEqual(self.window.status_dot._color, QColor(255, 149, 0))  # Amber
        self.assertEqual(self.window.waveform._level, 0.0, "Playback animation must stop immediately on interruption")

        # Smooth transition to user_speaking
        self.window.set_state("user_speaking")
        self.assertEqual(self.window.status_label.text(), "User Speaking")
        self.assertEqual(self.window.status_dot._color, QColor(0, 229, 255))

    # ─────────────────────────────────────────────────────────────────────────
    # 8.6 StatusHUD Subsystem Telemetry Synchronization
    # ─────────────────────────────────────────────────────────────────────────

    def test_status_hud_telemetry_updates_on_voice_state_changed(self) -> None:
        """Verify StatusHUD telemetry displays updated voice state (8.6)."""
        hud = StatusHUD()
        signals.voice_state_changed.emit("speaking")
        self.assertIn("TRANSMITTING", hud.label_readout.text())

        signals.voice_state_changed.emit("interrupted")
        self.assertIn("INTERRUPTED", hud.label_readout.text())

        signals.voice_state_changed.emit("muted")
        self.assertIn("MUTED", hud.label_readout.text())

        signals.voice_state_changed.emit("sleeping")
        self.assertIn("STANDBY", hud.label_readout.text())

        hud.close()


if __name__ == "__main__":
    unittest.main()
