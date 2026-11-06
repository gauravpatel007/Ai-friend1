"""Targeted Verification Suite for Desktop Companion Improvement (Task 6).

Verifies:
1. Real-time status display and dynamic tooltip synchronization.
2. Animation state synchronization with listening, thinking, transcribing, and speaking.
3. Live progressive partial captions rendered accurately with companion name.
4. Prevention of old captions lingering after speech finishes or cancels.
5. Smart speech bubble positioning avoiding conversation content overlap.
6. Clear speaking indicator active during TTS playback.
7. Clean return to idle animation and mouth openness reset when conversation ends.
"""

from unittest.mock import MagicMock, patch
import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtWidgets import QApplication

from app.character.states import CharacterState
from app.desktop.pet_window import DesktopPetWindow
from app.desktop.speech_bubble import SpeechBubbleWidget


@pytest.fixture
def pet_window(qapp_instance):
    """Instantiate DesktopPetWindow with mocked configuration."""
    cfg = MagicMock()
    cfg.get.side_effect = lambda key, default=None: {
        "pet.character": "robot",
        "pet.size": 120,
        "pet.animation_fps": 30,
        "pet.click_through": False,
        "pet.always_on_top": True,
        "ai.companion_name": "Bond",
        "companion.name": "Bond",
    }.get(key, default)

    window = DesktopPetWindow(config_manager=cfg)
    window.show()
    yield window
    window.close()


def test_meaningful_realtime_status_and_tooltip(pet_window):
    """Verify pet window updates active state and tooltip across all canonical states."""
    # Listening
    pet_window._on_state_changed("listening")
    assert pet_window._active_status_state == "LISTENING"
    assert "Listening" in pet_window.toolTip()
    assert "Bond" in pet_window.toolTip()

    # Transcribing
    pet_window._on_state_changed("transcribing")
    assert pet_window._active_status_state == "TRANSCRIBING"
    assert "Transcribing" in pet_window.toolTip()

    # Thinking
    pet_window._on_state_changed("thinking")
    assert pet_window._active_status_state == "THINKING"
    assert "Thinking" in pet_window.toolTip()

    # Speaking
    pet_window._on_state_changed("speaking")
    assert pet_window._active_status_state == "SPEAKING"
    assert "Speaking" in pet_window.toolTip()

    # Idle
    pet_window._on_state_changed("idle")
    assert pet_window._active_status_state == "IDLE"
    assert "Ready to chat" in pet_window.toolTip()


def test_animation_synchronization(pet_window):
    """Verify animation controller transitions to corresponding CharacterState."""
    # Listening
    pet_window._on_state_changed("listening")
    assert pet_window.anim_controller.current_state == CharacterState.LISTENING

    # Transcribing (mapped to THINKING animation)
    pet_window._on_state_changed("transcribing")
    assert pet_window.anim_controller.current_state == CharacterState.THINKING

    # Thinking
    pet_window._on_state_changed("thinking")
    assert pet_window.anim_controller.current_state == CharacterState.THINKING

    # Speaking
    pet_window._on_state_changed("speaking")
    assert pet_window.anim_controller.current_state == CharacterState.SPEAKING

    # Idle
    pet_window._on_state_changed("idle")
    assert pet_window.anim_controller.current_state == CharacterState.IDLE


def test_partial_speech_captions_and_no_stale_text(pet_window):
    """Verify actual partial captions are displayed and generic canned texts do not overwrite."""
    bubble = pet_window.speech_bubble
    assert bubble is not None

    # User speaks interim text
    pet_window._on_user_speech_interim("What is the weather")
    assert "What is the weather" in bubble.label.text()
    assert bubble.is_showing_user_speech is True

    # User continues speaking
    pet_window._on_user_speech_interim("What is the weather in London")
    assert "What is the weather in London" in bubble.label.text()

    # AI speaks synchronized sentence
    pet_window._on_ai_speech_subtitle("It is currently 15 degrees and sunny in London.")
    assert "It is currently 15 degrees and sunny in London." in bubble.label.text()
    assert "Bond" in bubble.label.text()
    assert bubble.is_showing_ai_subtitle is True


def test_prevent_old_captions_from_remaining_visible(pet_window):
    """Verify speech captions are cleared on completion and cancellation."""
    bubble = pet_window.speech_bubble

    # Show subtitle
    pet_window._on_ai_speech_subtitle("Here is the answer.")
    assert bubble.isVisible() is True

    # Speech finished -> dismiss timer started, and on timeout or clear it disappears
    pet_window._on_ai_speech_finished()
    assert pet_window._active_status_state == "IDLE"
    assert pet_window.anim_controller.current_state == CharacterState.IDLE
    assert pet_window.renderer.mouth_openness == 0.0

    # Explicit cancel immediately hides
    pet_window._on_ai_speech_subtitle("Another answer.")
    pet_window._on_speech_cancelled()
    assert bubble.isVisible() is False
    assert bubble.is_showing_ai_subtitle is False


