"""Voice Command Parser and Intent Dispatcher (Hands-Free Desktop Actions).

Parses recognized user speech for system commands and dispatches corresponding desktop actions
(e.g., opening settings, hiding/showing pet, muting/unmuting audio, changing models,
clearing conversations, entering sleep mode, or quitting the application)
without routing them as conversational LLM prompts.
"""

from __future__ import annotations

import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import QObject, Signal, Slot

from app.core.signals import signals
from app.utils.logger import get_logger

logger = get_logger(__name__)


class VoiceCommandParser:
    """Detects and categorizes voice commands from transcribed user speech."""

    # Conversational prefixes to strip before intent matching
    PREFIX_STRIP = re.compile(
        r"^(?:hey\s+|ok\s+|okay\s+)?(?:buddy|bond|friend|assistant|computer)?\s*(?:please\s+|can\s+you\s+|could\s+you\s+|would\s+you\s+)?",
        re.IGNORECASE,
    )

    # Polite trailing suffixes to strip
    SUFFIX_STRIP = re.compile(
        r"\s*(?:please|now|buddy|bond|friend|assistant|thanks|thank\s+you)$",
        re.IGNORECASE,
    )

    # Intent regex patterns across English, Hindi, and Gujarati
    COMMAND_PATTERNS: Dict[str, List[str]] = {
        "open_settings": [
            r"^open\s+(?:the\s+)?settings(?:\s+window|\s+dialog|\s+page)?$",
            r"^show\s+(?:the\s+)?settings(?:\s+window|\s+dialog|\s+page)?$",
            r"^launch\s+settings$",
            r"^settings(?:\s+window|\s+dialog)?$",
            r"^સેટિંગ્સ?\s+ખોલો$",
            r"^સેટિંગ્સ?$",
            r"^सेटिंग्स?\s+खोलो$",
            r"^सेटिंग्स?$",
        ],
        "hide_pet": [
            r"^hide\s+(?:the\s+)?(?:pet|buddy|companion|character|yourself|avatar)$",
            r"^hide$",
            r"^go\s+away$",
            r"^dismiss$",
            r"^સંતાઈ\s+જા$",
            r"^સંતઈ\s+જા$",
            r"^ગાયબ\s+થઈ\s+જા$",
            r"^छिप\s+जाओ$",
            r"^गायब\s+हो\s+जाओ$",
        ],
        "show_pet": [
            r"^show\s+(?:the\s+)?(?:pet|buddy|companion|character|yourself|avatar)$",
            r"^come\s+back$",
            r"^appear$",
            r"^unhide\s+(?:pet|buddy)?$",
            r"^સામે\s+આવ$",
            r"^પાછો\s+આવ$",
            r"^બહાર\s+આવ$",
            r"^सामने\s+आओ$",
            r"^वापस\s+आओ$",
        ],
        "toggle_pet": [
            r"^toggle\s+(?:the\s+)?(?:pet|buddy|companion)$",
        ],
        "open_chat": [
            r"^open\s+(?:the\s+)?chat(?:\s+window)?$",
            r"^show\s+(?:the\s+)?chat(?:\s+window)?$",
            r"^start\s+chat$",
            r"^ચેટ\s+ખોલો$",
            r"^ચેટ\s+બતાવો$",
            r"^चैट\s+खोलो$",
            r"^चैट\s+दिखाओ$",
        ],
        "close_chat": [
            r"^close\s+(?:the\s+)?chat(?:\s+window)?$",
            r"^hide\s+(?:the\s+)?chat(?:\s+window)?$",
            r"^ચેટ\s+બંધ\s+કર$",
            r"^चैट\s+बंद\s+करो$",
        ],
        "open_voice_window": [
            r"^open\s+(?:the\s+)?voice\s+(?:window|portal|screen)?$",
            r"^show\s+(?:the\s+)?voice\s+(?:window|portal|screen)?$",
            r"^voice\s+window$",
            r"^વૉઇસ\s+વિન્ડો\s+ખોલો$",
            r"^वॉयस\s+विंडो\s+खोलो$",
        ],
        "close_voice_window": [
            r"^close\s+(?:the\s+)?voice\s+(?:window|portal|screen)?$",
            r"^hide\s+(?:the\s+)?voice\s+(?:window|portal|screen)?$",
            r"^વૉઇસ\s+વિન્ડો\s+બંધ\s+કરો$",
            r"^वॉयस\s+विंडो\s+बंद\s+करो$",
        ],
        "minimize_chat": [
            r"^minimize(?:\s+(?:the\s+)?(?:chat|window))?$",
            r"^નાનું\s+કર$",
            r"^મિનિમાઇઝ\s+કર$",
            r"^छोटा\s+करो$",
            r"^मिनीमाइज\s+करो$",
        ],
        "maximize_chat": [
            r"^maximize(?:\s+(?:the\s+)?(?:chat|window))?$",
            r"^મોટું\s+કર$",
            r"^મેક્સિમાઇઝ\s+કર$",
            r"^बड़ा\s+करो$",
            r"^मैक्सिमाइज\s+करो$",
        ],
        "mute": [
            r"^mute(?:\s+voice|\s+audio|\s+sound|\s+yourself)?$",
            r"^be\s+quiet$",
            r"^silence$",
            r"^shh+$",
            r"^quiet$",
            r"^શાંત\s+રહે$",
            r"^ચૂપ\s+રહે$",
            r"^મ્યુટ\s+કર$",
            r"^शांत\s+रहो$",
            r"^चुप\s+रहो$",
            r"^म्यूट\s+करो$",
        ],
        "unmute": [
            r"^unmute(?:\s+voice|\s+audio|\s+sound)?$",
            r"^speak\s+again$",
            r"^અનમ્યુટ\s+કર$",
            r"^બોલ$",
            r"^अनम्यूट\s+करो$",
            r"^बोलो$",
        ],
        "sleep": [
            r"^go\s+to\s+sleep$",
            r"^sleep(?:\s+mode)?$",
            r"^take\s+a\s+nap$",
            r"^quiet\s+mode$",
            r"^stop\s+listening$",
            r"^સુઈ\s+જા$",
            r"^ઊંઘી\s+જા$",
            r"^સો\s+જાઓ$",
            r"^આરામ\s+કરો$",
            r"^સાંભળવાનું\s+બંધ\s+કર$",
            r"^सो\s+जाओ$",
            r"^आराम\s+करो$",
            r"^सुनना\s+बंद\s+करो$",
        ],
        "wake": [
            r"^(?:hey\s+)?(?:buddy|bond|friend|assistant)$",
            r"^wake(?:\s+up)?(?:\s+(?:buddy|bond|friend|assistant))?$",
            r"^(?:buddy|bond|friend|assistant)\s+wake(?:\s+up)?$",
            r"^(?:i\s*m|i\s+am)\s+talking\s+to\s+you(?:\s+(?:buddy|bond|friend|assistant))?$",
            r"^(?:(?:buddy|bond|friend|assistant)\s+)?are\s+you\s+there(?:\s+(?:buddy|bond|friend|assistant))?$",
            r"^rise\s+and\s+shine$",
            r"^are\s+you\s+awake$",
            r"^get\s+up$",
            r"^hello\s+again$",
            r"^start\s+listening$",
            r"^resume\s+listening$",
            r"^activate(?:\s+(?:buddy|bond|friend|assistant))?$",
            r"^જાગી\s+જા$",
            r"^ઊઠ$",
            r"^જાાગ\s+જાઓ$",
            r"^ઉઠો$",
            r"^સાંભળવાનું\s+શરૂ\s+કર$",
            r"^जाग\s+जाओ$",
            r"^उठो$",
            r"^सुनना\s+शुरू\s+करो$",
        ],
        "stop": [
            r"^(?:emergency\s+)?stop(?:\s+talking|\s+speaking|\s+audio)?$",
            r"^shut\s+up$",
            r"^stop\s+talking$",
            r"^stop\s+speaking$",
            r"^enough$",
            r"^halt$",
            r"^cancel\s+(?:speech|response|generation)$",
            r"^ઊભો\s+રહે$",
            r"^બોલવાનું\s+બંધ\s+કર$",
            r"^બસ\s+કર$",
            r"^રુક\s+જાઓ$",
            r"^બોલના\s+બંધ\s+કરો$",
            r"^બસ\s+કરો$",
            r"^रुक\s+जाओ$",
            r"^बोलना\s+बंद\s+करो$",
            r"^बस\s+करो$",
        ],
        "clear_chat": [
            r"^clear\s+(?:the\s+)?(?:chat|conversation|messages|history)$",
            r"^delete\s+(?:the\s+)?(?:chat|conversation)$",
            r"^(?:start\s+)?new\s+chat$",
            r"^ચેટ\s+સાફ\s+કર$",
            r"^નવી\s+ચેટ$",
            r"^ચેટ\s+સાફ\s+કરો$",
            r"^નઈ\s+ચેટ$",
            r"^चैट\s+साफ\s+करो$",
            r"^नई\s+चैट$",
        ],
        "change_model": [
            r"^(?:change|switch|next)\s+(?:the\s+)?(?:ai\s+)?model$",
            r"^model\s+change$",
            r"^સ્વિચ\s+મોડેલ$",
            r"^મોડલ\s+બદલો$",
            r"^मॉडल\s+बदलो$",
        ],
        "exit": [
            r"^(?:exit|quit|close|shutdown)(?:\s+application|\s+app|\s+program)?$",
            r"^bye\s+bye(?:\s+buddy)?$",
            r"^goodbye$",
            r"^એપ્લિકેશન\s+બંધ\s+કર$",
            r"^આવજો$",
            r"^બંધ\s+કરો$",
            r"^અલવિદા$",
            r"^बंद\s+करो$",
            r"^अलविदा$",
        ],
        "open_movies": [
            r"^open\s+(?:the\s+)?(?:movie\s+hub|movies?|cinema|films?)(?:\s+(?:tab|page|window))?$",
            r"^show\s+(?:the\s+)?(?:movie\s+hub|movies?|cinema|films?)(?:\s+(?:tab|page|window))?$",
            r"^launch\s+(?:movie\s+hub|movies?)$",
            r"^movie\s+hub$",
            r"^movies?$",
            r"^ફિલ્મો?\s+ખોલો$",
            r"^સિનેમા\s+ખોલો$",
            r"^मूवीज़?\s+खोलो$",
            r"^फ़िल्में?\s+खोलो$",
            r"^सिनेमा\s+खोलो$",
        ],
    }

    @classmethod
    def parse(cls, raw_text: str) -> Optional[Tuple[str, str]]:
        """Parse raw speech transcription into an intent identifier and cleaned text.

        Returns:
            Tuple of (intent_name, cleaned_command_text) if matched, or None.
        """
        if not raw_text or not raw_text.strip():
            return None

        # Clean punctuation and normalize whitespace
        text = raw_text.strip().lower()
        # Remove terminal punctuation .!?
        text = re.sub(r"[.!?।]+$", "", text).strip()
        # Replace internal punctuation (commas, colons, hyphens, quotes) with spaces
        text = re.sub(r"[,;:\'\"\-_]+", " ", text)
        text = re.sub(r"\s+", " ", text).strip()

        # Movie Discovery Voice Queries (Phase 11.3 Voice-Powered Discovery)
        # e.g., "Find me a Telugu action movie", "Recommend a Hindi comedy movie", "Search movie Inception"
        movie_match = re.search(
            r"^(?:please\s+)?(?:find(?:\s+me)?|recommend(?:\s+me)?|search(?:\s+for)?|show(?:\s+me)?|suggest(?:\s+me)?)\s+(?:a\s+|an\s+|some\s+)?(?P<movie_term>.+?\b(?:movie|movies|film|films|series|show|shows)\b.*)$",
            text,
            re.IGNORECASE,
        )
        if not movie_match:
            movie_match = re.search(
                r"^(?:search\s+(?:for\s+)?(?:movie|movies|film|series|show)\s+|movie\s+search\s+)(?P<movie_term>.+)$",
                text,
                re.IGNORECASE,
            )
        if movie_match:
            term = movie_match.group("movie_term").strip()
            return "movie_discovery", term

        # Reject long queries (informational questions meant for LLM chat)
        words = text.split()
        if len(words) > 7:
            return None

        # Question markers indicating an informational prompt rather than an imperative command
        question_starters = (
            "what", "why", "how", "who", "when", "where",
            "can you tell", "explain", "define", "give me",
        )
        if any(text.startswith(qs) for qs in question_starters) and not any(
            k in text for k in ("settings", "chat", "mute", "hide", "sleep")
        ):
            return None

        # Strip common conversational prefixes and suffixes
        cleaned = cls.PREFIX_STRIP.sub("", text)
        cleaned = cls.SUFFIX_STRIP.sub("", cleaned).strip()

        for intent, patterns in cls.COMMAND_PATTERNS.items():
            for pat in patterns:
                if (cleaned and re.match(pat, cleaned, re.IGNORECASE)) or re.match(pat, text, re.IGNORECASE):
                    return intent, cleaned if cleaned else text

        return None

    # Compound wake prefix pattern: captures wake invocation followed by optional prompt
    WAKE_PREFIX_PATTERN = re.compile(
        r"^(?P<wake>"
        r"(?:(?:hey|hi|hello|ok|okay)\s+)?(?:buddy|bond)\b|"
        r"(?:hey|hi|hello|ok|okay)\s+(?:buddy|bond|friend|assistant)\b|"
        r"wake\s*up(?:\s*(?:buddy|bond|friend|assistant))?|"
        r"(?:buddy|bond|friend|assistant)\s*wake\s*up|"
        r"rise\s*and\s*shine|are\s*you\s*awake|"
        r"(?:buddy|bond|friend|assistant)\s*are\s*you\s*there|"
        r"are\s*you\s*there(?:\s*(?:buddy|bond|friend|assistant))?|"
        r"(?:i\s*m|i\s*am)\s*talking\s*to\s*you(?:\s*(?:buddy|bond|friend|assistant))?|"
        r"come\s*back(?:\s*(?:buddy|bond|friend|assistant))?|"
        r"(?:start|resume)\s*listening|"
        r"activate\s+(?:buddy|bond|friend|assistant)|^activate$"
        r")\s*[,:;-]?\s*(?P<prompt>.*)$",
        re.IGNORECASE,
    )

    @classmethod
    def extract_wake_and_prompt(cls, raw_text: str) -> Optional[Tuple[str, str]]:
        """Extract wake invocation and remaining prompt from an utterance (Phase 5).

        Examples:
            'Hey Buddy, explain Python.' -> ('Hey Buddy', 'explain Python.')
            'Hey Buddy' -> ('Hey Buddy', '')
            'Hello' -> None

        Returns:
            (wake_phrase, remaining_prompt) if utterance starts with a wake command, else None.
        """
        if not raw_text or not raw_text.strip():
            return None
        text = raw_text.strip()
        m = cls.WAKE_PREFIX_PATTERN.match(text)
        if not m:
            return None
        wake = m.group("wake").strip()
        prompt = m.group("prompt").strip()
        prompt = re.sub(r"^[,\s:;-]+", "", prompt).strip()
        if prompt.lower() in ("buddy", "bond", "friend", "assistant", "wake up", "wake", "up"):
            wake = f"{wake} {prompt}"
            prompt = ""
        return wake, prompt

    @classmethod
    def register_custom_patterns(cls, intent: str, patterns: List[str]) -> None:
        """Register custom user-configured regex or string patterns for an intent (Phase 5)."""
        if intent in cls.COMMAND_PATTERNS:
            for pat in patterns:
                clean_pat = str(pat).strip()
                if not clean_pat:
                    continue
                # If plain phrase without regex meta-characters, wrap in anchors
                if not any(c in clean_pat for c in r"^$[]().*+?"):
                    regex_pat = r"^" + re.escape(clean_pat.lower()) + r"$"
                else:
                    regex_pat = clean_pat
                if regex_pat not in cls.COMMAND_PATTERNS[intent]:
                    cls.COMMAND_PATTERNS[intent].append(regex_pat)
                    logger.debug("Registered custom pattern for '%s': %s", intent, regex_pat)

    @classmethod
    def load_configuration(cls, config_manager: Optional[Any] = None) -> None:
        """Load configurable wake and sleep commands from config manager (Phase 5)."""
        if not config_manager or not hasattr(config_manager, "get"):
            return
        wake_words = config_manager.get("voice.custom_wake_words", [])
        if wake_words and isinstance(wake_words, list):
            cls.register_custom_patterns("wake", wake_words)
        sleep_words = config_manager.get("voice.custom_sleep_words", [])
        if sleep_words and isinstance(sleep_words, list):
            cls.register_custom_patterns("sleep", sleep_words)


