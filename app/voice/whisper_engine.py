"""Faster-Whisper Speech-To-Text (STT) Engine.

Runs quantized INT8 local Whisper models on CPU for real-time multilingual transcription
with zero cloud dependencies. Supports English, Hindi, Gujarati, and auto-detection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import threading
import time
from typing import Any, Callable, Dict, List, Optional

import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("KMP_BLOCKTIME", "0")

import numpy as np
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from app.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_WHISPER_MODEL = "tiny"
DEFAULT_COMPUTE_TYPE = "int8"
DEFAULT_DEVICE = "cpu"


@dataclass
class TranscriptionResult:
    """Encapsulates the output of a speech transcription."""
    text: str
    language: str
    language_probability: float
    duration_seconds: float
    segments: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not bool(self.text.strip())


class _TranscribeWorker(QRunnable):
    """Background worker runnable to transcribe audio without blocking Qt GUI thread."""

    def __init__(
        self,
        engine: "WhisperEngine",
        audio_data: np.ndarray,
        language: Optional[str],
        prompt: Optional[str],
        callback: Optional[Callable[[TranscriptionResult], None]],
        on_error: Optional[Callable[[str], None]],
    ) -> None:
        super().__init__()
        self.engine = engine
        self.audio_data = audio_data
        self.language = language
        self.prompt = prompt
        self.callback = callback
        self.on_error = on_error

    def run(self) -> None:
        try:
            result = self.engine.transcribe(
                audio_data=self.audio_data,
                language=self.language,
                prompt=self.prompt,
            )
            if self.callback:
                self.callback(result)
        except Exception as e:
            err_msg = f"Asynchronous transcription error: {e}"
            logger.error("[DIAGNOSTIC] Recognition failed: %s", err_msg)
            if self.on_error:
                self.on_error(err_msg)


class _InterimTranscribeWorker(QRunnable):
    """Background worker executing lightweight greedy interim transcription pass."""

    def __init__(
        self,
        engine: "WhisperEngine",
        audio_data: np.ndarray,
        generation_id: int,
        language: Optional[str],
        prompt: Optional[str],
        callback: Optional[Callable[[int, str], None]],
    ) -> None:
        super().__init__()
        self.engine = engine
        self.audio_data = audio_data
        self.generation_id = generation_id
        self.language = language
        self.prompt = prompt
        self.callback = callback
        self.setAutoDelete(True)

    def run(self) -> None:
        text = ""
        try:
            text = self.engine.transcribe_interim(
                audio_data=self.audio_data,
                language=self.language,
                prompt=self.prompt,
            )
        except Exception as e:
            logger.debug("Interim transcription pass skipped: %s", e)
        finally:
            if self.callback:
                try:
                    self.callback(self.generation_id, text)
                except Exception as cb_err:
                    logger.debug("Interim callback execution error: %s", cb_err)


class WhisperEngine(QObject):
    """Local Speech-to-Text inference engine powered by Faster-Whisper."""

    model_loaded = Signal(str)
    transcription_started = Signal()
    transcription_completed = Signal(object)  # Emits TranscriptionResult
    interim_transcription_ready = Signal(str)  # Emits interim text
    error_occurred = Signal(str)

    def __init__(
        self,
        model_size: str = DEFAULT_WHISPER_MODEL,
        compute_type: str = DEFAULT_COMPUTE_TYPE,
        device: str = DEFAULT_DEVICE,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.model_size = model_size
        self.compute_type = compute_type
        self.device = device

        self._model = None
        self._optimal_threads = min(12, max(4, int((os.cpu_count() or 4) * 0.6)))
        self._lock = threading.Lock()
        self._thread_pool = QThreadPool.globalInstance()

    @property
    def optimal_threads(self) -> int:
        """Configured thread allocation for CPU inference."""
        return self._optimal_threads

    # -------------------------------------------------------------------------
    # Model Lifecycle
    # -------------------------------------------------------------------------

    def load_model(
        self,
        model_size: Optional[str] = None,
        compute_type: Optional[str] = None,
        device: Optional[str] = None,
    ) -> bool:
        """Load or reload the Faster-Whisper model into memory."""
        with self._lock:
            if model_size:
                self.model_size = model_size
            if compute_type:
                self.compute_type = compute_type
            if device:
                self.device = device

            # 1. Safely import Faster-Whisper runtime
            try:
                from faster_whisper import WhisperModel
            except Exception as import_err:
                err_msg = f"Failed to import Faster-Whisper: {import_err}"
                logger.error(err_msg)
                self._model = None
                self.error_occurred.emit(err_msg)
                return False

            # 2. Attempt loading configured model with fallback to 'tiny'
            optimal_threads = self._optimal_threads
            try:
                logger.info(
                    "Loading Whisper model '%s' (compute_type=%s, device=%s, threads=%d)...",
                    self.model_size,
                    self.compute_type,
                    self.device,
                    optimal_threads,
                )
                self._model = WhisperModel(
                    model_size_or_path=self.model_size,
                    device=self.device,
                    compute_type=self.compute_type,
                    cpu_threads=optimal_threads,
                )
                logger.info("Whisper model '%s' successfully loaded.", self.model_size)
                self.model_loaded.emit(self.model_size)
                return True
            except Exception as e:
                if self.model_size != "tiny":
                    logger.warning("Could not load Whisper model '%s' (%s). Falling back to 'tiny'...", self.model_size, e)
                    try:
                        self.model_size = "tiny"
                        self._model = WhisperModel(
                            model_size_or_path="tiny",
                            device=self.device,
                            compute_type=self.compute_type,
                            cpu_threads=optimal_threads,
                        )
                        logger.info("Whisper model 'tiny' successfully loaded as fallback.")
                        self.model_loaded.emit("tiny")
                        return True
                    except Exception as fallback_err:
                        err_msg = f"Failed to load Faster-Whisper fallback model: {fallback_err}"
                        logger.error(err_msg)
                        self._model = None
                        self.error_occurred.emit(err_msg)
                        return False
                err_msg = f"Failed to load Faster-Whisper model '{self.model_size}': {e}"
                logger.error(err_msg)
                self._model = None
                self.error_occurred.emit(err_msg)
                return False

    def preload_async(self) -> None:
        """Asynchronously preload Whisper weights in background thread to avoid first-utterance latency."""
        if self.is_loaded():
            return

        class _PreloadWorker(QRunnable):
            def __init__(self, engine: "WhisperEngine") -> None:
                super().__init__()
                self.engine = engine
                self.setAutoDelete(True)

            def run(self) -> None:
                try:
                    self.engine.ensure_model_loaded()
                except Exception as ex:
                    logger.debug("Background Whisper preload notice: %s", ex)

        self._thread_pool.start(_PreloadWorker(self))

    def is_loaded(self) -> bool:
        return self._model is not None

    def ensure_model_loaded(self) -> bool:
        """Ensure the model is loaded before transcribing."""
        if not self.is_loaded():
            return self.load_model()
        return True

    def unload_model(self) -> bool:
        """Unload Whisper model weights to free RAM/VRAM."""
        with self._lock:
            if self._model is not None:
                logger.info("Unloading Faster-Whisper model '%s' from memory...", self.model_size)
                self._model = None
                import gc
                gc.collect()
                return True
            return False

    # -------------------------------------------------------------------------
    # Synchronous & Asynchronous Transcription
    # -------------------------------------------------------------------------

    def transcribe(
        self,
        audio_data: np.ndarray,
        language: Optional[str] = None,
        prompt: Optional[str] = None,
        beam_size: int = 1,
    ) -> TranscriptionResult:
        """Transcribe a 16kHz float32 audio numpy array synchronously.
        
        Args:
            audio_data: 1D numpy array of audio samples (float32, 16000 Hz).
            language: Language code (e.g. 'en', 'hi', 'gu') or None for auto-detect.
            prompt: Optional initial prompt for context or domain vocabulary.
            beam_size: Beam search width (1 = fast greedy search, recommended for real-time).
        """
        if not self.ensure_model_loaded():
            raise RuntimeError("Faster-Whisper model is not loaded.")

        self.transcription_started.emit()
        start_time = time.perf_counter()

        # Prepare and validate audio
        prepared_audio = self._prepare_audio(audio_data)
        duration_sec = len(prepared_audio) / 16000.0

        if len(prepared_audio) < 1200:  # < 75ms
            logger.debug("Audio clip too short (%.2fs); returning empty result.", duration_sec)
            result = TranscriptionResult(
                text="",
                language=language or "en",
                language_probability=1.0,
                duration_seconds=duration_sec,
            )
            self.transcription_completed.emit(result)
            return result

        # Language configuration & prompt isolation
        effective_lang = None if (language in (None, "", "auto")) else language.lower().strip()
        effective_prompt = prompt
        if effective_lang is None and prompt and "buddy ai" in prompt.lower():
            effective_prompt = None  # Prevent English prompt bias during auto-detection

        try:
            with self._lock:
                segments_gen, info = self._model.transcribe(
                    prepared_audio,
                    language=effective_lang,
                    task="transcribe",  # Explicitly transcribe, never translate
                    initial_prompt=effective_prompt,
                    beam_size=beam_size,
                    temperature=0.0,
                    condition_on_previous_text=False,
                    compression_ratio_threshold=2.4,
                    repetition_penalty=1.2,
                    vad_filter=False,  # Audio is already cleanly segmented by VADEngine
                    vad_parameters=dict(min_silence_duration_ms=400),
                )
                raw_segments = list(segments_gen)

            collected_text_parts: List[str] = []
            segment_list: List[Dict[str, Any]] = []

            for seg in raw_segments:
                seg_text = seg.text.strip()
                no_speech = getattr(seg, "no_speech_prob", None)
                # Only discard segment if Whisper is overwhelmingly confident there is no speech (> 0.88)
                if isinstance(no_speech, (int, float)) and no_speech > 0.88:
                    continue
                if seg_text:
                    collected_text_parts.append(seg_text)
                    segment_list.append({
                        "id": seg.id,
                        "start": seg.start,
                        "end": seg.end,
                        "text": seg_text,
                        "avg_logprob": getattr(seg, "avg_logprob", 0.0),
                    })

            full_text = " ".join(collected_text_parts).strip()

            # Hallucination filter: discard known subtitle/phantom artifacts
            # NOTE: Legitimate short responses like "thank you" or "bye" must NOT be filtered!
            hallucinations = {
                "photo", "photo.", "photo!", "photos", "photos.", "like photo", "like photo.",
                "thank you for watching", "thank you for watching.",
                "please like and subscribe", "like and subscribe",
                "subtitles by the amara.org community", "subtitles by", "transcribed by",
                "buddy ai desktop companion", "hinglish, hindi, gujarati",
            }
            cleaned_norm = full_text.lower().strip(".,!?:;\"' ")
            if cleaned_norm in hallucinations or cleaned_norm.startswith(("subtitles by", "transcribed by", "like and subscribe", "please like and subscribe")):
                logger.info("Filtered hallucinated Whisper phantom phrase: '%s'", full_text)
                full_text = ""

            # Filter single punctuation or tiny noise
            if len(cleaned_norm) <= 1:
                full_text = ""

            # Repetition loop filter: e.g. "very, very, very, very..."
            words = full_text.split()
            if len(words) >= 6:
                from collections import Counter
                counts = Counter([w.lower().strip(".,!?:;\"' ") for w in words])
                most_common_word, count = counts.most_common(1)[0]
                if count / len(words) > 0.45:
                    logger.info("Filtered Whisper repetitive loop phrase ('%s' x%d): '%s'", most_common_word, count, full_text[:60])
                    full_text = ""

            # Reject foreign language hallucinations on room noise only when language was unconstrained
            # and Whisper identified an obscure language with high confidence while text is non-Latin
            common_langs = (
                "en", "hi", "gu", "ur", "pa", "mr", "es", "fr", "de", "it",
                "ja", "ko", "zh", "ru", "pt", "ar", "bn", "ta", "te", "kn"
            )
            if not language and info.language not in common_langs and info.language_probability > 0.85:
                # If the transcribed text is standard ASCII letters, preserve it as it is likely English with an accent
                is_ascii_alpha = any(c.isascii() and c.isalpha() for c in full_text)
                if not is_ascii_alpha:
                    logger.info("Filtered Whisper unexpected language hallucination [%s (%.2f)]: '%s'", info.language, info.language_probability, full_text[:60])
                    full_text = ""
            elapsed = time.perf_counter() - start_time
            if full_text:
                logger.info("[DIAGNOSTIC] Transcription completed: '%s' [%s]", full_text, info.language)
            else:
                logger.info("[DIAGNOSTIC] Empty transcription rejected.")

            logger.info(
                "[LATENCY_PROFILE] STT (Whisper) completed in %.1fms (audio: %.2fs, text: '%s', lang: %s)",
                elapsed * 1000.0,
                duration_sec,
                full_text,
                info.language,
            )
            logger.info(
                "Transcribed %.1fs audio in %.2fs [Lang: %s (%.2f)]: '%s'",
                duration_sec,
                elapsed,
                info.language,
                info.language_probability,
                full_text,
            )
            try:
                from app.core.performance_monitor import get_performance_monitor
                get_performance_monitor().record_stt_duration(elapsed, duration_sec)
            except Exception:
                pass

            # Constrain detected language strictly among the 3 supported user languages (en, gu, hi)
            final_detected_lang = info.language
            if final_detected_lang not in ("en", "gu", "hi"):
                if any('\u0A80' <= c <= '\u0AFF' for c in full_text):
                    final_detected_lang = "gu"
                elif any('\u0900' <= c <= '\u097F' for c in full_text):
                    final_detected_lang = "hi"
                elif getattr(info, "all_language_probs", None):
                    probs = dict(info.all_language_probs)
                    final_detected_lang = max(("en", "gu", "hi"), key=lambda l: probs.get(l, 0.0))
                else:
                    final_detected_lang = "en"

            result = TranscriptionResult(
                text=full_text,
                language=final_detected_lang,
                language_probability=float(info.language_probability),
                duration_seconds=duration_sec,
                segments=segment_list,
            )
            self.transcription_completed.emit(result)
            return result

        except Exception as e:
            err_msg = f"Transcription failed: {e}"
            logger.error("[DIAGNOSTIC] Recognition failed: %s", err_msg)
            self.error_occurred.emit(err_msg)
            raise

    def transcribe_async(
        self,
        audio_data: np.ndarray,
        callback: Optional[Callable[[TranscriptionResult], None]] = None,
        language: Optional[str] = None,
        prompt: Optional[str] = None,
    ) -> None:
        """Submit audio transcription to the background thread pool."""
        worker = _TranscribeWorker(
            engine=self,
            audio_data=audio_data,
            language=language,
            prompt=prompt,
            callback=callback,
            on_error=lambda err: self.error_occurred.emit(err),
        )
        self._thread_pool.start(worker)

    def transcribe_interim(
        self,
        audio_data: np.ndarray,
        language: Optional[str] = None,
        prompt: Optional[str] = None,
    ) -> str:
        """Fast greedy interim transcription pass on progressive audio buffer."""
        prepared_audio = self._prepare_audio(audio_data)
        if len(prepared_audio) < 2400:  # < 150ms
            return ""

        if not self.ensure_model_loaded():
            return ""

        effective_lang = None if (language in (None, "", "auto")) else language.lower().strip()
        effective_prompt = prompt
        if effective_lang is None and prompt and "buddy ai" in prompt.lower():
            effective_prompt = None

        # Short non-blocking lock acquisition (80ms)
        acquired = self._lock.acquire(timeout=0.08)
        if not acquired:
            return ""

        try:
            segments_gen, _ = self._model.transcribe(
                prepared_audio,
                language=effective_lang,
                task="transcribe",
                initial_prompt=effective_prompt,
                beam_size=1,
                temperature=0.0,
                condition_on_previous_text=False,
                without_timestamps=True,
                vad_filter=False,
            )
            raw_segments = list(segments_gen)
            text_parts = [seg.text.strip() for seg in raw_segments if seg.text.strip()]
            full_text = " ".join(text_parts).strip()

            hallucinations = {
                "photo", "photo.", "photo!", "photos", "photos.", "like photo", "like photo.",
                "thank you for watching", "thank you for watching.",
                "please like and subscribe", "like and subscribe",
                "subtitles by the amara.org community", "subtitles by", "transcribed by",
                "buddy ai desktop companion", "hinglish, hindi, gujarati",
            }
            cleaned_norm = full_text.lower().strip(".,!?:;\"' ")
            if cleaned_norm in hallucinations or cleaned_norm.startswith(("subtitles by", "transcribed by", "like and subscribe")):
                return ""
            if len(cleaned_norm) <= 1:
                return ""
            return full_text
        except Exception as e:
            logger.debug("transcribe_interim error: %s", e)
            return ""
        finally:
            self._lock.release()

    def transcribe_interim_async(
        self,
        audio_data: np.ndarray,
        generation_id: int,
        callback: Optional[Callable[[int, str], None]] = None,
        language: Optional[str] = None,
        prompt: Optional[str] = None,
    ) -> None:
        """Submit greedy interim transcription to background thread pool."""
        worker = _InterimTranscribeWorker(
            engine=self,
            audio_data=audio_data,
            generation_id=generation_id,
            language=language,
            prompt=prompt,
            callback=callback,
        )
        self._thread_pool.start(worker)

    def _prepare_audio(self, audio: np.ndarray) -> np.ndarray:
        """Validate, sanitize, and normalize audio array to 16kHz float32 in [-1.0, 1.0]."""
        if audio is None:
            return np.zeros(0, dtype=np.float32)

        if not isinstance(audio, np.ndarray):
            audio = np.asarray(audio, dtype=np.float32)

        if audio.size == 0:
            return np.zeros(0, dtype=np.float32)

        if audio.ndim > 1:
            audio = audio.flatten()

        if audio.dtype != np.float32:
            if np.issubdtype(audio.dtype, np.integer):
                max_val = float(np.iinfo(audio.dtype).max)
                audio = audio.astype(np.float32) / max_val
            else:
                audio = audio.astype(np.float32)

        # Sanitize any NaNs or infinities from audio buffer
        if not np.isfinite(audio).all():
            audio = np.nan_to_num(audio, nan=0.0, posinf=1.0, neginf=-1.0)

        # Normalize volume if audio has non-zero amplitude
        peak = float(np.max(np.abs(audio))) if audio.size > 0 else 0.0
        if peak > 1.0:
            audio = audio / peak

        return audio