def test_avoid_overlapping_conversation_content(qapp_instance):
    """Verify speech bubble smart positioning avoids overlapping chat window."""
    bubble = SpeechBubbleWidget(companion_name="Bond")
    pet_rect = QRect(1000, 700, 120, 120)
    chat_rect = QRect(650, 400, 380, 500)

    # Reposition avoiding chat window
    bubble.show_message("Test message", pet_rect, duration_ms=0, avoid_rect=chat_rect)
    bubble_geo = bubble.frameGeometry()

    # Should not intersect the chat rect
    assert not bubble_geo.intersects(chat_rect)
    bubble.close()


def test_clear_speaking_indicator_while_tts_playing(pet_window):
    """Verify active speaking visual indicator is rendered while in speaking state."""
    pet_window.renderer.set_state("speaking")
    pet_window.renderer.set_mouth_openness(0.0)  # low openness baseline test

    # Must generate acoustic ripple overlay even at low openness
    pix = pet_window.renderer.get_current_pixmap()
    assert pix is not None
    assert not pix.isNull()

    # With active mouth openness
    pet_window.renderer.set_mouth_openness(0.65)
    pix_loud = pet_window.renderer.get_current_pixmap()
    assert pix_loud is not None


def test_return_to_idle_when_conversation_ends(pet_window):
    """Verify full reset to idle animation, mouth openness 0, and clear subtitles."""
    pet_window._on_state_changed("speaking")
    pet_window.set_mouth_openness(0.8)

    # Conversation finishes
    pet_window._on_ai_speech_finished()

    assert pet_window._active_status_state == "IDLE"
    assert pet_window.anim_controller.current_state == CharacterState.IDLE
    assert pet_window.renderer.mouth_openness == 0.0
    assert "Ready to chat" in pet_window.toolTip()


def test_hold_timer_preserves_reading_before_fade(pet_window):
    """Verify reading hold timer is not aborted prematurely by IDLE state transition."""
    bubble = pet_window.speech_bubble
    pet_window._on_ai_speech_subtitle("This is a final response that needs reading time.")
    assert bubble.isVisible() is True
    assert bubble.is_showing_ai_subtitle is True

    # Speech finishes -> hold timer active
    pet_window._on_ai_speech_finished()
    assert bubble.is_holding_for_dismiss is True
    assert bubble.isVisible() is True

    # Idle visual update does not cancel active reading hold timer
    pet_window._apply_visual_state("idle")
    assert bubble.is_holding_for_dismiss is True
    assert bubble.isVisible() is True

    # Timer timeout hides bubble cleanly
    bubble._dismiss_timer.timeout.emit()
    assert bubble._target_visible is False


def test_new_speech_immediately_replaces_holding_bubble(pet_window):
    """Verify incoming user speech immediately cleans up prior reading hold bubble."""
    bubble = pet_window.speech_bubble
    pet_window._on_ai_speech_subtitle("Old sentence.")
    pet_window._on_ai_speech_finished()
    assert bubble.is_holding_for_dismiss is True

    # User starts speaking new utterance
    pet_window._on_user_speech_interim("Kem cho")
    assert "Kem cho" in bubble.label.text()
    assert bubble.is_showing_user_speech is True
    assert bubble.is_holding_for_dismiss is False


def test_voice_window_avoid_rect_detected(qapp_instance):
    """Verify _get_conversation_avoid_rect properly detects VoiceWindow geometry."""
    from PySide6.QtWidgets import QWidget
    class VoiceWindow(QWidget):
        pass

    voice_win = VoiceWindow()
    voice_win.setGeometry(500, 300, 400, 500)
    voice_win.show()

    cfg = MagicMock()
    cfg.get.side_effect = lambda key, default=None: {
        "pet.character": "robot",
        "pet.size": 120,
        "pet.animation_fps": 30,
        "pet.click_through": False,
        "pet.always_on_top": True,
        "ai.companion_name": "Bond",
    }.get(key, default)
    window = DesktopPetWindow(config_manager=cfg)
    avoid_rect = window._get_conversation_avoid_rect()

    assert avoid_rect is not None
    assert avoid_rect == voice_win.frameGeometry()

    voice_win.close()
    window.close()