class VoiceCommandDispatcher(QObject):
    """Executes desktop and companion actions corresponding to recognized voice intents."""

    command_executed = Signal(str, str)  # (intent_name, raw_text)

    def __init__(
        self,
        voice_service: Optional[object] = None,
        ai_service: Optional[object] = None,
        conv_repo: Optional[object] = None,
        config_manager: Optional[object] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.voice_service = voice_service
        self.ai_service = ai_service
        self.conv_repo = conv_repo
        self.config_manager = config_manager
        self.feedback_enabled: bool = True
        self._last_executed_intent: Optional[str] = None
        self._last_executed_time: float = 0.0

        from app.core.buddy_state_manager import get_buddy_state_manager
        self.buddy_state_manager = get_buddy_state_manager()

        # Load configurable wake and sleep commands
        VoiceCommandParser.load_configuration(self.config_manager)

        # Custom handler registry
        self._handlers: Dict[str, Callable[[], Optional[str]]] = {
            "open_settings": self._handle_open_settings,
            "hide_pet": self._handle_hide_pet,
            "show_pet": self._handle_show_pet,
            "toggle_pet": self._handle_toggle_pet,
            "open_chat": self._handle_open_chat,
            "close_chat": self._handle_close_chat,
            "open_voice_window": self._handle_open_voice_window,
            "close_voice_window": self._handle_close_voice_window,
            "minimize_chat": self._handle_minimize_chat,
            "maximize_chat": self._handle_maximize_chat,
            "mute": self._handle_mute,
            "unmute": self._handle_unmute,
            "sleep": self._handle_sleep,
            "wake": self._handle_wake,
            "stop": self._handle_stop,
            "clear_chat": self._handle_clear_chat,
            "change_model": self._handle_change_model,
            "exit": self._handle_exit,
            "open_movies": self._handle_open_movies,
            "movie_discovery": self._handle_movie_discovery,
        }

    def register_handler(self, intent: str, handler: Callable[[], Optional[str]]) -> None:
        """Register or override a custom handler for a voice command intent."""
        self._handlers[intent] = handler

    def dispatch(self, user_text: str, language: Optional[str] = "en") -> bool:
        """Analyze text and execute corresponding voice command if recognized.

        Args:
            user_text: Transcribed speech utterance.
            language: Language code ('en', 'hi', 'gu', etc.)

        Returns:
            True if recognized and handled as a command, False otherwise.
        """
        # If Buddy's voice is currently playing, discard as acoustic self-echo (Phase 5)
        if self.voice_service and hasattr(self.voice_service, "audio_player"):
            if getattr(self.voice_service.audio_player, "is_playing", False) is True:
                logger.debug("Voice command ignored: Assistant speech playback currently active (self-echo).")
                return True

        parsed = VoiceCommandParser.parse(user_text)
        if not parsed:
            # Check for compound wake invocation (e.g. "Hey Buddy, explain Python.")
            compound = VoiceCommandParser.extract_wake_and_prompt(user_text)
            if compound:
                wake_phrase, remaining_prompt = compound
                # If Buddy is sleeping and there is NO conversational prompt, wake Buddy up
                if self.buddy_state_manager and self.buddy_state_manager.is_sleeping:
                    if not remaining_prompt.strip():
                        return self.dispatch("wake", language=language)
                # If there IS a conversational prompt, return False so the caller
                # can process the remaining prompt through the AI pipeline!
                return False

            # If Buddy is sleeping, ordinary non-command speech is ignored without triggering AI
            if self.buddy_state_manager and self.buddy_state_manager.is_sleeping:
                return True
            return False

        intent, cleaned_cmd = parsed
        self._current_command_arg = cleaned_cmd
        handler = self._handlers.get(intent)
        if not handler:
            return False

        # If Buddy is SLEEPING, only allow explicit WAKE command (or companion recall)!
        if self.buddy_state_manager and self.buddy_state_manager.is_sleeping:
            if intent not in ("wake", "show_pet"):
                logger.debug("Voice command '%s' ignored: Buddy is sleeping.", intent)
                return True  # Consumed so it does not trigger AI chat
            if intent == "show_pet":
                self._handle_wake()

        # Suppress duplicate invocations & debounce repeated sleep/wake events (Phase 5)
        now = time.time()
        debounce_window = 1.0 if intent in ("wake", "sleep", "stop") else 1.5
        if intent == self._last_executed_intent and (now - self._last_executed_time) < debounce_window:
            logger.debug("Debouncing duplicate dispatch for recently executed intent '%s' (%.2fs)", intent, now - self._last_executed_time)
            return True

        self._last_executed_intent = intent
        self._last_executed_time = now

        logger.info("Executing voice command intent '%s' for utterance '%s'", intent, user_text)
        try:
            ack_msg = handler()
            self.command_executed.emit(intent, user_text)

            # Spoken acknowledgment feedback
            if self.feedback_enabled and ack_msg and self.voice_service and hasattr(self.voice_service, "speak"):
                # Avoid speaking if we just muted or are sleeping
                can_speak = True
                if self.buddy_state_manager:
                    can_speak = self.buddy_state_manager.can_speak or intent == "wake"
                if can_speak:
                    is_muted = getattr(self.voice_service, "is_muted", False)
                    if (is_muted is not True) or intent == "unmute":
                        self.voice_service.speak(ack_msg)

            return True
        except Exception as e:
            logger.error("Error executing voice command '%s': %s", intent, e, exc_info=True)
            return False

    # ─── Action Handlers ────────────────────────────────────────────────

    def _handle_open_settings(self) -> str:
        signals.open_settings_requested.emit()
        return "Opening settings."

    def _handle_hide_pet(self) -> str:
        signals.hide_pet_requested.emit()
        return "Hiding now."

    def _handle_show_pet(self) -> str:
        signals.show_pet_requested.emit()
        return "I am right here!"

    def _handle_toggle_pet(self) -> str:
        signals.toggle_pet_requested.emit()
        return "Done."

    def _handle_open_chat(self) -> str:
        signals.open_chat_requested.emit()
        return "Opening chat."

    def _handle_close_chat(self) -> str:
        signals.close_chat_requested.emit()
        return "Closing chat."

    def _handle_open_voice_window(self) -> str:
        signals.open_voice_window_requested.emit()
        return "Opening voice window."

    def _handle_close_voice_window(self) -> str:
        signals.close_voice_window_requested.emit()
        return "Closing voice window."

    def _handle_minimize_chat(self) -> str:
        signals.minimize_chat_requested.emit()
        return "Minimizing."

    def _handle_maximize_chat(self) -> str:
        signals.maximize_chat_requested.emit()
        return "Maximizing."

    def _handle_mute(self) -> str:
        if self.voice_service and hasattr(self.voice_service, "set_muted"):
            self.voice_service.set_muted(True)
        if self.buddy_state_manager:
            self.buddy_state_manager.set_muted(True, reason="voice_command_mute")
        signals.voice_state_changed.emit("muted")
        return "Muted."

    def _handle_unmute(self) -> str:
        if self.voice_service and hasattr(self.voice_service, "set_muted"):
            self.voice_service.set_muted(False)
        if self.buddy_state_manager:
            self.buddy_state_manager.set_muted(False, reason="voice_command_unmute")
        signals.voice_state_changed.emit("listening")
        return "Voice unmuted."

    def _handle_sleep(self) -> str:
        signals.ai_cancel_requested.emit()
        if self.voice_service and hasattr(self.voice_service, "audio_player") and self.voice_service.audio_player:
            self.voice_service.audio_player.stop()
        if self.voice_service and hasattr(self.voice_service, "stop_speaking"):
            self.voice_service.stop_speaking()
        if self.buddy_state_manager:
            self.buddy_state_manager.enter_sleep(reason="voice_command_sleep")
        signals.sleep_requested.emit()
        return "Going to sleep mode. Goodnight!"

    def _handle_wake(self) -> str:
        if self.buddy_state_manager:
            self.buddy_state_manager.wake_up(reason="voice_command_wake")
        signals.wake_requested.emit()
        return "I'm here! What do you need?"

    def _handle_stop(self) -> str:
        signals.emergency_stop_requested.emit()
        signals.ai_cancel_requested.emit()
        if self.voice_service and hasattr(self.voice_service, "stop_speaking"):
            self.voice_service.stop_speaking()
        # Immediately transition to sleep mode quietly
        if self.buddy_state_manager:
            self.buddy_state_manager.enter_sleep(reason="voice_command_stop")
        signals.sleep_requested.emit()
        return ""

    def _handle_clear_chat(self) -> str:
        if self.conv_repo and self.ai_service:
            active_id = getattr(self.ai_service, "active_conversation_id", None)
            if active_id and hasattr(self.conv_repo, "clear_conversation_messages"):
                self.conv_repo.clear_conversation_messages(active_id)
        if self.ai_service and hasattr(self.ai_service, "clear_context"):
            self.ai_service.clear_context()

        from app.api.websocket import ws_manager
        ws_manager.broadcast_sync("chat_cleared", {})
        return "Conversation cleared."

    def _handle_change_model(self) -> str:
        if self.ai_service and hasattr(self.ai_service, "model_manager"):
            mm = self.ai_service.model_manager
            installed = mm.get_installed_models() if hasattr(mm, "get_installed_models") else []
            if len(installed) > 1:
                cur = mm.active_model
                try:
                    cur_idx = installed.index(cur)
                    next_model = installed[(cur_idx + 1) % len(installed)]
                except ValueError:
                    next_model = installed[0]
                mm.set_model(next_model)
                if self.config_manager and hasattr(self.config_manager, "set"):
                    self.config_manager.set("ai.model", next_model)
                from app.api.websocket import ws_manager
                ws_manager.broadcast_sync("model_changed", {"model": next_model})
                return f"Switched model to {next_model}."
        return "Model selector opened."

    def _handle_exit(self) -> str:
        from PySide6.QtCore import QTimer
        QTimer.singleShot(1500, signals.shutdown_requested.emit)
        return "Goodbye!"

    def _handle_open_movies(self) -> str:
        """Switch desktop UI to Movie Hub tab (Phase 11.3)."""
        try:
            from app.api.websocket import ws_manager
            ws_manager.broadcast_sync("open_movie_hub", {})
        except Exception as e:
            logger.debug("Failed to broadcast open_movie_hub: %s", e)
        if hasattr(signals, "open_movie_hub_requested"):
            signals.open_movie_hub_requested.emit()
        return "Opening Movie Hub."

    def _handle_movie_discovery(self) -> str:
        """Broadcast voice search query and switch to Movie Hub (Phase 11.3)."""
        search_query = getattr(self, "_current_command_arg", "").strip()
        try:
            from app.api.websocket import ws_manager
            ws_manager.broadcast_sync("movie_voice_search", {"query": search_query, "auto_open": True})
        except Exception as e:
            logger.debug("Failed to broadcast movie_voice_search: %s", e)
        if hasattr(signals, "movie_voice_search_requested"):
            signals.movie_voice_search_requested.emit(search_query)
        return f"Searching Movie Hub for {search_query}." if search_query else "Opening Movie Hub search."
