"""AI Service — Qt Asynchronous Integration Engine.

Coordinates the local LLM runtime with the desktop character UI, managing:
- Non-blocking streaming inference via background threads.
- Real-time chunk emission to PySide6 UI and character speech bubbles.
- Instant request cancellation with obsolete chunk suppression.
- Character state transitions (THINKING -> SPEAKING -> IDLE / ERROR).
- Inactivity memory reclamation timers.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, Optional

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal, Slot

from app.ai.cancellation import CancellationToken
from app.ai.conversation_context import ConversationContext
from app.ai.emotion_classifier import EmotionClassifier, EmotionType
from app.ai.generation_controls import GenerationConfig
from app.ai.model_manager import ModelManager
from app.ai.ollama_client import (
    OllamaCancelledError,
    OllamaClient,
    OllamaClientError,
    OllamaConnectionError,
    OllamaModelNotFoundError,
    OllamaTimeoutError,
)
from app.ai.personality_manager import PersonalityManager
from app.core.signals import signals
from app.memory.memory_manager import MemoryManager
from app.settings.config_manager import ConfigManager
from app.utils.logger import get_logger

logger = get_logger(__name__)


def deduplicate_continuation_prefix(previous_text: str, new_chunk: str, max_overlap_check: int = 80) -> str:
    """Strip any repeated prefix in continuation that overlaps with the end of previous_text."""
    if not previous_text or not new_chunk:
        return new_chunk

    prev_tail = previous_text[-max_overlap_check:]
    max_k = min(len(prev_tail), len(new_chunk))
    for k in range(max_k, 2, -1):
        if prev_tail.endswith(new_chunk[:k]):
            return new_chunk[k:]

    prev_stripped = prev_tail.rstrip()
    new_lstripped = new_chunk.lstrip()
    max_k2 = min(len(prev_stripped), len(new_lstripped))
    for k in range(max_k2, 2, -1):
        if prev_stripped.endswith(new_lstripped[:k]):
            return new_lstripped[k:]

    return new_chunk


class _WorkerSignals(QObject):
    """Signals for background generation worker."""

    started = Signal(int)           # generation_id
    chunk_received = Signal(int, str)  # generation_id, token_chunk
    completed = Signal(int, str)    # generation_id, full_text
    cancelled = Signal(int)         # generation_id
    failed = Signal(int, str)       # generation_id, error_message

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._meta_by_gen: dict[int, dict[str, Any]] = {}

    def record_metadata(self, gen_id: int, meta: dict[str, Any]) -> None:
        self._meta_by_gen[gen_id] = meta

    def get_metadata(self, gen_id: int) -> dict[str, Any]:
        return self._meta_by_gen.get(gen_id, {})


class _InferenceWorker(QRunnable):
    """Background runnable executing Ollama streaming chat without blocking the UI."""

    def __init__(
        self,
        generation_id: int,
        client: OllamaClient,
        model: str,
        messages: list[dict[str, str]],
        options: dict[str, Any],
        cancellation_token: CancellationToken,
        signals: _WorkerSignals,
        keep_alive: Optional[str] = "5m",
        format: Optional[Union[str, Dict[str, Any]]] = None,
    ) -> None:
        super().__init__()
        self.generation_id = generation_id
        self.client = client
        self.model = model
        self.messages = messages
        self.options = options
        self.cancellation_token = cancellation_token
        self.signals = signals
        self.keep_alive = keep_alive
        self.format = format
        self.metadata: dict[str, Any] = {}
        self.setAutoDelete(True)

    def run(self) -> None:
        """Stream chunks from Ollama and emit Qt signals with seamless continuation on token limits."""
        if self.cancellation_token.is_cancelled:
            try:
                self.signals.cancelled.emit(self.generation_id)
            except RuntimeError:
                pass
            return

        try:
            self.signals.started.emit(self.generation_id)
        except RuntimeError:
            return

        accumulated_chunks: list[str] = []
        current_full_text = ""
        continuation_count = 0
        max_continuations = int(self.options.get("max_continuations", 2))
        active_messages = list(self.messages)
        latest_metadata: dict[str, Any] = {
            "done_reason": "stop",
            "eval_count": 0,
            "continuations": 0,
            "truncated": False,
        }

        def _on_meta(m: dict[str, Any]) -> None:
            latest_metadata.update(m)

        try:
            while True:
                is_continuation = continuation_count > 0
                continuation_buffer = ""
                overlap_checked = not is_continuation

                stream_kwargs = {
                    "messages": active_messages,
                    "model": self.model,
                    "options": self.options,
                    "keep_alive": self.keep_alive,
                    "cancellation_token": self.cancellation_token,
                    "on_metadata": _on_meta,
                }
                if self.format is not None:
                    stream_kwargs["format"] = self.format

                stream = self.client.chat_stream(**stream_kwargs)

                for chunk in stream:
                    if self.cancellation_token.is_cancelled:
                        try:
                            self.signals.cancelled.emit(self.generation_id)
                        except RuntimeError:
                            pass
                        return

                    if is_continuation and not overlap_checked:
                        continuation_buffer += chunk
                        if len(continuation_buffer) >= 20 or "\n" in continuation_buffer:
                            cleaned_chunk = deduplicate_continuation_prefix(current_full_text, continuation_buffer)
                            overlap_checked = True
                            if cleaned_chunk:
                                accumulated_chunks.append(cleaned_chunk)
                                current_full_text += cleaned_chunk
                                try:
                                    self.signals.chunk_received.emit(self.generation_id, cleaned_chunk)
                                except RuntimeError:
                                    return
                        continue

                    accumulated_chunks.append(chunk)
                    current_full_text += chunk
                    try:
                        self.signals.chunk_received.emit(self.generation_id, chunk)
                    except RuntimeError:
                        return

                if is_continuation and not overlap_checked and continuation_buffer:
                    cleaned_chunk = deduplicate_continuation_prefix(current_full_text, continuation_buffer)
                    overlap_checked = True
                    if cleaned_chunk:
                        accumulated_chunks.append(cleaned_chunk)
                        current_full_text += cleaned_chunk
                        try:
                            self.signals.chunk_received.emit(self.generation_id, cleaned_chunk)
                        except RuntimeError:
                            return

                done_reason = latest_metadata.get("done_reason", "stop")
                # When response has genuinely reached its generation limit, continue without repeating
                if (
                    done_reason == "length"
                    and continuation_count < max_continuations
                    and not self.cancellation_token.is_cancelled
                ):
                    continuation_count += 1
                    logger.info(
                        "[CONTINUATION] Generation #%d hit token limit ('length'). "
                        "Triggering seamless continuation %d/%d (accumulated %d chars)...",
                        self.generation_id, continuation_count, max_continuations, len(current_full_text)
                    )
                    active_messages = list(self.messages)
                    active_messages.append({"role": "assistant", "content": current_full_text})
                    active_messages.append({
                        "role": "user",
                        "content": "Continue directly from where you left off. Do not repeat anything already generated.",
                    })
                    continue
                else:
                    break

            latest_metadata["continuations"] = continuation_count
            latest_metadata["truncated"] = (done_reason == "length")
            self.metadata = latest_metadata
            if hasattr(self.signals, "record_metadata"):
                self.signals.record_metadata(self.generation_id, latest_metadata)

            full_response = current_full_text.strip()
            try:
                self.signals.completed.emit(self.generation_id, full_response)
            except RuntimeError:
                pass
        except OllamaCancelledError:
            logger.debug("Worker #%d cancelled.", self.generation_id)
            try:
                self.signals.cancelled.emit(self.generation_id)
            except RuntimeError:
                pass
        except (OllamaConnectionError, OllamaModelNotFoundError, OllamaTimeoutError, OllamaClientError) as e:
            logger.error("Inference failed for worker #%d: %s", self.generation_id, e)
            try:
                self.signals.failed.emit(self.generation_id, str(e))
            except RuntimeError:
                pass
        except RuntimeError:
            return
        except Exception as e:
            logger.critical("Unexpected error in worker #%d: %s", self.generation_id, e, exc_info=True)
            try:
                self.signals.failed.emit(self.generation_id, f"Inference error: {e}")
            except RuntimeError:
                pass


class _OfflineWorker(QRunnable):
    """Background runnable executing offline companion response streaming without blocking UI."""

    def __init__(
        self,
        generation_id: int,
        engine: Any,
        user_prompt: str,
        cancellation_token: CancellationToken,
        signals: _WorkerSignals,
    ) -> None:
        super().__init__()
        self.generation_id = generation_id
        self.engine = engine
        self.user_prompt = user_prompt
        self.cancellation_token = cancellation_token
        self.signals = signals
        self.setAutoDelete(True)

    def run(self) -> None:
        if self.cancellation_token.is_cancelled:
            try:
                self.signals.cancelled.emit(self.generation_id)
            except RuntimeError:
                pass
            return

        try:
            self.signals.started.emit(self.generation_id)
        except RuntimeError:
            return

        accumulated_chunks: list[str] = []

        try:
            for chunk in self.engine.generate_stream(self.user_prompt):
                if self.cancellation_token.is_cancelled:
                    try:
                        self.signals.cancelled.emit(self.generation_id)
                    except RuntimeError:
                        pass
                    return
                accumulated_chunks.append(chunk)
                try:
                    self.signals.chunk_received.emit(self.generation_id, chunk)
                except RuntimeError:
                    return

            full_response = "".join(accumulated_chunks).strip()
            try:
                self.signals.completed.emit(self.generation_id, full_response)
            except RuntimeError:
                pass
        except RuntimeError:
            return
        except Exception as e:
            try:
                self.signals.failed.emit(self.generation_id, str(e))
            except RuntimeError:
                pass


class _DeterministicWorker(QRunnable):
    """Background runnable executing fast deterministic answer streaming without blocking UI."""

    def __init__(
        self,
        generation_id: int,
        response_text: str,
        cancellation_token: CancellationToken,
        signals: _WorkerSignals,
        chunk_words: int = 3,
    ) -> None:
        super().__init__()
        self.generation_id = generation_id
        self.response_text = response_text
        self.cancellation_token = cancellation_token
        self.signals = signals
        self.chunk_words = chunk_words
        self.setAutoDelete(True)

    def run(self) -> None:
        if self.cancellation_token.is_cancelled:
            try:
                self.signals.cancelled.emit(self.generation_id)
            except RuntimeError:
                pass
            return

        try:
            self.signals.started.emit(self.generation_id)
        except RuntimeError:
            return

        words = self.response_text.split(" ")
        accumulated_chunks: list[str] = []

        try:
            for i in range(0, len(words), self.chunk_words):
                if self.cancellation_token.is_cancelled:
                    try:
                        self.signals.cancelled.emit(self.generation_id)
                    except RuntimeError:
                        pass
                    return
                chunk = " ".join(words[i : i + self.chunk_words])
                if i + self.chunk_words < len(words):
                    chunk += " "
                accumulated_chunks.append(chunk)
                try:
                    self.signals.chunk_received.emit(self.generation_id, chunk)
                except RuntimeError:
                    return
                time.sleep(0.015)

            full_response = "".join(accumulated_chunks).strip()
            try:
                self.signals.completed.emit(self.generation_id, full_response)
            except RuntimeError:
                pass
        except RuntimeError:
            return
        except Exception as e:
            try:
                self.signals.failed.emit(self.generation_id, str(e))
            except RuntimeError:
                pass


class AIService(QObject):
    """Central AI service orchestrating model lifecycle, generation, and UI signals."""

    # Local AI service signals
    generation_started = Signal(int, str)   # generation_id, prompt
    generation_completed = Signal(int, str) # generation_id, full_response
    generation_cancelled = Signal(int)      # generation_id
    error_occurred = Signal(str)            # human-friendly error message

    def __init__(
        self,
        config_manager: Optional[ConfigManager] = None,
        client: Optional[OllamaClient] = None,
        memory_manager: Optional[MemoryManager] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.config_manager = config_manager
        endpoint = (
            self.config_manager.get("ai.ollama_host", "http://127.0.0.1:11434")
            if self.config_manager
            else "http://127.0.0.1:11434"
        )
        self.client = client or OllamaClient(base_url=endpoint)

        configured_model = (
            self.config_manager.get("ai.model", "llama3.2:latest")
            if self.config_manager
            else "llama3.2:latest"
        )
        self.model_manager = ModelManager(
            client=self.client,
            default_model=configured_model,
            config_manager=self.config_manager,
        )
        self.model_manager.select_active_model()
        self.model_manager.warmup_model()

        companion_name = (
            self.config_manager.get("ai.companion_name", "Buddy")
            if self.config_manager
            else "Buddy"
        )
        personality = (
            self.config_manager.get("ai.personality", "friendly")
            if self.config_manager
            else "friendly"
        )
        self.personality_manager = PersonalityManager(
            config_manager=self.config_manager,
            default_personality=personality,
            companion_name=companion_name,
        )

        from app.ai.offline_companion import OfflineCompanionEngine
        self.offline_engine = OfflineCompanionEngine(
            companion_name=companion_name,
            personality=personality,
        )

        self.context = ConversationContext()
        self.config = GenerationConfig(model=self.model_manager.active_model)

        # Phase 10: Intelligent Memory and Emotional Response
        self.memory_manager = memory_manager or MemoryManager()
        self.emotion_classifier = EmotionClassifier
        self.memory_enabled = (
            bool(self.config_manager.get("memory.enabled", True))
            if self.config_manager
            else True
        )
        self.auto_extract_memory = (
            bool(self.config_manager.get("memory.auto_extract_enabled", True))
            if self.config_manager
            else True
        )
        self.offline_fallback = (
            bool(self.config_manager.get("ai.offline_fallback", True))
            if self.config_manager
            else False
        )
        self.fast_greeting_enabled = (
            bool(self.config_manager.get("ai.fast_greeting_enabled", True))
            if self.config_manager
            else False
        )
        self._last_user_prompt: str = ""
        self.active_conversation_id: Optional[str] = None
        self.conv_repo: Optional[Any] = None

        self.thread_pool = QThreadPool.globalInstance()
        self._current_gen_id = 0
        self._active_token: Optional[CancellationToken] = None
        self._is_generating = False
        self._is_current_voice = False
        self._gen_start_time = 0.0
        self._first_token_time: Optional[float] = None
        self._active_request_id: Optional[str] = None
        self._t_backend_received: float = 0.0
        self._client_timestamp: Optional[float] = None
        self._t_first_token: float = 0.0
        self._t_llm_completed: float = 0.0
        self._latest_timing_metrics: Dict[str, Any] = {}
        self._last_routing_decision: Optional[Any] = None
        self._worker_signals_by_gen: Dict[int, Any] = {}
        self._request_payloads_by_gen: Dict[int, Dict[str, Any]] = {}
        self._fallback_attempts_by_gen: Dict[int, int] = {}
        self._lock = threading.Lock()

        # Phase 5: Adaptive Response Length & Style Tracking
        from app.ai.adaptive_response_style import ResponseStyle
        default_style_str = self.config_manager.get("ai.response_style", "normal_conversation") if self.config_manager else "normal_conversation"
        self._current_adaptive_style: ResponseStyle = ResponseStyle.from_string(default_style_str)

        # Inactivity auto-unloader timer (runs every 30 seconds)
        self._inactivity_timer = QTimer(self)
        self._inactivity_timer.setInterval(30000)
        self._inactivity_timer.timeout.connect(self._check_inactivity)
        self._inactivity_timer.start()

        # Connect global bus cancellation request
        signals.ai_cancel_requested.connect(self.cancel_generation)

        # Connect setting change hooks
        if self.config_manager:
            self.config_manager.setting_changed.connect(self._on_setting_changed)

    @property
    def is_current_generation_voice(self) -> bool:
        """Return True if the current active or most recent generation originated from voice chat."""
        with self._lock:
            return self._is_current_voice

    @property
    def current_response_style(self) -> ResponseStyle:
        """Return the current active adaptive response style (Phase 5)."""
        from app.ai.adaptive_response_style import ResponseStyle
        return getattr(self, "_current_adaptive_style", ResponseStyle.NORMAL_CONVERSATION)

    def set_response_style(self, style: Union[str, ResponseStyle]) -> None:
        """Explicitly configure or override the active response style (Phase 5.4)."""
        from app.ai.adaptive_response_style import ResponseStyle
        resolved = ResponseStyle.from_string(str(style))
        self._current_adaptive_style = resolved
        if self.config_manager:
            self.config_manager.set("ai.response_style", resolved.value)
        try:
            signals.adaptive_style_changed.emit(resolved.value)
        except Exception:
            pass

    def get_last_routing_decision(self) -> Optional[Any]:
        """Fetch the most recent automatic model routing decision (Phase 4)."""
        return self._last_routing_decision

    # ─── Public API ────────────────────────────────────────────────────

    def ask(
        self,
        user_prompt: str,
        is_voice: bool = False,
        response_style: Optional[str] = None,
        request_id: Optional[str] = None,
        backend_received_time: Optional[float] = None,
        client_timestamp: Optional[float] = None,
        interruption_context: Optional[Dict[str, Any]] = None,
        images: Optional[List[Any]] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        format_json: bool = False,
    ) -> int:
        """Send a user prompt to the local AI engine.
        
        Cancels any prior in-flight generation and starts streaming chunks.
        
        Args:
            user_prompt: User input string.
            is_voice: Whether this request originated from voice chat.
            response_style: Optional style override ('concise', 'casual', 'detailed').
            request_id: Unique correlation request ID for end-to-end response-time monitoring.
            backend_received_time: Monotonic perf_counter timestamp when backend received request.
            client_timestamp: Frontend performance.now() timestamp when user clicked Send.
            interruption_context: Optional context when user interrupted a prior assistant speech (Phase 4).
            
        Returns:
            The unique generation_id for this request.
        """
        cleaned = user_prompt.strip()
        if not cleaned:
            logger.info("[DIAGNOSTIC] Empty transcription rejected: Empty prompt supplied.")
            return 0

        # Reject duplicate request if already generating for this exact prompt
        with self._lock:
            if self._is_generating and cleaned == self._last_user_prompt:
                logger.warning("[DIAGNOSTIC] Duplicate request rejected: Prompt '%s' already in progress.", cleaned)
                return self._current_gen_id

        # Cancel previous generation if currently active
        self.cancel_generation()

        now_perf = time.perf_counter()
        with self._lock:
            self._current_gen_id += 1
            gen_id = self._current_gen_id
            self._active_token = CancellationToken()
            self._is_generating = True
            self._is_current_voice = bool(is_voice)
            self._last_user_prompt = cleaned
            self._active_request_id = request_id or f"req_{int(time.time() * 1000)}_{gen_id}"
            self._t_backend_received = backend_received_time or now_perf
            self._client_timestamp = client_timestamp
            self._gen_start_time = now_perf
            self._first_token_time = None
            self._t_first_token = 0.0
            self._t_llm_completed = 0.0

        # Phase 4: Context-Aware Interruption Context Injection
        if interruption_context:
            itype = interruption_context.get("type", "general")
            orig_query = interruption_context.get("original_query", "")
            actually_spoken = interruption_context.get("actually_spoken", "")
            interruption_text = cleaned

            # Record previous assistant spoken turn in context history so continuity is preserved
            if actually_spoken and hasattr(self.context, "record_interrupted_turn"):
                self.context.record_interrupted_turn(actually_spoken)
            elif actually_spoken and self.context._history and self.context._history[-1].get("role") == "user":
                self.context.add_assistant_message(f"{actually_spoken} [interrupted]")

            if itype == "correction":
                cleaned = (
                    f"[CONVERSATION CONTEXT - USER CORRECTION]\n"
                    f"Previous User Request: \"{orig_query}\"\n"
                    f"What you spoke before being interrupted: \"{actually_spoken}\"\n"
                    f"User's Correction: \"{interruption_text}\"\n\n"
                    f"Instruction: The user interrupted because your previous explanation had a misconception or they meant something else. "
                    f"Directly acknowledge the correction and answer according to what the user actually wants. "
                    f"Do NOT repeat the parts of the answer that you already communicated."
                )
            elif itype == "follow_up":
                cleaned = (
                    f"[CONVERSATION CONTEXT - USER FOLLOW-UP QUESTION]\n"
                    f"Previous User Request: \"{orig_query}\"\n"
                    f"What you spoke before being interrupted: \"{actually_spoken}\"\n"
                    f"User's Follow-up: \"{interruption_text}\"\n\n"
                    f"Instruction: The user interrupted with a follow-up question regarding what you just said. "
                    f"Answer their question directly in context. Continue naturally without restarting the entire previous answer from the beginning."
                )
            elif itype == "topic_change":
                cleaned = (
                    f"[CONVERSATION CONTEXT - TOPIC CHANGE]\n"
                    f"User's New Request: \"{interruption_text}\"\n\n"
                    f"Instruction: The user has interrupted and abandoned the previous topic to ask about a new subject. "
                    f"Immediately switch to the new topic and answer the new question directly."
                )

        # Deterministic Ground Truth Date and Time Evaluation
        configured_resp_lang = self.config_manager.get("language.response_language", "en") if self.config_manager else "en"
        date_eval = None
        if str(configured_resp_lang).lower().strip() in ("en", ""):
            from app.ai.datetime_evaluator import DateTimeEvaluator
            date_eval = DateTimeEvaluator.extract_and_answer(
                cleaned,
                personality=self.personality_manager.active_personality,
                is_voice=is_voice,
            )
        if date_eval is not None:
            answer_text, details = date_eval
            self.context.add_user_message(cleaned)
            logger.info(
                "[DATE_EVALUATOR] Deterministic date match (gen_id=%d): intent=%s, tz=%s, loc=%s, resp='%s'",
                gen_id,
                details.get("intent"),
                details.get("timezone"),
                details.get("location"),
                answer_text,
            )
            self._gen_start_time = time.perf_counter()
            self._first_token_time = None
            from app.core.buddy_state_manager import get_buddy_state_manager
            _sm = get_buddy_state_manager()
            if not (_sm and _sm.is_sleeping):
                signals.character_state_changed.emit("thinking")
            self.generation_started.emit(gen_id, cleaned)

            worker_signals = _WorkerSignals()
            worker_signals.chunk_received.connect(self._on_chunk_received)
            worker_signals.completed.connect(self._on_completed)
            worker_signals.cancelled.connect(self._on_cancelled)
            worker_signals.failed.connect(self._on_failed)

            worker = _DeterministicWorker(
                generation_id=gen_id,
                response_text=answer_text,
                cancellation_token=self._active_token,
                signals=worker_signals,
            )
            self.thread_pool.start(worker)
            try:
                from app.core.diagnostic_mode import diagnostic_tracker
                diagnostic_tracker.update_model_generation("thinking")
                diagnostic_tracker.update_assistant_response("receiving")
            except Exception:
                pass
            return gen_id

        # Phase 5: Optional Deterministic Fast Greeting Path for standalone greetings
        if getattr(self, "fast_greeting_enabled", True) and str(configured_resp_lang).lower().strip() in ("en", ""):
            from app.ai.greeting_evaluator import GreetingEvaluator
            greeting_eval = GreetingEvaluator.extract_and_answer(
                cleaned,
                companion_name=self.personality_manager.companion_name,
                personality=self.personality_manager.active_personality,
                is_voice=is_voice,
            )
            if greeting_eval is not None:
                answer_text, details = greeting_eval
                self.context.add_user_message(cleaned)
                logger.info(
                    "[GREETING_EVALUATOR] Fast greeting matched (gen_id=%d): salutation='%s', pers='%s', resp='%s'",
                    gen_id,
                    details.get("salutation"),
                    details.get("personality"),
                    answer_text,
                )
                self._gen_start_time = time.perf_counter()
                self._first_token_time = None
                from app.core.buddy_state_manager import get_buddy_state_manager
                _sm = get_buddy_state_manager()
                if not (_sm and _sm.is_sleeping):
                    signals.character_state_changed.emit("thinking")
                self.generation_started.emit(gen_id, cleaned)

                worker_signals = _WorkerSignals()
                worker_signals.chunk_received.connect(self._on_chunk_received)
                worker_signals.completed.connect(self._on_completed)
                worker_signals.cancelled.connect(self._on_cancelled)
                worker_signals.failed.connect(self._on_failed)

                worker = _DeterministicWorker(
                    generation_id=gen_id,
                    response_text=answer_text,
                    cancellation_token=self._active_token,
                    signals=worker_signals,
                )
                self.thread_pool.start(worker)
                try:
                    from app.core.diagnostic_mode import diagnostic_tracker
                    diagnostic_tracker.update_model_generation("thinking")
                    diagnostic_tracker.update_assistant_response("receiving")
                except Exception:
                    pass
                return gen_id

        # Check Ollama availability before queueing, attempting auto-launch via supervisor only if executable exists
        if not self.model_manager.is_available():
            logger.warning("[DIAGNOSTIC] Ollama health check FAILED on first attempt. Retrying with extended timeout...")
            if hasattr(self.model_manager, "supervisor") and self.model_manager.supervisor.find_ollama_executable():
                self.model_manager.supervisor.ensure_server_running(self.client.base_url, timeout=2.0)

        if not self.model_manager.is_available():
            if getattr(self, "offline_fallback", False) and hasattr(self, "offline_engine"):
                logger.warning(
                    "[DIAGNOSTIC][OFFLINE_FALLBACK] Ollama is OFFLINE — routing gen_id=%d to OfflineCompanionEngine. "
                    "User prompt: '%s'. This means the user will get a rule-based response instead of an LLM response.",
                    gen_id, cleaned[:80],
                )
                self._gen_start_time = time.perf_counter()
                self._first_token_time = None
                from app.core.buddy_state_manager import get_buddy_state_manager
                _sm = get_buddy_state_manager()
                if not (_sm and _sm.is_sleeping):
                    signals.character_state_changed.emit("thinking")
                self.generation_started.emit(gen_id, cleaned)

                worker_signals = _WorkerSignals()
                worker_signals.chunk_received.connect(self._on_chunk_received)
                worker_signals.completed.connect(self._on_completed)
                worker_signals.cancelled.connect(self._on_cancelled)
                worker_signals.failed.connect(self._on_failed)

                worker = _OfflineWorker(
                    generation_id=gen_id,
                    engine=self.offline_engine,
                    user_prompt=cleaned,
                    cancellation_token=self._active_token,
                    signals=worker_signals,
                )
                self.thread_pool.start(worker)
                return gen_id
            else:
                err = "Ollama is currently offline. Please launch the Ollama service to chat."
                logger.warning("Generation aborted: %s", err)
                # Ensure chat window displays a response bubble rather than freezing
                self.generation_started.emit(gen_id, cleaned)
                self._handle_error(gen_id, err)
                return gen_id

        # Intelligent Automatic Model Routing (Phase 4)
        auto_routing = True
        if self.config_manager:
            auto_routing = bool(self.config_manager.get("ai.auto_model_routing", True))

        routing_decision = None
        if hasattr(self.model_manager, "route_and_select_model"):
            try:
                hist = self.context.get_history() if hasattr(self.context, "get_history") else None
                routing_decision = self.model_manager.route_and_select_model(
                    prompt=cleaned,
                    context_history=hist,
                    images=images,
                    attachments=attachments,
                    is_voice=is_voice,
                    format_json=format_json,
                    auto_routing_enabled=auto_routing,
                )
            except Exception as route_err:
                logger.warning("Model router error: %s. Using default model selection.", route_err)

        active_model = self.model_manager.active_model
        self.config.model = active_model
        self._last_routing_decision = routing_decision

        if routing_decision:
            try:
                signals.model_routed.emit(routing_decision.to_dict())
            except Exception:
                pass

        self._last_user_prompt = cleaned

        # 10.8 Emotion Classification & Tone Adaptation
        emotion, confidence = self.emotion_classifier.classify(cleaned)
        if emotion != EmotionType.NEUTRAL:
            logger.info("Detected user emotion: %s (confidence: %.2f)", emotion.value, confidence)
            signals.user_emotion_detected.emit(emotion.value, confidence)

        tone_instruction = self.emotion_classifier.get_tone_instruction(emotion)

        # 10.4 Long-Term Memory Retrieval & Context Injection
        if self.memory_enabled:
            relevant_mems = self.memory_manager.search_memories(cleaned, limit=5)
            mem_snippets = [f"[{m.category.upper()}] {m.content}" for m in relevant_mems]
            self.context.inject_memories(mem_snippets)

            relevant_summaries = self.memory_manager.search_summaries(cleaned, limit=2)
            sum_snippets = [s.summary for s in relevant_summaries]
            self.context.inject_summaries(sum_snippets)
        else:
            self.context.clear_memories()
            self.context.clear_summaries()

        # Feedback Preferences Guidance Injection (Personalization via Like / Dislike)
        feedback_guidance = ""
        repo = getattr(self, "conv_repo", None)
        if repo and hasattr(repo, "get_feedback_prompt_guidance"):
            try:
                feedback_guidance = repo.get_feedback_prompt_guidance()
            except Exception as e:
                logger.debug("Feedback guidance extraction notice: %s", e)

        if feedback_guidance:
            self.context.inject_feedback_guidance(feedback_guidance)
        else:
            self.context.clear_feedback_guidance()

        # 10.5 Deterministic Arithmetic Math Evaluation
        from app.ai.math_evaluator import MathExpressionEvaluator
        math_sol = MathExpressionEvaluator.extract_and_solve(cleaned)
        math_instruction = ""
        if math_sol is not None:
            expr, val, formatted = math_sol
            logger.info("Deterministic arithmetic calculation: %s = %s (%s)", expr, val, formatted)
            math_instruction = (
                f"\n[Verified Calculation Ground Truth]: The user is asking about the arithmetic expression '{expr}'. "
                f"The exact mathematical result is {formatted} (numerical: {val}). "
                f"You MUST state {val} or {formatted} as the correct answer. Never calculate or guess any other number."
            )

        # Phase 5: Adaptive Response Style Resolution & Override Detection
        from app.ai.adaptive_response_style import AdaptiveStyleDetector, ResponseStyle
        active_style = None
        if response_style:
            active_style = ResponseStyle.from_string(str(response_style))
        else:
            prev_style = getattr(self, "_current_adaptive_style", ResponseStyle.NORMAL_CONVERSATION)
            detected_style, is_override, reason = AdaptiveStyleDetector.detect_style(
                user_prompt=cleaned,
                is_voice=is_voice,
                current_style=prev_style,
            )
            active_style = detected_style
            if is_override or detected_style != prev_style:
                self._current_adaptive_style = detected_style
                logger.info(
                    "[ADAPTIVE_STYLE] Response style set to '%s' (is_override=%s, reason='%s')",
                    detected_style.value, is_override, reason,
                )
                try:
                    signals.adaptive_style_changed.emit(detected_style.value)
                except Exception:
                    pass

        # Phase 6: Short Acknowledgement Handling (6.2)
        from app.ai.turn_taking_manager import TurnTakingManager
        is_ack, ack_term = TurnTakingManager.is_short_acknowledgement(cleaned)
        ack_instruction = ""
        if is_ack:
            logger.info("[TURN_TAKING] Short conversational acknowledgement detected: '%s' (term='%s')", cleaned, ack_term)
            if not response_style:
                active_style = ResponseStyle.QUICK_ANSWER
            ack_instruction = TurnTakingManager.build_acknowledgement_instruction(
                user_text=cleaned,
                response_language=str(configured_resp_lang),
            )

        # Build prompt & context
        system_prompt = self.personality_manager.build_system_prompt(
            is_voice=is_voice,
            response_style=active_style.value,
            user_input=cleaned,
        )
        if tone_instruction:
            system_prompt = f"{system_prompt}\n\n{tone_instruction}"
        if math_instruction:
            system_prompt = f"{system_prompt}\n{math_instruction}"
        if ack_instruction:
            system_prompt = f"{system_prompt}\n\n{ack_instruction}"
        self.context.set_system_prompt(system_prompt)

        # Ingest document and media attachments into user prompt context (Phase 7)
        from app.ai.attachment_processor import build_multimodal_prompt_context

        resolved_images: List[str] = list(images) if images else []
        if attachments:
            user_turn_content, resolved_from_att, att_refs = build_multimodal_prompt_context(
                attachments=attachments,
                user_prompt=cleaned,
            )
            for img_b64 in resolved_from_att:
                if img_b64 and img_b64 not in resolved_images:
                    resolved_images.append(img_b64)
        else:
            user_turn_content = cleaned

        # Phase 7 Requirement B: Vision Model Verification & Safe Fallback
        # A normal text-only model must never be falsely treated as a vision model.
        if resolved_images:
            has_vision = False
            from app.ai.model_capability_registry import ModelCapability, get_model_capability_registry
            reg = getattr(self, "model_capability_registry", None) or get_model_capability_registry()

            if reg.supports_capability(active_model, ModelCapability.VISION):
                has_vision = True
            else:
                # Can we select an installed model that supports vision?
                vision_candidates = reg.get_models_with_capability(ModelCapability.VISION)
                installed_vision = [m for m in vision_candidates if m.installed and m.model_id in self.model_manager.installed_models]
                if installed_vision:
                    active_model = installed_vision[0].model_id
                    self.config.model = active_model
                    has_vision = True
                    logger.info("[MULTIMODAL] Switched to installed vision model '%s' for visual media understanding.", active_model)

            if not has_vision:
                logger.warning("[MULTIMODAL] Image/video attached but NO local vision model is installed.")
                installed_str = ", ".join(self.model_manager.installed_models) or "None"
                att_names = ", ".join(a.get("name", "media") for a in (attachments or [])) or "media"
                explanation = (
                    f"I received your visual media ('{att_names}'), but no local vision-capable model is currently installed.\n\n"
                    f"The currently installed models (`{installed_str}`) are text-only models and cannot inspect image pixels or video frames.\n\n"
                    f"To enable image understanding and video analysis locally with Bond, please install a vision model using Ollama:\n\n"
                    f"```bash\nollama pull gemma3:4b\n```\n"
                    f"or `ollama pull llava:7b`. Once downloaded, Bond will automatically route all visual media to it."
                )
                self.context.add_user_message(user_turn_content)
                self._gen_start_time = time.perf_counter()
                self._first_token_time = None
                from app.core.buddy_state_manager import get_buddy_state_manager
                _sm = get_buddy_state_manager()
                if not (_sm and _sm.is_sleeping):
                    signals.character_state_changed.emit("thinking")
                self.generation_started.emit(gen_id, cleaned)

                worker_signals = _WorkerSignals()
                worker_signals.chunk_received.connect(self._on_chunk_received)
                worker_signals.completed.connect(self._on_completed)
                worker_signals.cancelled.connect(self._on_cancelled)
                worker_signals.failed.connect(self._on_failed)

                worker = _DeterministicWorker(
                    generation_id=gen_id,
                    response_text=explanation,
                    cancellation_token=self._active_token,
                    signals=worker_signals,
                )
                self.thread_pool.start(worker)
                return gen_id

        self.context.add_user_message(user_turn_content)

        messages = self.context.get_messages()

        # Phase 5 & 6: Dynamic Task-Complexity & Adaptive Style Token Allocation
        configured_max = self.config_manager.get("ai.max_tokens", None) if self.config_manager else None
        estimated_predict = GenerationConfig.estimate_task_token_budget(
            user_prompt=user_turn_content,
            is_voice=is_voice,
            configured_limit=configured_max,
            style=active_style,
        )
        if is_ack:
            estimated_predict = min(estimated_predict, 45 if is_voice else 80)

        options = self.config.to_ollama_options()
        options["num_predict"] = estimated_predict
        # Dynamic context window: allocate ample capacity (min 4096, default 8192)
        options["num_ctx"] = max(int(options.get("num_ctx", 2048)), 4096)
        options["max_continuations"] = 1 if is_voice else 2

        logger.info(
            "[TOKEN_BUDGET] Task budget assigned: num_predict=%d, num_ctx=%d (is_voice=%s, prompt_len=%d)",
            estimated_predict, options["num_ctx"], is_voice, len(user_turn_content)
        )

        # Transition character state to THINKING (if awake or text chat)
        self._gen_start_time = time.perf_counter()
        self._first_token_time = None
        from app.core.buddy_state_manager import get_buddy_state_manager
        _sm = get_buddy_state_manager()
        if not is_voice or not (_sm and _sm.is_sleeping):
            signals.character_state_changed.emit("thinking")
        self.generation_started.emit(gen_id, cleaned)

        # Worker signals and dispatch
        worker_signals = _WorkerSignals()
        worker_signals.chunk_received.connect(self._on_chunk_received)
        worker_signals.completed.connect(self._on_completed)
        worker_signals.cancelled.connect(self._on_cancelled)
        worker_signals.failed.connect(self._on_failed)
        self._worker_signals_by_gen[gen_id] = worker_signals

        # Attach multimodal images to the user turn if present
        if resolved_images and messages and messages[-1].get("role") == "user":
            messages[-1]["images"] = list(resolved_images)

        self._request_payloads_by_gen[gen_id] = {
            "cleaned": cleaned,
            "is_voice": is_voice,
            "images": resolved_images,
            "attachments": attachments,
            "format_json": format_json,
            "options": options,
            "messages": messages,
            "active_model": active_model,
        }

        worker = _InferenceWorker(
            generation_id=gen_id,
            client=self.client,
            model=active_model,
            messages=messages,
            options=options,
            cancellation_token=self._active_token,
            signals=worker_signals,
            keep_alive=getattr(self.model_manager, "model_keep_alive", "5m"),
            format="json" if format_json else None,
        )

        self.model_manager.touch_activity()
        self.thread_pool.start(worker)
        try:
            from app.core.diagnostic_mode import diagnostic_tracker
            diagnostic_tracker.update_model_generation("thinking")
            diagnostic_tracker.update_assistant_response("receiving")
        except Exception:
            pass
        logger.info("[BOUNDARY] Local model generation started: gen_id=%d, model='%s', is_voice=%s", gen_id, active_model, is_voice)
        logger.info("[DIAGNOSTIC] User message accepted (gen_id=%d).", gen_id)
        logger.info("[DIAGNOSTIC] AI request started (gen_id=%d, model='%s').", gen_id, active_model)
        logger.info("Dispatched generation #%d for model '%s'", gen_id, active_model)
        return gen_id

    @Slot()
    def cancel_generation(self) -> None:
        """Cancel ongoing generation immediately and discard subsequent chunks (Phase 6)."""
        with self._lock:
            if not self._is_generating or not self._active_token:
                return
            token = self._active_token
            gen_id = self._current_gen_id
            self._is_generating = False
            self._current_gen_id += 1  # Invalidate pending workers

        token.cancel()
        from app.core.buddy_state_manager import get_buddy_state_manager
        sm = get_buddy_state_manager()
        if not (sm and sm.is_sleeping):
            signals.character_state_changed.emit("idle")
        signals.ai_generation_cancelled.emit()
        self.generation_cancelled.emit(gen_id)
        logger.info("[DIAGNOSTIC] Errors and cancellations: Generation #%d cancelled.", gen_id)
        logger.info("Cancelled ongoing generation #%d.", gen_id)

    def clear_context(self) -> None:
        """Clear conversation history."""
        self.context.clear()
        logger.info("Conversation context cleared.")

    def stop(self) -> None:
        """Clean shutdown hook for background service coordination."""
        self.cancel_generation()
        self._inactivity_timer.stop()
        self.model_manager.unload_immediately()
        if hasattr(self.model_manager, "supervisor"):
            self.model_manager.supervisor.stop_server()

    # ─── Worker Event Handlers ─────────────────────────────────────────

    @Slot(int, str)
    def _on_chunk_received(self, gen_id: int, chunk: str) -> None:
        """Handle incoming token chunk from inference worker."""
        with self._lock:
            if gen_id != self._current_gen_id or not self._is_generating:
                return
            is_voice = getattr(self, "_is_current_voice", True)
            now_perf = time.perf_counter()
            if getattr(self, "_t_first_token", 0.0) == 0.0:
                self._t_first_token = now_perf
            if getattr(self, "_first_token_time", None) is None:
                start_time = getattr(self, "_gen_start_time", now_perf)
                self._first_token_time = now_perf - start_time
                logger.info("[LATENCY_PROFILE] AI First Token received (TTFT): %.1fms (gen_id=%d)", self._first_token_time * 1000.0, gen_id)
                logger.info("[BOUNDARY] First model output received: gen_id=%d, latency=%.3fs", gen_id, self._first_token_time)

        from app.core.buddy_state_manager import get_buddy_state_manager
        sm = get_buddy_state_manager()
        is_sleeping = sm and sm.is_sleeping

        # If sleeping and this generation was voice-originated, drop it
        if is_sleeping and is_voice:
            return

        # On the first emitted token chunk, switch character animation to SPEAKING if awake or text chat
        if not is_voice or not is_sleeping:
            signals.character_state_changed.emit("speaking")
        signals.ai_response_chunk.emit(chunk)
        try:
            from app.core.diagnostic_mode import diagnostic_tracker
            diagnostic_tracker.update_model_generation("generating")
        except Exception:
            pass

    @Slot(int, str)
    def _on_completed(self, gen_id: int, full_response: str) -> None:
        """Handle successful inference completion."""
        now_perf = time.perf_counter()
        with self._lock:
            if gen_id != self._current_gen_id:
                return
            self._is_generating = False
            self._t_llm_completed = now_perf
            is_voice = getattr(self, "_is_current_voice", True)
            start_time = getattr(self, "_gen_start_time", now_perf)
            total_duration = now_perf - start_time
            first_tok = getattr(self, "_first_token_time", None)
            if first_tok is None:
                first_tok = total_duration

            # Assemble response-time monitoring telemetry for this generation
            req_id = self._active_request_id or f"req_{gen_id}"
            t_recv = self._t_backend_received or start_time
            t_llm_start = start_time
            t_first_tok_perf = self._t_first_token if self._t_first_token > 0.0 else now_perf

            w_signals = self._worker_signals_by_gen.pop(gen_id, None)
            meta = w_signals.get_metadata(gen_id) if w_signals else {}
            done_reason = meta.get("done_reason", "stop")
            truncated = bool(meta.get("truncated", False) or done_reason == "length")
            eval_count = meta.get("eval_count", 0)
            continuations = meta.get("continuations", 0)

            self._latest_timing_metrics = {
                "request_id": req_id,
                "client_timestamp": self._client_timestamp,
                "t_backend_received": t_recv,
                "t_llm_start": t_llm_start,
                "t_first_token": t_first_tok_perf,
                "t_llm_completed": now_perf,
                "backend_to_llm_start_ms": max(0.0, (t_llm_start - t_recv) * 1000.0),
                "llm_time_to_first_token_ms": max(0.0, (t_first_tok_perf - t_llm_start) * 1000.0),
                "llm_generation_duration_ms": max(0.0, (now_perf - t_first_tok_perf) * 1000.0),
                "total_backend_duration_ms": max(0.0, (now_perf - t_recv) * 1000.0),
                "total_model_duration_ms": max(0.0, (now_perf - t_llm_start) * 1000.0),
                "response_length_chars": len(full_response),
                "done_reason": done_reason,
                "finish_reason": done_reason,
                "truncated": truncated,
                "eval_count": eval_count,
                "continuations": continuations,
            }

        from app.core.buddy_state_manager import get_buddy_state_manager
        sm = get_buddy_state_manager()
        is_sleeping = sm and sm.is_sleeping

        if is_sleeping and is_voice:
            logger.info("Discarding completed voice AI inference result: Buddy is currently sleeping (Phase 6).")
            return

        if not full_response.strip():
            logger.warning("[DIAGNOSTIC] Errors and cancellations: Generation #%d produced empty response. Discarding without conversational trigger.", gen_id)
            if not is_sleeping:
                signals.character_state_changed.emit("idle")
            return

        logger.info("[BOUNDARY] Assistant response completed: gen_id=%d, len=%d, total_sec=%.2f", gen_id, len(full_response), total_duration)

        try:
            from app.core.performance_monitor import get_performance_monitor
            get_performance_monitor().record_ai_latency(first_tok, total_duration, len(full_response))
        except Exception:
            pass

        # Ensure response script strictly matches configured format (Native vs Romanized)
        resp_lang = self.config_manager.get("language.response_language", "en") if self.config_manager else "en"
        if resp_lang not in ("en", "gu", "hi"):
            resp_lang = "en"
        resp_fmt = self.config_manager.get("language.response_format", "native") if self.config_manager else "native"
        from app.ai.multilingual_engine import MultilingualEngine
        formatted_response = MultilingualEngine.format_response_script(
            text=full_response,
            target_language=str(resp_lang),
            target_format=str(resp_fmt),
        )

        self.context.add_assistant_message(formatted_response)
        self.model_manager.touch_activity()
        logger.info("[DIAGNOSTIC] AI response completed (gen_id=%d, length=%d).", gen_id, len(formatted_response))

        signals.ai_response_complete.emit(formatted_response)
        self.generation_completed.emit(gen_id, formatted_response)

        # Restore IDLE animation if not sleeping or text chat
        if not is_voice or not is_sleeping:
            signals.character_state_changed.emit("idle")

        # Phase 10.3: Automatic Memory Extraction
        if self.memory_enabled and self.auto_extract_memory and self._last_user_prompt:
            try:
                extracted = self.memory_manager.extract_memories_from_text(
                    user_text=self._last_user_prompt,
                    source_conv_id=self.active_conversation_id,
                )
                for mem in extracted:
                    signals.memory_stored.emit(mem)
            except Exception as e:
                logger.debug("Automatic memory extraction notice: %s", e)

        if hasattr(self.model_manager, "clear_model_failure"):
            self.model_manager.clear_model_failure(self.model_manager.active_model)
        self._request_payloads_by_gen.pop(gen_id, None)
        self._fallback_attempts_by_gen.pop(gen_id, None)

        try:
            from app.core.diagnostic_mode import diagnostic_tracker
            diagnostic_tracker.update_model_generation("completed")
            diagnostic_tracker.update_assistant_response("received")
        except Exception:
            pass
        logger.info("Generation #%d completed successfully (%d chars).", gen_id, len(full_response))

    def get_latest_timing_metrics(self) -> Dict[str, Any]:
        """Return the timing telemetry dictionary from the most recent LLM generation."""
        with self._lock:
            return dict(self._latest_timing_metrics)

    def set_memory_enabled(self, enabled: bool) -> None:
        """Enable or disable long-term memory retrieval and extraction (Phase 10.6, 10.10)."""
        self.memory_enabled = enabled
        if not self.memory_enabled:
            self.context.clear_memories()
            self.context.clear_summaries()
        if self.config_manager:
            self.config_manager.set("memory.enabled", self.memory_enabled)
        logger.info("AI Service memory enabled set to: %s", self.memory_enabled)

    def set_auto_extract_memory(self, enabled: bool) -> None:
        """Enable or disable automatic extraction of memories from dialogue (Phase 10.3, 10.6)."""
        self.auto_extract_memory = enabled
        if self.config_manager:
            self.config_manager.set("memory.auto_extract_enabled", self.auto_extract_memory)
        logger.info("AI Service auto-extract memory set to: %s", self.auto_extract_memory)

    def set_personality(self, personality_key: str) -> bool:
        """Update companion personality profile (Phase 10.7)."""
        ok = self.personality_manager.set_personality(personality_key)
        if ok and self.config_manager:
            self.config_manager.set("ai.personality", personality_key)
        return ok

    def get_personality(self) -> str:
        """Get active companion personality profile key (Phase 10.7)."""
        return self.personality_manager.active_personality

    def get_voice_for_persona(self, persona_key: Optional[str] = None) -> str:
        """Get voice profile ID mapped to persona (Phase 2.1)."""
        return self.personality_manager.get_voice_for_persona(persona_key)

    def set_voice_for_persona(self, persona_key: str, voice_profile_id: str) -> bool:
        """Map persona to voice profile and persist (Phase 2.2)."""
        return self.personality_manager.set_voice_for_persona(persona_key, voice_profile_id)

    @Slot(int)
    def _on_cancelled(self, gen_id: int) -> None:
        """Handle worker cancellation acknowledgement."""
        self._request_payloads_by_gen.pop(gen_id, None)
        self._fallback_attempts_by_gen.pop(gen_id, None)
        with self._lock:
            if gen_id == self._current_gen_id:
                self._is_generating = False
        from app.core.buddy_state_manager import get_buddy_state_manager
        sm = get_buddy_state_manager()
        if not (sm and sm.is_sleeping):
            signals.character_state_changed.emit("idle")

    @Slot(int, str)
    def _on_failed(self, gen_id: int, error_message: str) -> None:
        """Handle inference failure with automatic fallback if viable alternatives exist (Phase 5)."""
        payload = self._request_payloads_by_gen.get(gen_id)
        attempts = self._fallback_attempts_by_gen.get(gen_id, 0)
        failed_model = payload.get("active_model", self.model_manager.active_model) if payload else self.model_manager.active_model

        # Record failure to avoid repeated loops
        if hasattr(self.model_manager, "record_model_failure"):
            self.model_manager.record_model_failure(failed_model, error_message)

        # Automatic fallback attempt (if not cancelled and under attempt limit)
        if payload and attempts < 1 and self._active_token and not self._active_token.is_cancelled:
            hist = self.context.get_history() if hasattr(self.context, "get_history") else None
            failed_list = [failed_model]
            if hasattr(self.model_manager, "get_failed_models"):
                failed_list = self.model_manager.get_failed_models()

            fallback_decision = None
            if hasattr(self.model_manager, "route_and_select_model"):
                try:
                    fallback_decision = self.model_manager.route_and_select_model(
                        prompt=payload["cleaned"],
                        context_history=hist,
                        images=payload["images"],
                        attachments=payload["attachments"],
                        is_voice=payload["is_voice"],
                        format_json=payload["format_json"],
                        failed_models=failed_list,
                    )
                except Exception as route_err:
                    logger.warning("Fallback model router notice: %s", route_err)

            if fallback_decision and fallback_decision.selected_model != failed_model and fallback_decision.selected_model not in failed_list:
                self._fallback_attempts_by_gen[gen_id] = attempts + 1
                payload["active_model"] = fallback_decision.selected_model
                self._last_routing_decision = fallback_decision
                logger.warning(
                    "[AUTOMATIC FALLBACK] Primary model '%s' failed (%s). Retrying request with alternative '%s'...",
                    failed_model, error_message, fallback_decision.selected_model
                )

                try:
                    signals.model_routed.emit(fallback_decision.to_dict())
                except Exception:
                    pass

                # If material change, emit warning chunk so user is informed
                if fallback_decision.material_change_note or fallback_decision.fallback_notification:
                    notice = fallback_decision.fallback_notification or fallback_decision.material_change_note
                    try:
                        signals.ai_response_chunk.emit(f"*{notice}*\n\n")
                    except Exception:
                        pass

                # Dispatch retry worker
                worker_signals = _WorkerSignals()
                worker_signals.chunk_received.connect(self._on_chunk_received)
                worker_signals.completed.connect(self._on_completed)
                worker_signals.cancelled.connect(self._on_cancelled)
                worker_signals.failed.connect(self._on_failed)
                self._worker_signals_by_gen[gen_id] = worker_signals

                fallback_worker = _InferenceWorker(
                    generation_id=gen_id,
                    client=self.client,
                    model=fallback_decision.selected_model,
                    messages=payload["messages"],
                    options=payload["options"],
                    cancellation_token=self._active_token,
                    signals=worker_signals,
                    keep_alive=getattr(self.model_manager, "model_keep_alive", "5m"),
                    format="json" if payload["format_json"] else None,
                )
                self.model_manager.touch_activity()
                self.thread_pool.start(fallback_worker)
                return

        # If fallback cannot proceed or all compatible models exhausted
        self._request_payloads_by_gen.pop(gen_id, None)
        self._fallback_attempts_by_gen.pop(gen_id, None)
        with self._lock:
            if gen_id != self._current_gen_id:
                return
            self._is_generating = False

        self._handle_error(gen_id, error_message)

    def _handle_error(self, gen_id: int, message: str) -> None:
        """Report error to user with descriptive user-friendly message and update character state."""
        with self._lock:
            self._is_generating = False

        friendly_msg = message
        lowered = message.lower()
        if "not found" in lowered:
            active_m = self.model_manager.active_model
            friendly_msg = f"Model '{active_m}' is not installed in Ollama. Pull it with: 'ollama pull {active_m}' or switch model in Settings."
        elif "connection" in lowered or "unreachable" in lowered or "not running" in lowered or "offline" in lowered:
            friendly_msg = (
                "⚠️ **Ollama is offline** and could not be started automatically.\n\n"
                "To chat with local AI models:\n"
                "1. Install Ollama from [ollama.com](https://ollama.com).\n"
                "2. Run `ollama serve` (or `ollama run llama3.2`) in your terminal.\n"
                "3. Or enable **Offline Fallback** in Settings to chat with built-in rules."
            )
        elif "timed out" in lowered:
            friendly_msg = "The AI model response timed out. The request was cancelled to preserve responsiveness."

        from app.core.buddy_state_manager import get_buddy_state_manager
        sm = get_buddy_state_manager()
        if not (sm and sm.is_sleeping):
            signals.character_state_changed.emit("error")
        signals.ai_error_occurred.emit(friendly_msg)
        signals.ai_response_chunk.emit(friendly_msg)
        signals.ai_response_complete.emit(friendly_msg)
        self.error_occurred.emit(friendly_msg)
        try:
            from app.core.diagnostic_mode import diagnostic_tracker, ERROR_MODEL_UNAVAILABLE
            if "connection" in lowered or "unreachable" in lowered or "not running" in lowered or "offline" in lowered:
                diagnostic_tracker.update_model_generation("unavailable", error=ERROR_MODEL_UNAVAILABLE)
            else:
                diagnostic_tracker.update_model_generation("failed", error=friendly_msg)
            diagnostic_tracker.update_assistant_response("failed")
        except Exception:
            pass
        logger.error("[DIAGNOSTIC] Errors and cancellations: AI generation error for gen_id #%d: %s", gen_id, friendly_msg)

        # Revert to idle after brief error display
        QTimer.singleShot(3000, lambda: signals.character_state_changed.emit("idle"))

    # ─── Settings & Lifecycle ──────────────────────────────────────────

    def _check_inactivity(self) -> None:
        """Check if active model should be unloaded due to prolonged inactivity."""
        with self._lock:
            if self._is_generating:
                return
        self.model_manager.check_inactivity_and_unload()

    @Slot(str, object)
    def _on_setting_changed(self, key_path: str, new_value: Any) -> None:
        """React to runtime configuration modifications."""
        if key_path == "ai.model":
            val_str = str(new_value).strip() if new_value else ""
            if val_str and val_str != self.model_manager.active_model:
                self.model_manager.set_configured_model(val_str)
                self.config.model = self.model_manager.active_model
        elif key_path in ("ai.companion_name", "companion.name", "character.name"):
            name_str = str(new_value).strip() if new_value else "Buddy"
            self.personality_manager.set_companion_name(name_str)
            if hasattr(self, "offline_engine"):
                self.offline_engine.update_profile(companion_name=name_str)
            try:
                from app.api.websocket import ws_manager
                ws_manager.broadcast_sync("companion_name_changed", {"name": name_str})
                ws_manager.broadcast_sync("companion_profile_updated", {"name": name_str})
            except Exception:
                pass
        elif key_path == "ai.personality":
            pers_str = str(new_value).strip() if new_value else "friendly"
            self.personality_manager.set_personality(pers_str)
            if hasattr(self, "offline_engine"):
                self.offline_engine.update_profile(personality=pers_str)
        elif key_path == "ai.persona_voice_map":
            if isinstance(new_value, dict):
                for k, v in new_value.items():
                    if isinstance(v, str):
                        self.personality_manager.persona_voice_map[str(k).lower()] = v.lower()
        elif key_path == "ai.ollama_host":
            host_str = str(new_value).strip() if new_value else "http://127.0.0.1:11434"
            self.client.set_base_url(host_str)
        elif key_path == "performance.idle_unload_minutes":
            try:
                mins = float(new_value)
                self.model_manager.set_inactivity_timeout(mins * 60.0)
            except Exception:
                pass
        elif key_path == "performance.model_keep_alive":
            self.model_manager.set_keep_alive(str(new_value))
        elif key_path == "ai.fast_greeting_enabled":
            self.fast_greeting_enabled = bool(new_value)
