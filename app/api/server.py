"""FastAPI Application Server for Tauri & React Desktop Frontend.

Provides RESTful endpoints and real-time WebSocket communication
for chat, model management, voice engine, and settings.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
import html
import os
from pathlib import Path
import re
import shutil
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from fastapi import FastAPI, HTTPException, Query, Body, Request, WebSocket, WebSocketDisconnect, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.ai.attachment_processor import AttachmentProcessor, get_temp_upload_dir
from app.api.websocket import ws_manager
from app.core.signals import signals
from app.memory.conversation_repository import ConversationRepository
from app.settings.config_manager import ConfigManager
from app.utils.logger import get_logger

logger = get_logger(__name__)


# ─── Pydantic Request / Response Schemas ─────────────────────────────────────

class ConfigUpdateRequest(BaseModel):
    key: str
    value: Any


class BatchConfigRequest(BaseModel):
    settings: Dict[str, Any]


class CreateConversationRequest(BaseModel):
    title: Optional[str] = "New Chat"


class RenameConversationRequest(BaseModel):
    title: str


class SendMessageRequest(BaseModel):
    content: str
    is_voice: Optional[bool] = False
    response_style: Optional[str] = None
    request_id: Optional[str] = None
    client_timestamp: Optional[float] = None
    images: Optional[List[str]] = None
    attachments: Optional[List[Dict[str, Any]]] = None


class SelectModelRequest(BaseModel):
    model: str


class RouterToggleRequest(BaseModel):
    enabled: bool


class ModelPreferencesRequest(BaseModel):
    model_selection_mode: Optional[str] = "auto"
    response_priority: Optional[str] = "balanced"
    task_preferred_models: Optional[Dict[str, str]] = None
    manual_model: Optional[str] = None


class RunBenchmarkRequest(BaseModel):
    models: Optional[List[str]] = None
    categories: Optional[List[str]] = None


class PetTopmostRequest(BaseModel):
    always_on_top: bool


class VoiceMuteRequest(BaseModel):
    muted: bool


class TestVoiceRequest(BaseModel):
    text: Optional[str] = None
    profile_id: Optional[str] = None
    voice_profile: Optional[str] = None
    voice: Optional[str] = None
    language: Optional[str] = "en"


class VoicePreviewRequest(BaseModel):
    profile_id: str = "arjun"
    language: str = "en"
    text: Optional[str] = None


class VoiceEngineRequest(BaseModel):
    engine: str


class VoiceSpeedRequest(BaseModel):
    speed: float


class FeedbackRequest(BaseModel):
    feedback: Optional[str] = None  # "like", "dislike", or None to clear


class ClipboardRequest(BaseModel):
    text: str


class VoiceVolumeRequest(BaseModel):
    volume: float


class ExportChatRequest(BaseModel):
    conversation_id: Optional[str] = ""


class VoiceModeRequest(BaseModel):
    mode: str


class MemoryCreateRequest(BaseModel):
    category: str = "general"
    content: str


class DiagnosticToggleRequest(BaseModel):
    enabled: Optional[bool] = None


class UpdateMessageRequest(BaseModel):
    content: str


class RetryMessageRequest(BaseModel):
    prompt: Optional[str] = None


class RecoveryActionRequest(BaseModel):
    action: str
    payload: Optional[Dict[str, Any]] = None


# ─── Static Asset Management & Multi-Directory Serving ───────────────────────

def sync_character_assets(project_root: Optional[str] = None) -> None:
    """Ensure all robot character state assets (including thinking.png) exist across public and dist."""
    if project_root is None:
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    src_char_dir = os.path.join(project_root, "assets", "characters", "robot")
    if not os.path.isdir(src_char_dir):
        return

    target_dirs = [
        os.path.join(project_root, "public", "assets", "characters", "robot"),
        os.path.join(project_root, "dist", "assets", "characters", "robot"),
    ]

    for target_dir in target_dirs:
        # If target is inside dist, only populate if dist itself exists
        if "dist" in target_dir and not os.path.isdir(os.path.join(project_root, "dist")):
            continue
        try:
            os.makedirs(target_dir, exist_ok=True)
            for fname in os.listdir(src_char_dir):
                if fname.lower().endswith(".png"):
                    src_file = os.path.join(src_char_dir, fname)
                    dst_file = os.path.join(target_dir, fname)
                    if not os.path.exists(dst_file) or os.path.getsize(dst_file) == 0:
                        shutil.copy2(src_file, dst_file)
        except Exception as e:
            logger.warning("Failed to sync character assets to %s: %s", target_dir, e)


class MultiDirStaticFiles(StaticFiles):
    """StaticFiles provider searching multiple directories in priority order with character fallback."""

    def __init__(self, directories: List[str], **kwargs):
        existing = [os.path.abspath(d) for d in directories if os.path.isdir(d)]
        primary = existing[0] if existing else "."
        super().__init__(directory=primary, check_dir=False, **kwargs)
        self.all_directories = [Path(d) for d in existing]

    def lookup_path(self, path: str):
        full_path, stat_result = super().lookup_path(path)
        if full_path and stat_result:
            return full_path, stat_result

        # Robust fallback for character avatar states to prevent broken image flashes in UI
        norm_path = path.replace("\\", "/")
        if "characters/" in norm_path and norm_path.endswith(".png"):
            parts = norm_path.split("/")
            if len(parts) >= 2:
                idle_path = "/".join(parts[:-1]) + "/idle.png"
                return super().lookup_path(idle_path)
        return "", None


# ─── Allowed Origins & Security Validation ───────────────────────────────────

ALLOWED_ORIGIN_PATTERNS = [
    re.compile(r"^https?://(127\.0\.0\.1|localhost)(:\d+)?$"),
    re.compile(r"^tauri://localhost$"),
    re.compile(r"^https?://tauri\.localhost(:\d+)?$"),
]

ALLOWED_ORIGINS = [
    "http://127.0.0.1:8765",
    "http://localhost:8765",
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "tauri://localhost",
    "http://tauri.localhost",
    "https://tauri.localhost",
]


def is_allowed_origin(origin: Optional[str]) -> bool:
    """Return True if the origin is a trusted local endpoint or Tauri origin."""
    if not origin:
        return False
    return any(pattern.match(origin) for pattern in ALLOWED_ORIGIN_PATTERNS)


# ─── FastAPI App Initialization ──────────────────────────────────────────────

def create_app() -> FastAPI:
    """Create and configure the FastAPI instance."""
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        loop = asyncio.get_running_loop()
        ws_manager.set_event_loop(loop)
        try:
            from app.core.diagnostic_mode import diagnostic_tracker
            diagnostic_tracker.set_ws_manager(ws_manager)
            cfg_mgr: Optional[ConfigManager] = getattr(app.state, "config_manager", None)
            if cfg_mgr:
                diagnostic_tracker.set_enabled(bool(cfg_mgr.get("general.debug", False)))
        except Exception:
            pass
        logger.info("FastAPI server started, event loop registered for WebSocket manager.")
        yield

    app = FastAPI(
        title="AI Desktop Friend Backend",
        version="2.0.0",
        description="Local desktop API layer powering Tauri + React frontend",
        lifespan=lifespan,
    )

    # Restrict CORS to trusted local/Tauri origins instead of wildcard *
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_origin_regex=r"^https?://(127\.0\.0\.1|localhost)(:\d+)?$",
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def validate_origin_middleware(request: Request, call_next):
        """Reject cross-origin state alteration or data extraction from unauthorized websites."""
        if request.url.path.startswith("/api/"):
            origin = request.headers.get("origin")
            if origin and not is_allowed_origin(origin):
                logger.warning("Rejected API request from unauthorized origin: %s (path=%s)", origin, request.url.path)
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Forbidden: cross-origin access from untrusted origin denied."}
                )
            referer = request.headers.get("referer")
            if referer:
                try:
                    parsed = urlparse(referer)
                    ref_origin = f"{parsed.scheme}://{parsed.netloc}"
                    if not is_allowed_origin(ref_origin):
                        logger.warning("Rejected API request from unauthorized referer: %s (path=%s)", referer, request.url.path)
                        return JSONResponse(
                            status_code=403,
                            content={"detail": "Forbidden: cross-origin access from untrusted referer denied."}
                        )
                except Exception:
                    pass
            host = request.headers.get("host", "")
            if host:
                host_domain = host.split(":")[0].lower()
                if host_domain not in ("127.0.0.1", "localhost", "testserver"):
                    logger.warning("Rejected API request with unauthorized host: %s (path=%s)", host, request.url.path)
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "Forbidden: invalid host header."}
                    )
        return await call_next(request)

    # ─── Health & Telemetry ──────────────────────────────────────────────────

    @app.get("/api/health")
    async def get_health() -> Dict[str, Any]:
        """Liveness check and system state."""
        return {
            "status": "online",
            "companion": "AI Desktop Friend",
            "version": "2.0.0",
            "ws_clients": len(ws_manager.active_connections),
        }

    def _get_config_manager() -> Optional[ConfigManager]:
        cfg = getattr(app.state, "config_manager", None)
        if cfg is None:
            try:
                cfg = ConfigManager()
                app.state.config_manager = cfg
            except Exception:
                pass
        return cfg

    # ─── Configuration ───────────────────────────────────────────────────────

    @app.get("/api/config")
    async def get_config() -> Dict[str, Any]:
        """Return the current complete configuration."""
        cfg_mgr = _get_config_manager()
        if not cfg_mgr:
            return {}
        return cfg_mgr.all_settings

    @app.put("/api/config")
    async def update_config(req: ConfigUpdateRequest) -> Dict[str, Any]:
        """Update a specific configuration key."""
        cfg_mgr = _get_config_manager()
        if not cfg_mgr:
            raise HTTPException(status_code=500, detail="Config manager not available")
        cfg_mgr.set(req.key, req.value)
        ws_manager.broadcast_sync("config_updated", {"key": req.key, "value": req.value})
        if req.key in ("ai.companion_name", "companion.name", "character.name"):
            clean_name = str(req.value).strip()
            cfg_mgr.set("ai.companion_name", clean_name)
            cfg_mgr.set("companion.name", clean_name)
            cfg_mgr.set("character.name", clean_name)
            ai_service = getattr(app.state, "ai_service", None)
            if ai_service and hasattr(ai_service, "personality_manager"):
                ai_service.personality_manager.set_companion_name(clean_name)
            ws_manager.broadcast_sync("companion_name_changed", {"name": clean_name})
            ws_manager.broadcast_sync("companion_profile_updated", {"name": clean_name})
        elif req.key == "movies.tmdb_api_key":
            tmdb_client = getattr(app.state, "tmdb_client", None)
            if tmdb_client:
                tmdb_client.set_api_key(str(req.value))
        elif req.key in ("general.start_at_login", "general.start_with_windows"):
            try:
                from app.core import startup_manager
                startup_manager.set_startup_enabled(bool(req.value))
            except Exception as e:
                logger.warning("Failed setting startup in registry via API: %s", e)
        return {"status": "ok", "key": req.key, "value": req.value}

    def _on_config_reset(target_cfg: Optional[ConfigManager] = None) -> None:
        """Synchronize runtime systems when configuration is reset to factory defaults."""
        cfg = target_cfg or _get_config_manager()
        if not cfg:
            return

        # 1. Explicitly invoke set_startup_enabled(default_startup)
        try:
            from app.core import startup_manager
            default_startup = bool(
                cfg.get("general.start_at_login", False)
                or cfg.get("general.start_with_windows", False)
            )
            startup_manager.set_startup_enabled(default_startup)
            logger.info("Synchronized Windows startup state on config reset: %s", default_startup)
        except Exception as e:
            logger.warning("Failed setting startup in registry on config reset: %s", e)

        # 2. Re-initialize TMDBCredentialManager.refresh() and active TMDB client key
        try:
            from app.api.tmdb_credential_manager import TMDBCredentialManager
            key_mgr: Optional[TMDBCredentialManager] = getattr(app.state, "tmdb_key_manager", None)
            if key_mgr is None:
                key_mgr = TMDBCredentialManager(config_manager=cfg)
                app.state.tmdb_key_manager = key_mgr
            active_key, source, active_id = key_mgr.refresh()

            tmdb_client = getattr(app.state, "tmdb_client", None)
            if tmdb_client:
                tmdb_client.set_api_key(active_key or None)
                logger.info("TMDB client synchronized on config reset (source=%s, id=%s)", source, active_id)
        except Exception as e:
            logger.warning("Failed to refresh TMDB credentials on config reset: %s", e)

        # 3. Synchronize Personality Prompt Parameters & Companion Name
        try:
            ai_service = getattr(app.state, "ai_service", None)
            default_name = cfg.get("ai.companion_name") or cfg.get("companion.name", "Buddy")
            clean_name = str(default_name).strip() if default_name else "Buddy"
            if ai_service and hasattr(ai_service, "personality_manager") and ai_service.personality_manager:
                if hasattr(ai_service.personality_manager, "reload_from_config"):
                    ai_service.personality_manager.reload_from_config()
                else:
                    ai_service.personality_manager.set_companion_name(clean_name)
                    ai_service.personality_manager.set_personality(cfg.get("ai.personality", "friendly"))
            ws_manager.broadcast_sync("companion_name_changed", {"name": clean_name})
            ws_manager.broadcast_sync("companion_profile_updated", {"name": clean_name})
        except Exception as e:
            logger.warning("Failed to synchronize personality manager on config reset: %s", e)

        # 4. Notify VoiceService (voice speed, engine, voice, mode)
        try:
            voice_service = getattr(app.state, "voice_service", None)
            if voice_service:
                if hasattr(voice_service, "reload_from_config"):
                    voice_service.reload_from_config()
                else:
                    voice_cfg = cfg.get_category("voice") or cfg.get("voice", {})
                    if "voice_speed" in voice_cfg and hasattr(voice_service, "set_tts_speed"):
                        voice_service.set_tts_speed(float(voice_cfg["voice_speed"]))
                    eng = voice_cfg.get("tts_engine") or voice_cfg.get("engine")
                    if eng and hasattr(voice_service, "set_tts_engine"):
                        voice_service.set_tts_engine(str(eng))
                    if "tts_voice" in voice_cfg and hasattr(voice_service, "set_voice"):
                        voice_service.set_voice(str(voice_cfg["tts_voice"]))
                    if "mode" in voice_cfg and hasattr(voice_service, "set_mode"):
                        voice_service.set_mode(str(voice_cfg["mode"]))
                logger.info("Notified VoiceService on config reset")
        except Exception as e:
            logger.warning("Failed to notify VoiceService on config reset: %s", e)

    app.state._on_config_reset = _on_config_reset

    @app.post("/api/config/reset")
    async def reset_config_defaults() -> Dict[str, Any]:
        """Reset all configuration values to defaults."""
        cfg_mgr = _get_config_manager()
        if not cfg_mgr:
            raise HTTPException(status_code=500, detail="Config manager not available")
        cfg_mgr.reset_to_defaults()
        _on_config_reset(cfg_mgr)
        ws_manager.broadcast_sync("config_reset", {"status": "ok"})
        return {"status": "ok", "config": cfg_mgr.all_settings}

    @app.post("/api/config/batch")
    @app.put("/api/config/batch")
    async def update_config_batch(req: BatchConfigRequest) -> Dict[str, Any]:
        """Update multiple configuration keys atomically with debouncing."""
        cfg_mgr = _get_config_manager()
        if not cfg_mgr:
            raise HTTPException(status_code=500, detail="Config manager not available")
        batch_name = req.settings.get("ai.companion_name") or req.settings.get("companion.name") or req.settings.get("character.name")
        if batch_name:
            clean_name = str(batch_name).strip()
            req.settings["ai.companion_name"] = clean_name
            req.settings["companion.name"] = clean_name
            req.settings["character.name"] = clean_name
        cfg_mgr.set_many(req.settings, auto_save=True)
        ws_manager.broadcast_sync("config_batch_updated", {"settings": req.settings})
        if batch_name:
            clean_name = str(batch_name).strip()
            ai_service = getattr(app.state, "ai_service", None)
            if ai_service and hasattr(ai_service, "personality_manager"):
                ai_service.personality_manager.set_companion_name(clean_name)
            ws_manager.broadcast_sync("companion_name_changed", {"name": clean_name})
            ws_manager.broadcast_sync("companion_profile_updated", {"name": clean_name})
        if "movies.tmdb_api_key" in req.settings:
            tmdb_client = getattr(app.state, "tmdb_client", None)
            if tmdb_client:
                tmdb_client.set_api_key(str(req.settings["movies.tmdb_api_key"]))

        if "general.start_at_login" in req.settings or "general.start_with_windows" in req.settings:
            autostart_val = req.settings.get("general.start_at_login") if "general.start_at_login" in req.settings else req.settings.get("general.start_with_windows")
            try:
                from app.core import startup_manager
                startup_manager.set_startup_enabled(bool(autostart_val))
            except Exception as e:
                logger.warning("Failed setting startup in registry via API batch: %s", e)

        engine_val = req.settings.get("voice.engine") or req.settings.get("voice.tts_engine")
        if engine_val:
            voice_service = getattr(app.state, "voice_service", None)
            if voice_service and hasattr(voice_service, "set_tts_engine"):
                voice_service.set_tts_engine(str(engine_val))

        speed_val = req.settings.get("voice.speed") if "voice.speed" in req.settings else req.settings.get("voice.voice_speed")
        if speed_val is not None:
            voice_service = getattr(app.state, "voice_service", None)
            if voice_service and hasattr(voice_service, "set_tts_speed"):
                try:
                    voice_service.set_tts_speed(float(speed_val))
                except Exception:
                    pass

        vol_val = req.settings.get("voice.volume")
        if vol_val is not None:
            voice_service = getattr(app.state, "voice_service", None)
            if voice_service and hasattr(voice_service, "set_volume"):
                try:
                    v = float(vol_val)
                    if v > 1.0:
                        v /= 100.0
                    voice_service.set_volume(max(0.0, min(1.0, v)))
                except Exception:
                    pass

        pers_val = req.settings.get("ai.personality")
        if pers_val:
            ai_service = getattr(app.state, "ai_service", None)
            if ai_service and hasattr(ai_service, "personality_manager"):
                ai_service.personality_manager.set_personality(str(pers_val))

        host_val = req.settings.get("ai.ollama_host")
        if host_val:
            ai_service = getattr(app.state, "ai_service", None)
            if ai_service and hasattr(ai_service, "client"):
                ai_service.client.set_base_url(str(host_val))

        return {"status": "ok", "updated": list(req.settings.keys())}

    # ─── Conversations ────────────────────────────────────────────────────────

    @app.get("/api/conversations")
    async def list_conversations(limit: int = 50) -> List[Dict[str, Any]]:
        """List recent conversations sorted by latest activity."""
        repo: Optional[ConversationRepository] = getattr(app.state, "conv_repo", None)
        if not repo:
            return []
        convs = repo.list_conversations(limit=limit)
        return [
            {
                "id": c.id,
                "title": c.title,
                "created_at": c.created_at,
                "updated_at": c.updated_at,
                "message_count": c.message_count,
            }
            for c in convs
        ]

    @app.post("/api/conversations")
    async def create_conversation(req: CreateConversationRequest) -> Dict[str, Any]:
        """Create a new conversational session."""
        repo: Optional[ConversationRepository] = getattr(app.state, "conv_repo", None)
        if not repo:
            raise HTTPException(status_code=500, detail="Repository unavailable")
        conv = repo.create_conversation(title=req.title)
        return {
            "id": conv.id,
            "title": conv.title,
            "created_at": conv.created_at,
            "updated_at": conv.updated_at,
            "message_count": 0,
        }

    @app.patch("/api/conversations/{conv_id}")
    @app.patch("/api/conversations/{conv_id}/title")
    async def rename_conversation(conv_id: str, req: RenameConversationRequest) -> Dict[str, Any]:
        """Rename an existing conversation."""
        repo: Optional[ConversationRepository] = getattr(app.state, "conv_repo", None)
        if not repo:
            raise HTTPException(status_code=500, detail="Repository unavailable")
        success = repo.rename_conversation(conv_id, req.title)
        if not success:
            raise HTTPException(status_code=404, detail="Conversation not found or invalid title")
        return {"status": "ok", "id": conv_id, "title": req.title}

    @app.delete("/api/conversations/{conv_id}")
    async def delete_conversation(conv_id: str) -> Dict[str, Any]:
        """Delete a conversation and its messages."""
        repo: Optional[ConversationRepository] = getattr(app.state, "conv_repo", None)
        if not repo:
            raise HTTPException(status_code=500, detail="Repository unavailable")
        success = repo.delete_conversation(conv_id)
        return {"status": "ok", "deleted": success, "id": conv_id}

    # ─── Messages & Chat ──────────────────────────────────────────────────────

    @app.get("/api/conversations/{conv_id}/messages")
    async def get_messages(conv_id: str) -> List[Dict[str, Any]]:
        """Fetch all messages for a specific conversation session."""
        repo: Optional[ConversationRepository] = getattr(app.state, "conv_repo", None)
        if not repo:
            return []

        app.state.active_conversation_id = conv_id
        ai_service = getattr(app.state, "ai_service", None)
        if ai_service:
            ai_service.active_conversation_id = conv_id
            if repo and not getattr(ai_service, "conv_repo", None):
                ai_service.conv_repo = repo
        ctrl = getattr(app.state, "controller", None)
        if ctrl and hasattr(ctrl, "ai_service") and ctrl.ai_service:
            ctrl.ai_service.active_conversation_id = conv_id
            if repo and not getattr(ctrl.ai_service, "conv_repo", None):
                ctrl.ai_service.conv_repo = repo

        msgs = repo.get_messages(conv_id)
        return [
            {
                "id": m.id,
                "conversation_id": m.conversation_id,
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at,
                "status": m.status,
                "feedback": getattr(m, "feedback", None),
            }
            for m in msgs
        ]

    @app.post("/api/conversations/{conv_id}/messages")
    async def send_message(conv_id: str, req: SendMessageRequest) -> Dict[str, Any]:
        """Post a user message and trigger local AI generation."""
        t_backend_received = time.perf_counter()
        req_id = req.request_id or f"req_{int(time.time() * 1000)}_{os.urandom(3).hex()}"
        repo: Optional[ConversationRepository] = getattr(app.state, "conv_repo", None)
        ai_service = getattr(app.state, "ai_service", None)
        if not repo:
            raise HTTPException(status_code=500, detail="Repository unavailable")

        cleaned = req.content.strip()
        if not cleaned:
            if req.images or req.attachments:
                cleaned = "Please analyze and process the attached file(s)."
            else:
                raise HTTPException(status_code=400, detail="User message content cannot be empty.")

        try:
            from app.core.diagnostic_mode import diagnostic_tracker
            diagnostic_tracker.update_submission("submitting")
        except Exception:
            pass

        logger.info("[BOUNDARY] Request received by backend: req_id=%s, conv_id=%s, is_voice=%s", req_id, conv_id, req.is_voice)

        # Guard against duplicate concurrent submissions of the exact same message
        if ai_service and getattr(ai_service, "_is_generating", False) and cleaned == getattr(ai_service, "_last_user_prompt", ""):
            logger.warning("[DIAGNOSTIC] Duplicate request rejected: Prompt '%s' already in-flight.", cleaned)
            return {
                "status": "duplicate_rejected",
                "message": "Duplicate request ignored — already processing your message.",
                "recovery_action": "none",
                "request_id": req_id,
                "user_message_id": None,
                "assistant_message_id": getattr(app.state, "current_assistant_msg_id", None),
                "generation_id": getattr(ai_service, "_current_gen_id", 0),
            }

        # If companion is sleeping, check if incoming text message is an intentional wake command
        from app.core.buddy_state_manager import get_buddy_state_manager
        buddy_sm = get_buddy_state_manager()
        if buddy_sm.is_sleeping:
            from app.voice.command_dispatcher import VoiceCommandParser
            parsed = VoiceCommandParser.parse(cleaned)
            compound = VoiceCommandParser.extract_wake_and_prompt(cleaned)
            if (parsed and parsed.intent == "wake") or (compound and compound[0]):
                buddy_sm.wake_up(reason="text_wake")
                signals.wake_requested.emit()
                signals.character_state_changed.emit("idle")

        # 1. Save user message to database
        user_msg = repo.add_message(
            conversation_id=conv_id,
            role="user",
            content=cleaned,
            status="completed",
        )

        # If user message was identified as a duplicate turn, abort without creating an assistant placeholder
        if getattr(user_msg, "_is_duplicate", False):
            logger.warning("[DIAGNOSTIC] Duplicate user message rejected by repository. Aborting assistant placeholder insertion.")
            return {
                "status": "duplicate_rejected",
                "message": "Duplicate request ignored — already processing your message.",
                "recovery_action": "none",
                "user_message_id": user_msg.id,
                "assistant_message_id": getattr(app.state, "current_assistant_msg_id", None),
                "generation_id": getattr(ai_service, "_current_gen_id", 0),
            }

        # 2. Insert placeholder assistant message in streaming state
        assistant_msg = repo.add_message(
            conversation_id=conv_id,
            role="assistant",
            content="",
            status="streaming",
        )

        # Notify UI of added messages
        ws_manager.broadcast_sync("message_added", {
            "message": {
                "id": user_msg.id,
                "conversation_id": user_msg.conversation_id,
                "role": user_msg.role,
                "content": user_msg.content,
                "created_at": user_msg.created_at,
                "status": user_msg.status,
                "attachments": req.attachments,
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

        # 3. Track active conversation & trigger AI generation
        gen_id = 0
        if ai_service:
            ai_service.active_conversation_id = conv_id
            app.state.current_assistant_msg_id = assistant_msg.id
            app.state.current_conv_id = conv_id
            app.state.current_request_id = req_id
            ctrl = getattr(app.state, "controller", None)
            if ctrl:
                ctrl.current_assistant_msg_id = assistant_msg.id
                ctrl.current_conv_id = conv_id
                ctrl.current_request_id = req_id
            gen_id = ai_service.ask(
                user_prompt=cleaned,
                is_voice=req.is_voice or False,
                response_style=req.response_style,
                request_id=req_id,
                backend_received_time=t_backend_received,
                client_timestamp=req.client_timestamp,
                images=req.images,
                attachments=req.attachments,
            )

        routing_info = None
        if ai_service and hasattr(ai_service, "get_last_routing_decision"):
            dec = ai_service.get_last_routing_decision()
            if dec:
                routing_info = dec.to_dict()

        try:
            from app.core.diagnostic_mode import diagnostic_tracker
            diagnostic_tracker.update_submission("submitted")
        except Exception:
            pass

        return {
            "status": "dispatched",
            "request_id": req_id,
            "user_message_id": user_msg.id,
            "assistant_message_id": assistant_msg.id,
            "generation_id": gen_id,
            "backend_received_time": t_backend_received,
            "routing": routing_info,
        }

    # ─── File Upload & Attachment Processing (Phase 6) ───────────────────────

    try:
        import multipart  # type: ignore # noqa: F401
        has_multipart = True
    except ImportError:
        has_multipart = False

    if has_multipart:
        @app.post("/api/upload")
        async def upload_file(file: UploadFile = File(...)) -> Dict[str, Any]:
            """Validate, store securely, and extract multimodal/text context from an uploaded file."""
            if not file.filename:
                raise HTTPException(status_code=400, detail="Filename missing.")

            content = await file.read()
            is_valid, err_msg, cat = AttachmentProcessor.validate_file(file.filename, content)
            if not is_valid:
                raise HTTPException(status_code=400, detail=err_msg or "Invalid file format or size.")

            try:
                whisper_eng = getattr(app.state, "whisper_engine", None)
                if not whisper_eng:
                    vs = getattr(app.state, "voice_service", None)
                    if vs and hasattr(vs, "whisper_engine"):
                        whisper_eng = vs.whisper_engine

                attachment_data = AttachmentProcessor.process_attachment(
                    filename=file.filename,
                    content_bytes=content,
                    save_to_disk=True,
                    whisper_engine=whisper_eng,
                )
                return {"status": "ok", "attachment": attachment_data}
            except Exception as e:
                logger.error("Failed processing attachment '%s': %s", file.filename, e)
                raise HTTPException(status_code=500, detail=f"Failed to process attachment: {e}")

        @app.post("/api/upload/multiple")
        async def upload_multiple_files(files: List[UploadFile] = File(...)) -> Dict[str, Any]:
            """Upload, validate, and process multiple media/document attachments concurrently."""
            if not files:
                raise HTTPException(status_code=400, detail="No files provided.")

            if len(files) > 10:
                raise HTTPException(status_code=400, detail="Maximum 10 files per message allowed.")

            whisper_eng = getattr(app.state, "whisper_engine", None)
            if not whisper_eng:
                vs = getattr(app.state, "voice_service", None)
                if vs and hasattr(vs, "whisper_engine"):
                    whisper_eng = vs.whisper_engine

            processed_list = []
            total_size = 0

            for f in files:
                content = await f.read()
                is_valid, err_msg, cat = AttachmentProcessor.validate_file(
                    filename=f.filename or "unknown",
                    content_bytes=content,
                    existing_total_size=total_size,
                    existing_file_count=len(processed_list),
                )
                if not is_valid:
                    raise HTTPException(status_code=400, detail=f"Error in '{f.filename}': {err_msg}")

                total_size += len(content)
                att_data = AttachmentProcessor.process_attachment(
                    filename=f.filename or "unknown",
                    content_bytes=content,
                    save_to_disk=True,
                    whisper_engine=whisper_eng,
                )
                processed_list.append(att_data)

            return {"status": "ok", "attachments": processed_list}
    else:
        @app.post("/api/upload")
        async def upload_file_unavailable() -> Dict[str, Any]:
            raise HTTPException(status_code=503, detail="File upload unavailable: python-multipart is not installed.")

        @app.post("/api/upload/multiple")
        async def upload_multiple_unavailable() -> Dict[str, Any]:
            raise HTTPException(status_code=503, detail="File upload unavailable: python-multipart is not installed.")

    @app.delete("/api/upload/{attachment_id}")
    async def remove_upload(attachment_id: str) -> Dict[str, Any]:
        """Delete temporary file from safe storage upon user removal."""
        upload_dir = get_temp_upload_dir()
        found = False
        for f in upload_dir.glob(f"{attachment_id}_*"):
            try:
                f.unlink(missing_ok=True)
                found = True
            except Exception:
                pass
        return {"status": "ok", "deleted": found, "attachment_id": attachment_id}

    @app.delete("/api/conversations/{conv_id}/messages")
    async def clear_messages(conv_id: str) -> Dict[str, Any]:
        """Clear all messages in a conversation."""
        repo: Optional[ConversationRepository] = getattr(app.state, "conv_repo", None)
        if not repo:
            raise HTTPException(status_code=500, detail="Repository unavailable")
        repo.clear_conversation_messages(conv_id)
        return {"status": "ok", "cleared": True, "id": conv_id}

    @app.post("/api/messages/{message_id}/feedback")
    @app.put("/api/messages/{message_id}/feedback")
    @app.post("/api/conversations/{conv_id}/messages/{message_id}/feedback")
    @app.put("/api/conversations/{conv_id}/messages/{message_id}/feedback")
    async def update_message_feedback(
        message_id: int,
        req: FeedbackRequest,
        conv_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Store or clear like/dislike rating on an assistant message and train style preferences."""
        repo: Optional[ConversationRepository] = getattr(app.state, "conv_repo", None)
        if not repo:
            raise HTTPException(status_code=500, detail="Repository unavailable")

        target_msg_id = message_id
        success = repo.set_message_feedback(target_msg_id, req.feedback)
        if not success:
            # If message_id was a temporary client timestamp, attempt resolving to the latest assistant message
            active_conv = conv_id or getattr(app.state, "current_conv_id", None)
            if active_conv:
                latest_msg = repo.get_latest_assistant_message(active_conv)
                if latest_msg:
                    target_msg_id = latest_msg.id
                    success = repo.set_message_feedback(target_msg_id, req.feedback)

        if not success:
            raise HTTPException(status_code=404, detail=f"Message #{message_id} not found")

        # Broadcast feedback update to all connected frontend clients
        ws_manager.broadcast_sync("message_feedback_updated", {
            "message_id": target_msg_id,
            "feedback": req.feedback,
            "conversation_id": conv_id,
        })

        return {
            "status": "ok",
            "message_id": target_msg_id,
            "feedback": req.feedback,
        }

    @app.delete("/api/messages/{message_id}")
    @app.delete("/api/conversations/{conv_id}/messages/{message_id}")
    async def delete_message(
        message_id: int,
        pair: bool = Query(True, description="Delete both the message and its paired turn"),
        conv_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Delete a message and optionally its corresponding response/prompt from database."""
        repo: Optional[ConversationRepository] = getattr(app.state, "conv_repo", None)
        if not repo:
            raise HTTPException(status_code=500, detail="Repository unavailable")

        msg = repo.get_message(message_id)
        if not msg:
            raise HTTPException(status_code=404, detail=f"Message #{message_id} not found")

        c_id = conv_id or msg.conversation_id
        if pair:
            deleted_ids = repo.delete_message_pair(message_id)
        else:
            repo.delete_message(message_id)
            deleted_ids = [message_id]

        ws_manager.broadcast_sync("message_deleted", {
            "message_ids": deleted_ids,
            "conversation_id": c_id,
        })
        return {"status": "ok", "deleted": True, "message_ids": deleted_ids, "conversation_id": c_id}

    @app.patch("/api/messages/{message_id}")
    @app.put("/api/messages/{message_id}")
    @app.patch("/api/conversations/{conv_id}/messages/{message_id}")
    async def update_message(
        message_id: int,
        req: UpdateMessageRequest,
        conv_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update content of a user or assistant message in SQLite database."""
        repo: Optional[ConversationRepository] = getattr(app.state, "conv_repo", None)
        if not repo:
            raise HTTPException(status_code=500, detail="Repository unavailable")

        clean_text = req.content.strip()
        if not clean_text:
            raise HTTPException(status_code=400, detail="Message content cannot be empty")

        msg = repo.get_message(message_id)
        if not msg:
            raise HTTPException(status_code=404, detail=f"Message #{message_id} not found")

        c_id = conv_id or msg.conversation_id
        repo.update_message_content(message_id, clean_text, status=msg.status)

        ws_manager.broadcast_sync("message_updated", {
            "message_id": message_id,
            "content": clean_text,
            "role": msg.role,
            "status": msg.status,
            "conversation_id": c_id,
        })
        return {"status": "ok", "id": message_id, "content": clean_text, "conversation_id": c_id}

    @app.post("/api/messages/{message_id}/retry")
    @app.post("/api/conversations/{conv_id}/messages/{message_id}/retry")
    async def retry_message(
        message_id: int,
        req: Optional[RetryMessageRequest] = Body(default=None),
        conv_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Regenerate ONLY this assistant response without removing any messages."""
        repo: Optional[ConversationRepository] = getattr(app.state, "conv_repo", None)
        ai_service = getattr(app.state, "ai_service", None)
        if not repo or not ai_service:
            raise HTTPException(status_code=500, detail="AI Service or Repository unavailable")

        msg = repo.get_message(message_id)
        if not msg:
            raise HTTPException(status_code=404, detail=f"Message #{message_id} not found")

        c_id = conv_id or msg.conversation_id

        if msg.role == "assistant":
            assistant_msg_id = msg.id
            if req and req.prompt and req.prompt.strip():
                prompt_to_run = req.prompt.strip()
            else:
                paired_user = repo.get_paired_user_message(message_id)
                prompt_to_run = paired_user.content if paired_user else getattr(ai_service, "_last_user_prompt", "")
        else:
            prompt_to_run = (req.prompt.strip() if req and req.prompt and req.prompt.strip() else msg.content)
            if prompt_to_run != msg.content:
                repo.update_message_content(msg.id, prompt_to_run, status="completed")
            paired_assistant = repo.get_paired_assistant_message(msg.id)
            if paired_assistant:
                assistant_msg_id = paired_assistant.id
            else:
                new_assistant = repo.add_message(c_id, role="assistant", content="", status="streaming")
                assistant_msg_id = new_assistant.id

        if not prompt_to_run:
            raise HTTPException(status_code=400, detail="Could not determine prompt to retry.")

        # Reset target assistant message to empty streaming state in DB
        repo.update_message_content(assistant_msg_id, "", status="streaming")

        # Notify frontend: reset this message to streaming
        ws_manager.broadcast_sync("message_updated", {
            "message_id": assistant_msg_id,
            "content": "",
            "status": "streaming",
            "role": "assistant",
            "conversation_id": c_id,
        })

        # Set active assistant message target
        app.state.current_assistant_msg_id = assistant_msg_id
        app.state.current_conv_id = c_id
        ctrl = getattr(app.state, "controller", None)
        if ctrl:
            ctrl.current_assistant_msg_id = assistant_msg_id
            ctrl.current_conv_id = c_id

        ai_service.active_conversation_id = c_id
        gen_id = ai_service.ask(
            user_prompt=prompt_to_run,
            is_voice=False,
        )

        return {
            "status": "dispatched",
            "assistant_message_id": assistant_msg_id,
            "generation_id": gen_id,
            "conversation_id": c_id,
        }

    @app.post("/api/clipboard/copy")
    async def copy_to_clipboard(req: ClipboardRequest) -> Dict[str, Any]:
        """Copy text reliably to native OS clipboard across platforms."""
        import sys
        success = False
        # 1. Try PySide6 QGuiApplication clipboard
        try:
            from PySide6.QtGui import QGuiApplication
            clip = QGuiApplication.clipboard()
            if clip:
                clip.setText(req.text)
                success = True
        except Exception:
            pass

        # 2. Try Windows ctypes OpenClipboard fallback (64-bit safe)
        if not success and sys.platform == "win32":
            try:
                import ctypes
                user32 = ctypes.windll.user32
                kernel32 = ctypes.windll.kernel32
                kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
                kernel32.GlobalAlloc.restype = ctypes.c_void_p
                kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
                kernel32.GlobalLock.restype = ctypes.c_void_p
                kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
                user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
                user32.SetClipboardData.restype = ctypes.c_void_p
                GMEM_MOVEABLE = 0x0002
                CF_UNICODETEXT = 13
                if user32.OpenClipboard(None):
                    user32.EmptyClipboard()
                    text_bytes = (req.text + "\0").encode("utf-16le")
                    h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(text_bytes))
                    if h_mem:
                        ptr = kernel32.GlobalLock(h_mem)
                        if ptr:
                            ctypes.memmove(ptr, text_bytes, len(text_bytes))
                            kernel32.GlobalUnlock(h_mem)
                            if user32.SetClipboardData(CF_UNICODETEXT, h_mem):
                                success = True
                    user32.CloseClipboard()
            except Exception:
                pass

        return {"status": "ok" if success else "fallback_used", "copied": success}

    # ─── AI Inference Control ─────────────────────────────────────────────────

    @app.post("/api/ai/cancel")
    async def cancel_ai() -> Dict[str, Any]:
        """Cancel ongoing AI response generation."""
        ai_service = getattr(app.state, "ai_service", None)
        if ai_service:
            ai_service.cancel_generation()
        else:
            signals.ai_generation_cancelled.emit()
            ws_manager.broadcast_sync("ai_cancelled", {})
        return {"status": "ok", "cancelled": True}

    @app.post("/api/recovery/action")
    async def execute_recovery_action(req: RecoveryActionRequest) -> Dict[str, Any]:
        """Execute a user-directed recovery action from an error dialog/banner."""
        import sys
        action = req.action.lower().strip()
        logger.info("[RECOVERY] Executing recovery action '%s' with payload: %s", action, req.payload)

        if action in ("open_settings", "open_privacy_settings"):
            if sys.platform == "win32":
                try:
                    os.system("start ms-settings:privacy-microphone")
                except Exception as e:
                    logger.debug("Could not open Windows privacy settings: %s", e)
            signals.open_settings_requested.emit()
            return {"status": "ok", "action": action, "executed": True}

        elif action in ("select_model", "open_model_settings"):
            signals.open_settings_requested.emit()
            return {"status": "ok", "action": action, "target": "model", "executed": True}

        elif action in ("retry_device", "retry_voice"):
            ctrl = getattr(app.state, "controller", None)
            if ctrl and hasattr(ctrl, "voice_service") and ctrl.voice_service:
                try:
                    import sounddevice as sd
                    sd._terminate()
                    sd._initialize()
                    ctrl.voice_service.mic_manager.get_input_devices()
                    ctrl.voice_service.set_mode("wake_word")
                    return {"status": "ok", "action": action, "executed": True}
                except Exception as e:
                    return {"status": "error", "message": str(e)}
            return {"status": "ok", "action": action, "executed": True}

        elif action in ("retry_playback", "retry_speaker"):
            ctrl = getattr(app.state, "controller", None)
            if ctrl and hasattr(ctrl, "voice_service") and ctrl.voice_service:
                try:
                    import sounddevice as sd
                    sd._terminate()
                    sd._initialize()
                    if hasattr(ctrl.voice_service, "audio_player") and ctrl.voice_service.audio_player:
                        ctrl.voice_service.audio_player.stop()
                    return {"status": "ok", "action": action, "executed": True}
                except Exception as e:
                    return {"status": "error", "message": str(e)}
            return {"status": "ok", "action": action, "executed": True}

        elif action in ("fallback_tts", "default_voice"):
            ctrl = getattr(app.state, "controller", None)
            if ctrl and hasattr(ctrl, "config_manager") and ctrl.config_manager:
                try:
                    ctrl.config_manager.set("voice.engine", "sapi5")
                    ctrl.config_manager.save()
                    return {"status": "ok", "action": action, "engine": "sapi5", "executed": True}
                except Exception as e:
                    return {"status": "error", "message": str(e)}
            return {"status": "ok", "action": action, "engine": "sapi5", "executed": True}

        elif action in ("start_ollama", "retry_ollama"):
            ai_service = getattr(app.state, "ai_service", None)
            if ai_service and hasattr(ai_service, "model_manager") and hasattr(ai_service.model_manager, "supervisor"):
                ai_service.model_manager.supervisor.ensure_server_running(ai_service.client.base_url, timeout=3.0)
                is_up = ai_service.model_manager.is_available()
                return {"status": "ok", "action": action, "online": is_up}
            return {"status": "ok", "action": action, "executed": True}

        elif action in ("retry_request", "retry"):
            prompt = req.payload.get("prompt") if req.payload else None
            ctrl = getattr(app.state, "controller", None)
            if prompt and ctrl and hasattr(ctrl, "ai_service") and ctrl.ai_service:
                try:
                    ctrl.ai_service.generate_response(prompt)
                    return {"status": "ok", "action": action, "prompt": prompt, "executed": True}
                except Exception as e:
                    return {"status": "error", "message": str(e)}
            return {"status": "ok", "action": action, "executed": True}

        elif action == "listen_again":
            ctrl = getattr(app.state, "controller", None)
            if ctrl and hasattr(ctrl, "voice_service") and ctrl.voice_service:
                conv_ctrl = getattr(ctrl.voice_service, "conversation_controller", None)
                if conv_ctrl:
                    from app.voice.conversation_state import ConversationState
                    conv_ctrl.vad_engine.reset_states()
                    conv_ctrl._transition_to(ConversationState.LISTENING)
            return {"status": "ok", "action": action, "executed": True}

        return {"status": "unknown_action", "action": action}

    @app.get("/api/models")
    async def get_models() -> Dict[str, Any]:
        """Fetch available Ollama models and currently active selection."""
        ai_service = getattr(app.state, "ai_service", None)
        if not ai_service or not hasattr(ai_service, "model_manager"):
            return {"active_model": "llama3.2:latest", "available_models": ["llama3.2:latest"], "models": []}

        model_mgr = ai_service.model_manager
        available = model_mgr.get_installed_models() if hasattr(model_mgr, "get_installed_models") else ["llama3.2:latest"]
        if not available:
            available = ["llama3.2:latest"]
        active = model_mgr.active_model
        profiles = []
        if hasattr(model_mgr, "capability_registry"):
            try:
                profiles = [m.to_dict() for m in model_mgr.capability_registry.get_all_models()]
            except Exception as e:
                logger.debug("Profiles serialization notice: %s", e)

        return {
            "active_model": active,
            "available_models": available,
            "is_online": model_mgr.is_available(),
            "models": profiles,
        }

    @app.get("/api/models/capabilities")
    async def get_model_capabilities() -> Dict[str, Any]:
        """Fetch centralized capability registry for all installed and discovered local models."""
        from app.ai.model_capability_registry import get_model_capability_registry
        ai_service = getattr(app.state, "ai_service", None)
        client = ai_service.client if ai_service and hasattr(ai_service, "client") else None
        reg = get_model_capability_registry(client=client)
        return reg.to_dict()

    @app.post("/api/models/select")
    async def select_model(req: SelectModelRequest) -> Dict[str, Any]:
        """Switch the active AI model."""
        ai_service = getattr(app.state, "ai_service", None)
        cfg_mgr: Optional[ConfigManager] = getattr(app.state, "config_manager", None)
        if cfg_mgr:
            cfg_mgr.set("ai.model", req.model)

        if ai_service and hasattr(ai_service, "model_manager"):
            if ai_service.model_manager.active_model != req.model:
                ai_service.model_manager.set_model(req.model)
            if hasattr(ai_service.model_manager, "capability_registry"):
                ai_service.model_manager.capability_registry.record_usage(req.model)

        ws_manager.broadcast_sync("model_changed", {"model": req.model})
        return {"status": "ok", "active_model": req.model}

    # ─── Model Benchmark Controls (Phase 3) ──────────────────────────────────

    @app.post("/api/models/benchmark/run")
    async def run_model_benchmark(req: RunBenchmarkRequest = RunBenchmarkRequest()) -> Dict[str, Any]:
        """Manually trigger controlled background benchmark across installed models."""
        from app.ai.model_benchmark_service import get_model_benchmark_runner
        ai_service = getattr(app.state, "ai_service", None)
        client = ai_service.client if ai_service and hasattr(ai_service, "client") else None
        runner = get_model_benchmark_runner(client=client)

        if runner.is_running:
            return {"status": "already_running", "progress": runner.get_progress()}

        def _on_progress(progress_data: Dict[str, Any]) -> None:
            ws_manager.broadcast_sync("benchmark_progress", progress_data)

        started = runner.start_benchmark(
            models=req.models,
            categories=req.categories,
            on_progress=_on_progress,
        )
        return {"status": "started" if started else "failed", "progress": runner.get_progress()}

    @app.post("/api/models/benchmark/cancel")
    async def cancel_model_benchmark() -> Dict[str, Any]:
        """Cancel an in-progress benchmark run."""
        from app.ai.model_benchmark_service import get_model_benchmark_runner
        runner = get_model_benchmark_runner()
        cancelled = runner.cancel()
        ws_manager.broadcast_sync("benchmark_cancelled", {"cancelled": cancelled})
        return {"status": "cancelled" if cancelled else "not_running"}

    @app.get("/api/models/benchmark/status")
    async def get_model_benchmark_status() -> Dict[str, Any]:
        """Get live execution status and progress of the benchmark suite."""
        from app.ai.model_benchmark_service import get_model_benchmark_runner
        runner = get_model_benchmark_runner()
        return runner.get_progress()

    @app.get("/api/models/benchmark/results")
    async def get_model_benchmark_results(
        model_id: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """Get persistent empirical benchmark results from SQLite."""
        from app.ai.model_benchmark_service import BenchmarkRepository
        repo = BenchmarkRepository()
        records = repo.get_records(model_id=model_id, category=category, limit=limit)
        summaries = repo.get_all_summaries()
        return {
            "records": [r.to_dict() for r in records],
            "summaries": summaries,
        }

    @app.get("/api/models/benchmark/recommendations")
    async def get_model_benchmark_recommendations() -> Dict[str, Any]:
        """Get evidenced task-based recommendations derived from benchmark performance."""
        from app.ai.model_capability_registry import get_model_capability_registry
        reg = get_model_capability_registry()
        return reg.get_benchmark_recommendations()

    @app.get("/api/models/router/status")
    async def get_model_router_status() -> Dict[str, Any]:
        """Fetch current intelligent model router status, active policy, and last decision."""
        from app.ai.model_router import get_model_router
        router = get_model_router()
        cfg_mgr: Optional[ConfigManager] = getattr(app.state, "config_manager", None)
        auto_routing = bool(cfg_mgr.get("ai.auto_model_routing", True)) if cfg_mgr else True
        ai_service = getattr(app.state, "ai_service", None)
        last_decision = None
        if ai_service and hasattr(ai_service, "get_last_routing_decision"):
            last_decision = ai_service.get_last_routing_decision()
        elif hasattr(router, "get_last_decision"):
            dec = router.get_last_decision()
            if dec:
                last_decision = dec.to_dict()

        return {
            "status": "ok",
            "auto_routing_enabled": auto_routing,
            "router": router.get_router_status(),
            "last_decision": last_decision,
        }

    @app.post("/api/models/router/toggle")
    async def toggle_model_router(req: RouterToggleRequest) -> Dict[str, Any]:
        """Enable or disable dynamic automatic model routing."""
        cfg_mgr: Optional[ConfigManager] = getattr(app.state, "config_manager", None)
        if cfg_mgr:
            cfg_mgr.set("ai.auto_model_routing", req.enabled)
            cfg_mgr.set("ai.model_selection_mode", "auto" if req.enabled else "manual")
        ws_manager.broadcast_sync("model_router_toggled", {"enabled": req.enabled})
        return {"status": "ok", "auto_routing_enabled": req.enabled}

    @app.get("/api/models/preferences")
    async def get_model_preferences() -> Dict[str, Any]:
        """Fetch model selection mode, response priority, and task preferences with compatible installed models."""
        cfg_mgr = _get_config_manager()
        ai_service = getattr(app.state, "ai_service", None)
        mode = "auto"
        priority = "balanced"
        task_prefs = {
            "general_conversation": "auto",
            "complex_reasoning": "auto",
            "coding": "auto",
            "document_summarization": "auto",
            "vision": "auto",
        }
        active_model = "llama3.2:3b"
        if cfg_mgr:
            mode = cfg_mgr.get("ai.model_selection_mode", "auto")
            priority = cfg_mgr.get("ai.response_priority", "balanced")
            task_prefs = cfg_mgr.get("ai.task_preferred_models", task_prefs)
            active_model = cfg_mgr.get("ai.model", active_model)

        compatible_by_task = {}
        is_manual_available = True
        installed_list = []
        if ai_service and hasattr(ai_service, "model_manager"):
            compatible_by_task = ai_service.model_manager.get_compatible_models_by_task()
            installed_list = ai_service.model_manager.get_installed_models()
            is_manual_available = (active_model in installed_list)
        else:
            from app.ai.model_router import get_model_router
            router = get_model_router()
            compatible_by_task = router.get_compatible_models_by_task()

        return {
            "status": "ok",
            "model_selection_mode": mode,
            "response_priority": priority,
            "task_preferred_models": task_prefs,
            "compatible_models_by_task": compatible_by_task,
            "active_model": active_model,
            "is_manual_model_available": is_manual_available,
            "available_models": installed_list or [active_model],
        }

    @app.post("/api/models/preferences")
    async def update_model_preferences(req: ModelPreferencesRequest) -> Dict[str, Any]:
        """Persist user model settings, priority, and task preferences."""
        cfg_mgr = _get_config_manager()
        ai_service = getattr(app.state, "ai_service", None)

        if cfg_mgr:
            if req.model_selection_mode is not None:
                cfg_mgr.set("ai.model_selection_mode", req.model_selection_mode)
                cfg_mgr.set("ai.auto_model_routing", (req.model_selection_mode.lower() == "auto"))
            if req.response_priority is not None:
                cfg_mgr.set("ai.response_priority", req.response_priority)
            if req.task_preferred_models is not None:
                cfg_mgr.set("ai.task_preferred_models", req.task_preferred_models)
            if req.manual_model:
                cfg_mgr.set("ai.model", req.manual_model)
                if ai_service and hasattr(ai_service, "model_manager"):
                    ai_service.model_manager.set_model(req.manual_model)

        ws_manager.broadcast_sync("model_preferences_updated", {
            "model_selection_mode": req.model_selection_mode,
            "response_priority": req.response_priority,
            "task_preferred_models": req.task_preferred_models,
            "manual_model": req.manual_model,
        })
        return {
            "status": "ok",
            "model_selection_mode": req.model_selection_mode,
            "response_priority": req.response_priority,
            "task_preferred_models": req.task_preferred_models,
            "manual_model": req.manual_model,
        }

    # ─── Voice Engine Controls ───────────────────────────────────────────────

    @app.get("/api/voice/status")
    async def get_voice_status() -> Dict[str, Any]:
        """Get current voice engine status and settings."""
        from app.core.buddy_state_manager import get_buddy_state_manager
        buddy_sm = get_buddy_state_manager()
        cfg_mgr = _get_config_manager()
        mic_permission = bool(cfg_mgr.get("privacy.microphone_permission_granted", True)) if cfg_mgr else True

        voice_service = getattr(app.state, "voice_service", None)
        if not voice_service:
            return {
                "mode": "off",
                "is_muted": buddy_sm.is_muted,
                "is_speaking": False,
                "is_recording": False,
                "device": None,
                "tts_enabled": not buddy_sm.is_sleeping,
                "is_sleeping": buddy_sm.is_sleeping,
                "operational_state": buddy_sm.state_name,
                "permission_granted": mic_permission,
            }

        mode_val = getattr(voice_service, "mode", "off")
        mode_str = mode_val.value if hasattr(mode_val, "value") else str(mode_val).lower().strip()
        is_muted = getattr(voice_service, "is_muted", False) or buddy_sm.is_muted
        mic_manager = getattr(voice_service, "mic_manager", None)
        is_recording = mic_manager.is_recording if mic_manager else False
        device_name = mic_manager.active_device_name if mic_manager else None

        return {
            "mode": mode_str,
            "is_muted": is_muted,
            "is_recording": is_recording,
            "device": device_name,
            "tts_enabled": getattr(voice_service, "tts_enabled", True) and not buddy_sm.is_sleeping,
            "is_sleeping": buddy_sm.is_sleeping,
            "operational_state": buddy_sm.state_name,
            "permission_granted": mic_permission,
        }

    @app.post("/api/voice/toggle")
    async def toggle_voice() -> Dict[str, Any]:
        """Toggle voice listening between active and off without signal inversion."""
        voice_service = getattr(app.state, "voice_service", None)
        cfg_mgr: Optional[ConfigManager] = getattr(app.state, "config_manager", None)
        from app.core.signals import signals

        def _to_mode_str(val: Any) -> str:
            if hasattr(val, "value"):
                return str(val.value).lower().strip()
            return str(val).lower().strip() if val is not None else "off"

        initial_mode = getattr(voice_service, "mode", None) if voice_service else None
        init_mode_str = _to_mode_str(initial_mode) if initial_mode is not None else None

        # Emit the toggle signal for UI and controller listeners
        signals.voice_toggle_requested.emit()

        if voice_service and hasattr(voice_service, "mode"):
            current_mode = voice_service.mode
            curr_mode_str = _to_mode_str(current_mode)

            # If a connected signal handler (e.g. ApplicationController._on_voice_toggle
            # or main_api.on_voice_toggle) already performed the mode transition,
            # respect the transition and do NOT invert it!
            if init_mode_str is not None and curr_mode_str != init_mode_str:
                if cfg_mgr and curr_mode_str != "off":
                    cfg_mgr.set("voice.mode", curr_mode_str)
                ws_manager.broadcast_sync("voice_state", {"state": curr_mode_str})
                return {"status": "ok", "mode": curr_mode_str}

            # If no signal handler transitioned the mode (e.g. in a decoupled or test environment),
            # execute the toggle directly here:
            from app.voice.voice_service import VoiceMode
            is_off = (
                curr_mode_str == "off"
                or current_mode == VoiceMode.OFF
                or curr_mode_str.endswith(".off")
            )

            if is_off:
                target_mode = "continuous"
                if cfg_mgr:
                    target_mode = cfg_mgr.get("voice.mode", "continuous")
                if not target_mode or target_mode == "off":
                    target_mode = "continuous"

                voice_service.set_mode(target_mode)
                actual_mode = voice_service.mode
                actual_mode_str = _to_mode_str(actual_mode)
                if cfg_mgr and actual_mode_str != "off":
                    cfg_mgr.set("voice.mode", actual_mode_str)
                signals.voice_state_changed.emit(actual_mode_str)
                ws_manager.broadcast_sync("voice_state", {"state": actual_mode_str})
                status_res = "ok" if actual_mode_str != "off" else "error"
                return {"status": status_res, "mode": actual_mode_str}
            else:
                voice_service.set_mode(VoiceMode.OFF)
                signals.voice_state_changed.emit("off")
                ws_manager.broadcast_sync("voice_state", {"state": "off"})
                return {"status": "ok", "mode": "off"}

        return {"status": "ok", "mode": "off"}

    @app.post("/api/voice/mode")
    async def set_voice_mode(req: VoiceModeRequest) -> Dict[str, Any]:
        """Set active voice interaction mode ('off', 'push_to_talk', 'continuous')."""
        voice_service = getattr(app.state, "voice_service", None)
        cfg_mgr: Optional[ConfigManager] = getattr(app.state, "config_manager", None)
        mode_clean = req.mode.lower().strip()
        if voice_service:
            voice_service.set_mode(mode_clean)
            actual_mode = voice_service.mode
            actual_mode_str = getattr(actual_mode, "value", str(actual_mode)).lower().strip()
            if cfg_mgr and actual_mode_str != "off":
                cfg_mgr.set("voice.mode", actual_mode_str)
            from app.core.signals import signals
            signals.voice_state_changed.emit(actual_mode_str)
            ws_manager.broadcast_sync("voice_state", {"state": actual_mode_str})
            status_res = "ok" if actual_mode_str == mode_clean else "error"
            return {"status": status_res, "mode": actual_mode_str}
        return {"status": "error", "message": "Voice service unavailable"}

    @app.post("/api/voice/ptt/start")
    async def start_ptt() -> Dict[str, Any]:
        """Begin push-to-talk microphone recording."""
        voice_service = getattr(app.state, "voice_service", None)
        if voice_service and hasattr(voice_service, "start_push_to_talk"):
            ok = voice_service.start_push_to_talk()
            if ok:
                ws_manager.broadcast_sync("voice_state", {"state": "listening"})
                return {"status": "ok", "recording": True}
            else:
                ws_manager.broadcast_sync("voice_state", {"state": "off"})
                return {"status": "error", "message": "Failed to start microphone recording", "recording": False}
        return {"status": "error", "message": "Voice service unavailable"}

    @app.post("/api/voice/ptt/stop")
    async def stop_ptt() -> Dict[str, Any]:
        """End push-to-talk recording, transcribe speech, and dispatch to assistant."""
        voice_service = getattr(app.state, "voice_service", None)
        if voice_service and hasattr(voice_service, "stop_push_to_talk"):
            voice_service.stop_push_to_talk()
            ws_manager.broadcast_sync("voice_state", {"state": "processing"})
            return {"status": "ok"}
        return {"status": "error", "message": "Voice service unavailable"}

    @app.post("/api/voice/dictate/start")
    async def start_voice_dictation() -> Dict[str, Any]:
        """Begin microphone dictation session specifically for search inputs (non-conversational)."""
        voice_service = getattr(app.state, "voice_service", None)
        if voice_service and hasattr(voice_service, "start_dictation"):
            ok = voice_service.start_dictation()
            if ok:
                return {"status": "ok", "recording": True}
            return {"status": "error", "message": "Microphone unavailable or permission denied", "recording": False}
        return {"status": "error", "message": "Voice service unavailable", "recording": False}

    @app.post("/api/voice/dictate/stop")
    async def stop_voice_dictation() -> Dict[str, Any]:
        """Stop dictation session, run local Faster-Whisper, and return recognized text without AI chat prompt dispatch."""
        voice_service = getattr(app.state, "voice_service", None)
        if voice_service and hasattr(voice_service, "stop_dictation"):
            import asyncio
            loop = asyncio.get_running_loop()
            text = await loop.run_in_executor(None, voice_service.stop_dictation)
            return {"status": "ok", "text": text}
        return {"status": "error", "message": "Voice service unavailable", "text": ""}

    @app.get("/api/voice/dictate/status")
    async def get_dictation_status() -> Dict[str, Any]:
        """Check whether voice dictation is currently active."""
        voice_service = getattr(app.state, "voice_service", None)
        is_dictating = bool(getattr(voice_service, "is_dictating", False))
        return {"status": "ok", "is_dictating": is_dictating}

    @app.post("/api/voice/engine")
    async def set_voice_engine(req: VoiceEngineRequest) -> Dict[str, Any]:
        """Switch active TTS speech synthesis engine ('piper' | 'kokoro' | 'system')."""
        voice_service = getattr(app.state, "voice_service", None)
        cfg_mgr: Optional[ConfigManager] = getattr(app.state, "config_manager", None)
        if voice_service and hasattr(voice_service, "set_tts_engine"):
            voice_service.set_tts_engine(req.engine)
        if cfg_mgr:
            cfg_mgr.set("voice.engine", req.engine)
        ws_manager.broadcast_sync("voice_engine_changed", {"engine": req.engine})
        return {"status": "ok", "engine": req.engine}

    @app.post("/api/voice/speed")
    async def set_voice_speed(req: VoiceSpeedRequest) -> Dict[str, Any]:
        """Set speech playback speed multiplier (0.5 to 2.0)."""
        voice_service = getattr(app.state, "voice_service", None)
        cfg_mgr: Optional[ConfigManager] = getattr(app.state, "config_manager", None)
        speed = max(0.5, min(2.0, float(req.speed)))
        if voice_service and hasattr(voice_service, "set_tts_speed"):
            voice_service.set_tts_speed(speed)
        if cfg_mgr:
            cfg_mgr.set("voice.voice_speed", speed)
        ws_manager.broadcast_sync("voice_speed_changed", {"speed": speed})
        return {"status": "ok", "speed": speed}

    @app.post("/api/voice/volume")
    async def set_voice_volume(req: VoiceVolumeRequest) -> Dict[str, Any]:
        """Set speaker output volume (0.0 to 1.0 or 0 to 100)."""
        voice_service = getattr(app.state, "voice_service", None)
        vol = float(req.volume)
        if vol > 1.0:
            vol = vol / 100.0
        vol = max(0.0, min(1.0, vol))
        if voice_service and hasattr(voice_service, "set_volume"):
            voice_service.set_volume(vol)
        cfg_mgr: Optional[ConfigManager] = getattr(app.state, "config_manager", None)
        if cfg_mgr:
            cfg_mgr.set("voice.volume", vol)
        ws_manager.broadcast_sync("voice_volume_changed", {"volume": vol})
        return {"status": "ok", "volume": vol}

    @app.get("/api/voice/devices")
    async def get_voice_devices() -> Dict[str, Any]:
        """List available microphone and speaker hardware."""
        input_devices: List[str] = []
        try:
            from app.voice.microphone_manager import MicrophoneManager
            devs = MicrophoneManager.get_input_devices()
            input_devices = [d.display_name() for d in devs]
        except Exception as e:
            logger.debug("Failed querying audio devices: %s", e)
        return {
            "input_devices": input_devices or ["Default Microphone"],
            "output_devices": ["Default Speaker"],
        }

    @app.post("/api/voice/stop")
    async def stop_voice() -> Dict[str, Any]:
        """Stop current speech synthesis, active AI generation, and listening immediately."""
        ai_service = getattr(app.state, "ai_service", None)
        if ai_service and hasattr(ai_service, "cancel_generation"):
            ai_service.cancel_generation()

        voice_service = getattr(app.state, "voice_service", None)
        if voice_service:
            if hasattr(voice_service, "stop_speaking"):
                voice_service.stop_speaking()
            if hasattr(voice_service, "emergency_stop"):
                voice_service.emergency_stop()

        from app.core.signals import signals
        signals.ai_cancel_requested.emit()
        signals.emergency_stop_requested.emit()
        ws_manager.broadcast_sync("voice_state", {"state": "off"})
        return {"status": "ok"}

    @app.post("/api/voice/mute")
    async def mute_voice(req: VoiceMuteRequest) -> Dict[str, Any]:
        """Mute or unmute voice audio output."""
        voice_service = getattr(app.state, "voice_service", None)
        if voice_service and hasattr(voice_service, "set_muted"):
            voice_service.set_muted(req.muted)
        ws_manager.broadcast_sync("voice_mute_changed", {"muted": req.muted})
        return {"status": "ok", "muted": req.muted}

    @app.post("/api/voice/test")
    async def test_voice(req: TestVoiceRequest) -> Dict[str, Any]:
        """Play a short TTS test voice clip using the active or requested voice profile."""
        voice_service = getattr(app.state, "voice_service", None)
        if not voice_service:
            ctrl = getattr(app.state, "controller", None)
            if ctrl and hasattr(ctrl, "voice_service"):
                voice_service = ctrl.voice_service
        if voice_service:
            target_profile = req.profile_id or req.voice_profile or req.voice or getattr(voice_service, "selected_voice_profile", "arjun")
            target_lang = req.language or "en"
            if hasattr(voice_service, "play_voice_preview"):
                voice_service.play_voice_preview(target_profile, language=target_lang, text=req.text)
                return {"status": "ok", "speaking": True, "profile_id": target_profile, "language": target_lang}
            elif hasattr(voice_service, "speak"):
                voice_service.speak(req.text or "Testing voice synthesizer.")
                return {"status": "ok", "speaking": True}
        return {"status": "voice_service_unavailable"}

    @app.post("/api/voice/preview")
    async def preview_voice(req: VoicePreviewRequest) -> Dict[str, Any]:
        """Play an instant voice preview for one of the 5 companion voice profiles."""
        voice_service = getattr(app.state, "voice_service", None)
        if not voice_service:
            ctrl = getattr(app.state, "controller", None)
            if ctrl and hasattr(ctrl, "voice_service"):
                voice_service = ctrl.voice_service
        if voice_service and hasattr(voice_service, "play_voice_preview"):
            voice_service.play_voice_preview(req.profile_id, language=req.language, text=req.text)
            return {"status": "ok", "profile_id": req.profile_id, "language": req.language}
        return {"status": "voice_service_unavailable"}

    @app.get("/api/voice/profiles")
    async def get_voice_profiles() -> Dict[str, Any]:
        """Return the 5 distinct companion voice profiles."""
        from app.voice.voice_registry import list_voice_profiles
        profiles = [p.to_dict() for p in list_voice_profiles()]
        return {"status": "ok", "profiles": profiles}

    @app.get("/api/language/preview")
    async def get_language_preview(
        language: str = Query("gu", description="Language code"),
        format: str = Query("native", description="Format ('native' or 'romanized')"),
    ) -> Dict[str, Any]:
        """Generate live test preview text using the application's actual formatting and transliteration pipeline."""
        from app.ai.multilingual_engine import MultilingualEngine
        return MultilingualEngine.generate_language_preview(target_language=language, target_format=format)

    @app.get("/api/voice/capability")
    async def get_tts_capability(
        language: str = Query("auto", description="Target language code"),
    ) -> Dict[str, Any]:
        """Check active TTS engine capability for the selected language."""
        from app.ai.multilingual_engine import MultilingualEngine
        cfg_mgr: Optional[ConfigManager] = _get_config_manager()
        eng = "system"
        if cfg_mgr:
            eng = cfg_mgr.get("voice.engine", "system")
        voice_service = getattr(app.state, "voice_service", None)
        installed_voices = None
        if voice_service and hasattr(voice_service, "get_available_voices"):
            try:
                installed_voices = [v.name if hasattr(v, "name") else str(v) for v in voice_service.get_available_voices()]
            except Exception:
                pass
        return MultilingualEngine.check_tts_capability(engine_name=eng, target_language=language, installed_voices=installed_voices)

    # ─── Character Companion State ───────────────────────────────────────────

    @app.get("/api/companion/state")
    async def get_companion_state() -> Dict[str, Any]:
        """Fetch companion character state and profile."""
        from app.core.buddy_state_manager import get_buddy_state_manager
        buddy_sm = get_buddy_state_manager()
        op_state = buddy_sm.state_name  # "active" | "sleeping" | "muted"

        char_state = "idle"
        controller = getattr(app.state, "controller", None)
        anim_ctrl = getattr(controller, "pet_window", None) if controller else None
        if anim_ctrl and hasattr(anim_ctrl, "animation_controller"):
            char_state = str(anim_ctrl.animation_controller.current_state.value).lower()

        if buddy_sm.is_sleeping:
            char_state = "sleeping"

        cfg_mgr = _get_config_manager()
        name = "Buddy"
        personality = "friendly"
        model = "llama3.2:3b"
        if cfg_mgr:
            name = cfg_mgr.get("ai.companion_name") or cfg_mgr.get("companion.name") or cfg_mgr.get("character.name") or "Buddy"
            personality = cfg_mgr.get("ai.personality") or "friendly"
            model = cfg_mgr.get("ai.model") or "llama3.2:3b"

        return {
            "name": name,
            "personality": personality,
            "state": char_state,
            "model": model,
            "operational_state": op_state,
        }

    @app.post("/api/companion/sleep")
    async def companion_sleep() -> Dict[str, Any]:
        """Put companion into resource-saving sleep mode."""
        from app.core.buddy_state_manager import get_buddy_state_manager
        from app.core.signals import signals
        buddy_sm = get_buddy_state_manager()
        buddy_sm.enter_sleep(reason="api_request")
        signals.sleep_requested.emit()
        signals.character_state_changed.emit("sleeping")
        ws_manager.broadcast_sync("buddy_state_changed", {"state": "sleeping"})
        ws_manager.broadcast_sync("char_state", {"state": "sleeping"})
        return {"status": "ok", "state": "sleeping", "operational_state": "sleeping"}

    @app.post("/api/companion/wake")
    async def companion_wake() -> Dict[str, Any]:
        """Wake companion from sleep mode into active state."""
        from app.core.buddy_state_manager import get_buddy_state_manager
        from app.core.signals import signals
        buddy_sm = get_buddy_state_manager()
        buddy_sm.wake_up(reason="api_request")
        signals.wake_requested.emit()
        signals.character_state_changed.emit("idle")
        ws_manager.broadcast_sync("buddy_state_changed", {"state": "active"})
        ws_manager.broadcast_sync("char_state", {"state": "idle"})
        return {"status": "ok", "state": "active", "operational_state": "active"}

    @app.post("/api/companion/mute")
    async def companion_mute() -> Dict[str, Any]:
        """Mute companion speech audio output."""
        from app.core.buddy_state_manager import get_buddy_state_manager
        buddy_sm = get_buddy_state_manager()
        buddy_sm.set_muted(True, "api_request")
        vs = getattr(app.state, "voice_service", None)
        if vs and hasattr(vs, "set_muted"):
            vs.set_muted(True)
        ws_manager.broadcast_sync("buddy_state_changed", {"state": "muted"})
        return {"status": "ok", "state": "muted", "operational_state": "muted"}

    @app.post("/api/companion/unmute")
    async def companion_unmute() -> Dict[str, Any]:
        """Unmute companion speech audio output."""
        from app.core.buddy_state_manager import get_buddy_state_manager
        buddy_sm = get_buddy_state_manager()
        buddy_sm.set_muted(False, "api_request")
        vs = getattr(app.state, "voice_service", None)
        if vs and hasattr(vs, "set_muted"):
            vs.set_muted(False)
        ws_manager.broadcast_sync("buddy_state_changed", {"state": "active"})
        return {"status": "ok", "state": "active", "operational_state": "active"}

    # ─── Diagnostic Mode (Phase 10) ──────────────────────────────────────────

    @app.get("/api/diagnostic/status")
    async def get_diagnostic_status() -> Dict[str, Any]:
        """Fetch current structured diagnostic health across voice communication stages."""
        from app.core.diagnostic_mode import diagnostic_tracker
        cfg_mgr: Optional[ConfigManager] = getattr(app.state, "config_manager", None)
        if cfg_mgr:
            is_debug = bool(cfg_mgr.get("general.debug", False))
            if is_debug != diagnostic_tracker.enabled:
                diagnostic_tracker.set_enabled(is_debug)
        return diagnostic_tracker.to_dict()

    @app.post("/api/diagnostic/toggle")
    async def toggle_diagnostic_mode(req: Optional[DiagnosticToggleRequest] = None) -> Dict[str, Any]:
        """Toggle or set diagnostic mode and sync with application debug configuration."""
        from app.core.diagnostic_mode import diagnostic_tracker
        cfg_mgr: Optional[ConfigManager] = getattr(app.state, "config_manager", None)

        current_enabled = diagnostic_tracker.enabled
        new_enabled = req.enabled if (req and req.enabled is not None) else not current_enabled

        diagnostic_tracker.set_enabled(new_enabled)
        if cfg_mgr:
            cfg_mgr.set("general.debug", new_enabled)

        return {"status": "ok", "enabled": new_enabled, "diagnostic": diagnostic_tracker.to_dict()}


    # ─── Long-Term Memory ────────────────────────────────────────────────────

    @app.get("/api/memories")
    async def list_memories(search: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """List or search stored long-term memories."""
        ai_service = getattr(app.state, "ai_service", None)
        memory_mgr = getattr(ai_service, "memory_manager", None) if ai_service else None
        if not memory_mgr:
            db_mgr = getattr(app.state, "db_manager", None)
            if db_mgr:
                from app.memory.memory_manager import MemoryManager
                memory_mgr = MemoryManager(db_manager=db_mgr)

        if not memory_mgr:
            return []

        try:
            if search and search.strip():
                mems = memory_mgr.search_memories(search.strip(), limit=limit)
            else:
                mems = memory_mgr.get_all_memories(limit=limit) if hasattr(memory_mgr, "get_all_memories") else memory_mgr.get_memories(limit=limit)
            return [
                {
                    "id": getattr(m, "id", ""),
                    "category": getattr(m, "category", "general"),
                    "content": getattr(m, "content", ""),
                    "created_at": getattr(m, "created_at", ""),
                }
                for m in mems
            ]
        except Exception as e:
            logger.warning("Failed to fetch memories: %s", e)
            return []

    @app.post("/api/memories")
    async def create_memory(req: MemoryCreateRequest) -> Dict[str, Any]:
        """Manually store a new long-term memory."""
        ai_service = getattr(app.state, "ai_service", None)
        memory_mgr = getattr(ai_service, "memory_manager", None) if ai_service else None
        if not memory_mgr:
            db_mgr = getattr(app.state, "db_manager", None)
            if db_mgr:
                from app.memory.memory_manager import MemoryManager
                memory_mgr = MemoryManager(db_manager=db_mgr)

        if not memory_mgr:
            raise HTTPException(status_code=500, detail="Memory manager unavailable")

        mem = memory_mgr.add_memory(category=req.category, content=req.content, source="user")
        mem_data = {
            "id": getattr(mem, "id", ""),
            "category": getattr(mem, "category", req.category),
            "content": getattr(mem, "content", req.content),
            "created_at": getattr(mem, "created_at", ""),
        }
        ws_manager.broadcast_sync("memory_stored", {"memory": mem_data})
        return {"status": "ok", "memory": mem_data}

    @app.delete("/api/memories/{memory_id}")
    async def delete_memory_entry(memory_id: str) -> Dict[str, Any]:
        """Delete an existing long-term memory."""
        ai_service = getattr(app.state, "ai_service", None)
        memory_mgr = getattr(ai_service, "memory_manager", None) if ai_service else None
        if not memory_mgr:
            db_mgr = getattr(app.state, "db_manager", None)
            if db_mgr:
                from app.memory.memory_manager import MemoryManager
                memory_mgr = MemoryManager(db_manager=db_mgr)

        if not memory_mgr:
            raise HTTPException(status_code=500, detail="Memory manager unavailable")

        success = memory_mgr.delete_memory(memory_id)
        return {"status": "ok", "deleted": success, "id": memory_id}

    # ─── Chat Export ─────────────────────────────────────────────────────────

    def _get_windows_downloads_dirs() -> List[Path]:
        """Find all valid Windows Downloads directories, including custom relocated drive paths."""
        dirs: List[Path] = []
        # 1. Query Windows Registry for KnownFolder Downloads ({374DE290-123F-4565-9164-39C4925E467B})
        try:
            import winreg
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                for val_name in ("{374DE290-123F-4565-9164-39C4925E467B}", "{7D83EE9B-2244-4E70-B1F5-56991452414A}"):
                    try:
                        raw_val, _ = winreg.QueryValueEx(key, val_name)
                        expanded = os.path.expandvars(raw_val)
                        p = Path(expanded)
                        if p.exists() and p not in dirs:
                            dirs.append(p)
                    except FileNotFoundError:
                        pass
        except Exception:
            pass

        # 2. Check standard user profile Downloads
        home_dl = Path.home() / "Downloads"
        if home_dl.exists() and home_dl not in dirs:
            dirs.append(home_dl)

        # 3. Fallback
        if not dirs:
            dirs.append(Path.home())
        return dirs

    @app.post("/api/chat/export")
    async def export_chat(req: ExportChatRequest) -> Dict[str, Any]:
        """Export conversation messages as markdown formatted text."""
        repo: Optional[ConversationRepository] = getattr(app.state, "conv_repo", None)
        if not repo:
            raise HTTPException(status_code=500, detail="Repository unavailable")

        conv = None
        target_id = (req.conversation_id or "").strip()
        if target_id:
            conv = repo.get_conversation(target_id)

        # Fallback to the latest available conversation if not found
        if not conv:
            all_convs = repo.list_conversations()
            if all_convs:
                conv = all_convs[0]
                target_id = conv.id

        companion_name = "Bond"
        cfg_mgr = _get_config_manager()
        if cfg_mgr:
            companion_name = cfg_mgr.get("ai.companion_name") or cfg_mgr.get("companion.name") or "Bond"

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if not conv:
            return {
                "conversation_id": target_id or "new_chat",
                "title": f"{companion_name}_Chat",
                "markdown": f"# {companion_name} Chat Export\n*Exported on {now_str}*\n\n---\n\n*No messages recorded yet.*\n",
            }

        def _format_time_label(iso_str: str) -> str:
            if not iso_str:
                return ""
            try:
                dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
                return dt.strftime("%I:%M %p")
            except Exception:
                parts = iso_str.split("T")
                if len(parts) > 1:
                    return parts[1].split(".")[0][:5]
                return iso_str[:16]

        messages = repo.get_messages(conv.id)
        formatted_export_time = datetime.now().strftime("%b %d, %Y, %I:%M %p")
        lines = [
            f"# 💬 {conv.title}",
            f"*{companion_name} Companion Chat • Exported on {formatted_export_time}*",
            "",
            "---",
            "",
        ]
        if not messages:
            lines.append("<div align=\"center\" style=\"color: #888; font-style: italic;\">No messages recorded in this conversation.</div>")
            lines.append("")
        else:
            for m in messages:
                is_user = (m.role == "user")
                speaker = "You" if is_user else companion_name
                time_label = _format_time_label(m.created_at or "")
                time_part = f" • {time_label}" if time_label else ""
                escaped_content = html.escape(m.content or "").replace("\n", "<br/>")

                if is_user:
                    lines.append(
                        f'<div align="right" style="margin: 12px 0 12px auto; text-align: right;">\n'
                        f'  <div style="display: inline-block; text-align: left; max-width: 78%; background-color: #2563eb; color: #ffffff; padding: 10px 16px; border-radius: 18px 18px 4px 18px; box-shadow: 0 2px 6px rgba(0,0,0,0.18); font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, Helvetica, Arial, sans-serif;">\n'
                        f'    <div style="font-size: 11px; font-weight: 700; color: #bfdbfe; margin-bottom: 4px; text-align: right;">{speaker}{time_part}</div>\n'
                        f'    <div style="font-size: 14px; line-height: 1.5; color: #ffffff;">{escaped_content}</div>\n'
                        f'  </div>\n'
                        f'</div>\n'
                    )
                else:
                    lines.append(
                        f'<div align="left" style="margin: 12px auto 12px 0; text-align: left;">\n'
                        f'  <div style="display: inline-block; text-align: left; max-width: 78%; background-color: #1e293b; color: #f8fafc; padding: 10px 16px; border-radius: 18px 18px 18px 4px; border: 1px solid #334155; box-shadow: 0 2px 6px rgba(0,0,0,0.18); font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, Helvetica, Arial, sans-serif;">\n'
                        f'    <div style="font-size: 11px; font-weight: 700; color: #38bdf8; margin-bottom: 4px;">{speaker} 🤖{time_part}</div>\n'
                        f'    <div style="font-size: 14px; line-height: 1.5; color: #f1f5f9;">{escaped_content}</div>\n'
                        f'  </div>\n'
                        f'</div>\n'
                    )

        markdown_text = "\n".join(lines)
        title = conv.title if conv else f"{companion_name}_Chat"

        # Auto-save export directly to all resolved Downloads directories (e.g. F:\Downloads and C:\Users\...\Downloads)
        saved_file_path = None
        try:
            clean_title = re.sub(r'[^a-zA-Z0-9_\-\u0900-\u0DFF]', '_', title)
            clean_title = re.sub(r'_+', '_', clean_title).strip('_') or "Chat"
            timestamp_suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
            target_dirs = _get_windows_downloads_dirs()
            for downloads_dir in target_dirs:
                try:
                    out_file = downloads_dir / f"{clean_title}_export_{timestamp_suffix}.md"
                    out_file.write_text(markdown_text, encoding="utf-8")
                    if not saved_file_path:
                        saved_file_path = str(out_file)
                    logger.info("Chat export saved to file: %s", out_file)
                except Exception as ex:
                    logger.warning("Failed writing export to %s: %s", downloads_dir, ex)
        except Exception as e:
            logger.debug("Auto-save export to Downloads note: %s", e)

        return {
            "conversation_id": conv.id if conv else (target_id or "new_chat"),
            "title": title,
            "markdown": markdown_text,
            "file_path": saved_file_path,
        }

    # ─── Real-Time WebSocket Channel ─────────────────────────────────────────

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        """Duplex real-time communication channel."""
        origin = websocket.headers.get("origin")
        if origin and not is_allowed_origin(origin):
            logger.warning("Rejected WebSocket connection from unauthorized origin: %s", origin)
            await websocket.close(code=1008)  # 1008: Policy Violation
            return

        await ws_manager.connect(websocket)
        # Send initial synchronized companion profile to newly connected client
        try:
            cfg_mgr = _get_config_manager()
            initial_name = "Buddy"
            personality = "friendly"
            active_model = "llama3.2:latest"
            if cfg_mgr:
                initial_name = cfg_mgr.get("ai.companion_name") or cfg_mgr.get("companion.name") or cfg_mgr.get("character.name") or "Buddy"
                personality = cfg_mgr.get("ai.personality") or "friendly"
                active_model = cfg_mgr.get("ai.model", active_model)
            await websocket.send_json({
                "type": "companion_profile_updated",
                "data": {
                    "name": initial_name,
                    "personality": personality,
                    "state": "idle",
                    "model": active_model,
                }
            })
        except Exception:
            pass

        try:
            while True:
                data = await websocket.receive_json()
                msg_type = data.get("type", "")
                payload = data.get("data", {})

                if msg_type == "ping":
                    await websocket.send_json({"type": "pong", "data": {}})

                elif msg_type == "cancel_generation":
                    ai_service = getattr(app.state, "ai_service", None)
                    if ai_service:
                        ai_service.cancel_generation()
                    ws_manager.broadcast_sync("ai_cancelled", {})

        except WebSocketDisconnect:
            ws_manager.disconnect(websocket)
        except Exception as e:
            logger.warning("WebSocket exception: %s", e)
            ws_manager.disconnect(websocket)

    # ─── Desktop Pet Window Controls & Visibility ────────────────────────────
    @app.get("/api/pet/status")
    async def get_pet_status() -> Dict[str, Any]:
        """Fetch pet always-on-top status and visibility settings."""
        cfg_mgr: Optional[ConfigManager] = getattr(app.state, "config_manager", None)
        always_on_top = cfg_mgr.get("pet.always_on_top", True) if cfg_mgr else True
        visible = cfg_mgr.get("pet.visible", True) if cfg_mgr else True
        char_name = cfg_mgr.get("pet.character", "robot") if cfg_mgr else "robot"
        controller = getattr(app.state, "controller", None)
        if controller and hasattr(controller, "pet_window") and controller.pet_window:
            try:
                visible = controller.pet_window.isVisible()
            except Exception:
                pass
        return {
            "always_on_top": always_on_top,
            "visible": visible,
            "character": char_name,
        }

    @app.post("/api/pet/topmost")
    async def set_pet_topmost(req: PetTopmostRequest) -> Dict[str, Any]:
        """Toggle Desktop Pet always-on-top state across all windows and apps."""
        cfg_mgr: Optional[ConfigManager] = getattr(app.state, "config_manager", None)
        if cfg_mgr:
            cfg_mgr.set("pet.always_on_top", req.always_on_top)
        from app.core.signals import signals
        signals.always_on_top_changed.emit(req.always_on_top)
        ws_manager.broadcast_sync("pet_topmost_changed", {"always_on_top": req.always_on_top})
        return {"status": "ok", "always_on_top": req.always_on_top}

    @app.post("/api/pet/show")
    async def show_pet_endpoint() -> Dict[str, Any]:
        """Show the desktop pet overlay."""
        cfg_mgr: Optional[ConfigManager] = getattr(app.state, "config_manager", None)
        if cfg_mgr:
            cfg_mgr.set("pet.visible", True)
        from app.core.signals import signals
        signals.show_pet_requested.emit()
        ws_manager.broadcast_sync("pet_visibility_changed", {"visible": True})
        return {"status": "ok", "visible": True}

    @app.post("/api/pet/hide")
    async def hide_pet_endpoint() -> Dict[str, Any]:
        """Hide the desktop pet overlay."""
        cfg_mgr: Optional[ConfigManager] = getattr(app.state, "config_manager", None)
        if cfg_mgr:
            cfg_mgr.set("pet.visible", False)
        from app.core.signals import signals
        signals.hide_pet_requested.emit()
        ws_manager.broadcast_sync("pet_visibility_changed", {"visible": False})
        return {"status": "ok", "visible": False}

    @app.post("/api/pet/reset_position")
    async def reset_pet_position_endpoint() -> Dict[str, Any]:
        """Reset the desktop pet overlay to default bottom-right on active display."""
        cfg_mgr: Optional[ConfigManager] = getattr(app.state, "config_manager", None)
        if cfg_mgr:
            cfg_mgr.set("pet.position_x", None)
            cfg_mgr.set("pet.position_y", None)
            cfg_mgr.set("pet.visible", True)
        from app.core.signals import signals
        signals.reset_pet_position_requested.emit()
        ws_manager.broadcast_sync("pet_position_reset", {})
        ws_manager.broadcast_sync("pet_visibility_changed", {"visible": True})
        return {"status": "ok"}
        ws_manager.broadcast_sync("pet_visibility_changed", {"visible": True})
        return {"status": "ok"}

    # ─── Desktop Frameless Window Controls ───────────────────────────────────
    @app.post("/api/window/minimize")
    async def window_minimize():
        from app.core.signals import signals
        signals.minimize_chat_requested.emit()
        return {"status": "ok"}

    @app.post("/api/window/maximize")
    async def window_maximize():
        from app.core.signals import signals
        signals.maximize_chat_requested.emit()
        return {"status": "ok"}

    @app.post("/api/window/close")
    async def window_close():
        from app.core.signals import signals
        signals.close_chat_requested.emit()
        return {"status": "ok"}

    class WindowMoveDelta(BaseModel):
        dx: int
        dy: int

    @app.post("/api/window/drag")
    async def window_drag():
        from app.core.signals import signals
        signals.drag_chat_requested.emit()
        return {"status": "ok"}

    @app.post("/api/window/move_delta")
    async def window_move_delta(req: WindowMoveDelta):
        from app.core.signals import signals
        signals.move_chat_delta.emit(req.dx, req.dy)
        return {"status": "ok"}

    # ─── Movie Hub Discovery Router ──────────────────────────────────────────
    from app.api.movie_routes import router as movie_router
    app.include_router(movie_router)

    # ─── Static Asset & SPA Serving ──────────────────────────────────────────
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sync_character_assets(project_root)

    dist_dir = os.path.join(project_root, "dist")
    candidate_asset_dirs = [
        os.path.join(dist_dir, "assets"),
        os.path.join(project_root, "public", "assets"),
        os.path.join(project_root, "assets"),
    ]
    app.mount("/assets", MultiDirStaticFiles(directories=candidate_asset_dirs), name="assets")

    if os.path.exists(dist_dir):
        safe_dist = os.path.abspath(dist_dir)

        @app.get("/")
        async def serve_index():
            return FileResponse(os.path.join(safe_dist, "index.html"))

        @app.get("/{catchall:path}")
        async def serve_spa(catchall: str):
            if catchall.startswith("api/") or catchall == "ws":
                raise HTTPException(status_code=404, detail="Not Found")
            file_path = os.path.abspath(os.path.join(safe_dist, catchall))
            try:
                # Ensure path does not traverse outside dist directory
                if os.path.commonpath([safe_dist, file_path]) != safe_dist:
                    return FileResponse(os.path.join(safe_dist, "index.html"))
            except ValueError:
                # Different drive on Windows
                return FileResponse(os.path.join(safe_dist, "index.html"))

            if os.path.isfile(file_path):
                return FileResponse(file_path)
            return FileResponse(os.path.join(safe_dist, "index.html"))

    return app


app = create_app()


def _on_config_reset(target_cfg: Optional[ConfigManager] = None) -> None:
    """Module-level helper to trigger runtime subsystem synchronization after config reset."""
    handler = getattr(app.state, "_on_config_reset", None)
    if callable(handler):
        handler(target_cfg)

