"""Streaming Audio Queue and Pipelined Speech Playback.

Coordinates background sentence synthesis and sequential audio playback:
LLM Streaming -> Sentence Chunker -> TTS Worker -> Audio Queue -> Audio Player
While one chunk is playing, the next chunk is synthesized in parallel. (Phase 8.6, 8.8)
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import threading
from typing import Deque, List, Optional

import numpy as np
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from app.utils.logger import get_logger
from app.voice.audio_player import AudioPlayer
from app.voice.tts_base import BaseTTSEngine, SynthesizedAudio

logger = get_logger(__name__)


@dataclass
class QueuedSentence:
    """A sentence waiting to be synthesized into audio."""
    turn_id: int
    chunk_index: int
    text: str
    is_final_sentence: bool = False
    display_text: Optional[str] = None
    voice_hint: Optional[str] = None
    speed: Optional[float] = None
    speaking_style: Optional[Any] = None


@dataclass
class QueuedAudio:
    """Synthesized audio waveform ready for sequential playback."""
    turn_id: int
    chunk_index: int
    audio: SynthesizedAudio
    is_final_sentence: bool = False
    display_text: Optional[str] = None


@dataclass
class InterruptedTurnSnapshot:
    """Detailed record of speech playback state at the instant of interruption (Phase 4)."""
    turn_id: int
    completed_sentences: List[str]
    interrupted_sentence: Optional[str] = None
    interrupted_progress_ratio: float = 0.0
    unspoken_sentences: List[str] = field(default_factory=list)
    all_sentences: List[str] = field(default_factory=list)

    @property
    def actually_spoken_text(self) -> str:
        """Text actually communicated to the user before the interruption occurred."""
        parts: List[str] = list(self.completed_sentences)
        if self.interrupted_sentence and self.interrupted_progress_ratio > 0.08:
            words = self.interrupted_sentence.split()
            word_count = max(1, int(round(len(words) * self.interrupted_progress_ratio)))
            spoken_words = " ".join(words[:word_count])
            parts.append(f"{spoken_words}...")
        return " ".join(parts).strip()


class _TTSWorkerSignals(QObject):
    """Signals for background TTS synthesis worker."""
    synthesized = Signal(object, object)  # (QueuedSentence, SynthesizedAudio)
    error = Signal(str)


class _TTSChunkSynthesizeWorker(QRunnable):
    """Background worker synthesizing a single sentence chunk via the TTS engine."""

    def __init__(
        self,
        item: QueuedSentence,
        tts_engine: BaseTTSEngine,
    ) -> None:
        super().__init__()
        self.item = item
        self.tts_engine = tts_engine
        self.signals = _TTSWorkerSignals()
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            from app.core.diagnostic_mode import diagnostic_tracker
            diagnostic_tracker.update_tts("synthesizing")
        except Exception:
            pass

        try:
            kwargs = {}
            if self.item.voice_hint:
                kwargs["voice"] = self.item.voice_hint
                kwargs["voice_name"] = self.item.voice_hint
            if self.item.speed is not None:
                kwargs["speed"] = self.item.speed
            audio = self.tts_engine.synthesize(self.item.text, **kwargs)

            # Phase 7: Apply per-persona speaking style DSP (pitch, energy, pause duration)
            if getattr(self.item, "speaking_style", None) and audio and not audio.is_empty:
                try:
                    from app.voice.speaking_style import apply_speaking_style_dsp
                    processed_samples = apply_speaking_style_dsp(
                        samples=audio.samples,
                        sample_rate=audio.sample_rate,
                        style=self.item.speaking_style,
                        is_inter_sentence=not self.item.is_final_sentence,
                    )
                    audio.samples = processed_samples
                    audio.duration_seconds = len(processed_samples) / float(audio.sample_rate)
                except Exception as e:
                    logger.debug("Speaking style DSP application skipped: %s", e)

            try:
                self.signals.synthesized.emit(self.item, audio)
            except (Exception, RuntimeError):
                pass
        except Exception as e:
            logger.error("Error synthesizing sentence chunk #%d (turn %d): %s", self.item.chunk_index, self.item.turn_id, e)
            try:
                from app.core.diagnostic_mode import diagnostic_tracker, ERROR_TTS_FAILED
                diagnostic_tracker.update_tts("failed", error=ERROR_TTS_FAILED)
            except Exception:
                pass
            try:
                self.signals.error.emit(f"Neural TTS synthesis error: {e}")
            except (Exception, RuntimeError):
                pass
            # Create a brief empty or fallback audio object so sequence isn't permanently blocked
            empty = SynthesizedAudio(
                samples=np.zeros(0, dtype=np.float32),
                sample_rate=22050,
                duration_seconds=0.0,
                text=self.item.text,
                voice_name="error",
            )
            try:
                self.signals.synthesized.emit(self.item, empty)
            except (Exception, RuntimeError):
                pass


class StreamingAudioQueue(QObject):
    """Manages parallel TTS synthesis and gapless sequential playback of speech chunks."""

    # Signals for orchestration and observability
    chunk_synthesized = Signal(int, int, str)  # (turn_id, chunk_index, text)
    chunk_playback_started = Signal(int, int, str)  # (turn_id, chunk_index, text)
    chunk_playback_finished = Signal(int, int, str)  # (turn_id, chunk_index, text) (Phase 2)
    all_chunks_played = Signal(int)  # turn_id
    queue_cleared = Signal(int)  # turn_id
    error_occurred = Signal(str)

    def __init__(
        self,
        audio_player: AudioPlayer,
        tts_engine: BaseTTSEngine,
        max_queued_audio: int = 5,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.audio_player = audio_player
        self.tts_engine = tts_engine
        self.max_queued_audio = max_queued_audio

        self.active_turn_id: int = 0
        self._next_chunk_index: int = 0
        self._stream_ended_for_turn: bool = False
        self._is_shutdown: bool = False

        # Queues and locks
        self._lock = threading.Lock()
        self._pending_sentences: Deque[QueuedSentence] = deque()
        self._synthesized_audio_map: dict[int, QueuedAudio] = {}  # chunk_index -> QueuedAudio
        self._next_playback_index: int = 0
        self._is_synthesizing: bool = False
        self._is_playing_chunk: bool = False
        self._current_playing_item: Optional[QueuedAudio] = None
        self._turn_sentences: List[str] = []
        self._completed_sentences: List[str] = []
        self._last_interruption_snapshot: Optional[InterruptedTurnSnapshot] = None

        self._thread_pool = QThreadPool.globalInstance()

        # Connect audio player finished/stopped events
        self.audio_player.playback_finished.connect(self._on_player_chunk_finished)
        self.audio_player.playback_stopped.connect(self._on_player_chunk_stopped)

    @property
    def is_shutdown(self) -> bool:
        return self._is_shutdown

    def start_new_turn(self, turn_id: int) -> None:
        """Initialize queue for a new conversation turn."""
        if self._is_shutdown:
            logger.debug("StreamingAudioQueue start_new_turn rejected: queue is shut down.")
            return

        self.clear()
        with self._lock:
            self.active_turn_id = turn_id
            self._next_chunk_index = 0
            self._next_playback_index = 0
            self._stream_ended_for_turn = False
            self._is_playing_chunk = False
            self._current_playing_item = None
            self._turn_sentences = []
            self._completed_sentences = []
        logger.debug("StreamingAudioQueue initialized for turn #%d", turn_id)

    def enqueue_sentence(
        self,
        sentence: str,
        turn_id: int,
        is_final: bool = False,
        display_text: Optional[str] = None,
        voice_hint: Optional[str] = None,
        speed: Optional[float] = None,
        speaking_style: Optional[Any] = None,
    ) -> None:
        """Enqueue a sentence to be synthesized and played for the given turn."""
        cleaned = sentence.strip()
        if not cleaned:
            return

        with self._lock:
            if turn_id != self.active_turn_id:
                logger.debug("Discarding sentence for obsolete turn #%d (active: %d)", turn_id, self.active_turn_id)
                return

            chunk_idx = self._next_chunk_index
            self._next_chunk_index += 1
            item = QueuedSentence(
                turn_id=turn_id,
                chunk_index=chunk_idx,
                text=cleaned,
                is_final_sentence=is_final,
                display_text=display_text or cleaned,
                voice_hint=voice_hint,
                speed=speed,
                speaking_style=speaking_style,
            )
            self._turn_sentences.append(cleaned)
            self._pending_sentences.append(item)

        # Trigger synthesis loop if idle
        self._pump_synthesis()

    def mark_stream_finished(self, turn_id: int) -> None:
        """Mark that the LLM has finished streaming text for this turn."""
        with self._lock:
            if turn_id == self.active_turn_id:
                self._stream_ended_for_turn = True
                # If there are no pending sentences and nothing playing, check completion
                if not self._pending_sentences and not self._synthesized_audio_map and not self._is_playing_chunk and not self._is_synthesizing:
                    QThreadPool.globalInstance()
                    self.all_chunks_played.emit(turn_id)

    def stop_and_capture_interruption(self) -> InterruptedTurnSnapshot:
        """Immediately stop playback and capture precise speech delivery state (Phase 4).
        
        Returns:
            InterruptedTurnSnapshot indicating what completed, what was partially spoken,
            and what was left unspoken.
        """
        with self._lock:
            turn = self.active_turn_id
            completed = list(self._completed_sentences)
            curr = self._current_playing_item
            interrupted_sentence = curr.audio.text if curr and curr.audio else None

            # Get progress from AudioPlayer
            progress_ratio = self.audio_player.get_playback_progress()[2]

            # Calculate unspoken sentences based on sequentially scheduled turn sentences
            consumed_count = len(completed) + (1 if interrupted_sentence else 0)
            unspoken = list(self._turn_sentences[consumed_count:])

            snapshot = InterruptedTurnSnapshot(
                turn_id=turn,
                completed_sentences=completed,
                interrupted_sentence=interrupted_sentence,
                interrupted_progress_ratio=progress_ratio,
                unspoken_sentences=unspoken,
                all_sentences=list(self._turn_sentences),
            )
            self._last_interruption_snapshot = snapshot

        self.clear()
        logger.info(
            "[INTERRUPTION_2.0] Turn #%d interrupted snapshot: %d completed, partial='%s' (%.1f%%), %d unspoken. Actually spoken: '%s'",
            snapshot.turn_id,
            len(snapshot.completed_sentences),
            (snapshot.interrupted_sentence[:30] + "...") if snapshot.interrupted_sentence else "None",
            snapshot.interrupted_progress_ratio * 100.0,
            len(snapshot.unspoken_sentences),
            snapshot.actually_spoken_text[:60],
        )
        return snapshot

    def clear(self) -> None:
        """Clear all pending sentences and audio chunks immediately (Phase 8.8)."""
        with self._lock:
            turn = self.active_turn_id
            self.active_turn_id += 1  # Invalidate any in-flight workers for this turn
            self._pending_sentences.clear()
            self._synthesized_audio_map.clear()
            self._is_playing_chunk = False
            self._current_playing_item = None
            self._stream_ended_for_turn = True

        self.audio_player.stop()
        try:
            self.queue_cleared.emit(turn)
        except Exception:
            pass
        logger.debug("StreamingAudioQueue cleared (invalidated turn #%d)", turn)

    def emergency_stop(self) -> None:
        """Immediately abort all synthesis, clear queues, and halt audio output."""
        logger.info("StreamingAudioQueue emergency stop requested.")
        with self._lock:
            self.active_turn_id += 1
            self._pending_sentences.clear()
            self._synthesized_audio_map.clear()
            self._is_playing_chunk = False
            self._current_playing_item = None
            self._stream_ended_for_turn = True
        self.audio_player.emergency_stop()

    def shutdown(self) -> None:
        """Permanently shut down queue, aborting active synthesis and audio playback."""
        logger.info("StreamingAudioQueue shutting down...")
        self._is_shutdown = True
        self.emergency_stop()
        self.audio_player.shutdown()

    def get_queue_length(self) -> int:
        """Return total count of queued sentences and ready audio chunks."""
        with self._lock:
            length = len(self._pending_sentences) + len(self._synthesized_audio_map)
        try:
            from app.core.performance_monitor import get_performance_monitor
            get_performance_monitor().update_audio_queue_length(length)
        except Exception:
            pass
        return length

    @property
    def is_empty(self) -> bool:
        """Return True if queue has no pending sentences, synthesized audio, or playing chunk."""
        with self._lock:
            return not self._pending_sentences and not self._synthesized_audio_map and not self._is_playing_chunk

    # ─── Pipelined Synthesis Loop ─────────────────────────────────────

    def _pump_synthesis(self) -> None:
        """Pick the next queued sentence and dispatch to background TTS worker."""
        if self._is_shutdown:
            return

        with self._lock:
            if self._is_shutdown or self._is_synthesizing:
                return

            # Check bounded audio queue (backpressure check)
            if len(self._synthesized_audio_map) >= self.max_queued_audio:
                return

            if not self._pending_sentences:
                return

            item = self._pending_sentences.popleft()
            if item.turn_id != self.active_turn_id:
                return

            self._is_synthesizing = True

        worker = _TTSChunkSynthesizeWorker(
            item=item,
            tts_engine=self.tts_engine,
        )
        worker.signals.synthesized.connect(self._on_sentence_synthesized)
        worker.signals.error.connect(self.error_occurred.emit)
        self._thread_pool.start(worker)

    def _on_sentence_synthesized(self, item: QueuedSentence, audio: SynthesizedAudio) -> None:
        """Callback from worker when a sentence has been synthesized."""
        if self._is_shutdown:
            return

        with self._lock:
            self._is_synthesizing = False

            # Discard if turn superseded or shut down
            if self._is_shutdown or item.turn_id != self.active_turn_id:
                logger.debug("Discarding synthesized chunk #%d for obsolete turn #%d", item.chunk_index, item.turn_id)
                return

            queued_audio = QueuedAudio(
                turn_id=item.turn_id,
                chunk_index=item.chunk_index,
                audio=audio,
                is_final_sentence=item.is_final_sentence,
                display_text=item.display_text,
            )
            self._synthesized_audio_map[item.chunk_index] = queued_audio

        self.chunk_synthesized.emit(item.turn_id, item.chunk_index, item.text)

        # Trigger synthesis of subsequent sentence (pipelining)
        self._pump_synthesis()

        # Trigger playback of next available sequential audio chunk
        self._pump_playback()

    # ─── Sequential Audio Playback Loop ───────────────────────────────

    def _pump_playback(self) -> None:
        """Play the next in-order audio chunk if player is currently idle."""
        if self._is_shutdown:
            return

        with self._lock:
            if self._is_shutdown or self._is_playing_chunk:
                return

            expected_idx = self._next_playback_index
            if expected_idx not in self._synthesized_audio_map:
                # Next sequential chunk not synthesized yet; wait for it
                return

            next_audio = self._synthesized_audio_map.pop(expected_idx)
            if next_audio.turn_id != self.active_turn_id:
                return

            self._next_playback_index += 1
            self._is_playing_chunk = True
            self._current_playing_item = next_audio

        # Play through AudioPlayer
        text = next_audio.audio.text
        self.chunk_playback_started.emit(next_audio.turn_id, next_audio.chunk_index, text)
        display_str = next_audio.display_text or text
        from app.core.signals import signals
        signals.ai_speech_subtitle.emit(display_str)
        logger.info(
            "Playing speech chunk #%d for turn #%d: '%s' (%.2fs)",
            next_audio.chunk_index,
            next_audio.turn_id,
            text[:35] + ("..." if len(text) > 35 else ""),
            next_audio.audio.duration_seconds,
        )

        if not next_audio.audio.is_empty:
            self.audio_player.play(next_audio.audio.samples, next_audio.audio.sample_rate)
        else:
            # Empty audio (e.g. error fallback), advance immediately
            self._on_player_chunk_finished()

    @Slot()
    def _on_player_chunk_finished(self) -> None:
        """Callback when AudioPlayer finishes playing current chunk."""
        if self._is_shutdown:
            return

        with self._lock:
            self._is_playing_chunk = False
            last_item = self._current_playing_item
            self._current_playing_item = None

            turn_id = self.active_turn_id
            expected_idx = self._next_playback_index
            has_more_ready = expected_idx in self._synthesized_audio_map
            has_more_pending = bool(self._pending_sentences)
            is_done = self._stream_ended_for_turn and not has_more_ready and not has_more_pending and not self._is_synthesizing

        if last_item:
            with self._lock:
                if last_item.audio and last_item.audio.text:
                    self._completed_sentences.append(last_item.audio.text)
            self.chunk_playback_finished.emit(last_item.turn_id, last_item.chunk_index, last_item.audio.text)

        if has_more_ready:
            self._pump_playback()
        elif has_more_pending or self._is_synthesizing:
            # More chunks being synthesized; continue pump
            self._pump_synthesis()
        elif is_done:
            logger.info("All speech chunks played for conversation turn #%d", turn_id)
            self.all_chunks_played.emit(turn_id)

    @Slot()
    def _on_player_chunk_stopped(self) -> None:
        """Callback when AudioPlayer is stopped prematurely."""
        with self._lock:
            self._is_playing_chunk = False
            self._current_playing_item = None
