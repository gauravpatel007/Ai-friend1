"""Headless FastAPI + WebSocket Backend Entry Point.

Powers the Tauri 2 + React 19 desktop application by running
local AI inference, long-term memory, voice processing, and
configuration as a high-performance local daemon without Qt GUI windows.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
import sys

# Resolve project root regardless of launch origin
if getattr(sys, "frozen", False):
    project_root = Path(sys.executable).resolve().parent
else:
    project_root = Path(__file__).resolve().parent

try:
    from dotenv import load_dotenv
    load_dotenv(project_root / ".env")
except Exception:
    pass

try:
    os.chdir(project_root)
except Exception:
    pass

# Ensure local loopback bypasses proxy environments (e.g., enterprise proxies, sandbox)
os.environ["NO_PROXY"] = "localhost,127.0.0.1"
os.environ["no_proxy"] = "localhost,127.0.0.1"

from typing import Optional
import uvicorn
from PySide6.QtCore import QCoreApplication, QObject, Qt

from app.api.server import app
from app.api.websocket import ws_manager
from app.core.lifecycle import get_lifecycle_manager
from app.core.signals import signals
from app.memory.conversation_repository import ConversationRepository
from app.settings.config_manager import ConfigManager
from app.utils.logger import get_logger

logger = get_logger("ai_desktop_friend.api")


_active_api_signal_bridges: list = []


def teardown_signal_bridges() -> None:
    """Disconnect all active signal bridges created by setup_signal_bridges."""
    global _active_api_signal_bridges
    for conn in _active_api_signal_bridges:
        try:
            QObject.disconnect(conn)
        except Exception:
            pass
    _active_api_signal_bridges.clear()


def setup_signal_bridges(q_app: QCoreApplication, conv_repo: ConversationRepository) -> None:
    """Connect Qt bus signals to WebSocket broadcasts and database updates."""
    teardown_signal_bridges()

    if getattr(app.state, "controller", None):
        logger.info("ApplicationController is active; using controller native WebSocket signal bridges.")
        return

    def on_ai_chunk(chunk: str) -> None:
        msg_id = getattr(app.state, "current_assistant_msg_id", None)
        req_id = getattr(app.state, "current_request_id", None)
        ws_manager.broadcast_sync("ai_chunk", {"chunk": chunk, "message_id": msg_id, "request_id": req_id})

    def on_ai_complete(full_text: str) -> None:
        msg_id = getattr(app.state, "current_assistant_msg_id", None)
        req_id = getattr(app.state, "current_request_id", None)
        if msg_id:
            try:
                conv_repo.update_message_content(msg_id, full_text, status="completed")
            except Exception as e:
                logger.error("Failed to update message in database: %s", e)
        ai_srv = getattr(app.state, "ai_service", None)
        timings = ai_srv.get_latest_timing_metrics() if ai_srv and hasattr(ai_srv, "get_latest_timing_metrics") else {}
        if not req_id:
            req_id = timings.get("request_id")
        ws_manager.broadcast_sync("ai_complete", {
            "text": full_text,
            "message_id": msg_id,
            "request_id": req_id,
            "timings": timings,
        })
        signals.character_state_changed.emit("idle")
        app.state.current_assistant_msg_id = None
        app.state.current_request_id = None

    def on_ai_error(error_msg: str) -> None:
        msg_id = getattr(app.state, "current_assistant_msg_id", None)
        if msg_id:
            try:
                conv_repo.update_message_content(msg_id, error_msg, status="error")
            except Exception as e:
                logger.error("Failed to update message error in database: %s", e)
        ws_manager.broadcast_sync("ai_error", {"message": error_msg, "message_id": msg_id})
        signals.character_state_changed.emit("idle")

    def on_ai_cancelled() -> None:
        msg_id = getattr(app.state, "current_assistant_msg_id", None)
        if msg_id:
            try:
                conv_repo.update_message_content(msg_id, "[Cancelled by user]", status="cancelled")
            except Exception:
                pass
        ws_manager.broadcast_sync("ai_cancelled", {"message_id": msg_id})

    def on_char_state(state: str) -> None:
        ws_manager.broadcast_sync("char_state", {"state": state})

    def on_voice_state(state: str) -> None:
        ws_manager.broadcast_sync("voice_state", {"state": state})

    def on_buddy_state_changed(old_state: str, new_state: str) -> None:
        ws_manager.broadcast_sync("buddy_state_changed", {"state": new_state, "previous_state": old_state})
        if new_state == "sleeping":
            ws_manager.broadcast_sync("char_state", {"state": "sleeping"})
        elif old_state == "sleeping" and new_state == "active":
            ws_manager.broadcast_sync("char_state", {"state": "idle"})

    def on_transcription(text: str) -> None:
        ws_manager.broadcast_sync("transcription", {"text": text})

    def on_emotion(emotion: str, score: float) -> None:
        ws_manager.broadcast_sync("user_emotion", {"emotion": emotion, "confidence": score})

    def on_memory_stored(memory_obj: object) -> None:
        mem_data = {
            "id": getattr(memory_obj, "id", ""),
            "category": getattr(memory_obj, "category", ""),
            "content": getattr(memory_obj, "content", ""),
            "created_at": getattr(memory_obj, "created_at", ""),
        }
        ws_manager.broadcast_sync("memory_stored", {"memory": mem_data})

    def on_voice_toggle() -> None:
        if getattr(app.state, "controller", None):
            # ApplicationController is active and already handles voice_toggle_requested
            return
        vs = getattr(app.state, "voice_service", None)
        cfg = getattr(app.state, "config_manager", None)
        if vs:
            from app.voice.voice_service import VoiceMode
            current_mode = vs.mode
            is_off = (
                current_mode == VoiceMode.OFF
                or (hasattr(current_mode, "value") and current_mode.value == "off")
                or str(current_mode).lower().strip() in ("off", "voicemode.off")
            )
            if is_off:
                target_mode = cfg.get("voice.mode", "continuous") if cfg else "continuous"
                if not target_mode or target_mode == "off":
                    target_mode = "continuous"
                vs.set_mode(target_mode)
                signals.voice_state_changed.emit(target_mode)
                logger.info("Headless voice mode activated: %s", target_mode)
            else:
                vs.set_mode(VoiceMode.OFF)
                signals.voice_state_changed.emit("off")
                logger.info("Headless voice mode deactivated.")

    def on_transcription_received(text: str, lang: str = "en") -> None:
        cleaned = text.strip()
        if not cleaned:
            try:
                from app.core.diagnostic_mode import diagnostic_tracker, ERROR_NO_SPEECH
                diagnostic_tracker.update_transcription("no_speech", error=ERROR_NO_SPEECH)
            except Exception:
                pass
            return
        try:
            from app.core.diagnostic_mode import diagnostic_tracker
            diagnostic_tracker.update_transcription("completed", text=cleaned)
        except Exception:
            pass
        signals.voice_transcription_ready.emit(cleaned)
        ai = getattr(app.state, "ai_service", None)
        active_id = getattr(ai, "active_conversation_id", None) if ai else None
        if not active_id:
            recent = conv_repo.list_conversations(limit=1)
            active_id = recent[0].id if recent else conv_repo.create_conversation("Voice Chat").id
            if ai:
                ai.active_conversation_id = active_id

        user_msg = conv_repo.add_message(active_id, "user", cleaned, status="completed")
        assistant_msg = conv_repo.add_message(active_id, "assistant", "", status="streaming")
        app.state.current_assistant_msg_id = assistant_msg.id
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
        vs = getattr(app.state, "voice_service", None)
        conv_ctrl = getattr(vs, "conversation_controller", None) if vs else None
        has_conv_controller = (
            conv_ctrl
            and conv_ctrl.is_enabled
            and conv_ctrl.ai_service is not None
        )
        if not has_conv_controller and ai and not getattr(ai, "_is_generating", False):
            ai.ask(cleaned, is_voice=True)

    from app.core.buddy_state_manager import get_buddy_state_manager
    buddy_sm = get_buddy_state_manager()

    # Connect signals and track them for clean teardown
    global _active_api_signal_bridges
    _active_api_signal_bridges = [
        signals.ai_response_chunk.connect(on_ai_chunk),
        signals.ai_response_complete.connect(on_ai_complete),
        signals.ai_error_occurred.connect(on_ai_error),
        signals.ai_generation_cancelled.connect(on_ai_cancelled),
        signals.character_state_changed.connect(on_char_state),
        signals.voice_state_changed.connect(on_voice_state),
        signals.voice_transcription_ready.connect(on_transcription),
        signals.user_emotion_detected.connect(on_emotion),
        signals.memory_stored.connect(on_memory_stored),
        buddy_sm.state_changed.connect(on_buddy_state_changed),
    ]
    if not getattr(app.state, "controller", None):
        _active_api_signal_bridges.append(
            signals.voice_toggle_requested.connect(on_voice_toggle, Qt.ConnectionType.DirectConnection)
        )

    # Attach voice service transcription if active
    vs = getattr(app.state, "voice_service", None)
    if vs and hasattr(vs, "transcription_ready"):
        _active_api_signal_bridges.append(vs.transcription_ready.connect(on_transcription_received))


async def pump_qt_events(q_app: QCoreApplication) -> None:
    """Pump Qt event loop periodically so signals and timers execute without GUI."""
    while True:
        try:
            q_app.processEvents()
        except Exception as e:
            logger.error("Error processing Qt events: %s", e)
        await asyncio.sleep(0.015)


def main() -> None:
    """Start the headless backend server."""
    lifecycle = get_lifecycle_manager()
    lifecycle.setup_console_ctrl_handler()

    def handle_sigint(signum=None, frame=None):
        print("\n[!] Ctrl+C detected. Shutting down immediately...", flush=True)
        try:
            from app.core.single_instance import SingleInstanceGuard
            SingleInstanceGuard.clean_lock_file()
        except Exception:
            pass
        try:
            lifecycle.fast_kill_children()
        except Exception:
            pass
        try:
            if sys.platform == "win32":
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

    import signal
    signal.signal(signal.SIGINT, handle_sigint)
    signal.signal(signal.SIGTERM, handle_sigint)

    if sys.platform == "win32":
        try:
            import ctypes
            @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_ulong)
            def api_ctrl_handler(ctrl_type: int) -> bool:
                handle_sigint()
                return True

            global _api_ctrl_handler_ref
            _api_ctrl_handler_ref = api_ctrl_handler
            ctypes.windll.kernel32.SetConsoleCtrlHandler(_api_ctrl_handler_ref, True)
        except Exception:
            pass

    logger.info("Initializing headless Qt application core...")
    q_app = QCoreApplication.instance() or QCoreApplication(sys.argv)

    # 1. Initialize core services
    logger.info("Initializing ConfigManager and ConversationRepository...")
    config_manager = ConfigManager()
    conv_repo = ConversationRepository()

    # 2. Initialize AI Service
    logger.info("Initializing AIService...")
    from app.ai.ai_service import AIService
    ai_service = AIService(config_manager=config_manager)
    lifecycle.register_shutdown_hook(ai_service.stop, priority=50, name="AIService")

    # 3. Initialize Voice Service
    voice_service = None
    try:
        logger.info("Initializing VoiceService...")
        from app.voice.voice_service import VoiceService
        voice_service = VoiceService()
        voice_service.attach_ai_service(ai_service)
        lifecycle.register_shutdown_hook(voice_service.shutdown, priority=100, name="VoiceService")
        if config_manager.get("voice.enabled", True):
            voice_service.set_mode("continuous")
            signals.voice_state_changed.emit("continuous")
            logger.info("Continuous hands-free voice mode auto-activated on startup.")
    except Exception as e:
        logger.warning("VoiceService could not be initialized (audio device issue?): %s", e)

    # Attach services to FastAPI application state
    app.state.config_manager = config_manager
    app.state.conv_repo = conv_repo
    app.state.ai_service = ai_service
    app.state.voice_service = voice_service
    app.state.current_assistant_msg_id = None

    # Connect Qt bus signals to WebSocket events
    setup_signal_bridges(q_app, conv_repo)

    # Register Qt event pump in FastAPI startup hook
    @app.on_event("startup")
    async def start_event_pump() -> None:
        asyncio.create_task(pump_qt_events(q_app))
        logger.info("Qt event pump started.")

    port = int(config_manager.get("api.port", 8765))
    host = "127.0.0.1"
    logger.info("Starting FastAPI Uvicorn server on http://%s:%d ...", host, port)

    uvicorn_config = uvicorn.Config(
        app=app,
        host=host,
        port=port,
        log_level="info",
        access_log=False,
    )
    server = uvicorn.Server(uvicorn_config)
    lifecycle.register_shutdown_hook(lambda: setattr(server, "should_exit", True), priority=90, name="UvicornServer")

    try:
        server.run()
    except KeyboardInterrupt:
        handle_sigint()
    finally:
        handle_sigint()


if __name__ == "__main__":
    main()
