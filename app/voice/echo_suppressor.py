"""Acoustic Feedback and Echo Suppressor (Bug 5 Fix).

Prevents conversational feedback loops in continuous hands-free voice dialogue
by monitoring spoken assistant utterances, calculating semantic and phonetic token
overlap, fuzzy SequenceMatcher similarity, and managing room reverberation decay.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import difflib
import re
import time
import unicodedata
from typing import List, Optional, Set, Tuple

from app.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class SpokenUtterance:
    """Record of a spoken assistant sentence or prompt with normalized tokens."""

    raw_text: str
    norm_text: str
    words: Set[str]
    word_list: List[str]
    timestamp: float = field(default_factory=time.time)


def normalize_text(text: str) -> str:
    """Strip punctuation, convert to lowercase, and normalize whitespace.
    
    Preserves combining marks (Mn, Mc) to correctly handle Indic scripts
    like Gujarati, Hindi, as well as accented Latin characters.
    """
    if not text:
        return ""
    chars = []
    for ch in text.lower():
        cat = unicodedata.category(ch)
        if cat.startswith("P") or cat.startswith("S"):
            chars.append(" ")
        else:
            chars.append(ch)
    cleaned = "".join(chars)
    return " ".join(cleaned.split())


class AcousticEchoSuppressor:
    """Detects and suppresses acoustic speaker-to-microphone feedback loops."""

    def __init__(
        self,
        history_retention_sec: float = 25.0,
        fuzzy_similarity_threshold: float = 0.65,
        word_overlap_threshold: float = 0.50,
        cooldown_decay_sec: float = 0.35,
    ) -> None:
        self.history_retention_sec = history_retention_sec
        self.fuzzy_similarity_threshold = fuzzy_similarity_threshold
        self.word_overlap_threshold = word_overlap_threshold
        self.cooldown_decay_sec = cooldown_decay_sec

        self._assistant_history: List[SpokenUtterance] = []
        self._user_history: List[Tuple[str, float]] = []  # (norm_text, timestamp)
        self._last_playback_end_time: float = 0.0
        self._is_playing: bool = False

    def mark_playback_started(self) -> None:
        """Mark that audio player has begun output playback."""
        self._is_playing = True

    def mark_playback_ended(self) -> None:
        """Mark that audio player has finished output playback and start decay timer."""
        was_playing = self._is_playing
        self._is_playing = False
        if was_playing:
            self._last_playback_end_time = time.time()

    @property
    def is_in_decay_window(self) -> bool:
        """Return True if within reverberation and audio driver drain cooldown window."""
        if self._is_playing:
            return True
        return (time.time() - self._last_playback_end_time) < self.cooldown_decay_sec

    def record_assistant_speech(self, text: str) -> None:
        """Register spoken assistant text into rolling history buffer."""
        cleaned = text.strip()
        if not cleaned:
            return

        norm = normalize_text(cleaned)
        if not norm:
            return

        words = set(norm.split())
        word_list = norm.split()
        now = time.time()

        # Prune stale utterances
        self._prune_history(now)

        # Avoid redundant consecutive duplicates
        if self._assistant_history:
            last = self._assistant_history[-1]
            if last.norm_text == norm and (now - last.timestamp) < 5.0:
                return

        self._assistant_history.append(
            SpokenUtterance(
                raw_text=cleaned,
                norm_text=norm,
                words=words,
                word_list=word_list,
                timestamp=now,
            )
        )
        logger.debug("EchoSuppressor registered assistant speech: '%s' (%d words)", norm, len(words))

    def record_user_speech(self, text: str) -> None:
        """Record accepted user speech for repetition and deduplication filtering."""
        norm = normalize_text(text)
        if norm:
            self._user_history.append((norm, time.time()))
            if len(self._user_history) > 10:
                self._user_history = self._user_history[-10:]

    def is_recent_duplicate_user(self, text: str, window_sec: float = 4.0) -> bool:
        """Check if user transcript is an immediate accidental duplicate of previous turn."""
        norm = normalize_text(text)
        if not norm or not self._user_history:
            return False

        now = time.time()
        for prev_text, ts in reversed(self._user_history):
            if (now - ts) > window_sec:
                break
            if norm == prev_text:
                return True
            # Fuzzy match for duplicate query with minor STT noise
            if len(norm) >= 8 and len(prev_text) >= 8:
                sim = difflib.SequenceMatcher(None, norm, prev_text).ratio()
                if sim >= 0.85:
                    return True
        return False

    def is_echo(self, transcript: str) -> Tuple[bool, str, float]:
        """Evaluate if user transcript is acoustic echo feedback from assistant speech.

        Returns:
            Tuple[is_echo_detected: bool, matched_reason: str, confidence_score: float]
        """
        norm_user = normalize_text(transcript)
        if not norm_user:
            return False, "empty", 0.0

        user_words = norm_user.split()
        user_words_set = set(user_words)
        user_word_count = len(user_words)
        now = time.time()

        self._prune_history(now)

        if not self._assistant_history:
            return False, "no_history", 0.0

        # Check against recent assistant utterances (newest first)
        for utt in reversed(self._assistant_history):
            age = now - utt.timestamp
            if age > self.history_retention_sec:
                continue

            entry_norm = utt.norm_text
            entry_words = utt.words

            # 1. Exact match (any length)
            if norm_user == entry_norm:
                logger.warning("🛡️ Acoustic Echo detected (exact match): '%s'", norm_user)
                return True, "exact_match", 1.0

            # 2. Immediate post-playback fragment / word leak detection (< 3.0s after playback)
            if (now - self._last_playback_end_time) < 3.0 or age < 4.0:
                if norm_user in entry_norm or norm_user in entry_words or (user_word_count == 1 and user_words[0] in entry_words):
                    logger.warning(
                        "🛡️ Acoustic Echo detected (immediate post-playback fragment): '%s' in '%s'",
                        norm_user,
                        entry_norm,
                    )
                    return True, "post_playback_fragment", 1.0

            # 3. Full Substring Match (user speech is captured fragment of assistant speech)
            if norm_user in entry_norm:
                if user_word_count >= 2 or len(norm_user) >= 6:
                    logger.warning(
                        "🛡️ Acoustic Echo detected (substring match): '%s' in '%s'",
                        norm_user,
                        entry_norm,
                    )
                    return True, "substring_match", 1.0

            # 2. Token Word-Level Overlap (Intersection & Containment)
            if user_word_count >= 2:
                common_words = user_words_set.intersection(entry_words)
                containment = len(common_words) / float(user_word_count)

                # If majority of transcribed words were in the assistant sentence
                if containment >= self.word_overlap_threshold:
                    # Stricter if utterance occurred right after playback
                    time_factor = 1.2 if (now - self._last_playback_end_time) < 3.0 else 1.0
                    score = min(1.0, containment * time_factor)
                    if score >= self.word_overlap_threshold:
                        logger.warning(
                            "🛡️ Acoustic Echo detected (word overlap %.0f%%): '%s' overlapping '%s'",
                            containment * 100,
                            norm_user,
                            entry_norm,
                        )
                        return True, "word_overlap", score

            # 3. Fuzzy Sequence Similarity (handles Whisper phonetic typos/variations)
            if user_word_count >= 2:
                sim = difflib.SequenceMatcher(None, norm_user, entry_norm).ratio()
                if sim >= self.fuzzy_similarity_threshold:
                    logger.warning(
                        "🛡️ Acoustic Echo detected (fuzzy ratio %.2f): '%s' vs '%s'",
                        sim,
                        norm_user,
                        entry_norm,
                    )
                    return True, "fuzzy_similarity", sim

            # 4. N-Gram Shingle Match (Consecutive 3-word phrase matching)
            if user_word_count >= 3:
                for i in range(len(user_words) - 2):
                    shingle = " ".join(user_words[i : i + 3])
                    if shingle in entry_norm:
                        # If a 3-word phrase from assistant speech was caught and user speech is short
                        if user_word_count <= 8:
                            logger.warning(
                                "🛡️ Acoustic Echo detected (shingle '%s'): '%s'",
                                shingle,
                                norm_user,
                            )
                            return True, "phrase_shingle", 0.85

        return False, "clean", 0.0

    def _prune_history(self, now: float) -> None:
        """Discard utterances older than retention window."""
        cutoff = now - self.history_retention_sec
        self._assistant_history = [
            u for u in self._assistant_history if u.timestamp >= cutoff
        ]

    def clear(self) -> None:
        """Reset all utterance history."""
        self._assistant_history.clear()
        self._user_history.clear()
        self._last_playback_end_time = 0.0
        self._is_playing = False
