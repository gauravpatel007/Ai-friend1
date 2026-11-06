"""Showcase UI Complete Verification Suite.

Validates that all UI components matching BIN/JARVIS AI Desktop Friend UI Showcase.png
initialize, render, and operate properly without errors.
"""

import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication

def run_tests():
    app = QApplication.instance() or QApplication(sys.argv)
    print("Testing Showcase UI Components...")

    # 1. Config & Theme
    from app.settings.config_manager import ConfigManager
    from app.desktop.jarvis_theme import load_jarvis_fonts
    cfg = ConfigManager()
    load_jarvis_fonts()
    print("[OK] Config & Theme applied successfully")

    # 2. Character Sprites
    from app.character.renderer import CharacterRenderer
    renderer = CharacterRenderer(character_name="robot", size=120)
    assert len(renderer._source_frames.keys()) >= 6, "Must have all 6 character states"
    for state in ("idle", "listening", "thinking", "speaking", "happy", "sleeping"):
        assert state in renderer._source_frames, f"Missing state {state}"
        frames = renderer._source_frames[state]
        assert len(frames) > 0 and not frames[0].isNull(), f"Invalid frame for state {state}"
    print(f"[OK] CharacterRenderer loaded all 6 states: {list(renderer._source_frames.keys())}")

    # 3. Speech Bubble Widget (Section 1 & 3)
    from app.desktop.speech_bubble import SpeechBubbleWidget
    bubble = SpeechBubbleWidget()
    bubble.show_message("Hey! I am your AI Friend!", bubble.geometry(), duration_ms=1000)
    assert "AI Friend" in bubble.label.text()
    bubble.close()
    print("[OK] SpeechBubbleWidget verified")

    # 4. Floating Control Bar (Section 2 - Capsule Pill Dock)
    from app.desktop.control_bar import FloatingControlBar
    bar = FloatingControlBar()
    assert hasattr(bar, "btn_chat")
    assert hasattr(bar, "btn_voice")
    assert hasattr(bar, "btn_settings")
    assert hasattr(bar, "btn_hide")
    bar.close()
    print("[OK] FloatingControlBar (Capsule Dock) verified")

    # 5. Desktop Pet Window (Section 1, 2, 8)
    from app.desktop.pet_window import DesktopPetWindow
    pet = DesktopPetWindow(config_manager=cfg)
    assert hasattr(pet, "speech_bubble")
    assert hasattr(pet, "control_bar")
    pet.close()
    print("[OK] DesktopPetWindow verified")

    # 6. Chat Window (Section 4 - Split Layout)
    from app.desktop.chat_window import FloatingChatWindow
    chat = FloatingChatWindow(config_manager=cfg)
    assert hasattr(chat, "recent_chats_list"), "Must have left sidebar recent chats"
    assert hasattr(chat, "btn_sidebar_new_chat"), "Must have + New Chat button"
    assert "Buddy" in chat.title_label.text(), "Must have Buddy in title"
    assert hasattr(chat.input_bar, "btn_attach"), "Must have attachment button in input bar"
    chat.close()
    print("[OK] FloatingChatWindow (Split Layout) verified")

    # 7. Voice Conversation UI (Section 5)
    from app.desktop.voice_window import VoiceWindow
    voice = VoiceWindow(config_manager=cfg)
    assert hasattr(voice, "portal"), "Must have center portal"
    assert hasattr(voice, "waveform"), "Must have audio waveform equalizer"
    assert hasattr(voice, "btn_mute")
    assert hasattr(voice, "btn_stop")
    assert hasattr(voice, "btn_settings")
    voice.set_state("listening")
    assert "listening" in voice.status_label.text().lower()
    voice.close()
    print("[OK] VoiceWindow (Concentric Portal & Equalizer) verified")

    # 8. Settings Dialog (Section 6 - 10 Categories & Size Presets)
    from app.desktop.settings_dialog import SettingsDialog
    settings = SettingsDialog(config_manager=cfg)
    assert settings.nav_list.count() == 10, f"Expected 10 categories, got {settings.nav_list.count()}"
    assert len(settings._size_cards) == 3, "Expected 3 size preset cards (Small, Med, Large)"
    assert hasattr(settings, "cb_memory_enabled"), "Must maintain memory toggle compatibility"
    assert hasattr(settings, "cb_auto_extract"), "Must maintain auto-extract toggle compatibility"
    assert hasattr(settings, "mem_table"), "Must maintain memory table"
    settings.close()
    print("[OK] SettingsDialog (10 Categories, Toggles & Size Presets) verified")

    # 9. Notification Toast (Section 9)
    from app.desktop.notification_toast import NotificationToast
    toast = NotificationToast(title="Buddy", message="I have organized your daily schedule!")
    assert toast.title_lbl.text() == "Buddy"
    assert "organized" in toast.msg_lbl.text()
    toast.close()
    print("[OK] NotificationToast verified")

    print("\nALL SHOWCASE UI TESTS PASSED SUCCESSFULLY! (OK)")

def test_showcase_ui_suite(qapp_instance):
    """Pytest hook to run complete showcase UI verification."""
    run_tests()


if __name__ == "__main__":
    run_tests()
