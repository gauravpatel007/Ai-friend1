"""Main Application Controller.

Central coordinator of desktop windows, system tray, background services,
and application lifecycle.
"""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING, Any, List, Optional

from PySide6.QtCore import QObject, Signal, Slot, QTimer, Qt
from PySide6.QtWidgets import QApplication

if TYPE_CHECKING:
    from app.ai.ai_service import AIService
    from app.desktop.chat_window import FloatingChatWindow
    from app.voice.voice_service import VoiceService

from app.core.lifecycle import get_lifecycle_manager, LifecycleState
from app.core.signals import signals
from app.core.single_instance import SingleInstanceGuard
from app.desktop.pet_window import DesktopPetWindow
from app.desktop.tray_icon import SystemTrayManager
from app.settings.config_manager import ConfigManager
from app.utils.logger import get_logger
from app.voice.conversation_state import ConversationState

logger = get_logger(__name__)


class ApplicationController(QObject):
    """Central controller coordinating the AI Desktop Friend application."""

    # Controller lifecycle signals
    initialized = Signal()
    shutting_down = Signal()

    def __init__(
        self,
        app: QApplication,
        config_manager: Optional[ConfigManager] = None,
        single_instance_guard: Optional[SingleInstanceGuard] = None,
        conv_repo: Optional[Any] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.app = app
        self.config_manager = config_manager or ConfigManager(parent=self)
        self.guard = single_instance_guard

        self.tray_manager: Optional[SystemTrayManager] = None
        self.pet_window: Optional[DesktopPetWindow] = None
        self.status_hud: Optional[Any] = None
        self.chat_window: Optional[Any] = None
        self.ai_service: Optional[AIService] = None
        self.voice_service: Optional[VoiceService] = None
        self.conv_repo: Optional[Any] = conv_repo
        self.current_assistant_msg_id: Optional[int] = None
        self._settings_dialog: Optional[Any] = None
        self._background_services: List[QObject] = []
        self._is_shutting_down = False
        self._is_emergency_exiting = False
        self._window_hwnds: List[int] = []
        # Requirement 1: Bond must ALWAYS start in SLEEP MODE
        self._is_sleeping = True
        from app.core.buddy_state_manager import get_buddy_state_manager
        self.buddy_state_manager = get_buddy_state_manager()
        self.buddy_state_manager.enter_sleep(reason="controller_init")
        self._api_server: Optional[Any] = None
        self._api_server_thread: Optional[threading.Thread] = None

        # Phase 11 subsystems
        self.perf_monitor: Optional[Any] = None
        self.perf_profiles: Optional[Any] = None
        self.windows_integration: Optional[Any] = None
        self.error_recovery: Optional[Any] = None

    @property
    def is_sleeping(self) -> bool:
        """Return True if Bond is currently in strict sleep mode."""
        return self._is_sleeping or (hasattr(self, "buddy_state_manager") and self.buddy_state_manager.is_sleeping)

    def initialize(self) -> bool:
        """Initialize all components, desktop character, and system tray."""
        logger.info("Initializing ApplicationController...")

        try:
            # 1. Connect core lifecycle signals and register with centralized LifecycleManager
            lifecycle = get_lifecycle_manager()
            lifecycle.register_emergency_exit_handler(self.emergency_fast_exit)
            lifecycle.register_shutdown_hook(self.shutdown, priority=200, name="ApplicationController")

            signals.shutdown_requested.connect(lambda: lifecycle.request_shutdown(source="signals.shutdown_requested"))
            if self.guard:
                self.guard.instance_activated.connect(signals.activate_requested.emit)

            # 2. Initialize Desktop Pet Window
            logger.info("Initializing Desktop Pet...")
            self.pet_window = DesktopPetWindow(self.config_manager)
            self.pet_window.show_pet()
            try:
                self._window_hwnds.append(int(self.pet_window.winId()))
            except Exception:
                pass

            # 2.1. Initialize Modern Chat Window immediately so both companion windows render on display in <100ms
            logger.info("Initializing Modern Chat Window...")
            from app.desktop.modern_chat_window import ModernChatWindow
            self.chat_window = ModernChatWindow(
                config_manager=self.config_manager,
                parent=None,
            )
            self.chat_window.position_near_pet(self.pet_window.frameGeometry())
            self.chat_window.show_chat()
            self.pet_window.enforce_topmost()
            try:
                self._window_hwnds.append(int(self.chat_window.winId()))
            except Exception:
                pass
            QApplication.processEvents()

            # 2.5. Status HUD (optional, hidden by default to match Showcase design)
            if self.config_manager.get("general.show_hud", False):
                logger.info("Initializing Status HUD...")
                from app.desktop.status_hud import StatusHUD
                self.status_hud = StatusHUD()
                self.status_hud.reposition_near_pet(self.pet_window.frameGeometry())
                self.status_hud.show()
                try:
                    self._window_hwnds.append(int(self.status_hud.winId()))
                except Exception:
                    pass

            # 3. Initialize System Tray
            logger.info("Initializing System Tray...")
            self.tray_manager = SystemTrayManager(self)
            tray_success = self.tray_manager.initialize()
            if not tray_success:
                logger.warning("System tray initialization was not supported or failed.")

            # 4. Initialize Local AI Service (Phase 4)
            logger.info("Initializing Local AI Engine...")
            from app.ai.ai_service import AIService
            self.ai_service = AIService(self.config_manager, parent=self)
            self.register_background_service(self.ai_service)

            if self.conv_repo is None:
                from app.memory.conversation_repository import ConversationRepository
                self.conv_repo = ConversationRepository()
            self.ai_service.conv_repo = self.conv_repo

            # 5. Initialize Voice & Speech Recognition Engine (Phase 6)
            logger.info("Initializing Voice & Speech Recognition Engine...")
            from app.voice.voice_service import VoiceService
            self.voice_service = VoiceService(parent=self)
            self.voice_service.attach_ai_service(self.ai_service)
            if hasattr(self.voice_service, "conversation_controller") and self.voice_service.conversation_controller:
                self.voice_service.conversation_controller.enable_direct_ai_dispatch = False
            if hasattr(self.voice_service, "command_dispatcher") and self.voice_service.command_dispatcher:
                self.voice_service.command_dispatcher.conv_repo = self.conv_repo
                self.voice_service.command_dispatcher.config_manager = self.config_manager
            self.register_background_service(self.voice_service)
            self.voice_service.transcription_ready.connect(self._on_voice_transcription_ready)
            if hasattr(self, "buddy_state_manager") and hasattr(self.voice_service, "audio_player"):
                self.buddy_state_manager.set_audio_player(self.voice_service.audio_player)

            # Requirement 1: Bond must ALWAYS start in SLEEP MODE when the application launches
            # Keep lightweight wake-word detector active on startup (if enabled)
            wake_enabled = self.config_manager.get("voice.wake_word_enabled", True) and self.config_manager.get("voice.enabled", True)
            if wake_enabled:
                self.voice_service.set_mode("wake_word")
                if hasattr(self.voice_service, "conversation_controller") and self.voice_service.conversation_controller:
                    self.voice_service.conversation_controller._transition_to(ConversationState.SLEEPING)
                signals.voice_state_changed.emit("wake_word")
                logger.info("[CONTROLLER] Bond initialized in STRICT SLEEP MODE with wake-word standby enabled.")
            else:
                self.voice_service.set_mode("off")
                signals.voice_state_changed.emit("off")
                logger.info("[CONTROLLER] Bond initialized in STRICT SLEEP MODE with voice disabled.")

            # Ensure character visual state and app mode reflect SLEEP MODE on startup
            signals.character_state_changed.emit("sleeping")
            signals.app_mode_changed.emit("sleeping")

            # 5.2. Initialize Performance Monitoring & Profiles (Phase 11.1 & 11.3)
            logger.info("Initializing Performance Monitor & Profile Manager...")
            from app.core.performance_monitor import get_performance_monitor
            from app.core.performance_profiles import PerformanceProfileManager
            self.perf_monitor = get_performance_monitor()
            self.perf_monitor.start_monitoring(interval_ms=10000)
            self.perf_profiles = PerformanceProfileManager(self.config_manager, parent=self)

            # 5.3. Initialize Windows Integration & Error Recovery Coordinator (Phase 11.6 & 11.7)
            logger.info("Initializing Windows Integration & Error Recovery Coordinator...")
            from app.core.windows_integration import WindowsIntegration
            from app.core.error_recovery import ErrorRecoveryCoordinator
            self.windows_integration = WindowsIntegration(parent=self, config_manager=self.config_manager)
            self.error_recovery = ErrorRecoveryCoordinator(parent=self)

            # Track and connect signal connections
            self._signal_connections = [
                signals.activate_requested.connect(self._on_activate_requested),
                signals.ai_response_complete.connect(self._on_ai_response_tts),
                signals.ai_cancel_requested.connect(self.voice_service.stop_speaking),
                signals.emergency_stop_requested.connect(self._on_emergency_stop),
                signals.wake_word_detected.connect(self._on_wake_word_detected),
                signals.open_chat_requested.connect(self._on_open_chat),
                signals.close_chat_requested.connect(lambda: self.chat_window.hide() if self.chat_window else None),
                signals.minimize_chat_requested.connect(lambda: self.chat_window.showMinimized() if self.chat_window else None),
                signals.maximize_chat_requested.connect(lambda: self.chat_window.toggle_maximize() if self.chat_window else None),
                signals.drag_chat_requested.connect(lambda: self.chat_window.start_drag() if self.chat_window else None),
                signals.move_chat_delta.connect(lambda dx, dy: self.chat_window.move_delta(dx, dy) if self.chat_window else None),
                signals.open_settings_requested.connect(self._on_open_settings),
                signals.user_emotion_detected.connect(self._on_user_emotion_detected),
                signals.sleep_requested.connect(self.enter_sleep_mode, Qt.ConnectionType.QueuedConnection),
                signals.wake_requested.connect(self.wake_up, Qt.ConnectionType.QueuedConnection),
            ]

            # Wire WebSocket streaming and UI state bridges (Bug 12)
            self._signal_connections.extend([
                signals.ai_response_chunk.connect(self._on_ai_chunk),
                signals.ai_response_complete.connect(self._on_ai_complete),
                signals.ai_error_occurred.connect(self._on_ai_error),
                signals.ai_generation_cancelled.connect(self._on_ai_cancelled),
                signals.character_state_changed.connect(self._on_char_state_changed),
                signals.voice_state_changed.connect(self._on_voice_state_changed),
                signals.user_speech_interim.connect(self._on_user_speech_interim),
                signals.ai_speech_subtitle.connect(self._on_ai_speech_subtitle),
                signals.ai_speech_finished.connect(self._on_ai_speech_finished),
                signals.memory_stored.connect(self._on_memory_stored),
                signals.model_routed.connect(self._on_model_routed),
            ])
            if self.voice_service:
                self._signal_connections.append(
                    self.voice_service.error_occurred.connect(self._on_voice_error)
                )

            # Wire Windows Integration & Error Recovery events (Phase 11.6 & 11.7)
            self._signal_connections.append(
                self.error_recovery.user_alert_requested.connect(self._on_user_alert)
            )
            if self.tray_manager:
                self._signal_connections.append(
                    self.windows_integration.taskbar_created.connect(self.tray_manager.recover_tray_icon)
                )
            self._signal_connections.extend([
                self.windows_integration.system_sleep_requested.connect(self.enter_sleep_mode),
                self.windows_integration.system_resumed.connect(self._on_system_resumed),
                self.windows_integration.display_configuration_changed.connect(self._on_display_configuration_changed),
            ])

            # Connect Voice events to character animation states & lip sync (Phase 6 & 7)
            if self.pet_window and hasattr(self.pet_window, "anim_controller"):
                self._signal_connections.extend([
                    self.voice_service.speech_detected.connect(self._on_speech_detected),
                    self.voice_service.transcription_started.connect(self._on_transcription_started),
                    self.voice_service.speaking_started.connect(self._on_speaking_started),
                    self.voice_service.speaking_finished.connect(self._on_speaking_finished),
                    self.voice_service.lip_sync_amplitude.connect(self._on_lip_sync_amplitude),
                ])

            # 5.5. Start FastAPI local server daemon in background thread
            self._start_api_server()

            # 6. Connect services to Modern Chat Window
            if self.chat_window:
                self.chat_window.ai_service = self.ai_service
                self.chat_window.voice_service = self.voice_service
                if self.pet_window:
                    self.chat_window.position_near_pet(self.pet_window.frameGeometry())
                    if self.config_manager.get("pet.always_on_top", True):
                        self.pet_window.enforce_topmost()
                    self.chat_window.show_chat()

            # Ensure windows are foreground elevated once Qt event loop begins
            QTimer.singleShot(50, self._ensure_windows_foreground)
            QTimer.singleShot(300, self._ensure_windows_foreground)
            QTimer.singleShot(1200, self._ensure_windows_foreground)

            # 6.5. Initialize Dedicated Voice Conversation Window (Showcase Section 5)
            logger.info("Initializing Voice Conversation Window...")
            from app.desktop.voice_window import VoiceWindow
            self.voice_window = VoiceWindow(
                config_manager=self.config_manager,
                voice_service=self.voice_service,
                parent=None,
            )
            self._signal_connections.extend([
                signals.open_voice_window_requested.connect(self._on_open_voice_window),
                signals.close_voice_window_requested.connect(self._on_close_voice_window),
                signals.toggle_voice_window_requested.connect(self._on_toggle_voice_window),
                signals.voice_toggle_requested.connect(
                    self._on_voice_toggle, Qt.ConnectionType.DirectConnection
                ),
            ])

            # Wire Status HUD positioning and mode updates
            if self.status_hud:
                self._signal_connections.extend([
                    signals.pet_moved.connect(
                        lambda x, y: self.status_hud.reposition_near_pet(self.pet_window.frameGeometry())
                        if (self.status_hud and self.pet_window) else None
                    ),
                    signals.pet_visibility_changed.connect(
                        lambda vis: self.status_hud.setVisible(vis) if self.status_hud else None
                    ),
                    signals.voice_state_changed.connect(self.status_hud.set_voice_mode),
                ])

            # 7. Hook app aboutToQuit
            self.app.aboutToQuit.connect(self._on_app_about_to_quit)

            logger.info("ApplicationController successfully initialized.")
            self.initialized.emit()
            return True

        except Exception as e:
            logger.critical("Fatal error during ApplicationController initialization: %s", e, exc_info=True)
            return False

    @Slot()
    def _ensure_windows_foreground(self) -> None:
        """Guarantees both the desktop pet and chat window are raised to front once event loop begins."""
        from app.utils.window_elevation import elevate_window_to_front
        if self.tray_manager:
            self.tray_manager.ensure_tray_visible()
        if self.pet_window and self.pet_window.isVisible():
            if self.config_manager.get("pet.always_on_top", True):
                self.pet_window.enforce_topmost()
                elevate_window_to_front(int(self.pet_window.winId()), keep_topmost=True)
        if self.chat_window and self.chat_window.isVisible():
            self.chat_window.show_chat()
            elevate_window_to_front(int(self.chat_window.winId()), keep_topmost=False)

    @Slot()
    def _on_activate_requested(self) -> None:
        """Brings companion pet and chat interface to the foreground when app is re-launched."""
        logger.info("Activation requested: ensuring pet and chat window are foreground active.")
        if self.pet_window:
            self.pet_window.activate_and_highlight()
        if self.chat_window:
            self.chat_window.show_chat()

    @Slot()
    def _on_speech_detected(self) -> None:
        if self.pet_window and hasattr(self.pet_window, "anim_controller"):
            from app.character.states import CharacterState
            self.pet_window.anim_controller.request_state(CharacterState.LISTENING)
        signals.character_state_changed.emit("listening")

    @Slot()
    def _on_transcription_started(self) -> None:
        if self.pet_window and hasattr(self.pet_window, "anim_controller"):
            from app.character.states import CharacterState
            self.pet_window.anim_controller.request_state(CharacterState.THINKING)
        signals.character_state_changed.emit("transcribing")

    @Slot()
    def _on_speaking_started(self) -> None:
        if self.pet_window and hasattr(self.pet_window, "anim_controller"):
            from app.character.states import CharacterState
            self.pet_window.anim_controller.request_state(CharacterState.SPEAKING)
        signals.character_state_changed.emit("speaking")

    @Slot()
    def _on_speaking_finished(self) -> None:
        if self.pet_window and hasattr(self.pet_window, "anim_controller"):
            from app.character.states import CharacterState
            self.pet_window.anim_controller.request_state(CharacterState.IDLE)
        signals.character_state_changed.emit("idle")

    @Slot(float)
    def _on_lip_sync_amplitude(self, amplitude: float) -> None:
        if self.pet_window:
            self.pet_window.set_mouth_openness(amplitude)

    @Slot()
    def _on_open_chat(self) -> None:
        """Handle request to open chat window, positioning near the pet if visible."""
        if self.chat_window:
            if self.pet_window and self.pet_window.isVisible():
                self.chat_window.position_near_pet(self.pet_window.frameGeometry())
            if hasattr(self.chat_window, "open_chat_view"):
                self.chat_window.open_chat_view()
            else:
                self.chat_window.show_chat()

    @Slot()
    def _on_open_voice_window(self) -> None:
        """Handle request to open dedicated voice window, routing to modern React Voice Portal when active."""
        from app.desktop.modern_chat_window import ModernChatWindow
        if isinstance(self.chat_window, ModernChatWindow):
            if self.pet_window and self.pet_window.isVisible():
                self.chat_window.position_near_pet(self.pet_window.frameGeometry())
            self.chat_window.open_voice_portal()
            return
        if hasattr(self, "voice_window") and self.voice_window:
            if self.pet_window and self.pet_window.isVisible():
                self.voice_window.position_near_pet(self.pet_window.frameGeometry())
            self.voice_window.show_window()
        elif hasattr(self, "chat_window") and hasattr(self.chat_window, "open_voice_portal"):
            self.chat_window.open_voice_portal()

    @Slot()
    def _on_close_voice_window(self) -> None:
        """Handle request to close dedicated voice window."""
        if hasattr(self, "voice_window") and self.voice_window:
            self.voice_window.hide_window()

    @Slot()
    def _on_toggle_voice_window(self) -> None:
        """Handle request to toggle dedicated voice window visibility."""
        from app.desktop.modern_chat_window import ModernChatWindow
        if isinstance(self.chat_window, ModernChatWindow):
            self._on_open_voice_window()
            return
        if hasattr(self, "voice_window") and self.voice_window:
            if self.voice_window.isVisible():
                self.voice_window.hide_window()
            else:
                self._on_open_voice_window()
        elif hasattr(self, "chat_window") and hasattr(self.chat_window, "open_voice_portal"):
            self.chat_window.open_voice_portal()

    @Slot(str)
    def _on_ai_response_tts(self, full_text: str) -> None:
        """Forward completed AI text response to TTS engine for spoken playback."""
        # Suppress late AI response playback if Buddy is sleeping (Phase 6)
        if self._is_sleeping or (hasattr(self, "buddy_state_manager") and self.buddy_state_manager.is_sleeping):
            logger.debug("Skipping TTS playback: Buddy is currently sleeping.")
            return

        cleaned = full_text.strip()
        if not cleaned:
            return

        if not self.voice_service or not self.voice_service.tts_enabled:
            return

        # Separate text-chat responses from voice-mode responses:
        # If the user typed this message via text chat (is_voice=False), do NOT speak it aloud.
        is_voice = getattr(self.ai_service, "is_current_generation_voice", False)
        if not is_voice:
            logger.debug("Skipping TTS playback: message originated from text chat.")
            return

        # If continuous conversation controller is active, StreamingAudioQueue handles real-time chunk synthesis.
        # Suppress duplicate full-text playback to ensure words are never repeated!
        conv_ctrl = getattr(self.voice_service, "conversation_controller", None)
        if conv_ctrl and conv_ctrl.is_enabled:
            logger.debug("Skipping full-text TTS: continuous conversation controller manages streaming playback.")
            return

        from app.voice.voice_service import VoiceMode
        if getattr(self.voice_service, "mode", None) == VoiceMode.OFF:
            return

        logger.info("Triggering single TTS spoken playback for voice response (%d chars)", len(cleaned))
        self.voice_service.speak(cleaned)

    # ─── WebSocket Streaming & Modern Chat UI Bridges (Bug 12) ──────────────

    @Slot(str)
    def _on_ai_chunk(self, chunk: str) -> None:
        """Broadcast streaming AI token chunk to modern React UI over WebSocket."""
        is_sleeping = getattr(self, "_is_sleeping", False) or (hasattr(self, "buddy_state_manager") and getattr(self.buddy_state_manager, "is_sleeping", False))
        if is_sleeping:
            return
        msg_id = getattr(self, "current_assistant_msg_id", None)
        conv_id = getattr(self, "current_conv_id", None)
        req_id = getattr(self, "current_request_id", None)
        if not msg_id or not req_id:
            from app.api.server import app as fastapi_app
            if not msg_id:
                msg_id = getattr(fastapi_app.state, "current_assistant_msg_id", None)
            if not conv_id:
                conv_id = getattr(fastapi_app.state, "current_conv_id", None)
            if not req_id:
                req_id = getattr(fastapi_app.state, "current_request_id", None)
        from app.api.websocket import ws_manager
        ws_manager.broadcast_sync("ai_chunk", {
            "chunk": chunk,
            "message_id": msg_id,
            "conversation_id": conv_id,
            "request_id": req_id,
        })

    @Slot(str)
    def _on_ai_complete(self, full_text: str) -> None:
        """Update message in SQLite repository and broadcast completion to modern React UI."""
        msg_id = getattr(self, "current_assistant_msg_id", None)
        conv_id = getattr(self, "current_conv_id", None)
        req_id = getattr(self, "current_request_id", None)
        if not msg_id or not req_id:
            from app.api.server import app as fastapi_app
            if not msg_id:
                msg_id = getattr(fastapi_app.state, "current_assistant_msg_id", None)
            if not conv_id:
                conv_id = getattr(fastapi_app.state, "current_conv_id", None)
            if not req_id:
                req_id = getattr(fastapi_app.state, "current_request_id", None)
        if msg_id and self.conv_repo:
            try:
                self.conv_repo.update_message_content(msg_id, full_text, status="completed")
            except Exception as e:
                logger.error("Failed to update completed message %s in repository: %s", msg_id, e)

        timings = {}
        if hasattr(self, "ai_service") and hasattr(self.ai_service, "get_latest_timing_metrics"):
            timings = self.ai_service.get_latest_timing_metrics()
            if not req_id:
                req_id = timings.get("request_id")

        finish_reason = timings.get("finish_reason", "stop")
        truncated = bool(timings.get("truncated", False) or finish_reason == "length")

        routing_info = None
        if hasattr(self.ai_service, "get_last_routing_decision"):
            dec = self.ai_service.get_last_routing_decision()
            if dec:
                routing_info = dec.to_dict()

        from app.api.websocket import ws_manager
        ws_manager.broadcast_sync("ai_complete", {
            "text": full_text,
            "message_id": msg_id,
            "conversation_id": conv_id,
            "request_id": req_id,
            "finish_reason": finish_reason,
            "truncated": truncated,
            "eval_count": timings.get("eval_count", 0),
            "timings": timings,
            "routing": routing_info,
        })
        is_sleeping = getattr(self, "_is_sleeping", False) or (hasattr(self, "buddy_state_manager") and getattr(self.buddy_state_manager, "is_sleeping", False))
        if not is_sleeping:
            signals.character_state_changed.emit("idle")
        self.current_assistant_msg_id = None
        self.current_conv_id = None
        self.current_request_id = None
        from app.api.server import app as fastapi_app
        fastapi_app.state.current_assistant_msg_id = None
        fastapi_app.state.current_conv_id = None
        fastapi_app.state.current_request_id = None

    @Slot(str)
    def _on_ai_error(self, error_msg: str) -> None:
        """Update message error status in repository and broadcast error event to modern React UI."""
        msg_id = getattr(self, "current_assistant_msg_id", None)
        conv_id = getattr(self, "current_conv_id", None)
        if not msg_id:
            from app.api.server import app as fastapi_app
            msg_id = getattr(fastapi_app.state, "current_assistant_msg_id", None)
            if not conv_id:
                conv_id = getattr(fastapi_app.state, "current_conv_id", None)

        if not getattr(self, "error_recovery", None):
            from app.core.error_recovery import ErrorRecoveryCoordinator
            try:
                self.error_recovery = ErrorRecoveryCoordinator(parent=self)
            except Exception:
                self.error_recovery = ErrorRecoveryCoordinator(parent=None)

        ai_svc = getattr(self, "ai_service", None)
        desc = self.error_recovery.classify_and_handle(
            error_msg,
            context={
                "model_name": getattr(getattr(ai_svc, "model_manager", None), "active_model", "llama3.2:3b"),
                "client": getattr(ai_svc, "client", None),
            },
        )
        final_message = desc.message or error_msg

        if msg_id and self.conv_repo:
            try:
                self.conv_repo.update_message_content(msg_id, final_message, status="error")
            except Exception as e:
                logger.error("Failed to update error status for message %s in repository: %s", msg_id, e)

        from app.api.websocket import ws_manager
        ws_manager.broadcast_sync("ai_error", {
            "message": final_message,
            "title": desc.title,
            "error_type": desc.error_type,
            "recovery_action": desc.recovery_action,
            "recovery_label": desc.recovery_label,
            "urgency": desc.urgency,
            "message_id": msg_id,
            "conversation_id": conv_id,
        })

        is_sleeping = getattr(self, "_is_sleeping", False) or (hasattr(self, "buddy_state_manager") and getattr(self.buddy_state_manager, "is_sleeping", False))
        if not is_sleeping:
            signals.character_state_changed.emit("error")
            signals.character_state_changed.emit("idle")
            # Auto-restore to idle after brief error alert
            QTimer.singleShot(3500, lambda: signals.character_state_changed.emit("idle"))

        self.current_assistant_msg_id = None
        self.current_conv_id = None
        from app.api.server import app as fastapi_app
        fastapi_app.state.current_assistant_msg_id = None
        fastapi_app.state.current_conv_id = None

    @Slot(str)
    def _on_voice_error(self, error_msg: str) -> None:
        """Handle voice pipeline errors, classify with ErrorRecoveryCoordinator, and notify UI/desktop."""
        if not self.error_recovery:
            from app.core.error_recovery import ErrorRecoveryCoordinator
            self.error_recovery = ErrorRecoveryCoordinator(parent=self)

        desc = self.error_recovery.classify_and_handle(
            error_msg,
            context={
                "voice_service": self.voice_service,
                "voice_controller": getattr(self.voice_service, "conversation_controller", None),
                "audio_player": getattr(self.voice_service, "audio_player", None),
            },
        )

        from app.api.websocket import ws_manager
        ws_manager.broadcast_sync("voice_error", {
            "message": desc.message,
            "title": desc.title,
            "error_type": desc.error_type,
            "recovery_action": desc.recovery_action,
            "recovery_label": desc.recovery_label,
            "urgency": desc.urgency,
        })

        is_sleeping = getattr(self, "_is_sleeping", False) or (hasattr(self, "buddy_state_manager") and getattr(self.buddy_state_manager, "is_sleeping", False))
        if not is_sleeping and desc.urgency in ("error", "warning"):
            signals.character_state_changed.emit("error")
            QTimer.singleShot(3000, lambda: signals.character_state_changed.emit("idle"))

    @Slot(str, str, str)
    def _on_user_alert(self, title: str, message: str, level: str = "warning") -> None:
        """Display desktop notification toast and system tray message for user-facing alerts."""
        if self.config_manager:
            if not self.config_manager.get("general.show_tray_notifications", True):
                return
            if title == "No Speech Heard" and not self.config_manager.get("voice.notify_on_empty_speech", False):
                return

        try:
            from app.desktop.notification_toast import show_buddy_toast
            show_buddy_toast(title, message)
        except Exception as e:
            logger.debug("Could not spawn desktop notification toast: %s", e)

        if self.tray_manager:
            try:
                self.tray_manager.show_message(title, message)
            except Exception as e:
                logger.debug("Could not show tray alert: %s", e)

    @Slot()
    def _on_ai_cancelled(self) -> None:
        """Mark cancelled message status in repository and broadcast cancellation to modern React UI."""
        msg_id = getattr(self, "current_assistant_msg_id", None)
        conv_id = getattr(self, "current_conv_id", None)
        if not msg_id:
            from app.api.server import app as fastapi_app
            msg_id = getattr(fastapi_app.state, "current_assistant_msg_id", None)
            if not conv_id:
                conv_id = getattr(fastapi_app.state, "current_conv_id", None)
        if msg_id and self.conv_repo:
            try:
                self.conv_repo.update_message_content(msg_id, "[Cancelled by user]", status="cancelled")
            except Exception as e:
                logger.debug("Failed to mark message %s cancelled: %s", msg_id, e)
        from app.api.websocket import ws_manager
        ws_manager.broadcast_sync("ai_cancelled", {"message_id": msg_id, "conversation_id": conv_id})
        is_sleeping = getattr(self, "_is_sleeping", False) or (hasattr(self, "buddy_state_manager") and getattr(self.buddy_state_manager, "is_sleeping", False))
        if not is_sleeping:
            signals.character_state_changed.emit("idle")
        self.current_assistant_msg_id = None
        self.current_conv_id = None
        from app.api.server import app as fastapi_app
        fastapi_app.state.current_assistant_msg_id = None
        fastapi_app.state.current_conv_id = None

    @Slot(str)
    def _on_char_state_changed(self, state: str) -> None:
        """Broadcast character and canonical application state changes to modern React UI over WebSocket."""
        from app.api.websocket import ws_manager
        ws_manager.broadcast_sync("char_state", {"state": state})
        canonical_map = {
            "idle": "IDLE",
            "listening": "LISTENING",
            "transcribing": "TRANSCRIBING",
            "thinking": "THINKING",
            "speaking": "SPEAKING",
            "error": "ERROR",
            "happy": "IDLE",
            "sleeping": "IDLE",
        }
        canonical_state = canonical_map.get(state.lower().strip(), "IDLE")
        ws_manager.broadcast_sync("app_state", {"state": canonical_state})

    @Slot(dict)
    def _on_model_routed(self, decision_dict: dict) -> None:
        """Broadcast intelligent automatic model routing decision to UI."""
        from app.api.websocket import ws_manager
        ws_manager.broadcast_sync("model_routed", decision_dict)

    @Slot(str)
    def _on_voice_state_changed(self, state: str) -> None:
        """Broadcast voice state transitions to modern React UI over WebSocket."""
        from app.api.websocket import ws_manager
        ws_manager.broadcast_sync("voice_state", {"state": state})

    @Slot(str)
    def _on_user_speech_interim(self, text: str) -> None:
        """Broadcast live interim speech recognition to UI."""
        from app.api.websocket import ws_manager
        ws_manager.broadcast_sync("user_speech_interim", {"text": text})

    @Slot(str)
    def _on_ai_speech_subtitle(self, subtitle: str) -> None:
        """Broadcast synchronized speech subtitles to UI and desktop pet speech bubble."""
        from app.api.websocket import ws_manager
        ws_manager.broadcast_sync("speech_subtitle", {"text": subtitle})
        if self.pet_window and hasattr(self.pet_window, "speech_bubble") and self.pet_window.speech_bubble and self.pet_window.isVisible():
            self.pet_window.speech_bubble.show_message(subtitle, self.pet_window.frameGeometry(), duration_ms=4000)

    @Slot()
    def _on_ai_speech_finished(self) -> None:
        """Broadcast completion of assistant speech playback to UI."""
        from app.api.websocket import ws_manager
        ws_manager.broadcast_sync("speech_finished", {})

    @Slot(object)
    def _on_memory_stored(self, memory_obj: object) -> None:
        """Broadcast newly stored memory to modern React UI over WebSocket."""
        mem_data = {
            "id": getattr(memory_obj, "id", ""),
            "category": getattr(memory_obj, "category", ""),
            "content": getattr(memory_obj, "content", ""),
            "created_at": getattr(memory_obj, "created_at", ""),
        }
        from app.api.websocket import ws_manager
        ws_manager.broadcast_sync("memory_stored", {"memory": mem_data})

    @Slot(str, float)
    def _on_user_emotion_detected(self, emotion: str, confidence: float) -> None:
        """Trigger happy character animation when positive emotion detected (Phase 10.9)."""
        from app.api.websocket import ws_manager
        ws_manager.broadcast_sync("user_emotion", {"emotion": emotion, "confidence": confidence})
        if emotion in ("happy", "excited") and confidence >= 0.60:
            if self.pet_window and hasattr(self.pet_window, "anim_controller"):
                from app.character.states import CharacterState
                self.pet_window.anim_controller.request_state(CharacterState.HAPPY)

    @Slot()
    def _on_voice_toggle(self) -> None:
        """Handle request to toggle voice conversation listening mode."""
        if self.voice_service:
            from app.voice.voice_service import VoiceMode
            current_mode = self.voice_service.mode
            is_off = (
                current_mode == VoiceMode.OFF
                or (hasattr(current_mode, "value") and current_mode.value == "off")
                or str(current_mode).lower().strip() in ("off", "voicemode.off")
            )
            if is_off:
                target_mode = self.config_manager.get("voice.mode", "wake_word")
                if target_mode in ("off", "", None):
                    target_mode = "wake_word"
                self.voice_service.set_mode(target_mode)
                self.config_manager.set("voice.mode", target_mode)
                signals.voice_state_changed.emit(target_mode)
                logger.info("Voice listening mode activated: %s", target_mode)
            else:
                self.voice_service.set_mode(VoiceMode.OFF)
                signals.voice_state_changed.emit("off")
                logger.info("Voice listening mode deactivated.")

    @Slot(str, float)
    def _on_wake_word_detected(self, phrase: str, score: float) -> None:
        """Handle wake-word trigger: sync pet visual state and show greeting bubble."""
        logger.info("🎯 Wake-word detected in controller: '%s' (score=%.2f)", phrase, score)
        if self._is_sleeping or (hasattr(self, "buddy_state_manager") and self.buddy_state_manager.is_sleeping):
            logger.info("Wake word detected while Buddy was sleeping -> Waking up Buddy!")
            self.wake_up()
            return

        if self.pet_window:
            if hasattr(self.pet_window, "anim_controller"):
                from app.character.states import CharacterState
                self.pet_window.anim_controller.request_state(CharacterState.LISTENING)
            if hasattr(self.pet_window, "speech_bubble") and self.pet_window.speech_bubble and self.pet_window.isVisible():
                self.pet_window.speech_bubble.show_message("I'm listening...", self.pet_window.frameGeometry(), duration_ms=3200)

    @Slot(str, str)
    def _on_voice_transcription_ready(self, text: str, lang: str = "en") -> None:
        """Forward spoken transcription to global signal bus and local AI service."""
        cleaned = text.strip()
        if not cleaned:
            logger.info("[DIAGNOSTIC] No speech detected: Empty transcription received.")
            try:
                from app.core.diagnostic_mode import diagnostic_tracker, ERROR_NO_SPEECH
                diagnostic_tracker.update_transcription("no_speech", error=ERROR_NO_SPEECH)
            except Exception:
                pass
            from app.api.websocket import ws_manager
            ws_manager.broadcast_sync("voice_error", {"message": "No speech was detected. Please try again."})
            return

        # 1. Acoustic Self-Echo & Assistant Voice Suppression (Phase 5)
        if self.voice_service:
            if hasattr(self.voice_service, "audio_player") and getattr(self.voice_service.audio_player, "is_playing", False) is True:
                logger.debug("Discarding voice transcription: Assistant speech is currently playing (self-echo).")
                return
            conv_ctrl = getattr(self.voice_service, "conversation_controller", None)
            if conv_ctrl and hasattr(conv_ctrl, "echo_suppressor"):
                try:
                    res = conv_ctrl.echo_suppressor.is_echo(cleaned)
                    if isinstance(res, (tuple, list)) and len(res) >= 1 and bool(res[0]):
                        logger.debug("Discarding voice transcription: Identified as assistant acoustic echo.")
                        return
                except Exception:
                    pass

        # 2. Check if recognized utterance is a direct voice command (e.g. "go to sleep", "mute")
        cmd_dispatcher = getattr(self.voice_service, "command_dispatcher", None)
        if cmd_dispatcher and cmd_dispatcher.dispatch(cleaned, language=lang):
            logger.info("Voice command handled by dispatcher: '%s' [%s]. Skipping chat prompt.", cleaned, lang)
            return

        # 3. Compound wake + prompt handling (Phase 5: "Hey Buddy, explain Python.")
        from app.voice.command_dispatcher import VoiceCommandParser
        compound = VoiceCommandParser.extract_wake_and_prompt(cleaned)
        prompt_text = cleaned
        if compound:
            wake_phrase, remaining_prompt = compound
            is_sleeping = getattr(self, "_is_sleeping", False) or (hasattr(self, "buddy_state_manager") and getattr(self.buddy_state_manager, "is_sleeping", False))
            if is_sleeping:
                logger.info("Compound wake command detected: '%s' (prompt='%s'). Waking Buddy!", wake_phrase, remaining_prompt)
                has_prompt = bool(remaining_prompt.strip())
                self.wake_up(speak_ack=not has_prompt)
                if not has_prompt:
                    return
            if remaining_prompt.strip():
                prompt_text = remaining_prompt.strip()

        # 4. If Buddy is STILL sleeping, ignore ordinary speech (do not submit to chat or AI)
        if self._is_sleeping or (hasattr(self, "buddy_state_manager") and self.buddy_state_manager.is_sleeping):
            logger.debug("Voice input '%s' ignored: Buddy is currently sleeping.", cleaned)
            return

        cleaned = prompt_text

        try:
            from app.core.diagnostic_mode import diagnostic_tracker
            diagnostic_tracker.update_transcription("completed", text=cleaned)
        except Exception:
            pass

        logger.info("Voice transcription received: '%s' [%s]", cleaned, lang)
        signals.voice_transcription_ready.emit(cleaned)
        from app.api.websocket import ws_manager

        # Resolve active conversation ID
        active_conv_id = getattr(self.ai_service, "active_conversation_id", None)
        if not active_conv_id:
            try:
                from app.api.server import app as fastapi_app
                active_conv_id = getattr(fastapi_app.state, "active_conversation_id", None)
            except Exception:
                pass
        if self.conv_repo and not active_conv_id:
            recent = self.conv_repo.list_conversations(limit=1)
            active_conv_id = recent[0].id if recent else self.conv_repo.create_conversation("Voice Chat").id
            if self.ai_service:
                self.ai_service.active_conversation_id = active_conv_id

        # Persist conversation turn and broadcast immediately to all connected UI clients
        if self.conv_repo and active_conv_id:
            user_msg = self.conv_repo.add_message(active_conv_id, "user", cleaned, status="completed")
            if getattr(user_msg, "_is_duplicate", False):
                logger.warning("[DIAGNOSTIC] Duplicate voice transcription already recorded in repository. Skipping assistant turn.")
                return
            assistant_msg = self.conv_repo.add_message(active_conv_id, "assistant", "", status="streaming")
            self.current_assistant_msg_id = assistant_msg.id
            self.current_conv_id = active_conv_id
            try:
                from app.api.server import app as fastapi_app
                fastapi_app.state.current_assistant_msg_id = assistant_msg.id
                fastapi_app.state.current_conv_id = active_conv_id
            except Exception:
                pass

            ws_manager.broadcast_sync("message_added", {
                "message": {
                    "id": user_msg.id,
                    "conversation_id": user_msg.conversation_id,
                    "role": user_msg.role,
                    "content": user_msg.content,
                    "created_at": user_msg.created_at,
                    "status": user_msg.status,
                }
            })
            ws_manager.broadcast_sync("message_added", {
                "message": {
                    "id": assistant_msg.id,
                    "conversation_id": assistant_msg.conversation_id,
                    "role": assistant_msg.role,
                    "content": assistant_msg.content,
                    "created_at": assistant_msg.created_at,
                    "status": assistant_msg.status,
                }
            })

        # Broadcast finalized transcription event with dispatched=True to avoid duplicate client requests
        ws_manager.broadcast_sync("transcription", {"text": cleaned, "language": lang, "dispatched": True})

        # Start LLM inference immediately without waiting for frontend round-trip delay
        if self.ai_service and not getattr(self.ai_service, "_is_generating", False):
            req_id = None
            if hasattr(self, "voice_service") and self.voice_service and hasattr(self.voice_service, "conversation_controller"):
                ctrl = self.voice_service.conversation_controller
                if ctrl and getattr(ctrl, "_active_metrics", None):
                    req_id = ctrl._active_metrics.request_id
            self.ai_service.ask(cleaned, is_voice=True, request_id=req_id)

    @Slot()
    def enter_sleep_mode(self) -> None:
        """Resource-saving sleep mode: stops ordinary listening, cancels inference, keeps wake-word detector operational."""
        from PySide6.QtCore import QThread
        from PySide6.QtWidgets import QApplication

        qapp = QApplication.instance()
        if qapp and QThread.currentThread() != qapp.thread():
            logger.info("ApplicationController.enter_sleep_mode invoked off GUI thread; safely dispatching via QMetaObject")
            from PySide6.QtCore import QMetaObject
            QMetaObject.invokeMethod(self, "enter_sleep_mode", Qt.ConnectionType.QueuedConnection)
            return

        if self._is_sleeping:
            return
        self._is_sleeping = True
        logger.info("Entering resource-saving sleep mode (Buddy sleeping)...")

        if hasattr(self, "buddy_state_manager") and not self.buddy_state_manager.is_sleeping:
            self.buddy_state_manager.enter_sleep(reason="controller_enter_sleep")

        # 1. Stop speech playback and switch to minimal wake-word standby mode
        if self.voice_service:
            try:
                self.voice_service.stop_speaking()
                # Keep minimal wake-word detector operational instead of turning mic completely off
                from app.voice.voice_service import VoiceMode
                self.voice_service.set_mode(VoiceMode.WAKE_WORD)
            except Exception as e:
                logger.debug("Error configuring voice service for sleep: %s", e)

        # 1.5. Hide open voice window
        if hasattr(self, "voice_window") and self.voice_window:
            try:
                if self.voice_window.isVisible():
                    self.voice_window.hide_window()
            except Exception as e:
                logger.debug("Error hiding voice window: %s", e)

        # 2. Stop active inference
        if self.ai_service:
            try:
                self.ai_service.cancel_generation()
            except Exception as e:
                logger.debug("Error cancelling AI generation for sleep: %s", e)

        # 3. Unload heavy models where appropriate
        if self.ai_service and hasattr(self.ai_service, "model_manager"):
            try:
                self.ai_service.model_manager.unload_immediately()
            except Exception as e:
                logger.debug("Error unloading AI model for sleep: %s", e)

        if self.voice_service and hasattr(self.voice_service, "unload_models"):
            try:
                self.voice_service.unload_models(keep_wake_detector=True)
            except TypeError:
                try:
                    self.voice_service.unload_models()
                except Exception as e:
                    logger.debug("Error unloading voice models for sleep: %s", e)
            except Exception as e:
                logger.debug("Error unloading voice models for sleep: %s", e)

        # 4. Display lightweight sleeping animation (throttled to 2 FPS in DesktopPetWindow)
        if self.pet_window and hasattr(self.pet_window, "anim_controller"):
            try:
                from app.character.states import CharacterState
                self.pet_window.anim_controller.request_state(CharacterState.SLEEPING, force=True)
            except Exception as e:
                logger.debug("Error setting pet animation state to sleeping: %s", e)

        from app.api.websocket import ws_manager
        ws_manager.broadcast_sync("buddy_state_changed", {"state": "sleeping"})
        ws_manager.broadcast_sync("char_state", {"state": "sleeping"})

        signals.app_mode_changed.emit("sleeping")
        signals.character_state_changed.emit("sleeping")
        logger.info("Entered resource-saving sleep mode successfully.")

    @Slot()
    def wake_up(self, speak_ack: bool = True) -> None:
        """Wake up from sleep mode, restore idle animation, and optionally acknowledge spoken wake."""
        from PySide6.QtCore import QThread
        from PySide6.QtWidgets import QApplication

        qapp = QApplication.instance()
        if qapp and QThread.currentThread() != qapp.thread():
            logger.info("ApplicationController.wake_up invoked off GUI thread; safely dispatching via QMetaObject")
            from PySide6.QtCore import QMetaObject
            QMetaObject.invokeMethod(self, "wake_up", Qt.ConnectionType.QueuedConnection)
            return

        self._is_sleeping = False
        logger.info("Waking up from sleep mode...")

        if hasattr(self, "buddy_state_manager"):
            self.buddy_state_manager.wake_up(reason="controller_wake")

        if self.pet_window:
            try:
                if not self.pet_window.isVisible():
                    self.pet_window.show()
                if hasattr(self.pet_window, "anim_controller"):
                    from app.character.states import CharacterState
                    self.pet_window.anim_controller.request_state(CharacterState.IDLE, force=True)
            except Exception as e:
                logger.warning("Error restoring pet window on wake: %s", e)

        # Restore configured voice mode
        if self.voice_service:
            try:
                auto_return = self.config_manager.get("voice.auto_return_to_sleep", True)
                configured_mode = self.config_manager.get("voice.mode", "wake_word")
                if auto_return and configured_mode != "continuous":
                    mode = "wake_word"
                else:
                    mode = configured_mode
                self.voice_service.set_mode(mode)
                signals.voice_state_changed.emit(mode)
            except Exception as e:
                logger.warning("Error restoring voice mode on wake: %s", e)

        # Provide spoken acknowledgment and visual speech bubble (Phase 3 & Phase 5)
        if speak_ack:
            ack = "I'm here! What do you need?"
            try:
                if self.pet_window and hasattr(self.pet_window, "speech_bubble") and self.pet_window.speech_bubble and self.pet_window.isVisible():
                    self.pet_window.speech_bubble.show_message(ack, self.pet_window.frameGeometry(), duration_ms=3500)
            except Exception as e:
                logger.warning("Error showing speech bubble on wake: %s", e)

            try:
                if self.voice_service and hasattr(self.voice_service, "speak"):
                    is_muted = getattr(self.voice_service, "is_muted", False)
                    if not is_muted:
                        self.voice_service.speak(ack)
            except Exception as e:
                logger.warning("Error playing spoken wake ack: %s", e)

        from app.api.websocket import ws_manager
        ws_manager.broadcast_sync("char_state", {"state": "idle"})
        ws_manager.broadcast_sync("buddy_state_changed", {"state": "active"})

        signals.app_mode_changed.emit("active")
        signals.character_state_changed.emit("idle")
        logger.info("Woke up from sleep mode successfully.")

    @Slot()
    def _on_emergency_stop(self) -> None:
        """Immediate Emergency Audio / AI Stop across all subsystems (Bug 18)."""
        logger.warning("Emergency stop triggered globally: halting speech, voice capture, and AI generation.")
        if self.voice_service and hasattr(self.voice_service, "emergency_stop"):
            self.voice_service.emergency_stop()
        if self.ai_service and hasattr(self.ai_service, "cancel_generation"):
            self.ai_service.cancel_generation()
        if self.pet_window and hasattr(self.pet_window, "anim_controller"):
            self.pet_window.anim_controller.request_state("idle", force=True)
        signals.character_state_changed.emit("idle")

    @Slot()
    def _on_system_resumed(self) -> None:
        """Handle Windows system resume from sleep/standby (Phase 11.7)."""
        logger.info("Windows resumed from sleep. Revalidating audio devices and background services...")
        if self.error_recovery:
            self.error_recovery.revalidate_after_resume(self.ai_service, self.voice_service)
        self._on_display_configuration_changed()
        if self._is_sleeping:
            self.wake_up()

    @Slot()
    def _on_display_configuration_changed(self) -> None:
        """Revalidate window positions across multi-monitor setup (Phase 11.7)."""
        logger.info("Display configuration changed. Revalidating window positions...")
        if self.pet_window:
            self.pet_window.revalidate_screen_position()
            if self.chat_window and self.chat_window.isVisible():
                self.chat_window.position_near_pet(self.pet_window.frameGeometry())
            if hasattr(self, "voice_window") and self.voice_window and self.voice_window.isVisible():
                self.voice_window.position_near_pet(self.pet_window.frameGeometry())
            if self.status_hud and self.status_hud.isVisible():
                self.status_hud.reposition_near_pet(self.pet_window.frameGeometry())

    @Slot()
    def _on_open_settings(self) -> None:
        """Open settings dialog, routing to modern React Settings Modal when available."""
        if hasattr(self, "chat_window") and hasattr(self.chat_window, "open_settings"):
            if self.pet_window and self.pet_window.isVisible() and hasattr(self.chat_window, "position_near_pet"):
                self.chat_window.position_near_pet(self.pet_window.frameGeometry())
            self.chat_window.open_settings()
            return
        if self._settings_dialog is None:
            from app.desktop.settings_dialog import SettingsDialog
            memory_mgr = getattr(self.ai_service, "memory_manager", None)
            self._settings_dialog = SettingsDialog(
                config_manager=self.config_manager,
                memory_manager=memory_mgr,
                ai_service=self.ai_service,
                voice_service=self.voice_service,
                parent=None,
            )
        self._settings_dialog.show()
        self._settings_dialog.raise_()
        self._settings_dialog.activateWindow()

    def _start_api_server(self) -> None:
        """Start local FastAPI + WebSocket server in a daemon thread."""
        import os
        if "PYTEST_CURRENT_TEST" in os.environ:
            return

        import threading
        import urllib.request
        from app.api.server import app as fastapi_app
        from app.memory.conversation_repository import ConversationRepository
        from main_api import setup_signal_bridges

        conv_repo = self.conv_repo or ConversationRepository()
        self.conv_repo = conv_repo
        fastapi_app.state.config_manager = self.config_manager
        fastapi_app.state.conv_repo = conv_repo
        from app.memory.movie_storage_repository import MovieStorageRepository
        from app.api.movie_cache_manager import MovieCacheManager
        from app.api.tmdb_client import TMDBClient
        fastapi_app.state.movie_repo = MovieStorageRepository(conv_repo.db)
        movie_cache = MovieCacheManager(db_manager=conv_repo.db)
        fastapi_app.state.movie_cache = movie_cache
        api_key = (self.config_manager.get("movies.tmdb_api_key", "") or os.environ.get("TMDB_API_KEY", "")).strip()
        fastapi_app.state.tmdb_client = TMDBClient(api_key=api_key or None, cache_manager=movie_cache)
        fastapi_app.state.ai_service = self.ai_service
        fastapi_app.state.voice_service = self.voice_service
        fastapi_app.state.controller = self
        fastapi_app.state.current_assistant_msg_id = None

        setup_signal_bridges(self.app, conv_repo)

        # Ensure port 8765 is not held by a stale process from a prior run
        try:
            import psutil
            current_pid = os.getpid()
            for conn in psutil.net_connections(kind="inet"):
                if conn.laddr and conn.laddr.port == 8765 and conn.status == psutil.CONN_LISTEN:
                    if conn.pid and conn.pid != current_pid:
                        logger.warning("Port 8765 held by stale PID %d. Terminating to release port...", conn.pid)
                        try:
                            stale_proc = psutil.Process(conn.pid)
                            stale_proc.terminate()
                            stale_proc.wait(timeout=2)
                        except Exception:
                            pass
        except Exception as e:
            logger.debug("Port verification check: %s", e)

        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open("http://127.0.0.1:8765/api/health", timeout=0.5) as resp:
                if resp.status == 200:
                    logger.info("FastAPI backend is already active on 127.0.0.1:8765; signals bridged.")
                    return
        except Exception:
            pass

        def run_uvicorn():
            import uvicorn
            config = uvicorn.Config(
                app=fastapi_app,
                host="127.0.0.1",
                port=8765,
                log_level="warning",
                access_log=False,
            )
            server = uvicorn.Server(config)
            self._api_server = server
            server.run()

        thread = threading.Thread(target=run_uvicorn, daemon=True, name="UvicornServerThread")
        self._api_server_thread = thread
        thread.start()
        logger.info("FastAPI local server daemon started on http://127.0.0.1:8765")

    def register_background_service(self, service: QObject) -> None:
        """Register a background service/worker for clean shutdown coordination."""
        self._background_services.append(service)

    @staticmethod
    def _hard_kill_process() -> None:
        """Unconditionally terminate current process without waiting for DLL detach or thread joins."""
        if sys.platform == "win32":
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                kernel32.GetCurrentProcess.restype = ctypes.c_void_p
                kernel32.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint]
                kernel32.TerminateProcess.restype = ctypes.c_bool
                kernel32.TerminateProcess(kernel32.GetCurrentProcess(), 0)
            except Exception:
                pass
        try:
            os._exit(0)
        except Exception:
            pass

    def emergency_fast_exit(self) -> None:
        """Instant emergency shutdown triggered on terminal Ctrl+C or console close event.

        Guarantees that:
        1. All visible companion windows vanish from the screen instantly (sub-millisecond Win32 ShowWindowAsync).
        2. SingleInstanceGuard lock is released (pipe removed & port lockfile unlinked) so subsequent launches succeed.
        3. Uvicorn server is told to stop; child processes are killed.
        4. Process is terminated instantly via Win32 TerminateProcess without DLL_PROCESS_DETACH deadlock.
        """
        if getattr(self, "_is_emergency_exiting", False):
            self._hard_kill_process()
            return

        self._is_emergency_exiting = True
        self._is_shutting_down = True
        logger.warning("[EMERGENCY EXIT] Initiating instant shutdown on Ctrl+C...")

        # 1. Asynchronously hide all tracked window HWNDs using native Win32 ShowWindowAsync(SW_HIDE = 0)
        if sys.platform == "win32":
            try:
                import ctypes
                user32 = ctypes.windll.user32
                user32.ShowWindowAsync.argtypes = [ctypes.c_void_p, ctypes.c_int]
                SW_HIDE = 0
                for hwnd in getattr(self, "_window_hwnds", []):
                    try:
                        if hwnd:
                            user32.ShowWindowAsync(ctypes.c_void_p(hwnd), SW_HIDE)
                    except Exception:
                        pass
            except Exception as e:
                logger.debug("Win32 emergency hide note: %s", e)

        # 2. Release single-instance lock directly without invoking Qt QObject methods across threads
        try:
            from app.core.single_instance import SingleInstanceGuard
            SingleInstanceGuard.clean_lock_file()
            if self.guard:
                self.guard.fast_release()
        except Exception as e:
            logger.debug("Error releasing single instance guard: %s", e)

        # 3. Signal uvicorn to exit immediately
        try:
            if getattr(self, "_api_server", None) is not None:
                self._api_server.should_exit = True
                for srv in getattr(self._api_server, "servers", []):
                    try:
                        srv.close()
                    except Exception:
                        pass
        except Exception:
            pass

        # 4. Fast kill child processes via LifecycleManager
        try:
            lifecycle = get_lifecycle_manager()
            lifecycle.fast_kill_children()
        except Exception:
            pass

        # 5. Immediate process termination at the NT kernel level
        self._hard_kill_process()

    @Slot()
    def shutdown(self, source: str = "controller") -> None:
        """Centralized shutdown handler for ApplicationController.
        
        Routes through LifecycleManager to guarantee single, coordinated execution.
        """
        lifecycle = get_lifecycle_manager()
        if not lifecycle.is_shutting_down:
            lifecycle.request_shutdown(source=source)
            return

        if self._is_shutting_down:
            return
        self._is_shutting_down = True

        logger.info("[SHUTDOWN] Step 1/9: Marking shutdown as requested...")
        try:
            self.shutting_down.emit()
        except Exception:
            pass

        # Hide all windows immediately so user does not see frozen frames during graceful cleanup
        windows = [
            getattr(self, "pet_window", None),
            getattr(self, "chat_window", None),
            getattr(self, "status_hud", None),
            getattr(self, "voice_window", None),
            getattr(self, "_settings_dialog", None),
        ]
        for win in windows:
            if win is not None:
                try:
                    win.hide()
                except Exception:
                    pass

        # Disconnect all tracked signal connections cleanly
        for conn in getattr(self, "_signal_connections", []):
            try:
                QObject.disconnect(conn)
            except Exception:
                pass
        self._signal_connections = []

        try:
            # Step 2: Stop global input hooks
            logger.info("[SHUTDOWN] Step 2/9: Stopping global input hooks...")
            if self.windows_integration:
                try:
                    self.windows_integration.cleanup()
                    self.windows_integration = None
                except Exception as e:
                    logger.error("[SHUTDOWN] Error cleaning up windows integration / global hotkeys: %s", e)

            # Step 3: Stop voice and audio hardware
            logger.info("[SHUTDOWN] Step 3/9: Stopping voice and audio hardware...")
            if self.voice_service:
                try:
                    logger.info("Shutting down VoiceService and releasing audio resources...")
                    self.voice_service.emergency_stop()
                    self.voice_service.shutdown()
                    self.voice_service = None
                except Exception as e:
                    logger.error("[SHUTDOWN] Error shutting down VoiceService: %s", e)

            try:
                import sounddevice as sd
                sd.stop()
            except Exception:
                pass

            # Step 4: Cancel AI and background tasks
            logger.info("[SHUTDOWN] Step 4/9: Canceling AI and background tasks...")
            if self.ai_service:
                try:
                    logger.info("Stopping AIService inference and unloading LLM...")
                    self.ai_service.stop()
                    self.ai_service = None
                except Exception as e:
                    logger.error("[SHUTDOWN] Error stopping AIService: %s", e)

            for service in self._background_services:
                try:
                    if hasattr(service, "set_mode"):
                        service.set_mode("off")
                    if hasattr(service, "stop"):
                        service.stop()
                except Exception as e:
                    logger.error("[SHUTDOWN] Error stopping background service %s: %s", service, e)
            self._background_services = []

            if self.perf_monitor:
                try:
                    self.perf_monitor.stop_monitoring()
                    self.perf_monitor = None
                except Exception as e:
                    logger.error("[SHUTDOWN] Error stopping performance monitor: %s", e)

            # Step 5: Stop local server and network resources
            logger.info("[SHUTDOWN] Step 5/9: Stopping local server and network resources...")
            if getattr(self, "_api_server", None) is not None:
                try:
                    logger.info("Signaling local API server to exit...")
                    self._api_server.should_exit = True
                    for srv in getattr(self._api_server, "servers", []):
                        try:
                            srv.close()
                        except Exception:
                            pass
                except Exception as e:
                    logger.debug("[SHUTDOWN] Error closing API server sockets: %s", e)

            if getattr(self, "_api_server_thread", None) is not None and self._api_server_thread.is_alive():
                try:
                    self._api_server_thread.join(timeout=2.0)
                    logger.info("[SHUTDOWN] API server background thread joined.")
                except Exception as e:
                    logger.debug("[SHUTDOWN] Error joining API server thread: %s", e)

            # Step 6: Drain thread pools
            logger.info("[SHUTDOWN] Step 6/9: Draining thread pools...")
            try:
                from PySide6.QtCore import QThreadPool
                pool = QThreadPool.globalInstance()
                if pool:
                    pool.waitForDone(1500)
            except Exception as e:
                logger.debug("[SHUTDOWN] Error draining QThreadPool: %s", e)

            # Step 7: Tear down Qt UI objects
            logger.info("[SHUTDOWN] Step 7/9: Tearing down Qt UI objects...")
            if self._settings_dialog:
                try:
                    self._settings_dialog.close()
                    self._settings_dialog = None
                except Exception as e:
                    logger.error("Error closing settings dialog: %s", e)

            if self.chat_window:
                try:
                    self.chat_window.cleanup()
                    self.chat_window.close()
                    self.chat_window = None
                except Exception as e:
                    logger.error("Error closing chat window: %s", e)

            if hasattr(self, "voice_window") and self.voice_window:
                try:
                    self.voice_window.close()
                    self.voice_window = None
                except Exception as e:
                    logger.error("Error closing voice window: %s", e)

            if self.status_hud:
                try:
                    self.status_hud.close()
                    self.status_hud = None
                except Exception as e:
                    logger.error("Error closing status HUD: %s", e)

            if self.pet_window:
                try:
                    self.pet_window.close()
                    self.pet_window = None
                except Exception as e:
                    logger.error("Error closing pet window: %s", e)

            if self.tray_manager:
                try:
                    self.tray_manager.cleanup()
                    self.tray_manager = None
                except Exception as e:
                    logger.error("Error cleaning up tray manager: %s", e)

            # Flush Qt deferred deletions safely without spinning event loop
            try:
                from PySide6.QtCore import QCoreApplication, QEvent
                QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            except Exception:
                pass

            # Save final settings
            try:
                self.config_manager.save()
            except Exception as e:
                logger.error("Error saving final configuration: %s", e)

        finally:
            if self.guard:
                try:
                    self.guard.release()
                except Exception as e:
                    logger.error("Error releasing single instance guard: %s", e)

        logger.info("[SHUTDOWN] ApplicationController cleanup completed.")

    def _on_app_about_to_quit(self) -> None:
        """Final safety hook when Qt event loop begins quitting."""
        lifecycle = get_lifecycle_manager()
        if not lifecycle.is_shutting_down:
            lifecycle.request_shutdown(source="app_about_to_quit")
