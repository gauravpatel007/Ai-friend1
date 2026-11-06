"""Deterministic Greeting Evaluator and Fast Path Handler.

Provides instantaneous (<20ms), varied, and personality-aligned greetings
for unambiguous, standalone greeting messages (e.g. 'hi', 'hello', 'hey', 'good morning').
Ensures that complex questions, multi-part queries, or technical requests
always pass through to the local neural model without being intercepted.
"""

from __future__ import annotations

import random
import re
from typing import Any, Dict, List, Optional, Tuple

from app.utils.logger import get_logger

logger = get_logger(__name__)

# Patterns that indicate an unambiguous standalone greeting.
# Matches: "hello", "hi", "hey!", "good morning", "greetings buddy", "yo", etc.
_STANDALONE_GREETING_REGEX = re.compile(
    r"^(?P<salutation>"
    r"hi+|hello+|hey+|heyy+|heya|howdy|sup|yo|hiya|greetings|"
    r"good\s+(?:morning|afternoon|evening|day)"
    r")"
    r"(?:[\s,]+(?:there|buddy|bond|friend|pal|mate|ai|companion|assistant))?"
    r"[\s!.,\?😊👋✨]*$",
    re.IGNORECASE,
)

# Common words that indicate the message is actually a question or task even if starting with greeting:
# e.g. "Hello, can you explain Python?", "Hi what is the date?", "Hey tell me a joke"
_INTENT_DISQUALIFIERS = re.compile(
    r"\b(?:what|who|where|when|why|how|explain|can\s+you|could\s+you|please|tell|show|write|code|summarize|calculate|find|help\s+me\s+with|is\s+there)\b",
    re.IGNORECASE,
)


class GreetingEvaluator:
    """Evaluates standalone greetings and provides fast-path responses."""

    _last_response_by_personality: Dict[str, str] = {}

    @classmethod
    def is_standalone_greeting(cls, text: str) -> bool:
        """Check if input text is strictly a standalone greeting without a follow-up query."""
        cleaned = text.strip()
        if not cleaned or len(cleaned) > 40:
            return False

        # If it contains any substantive question or task words, do NOT treat as standalone
        if _INTENT_DISQUALIFIERS.search(cleaned):
            return False

        return bool(_STANDALONE_GREETING_REGEX.match(cleaned))

    @classmethod
    def extract_and_answer(
        cls,
        user_prompt: str,
        companion_name: str = "Buddy",
        personality: str = "friendly",
        is_voice: bool = False,
    ) -> Optional[Tuple[str, Dict[str, Any]]]:
        """Evaluate user prompt for standalone greeting and generate appropriate response.

        Returns:
            Tuple of (response_text, metadata_dict) or None if prompt is not a standalone greeting.
        """
        cleaned = user_prompt.strip()
        match = _STANDALONE_GREETING_REGEX.match(cleaned)
        if not match:
            return None

        # Double check: no question or multi-part intent
        if _INTENT_DISQUALIFIERS.search(cleaned):
            return None

        salutation = match.group("salutation").lower().strip()
        pers = (personality or "friendly").lower()
        name = companion_name or "Buddy"

        # Determine time-of-day specific greeting if salutation was good morning/afternoon/evening
        is_morning = "morning" in salutation
        is_afternoon = "afternoon" in salutation
        is_evening = "evening" in salutation

        candidates: List[str] = []

        if is_morning:
            if is_voice:
                candidates = [
                    f"Good morning! How can I assist you today?",
                    f"Good morning! What are we working on today?",
                    f"Good morning! Ready when you are.",
                ]
            else:
                candidates = [
                    f"Good morning! What are we working on today?",
                    f"Good morning! {name} here, ready to help whenever you need.",
                    f"Good morning! Hope you're having a productive start to your day. How can I help?",
                    f"Morning! What can I help you with today?",
                ]
        elif is_afternoon:
            if is_voice:
                candidates = [
                    f"Good afternoon! How can I help you today?",
                    f"Good afternoon! What's on your agenda?",
                ]
            else:
                candidates = [
                    f"Good afternoon! How can I help you today?",
                    f"Good afternoon! How is your day going so far?",
                    f"Good afternoon! Ready to help with whatever you're working on.",
                ]
        elif is_evening:
            if is_voice:
                candidates = [
                    f"Good evening! How can I assist you tonight?",
                    f"Good evening! What can I help you with?",
                ]
            else:
                candidates = [
                    f"Good evening! How can I assist you tonight?",
                    f"Good evening! Working late or winding down? Let me know how I can help.",
                    f"Good evening! Always here if you need anything.",
                ]
        else:
            # General greeting (hello, hi, hey, etc.) based on personality
            if pers in ("concise", "professional"):
                if is_voice:
                    candidates = [
                        f"Hello. How can I assist you today?",
                        f"Hi there. What can I help you with?",
                        f"Hello. Ready for your instructions.",
                        f"Good day. How may I help you?",
                    ]
                else:
                    candidates = [
                        f"Hello. How can I assist you today?",
                        f"Hi there. What can I help you with?",
                        f"Good day. How may I be of assistance?",
                        f"Hello! What are we working on right now?",
                        f"Greetings. Standing by to assist you.",
                    ]
            elif pers in ("playful", "funny"):
                if is_voice:
                    candidates = [
                        f"Hey there! What kind of adventure are we on today?",
                        f"Yo! {name} is on duty. What's up?",
                        f"Beep boop! Ready for action. How can I help?",
                    ]
                else:
                    candidates = [
                        f"Hey! {name} has entered the chat! 🚀 What are we tackling today?",
                        f"Yo! Ready when you are. What's on your mind?",
                        f"Hiya! I was just organizing digital electrons until you showed up. What's up?",
                        f"Hey boss! Ready to make things happen. How can I help?",
                    ]
            elif pers == "calm":
                candidates = [
                    f"Hello. Hope you're having a calm and steady day. How can I assist?",
                    f"Greetings. Take your time, what can I help you with?",
                    f"Hello. I'm right here with you. What's on your mind?",
                ]
            elif pers == "energetic":
                candidates = [
                    f"Hey there! Ready to crush some goals! What's up?",
                    f"Hello! Awesome to see you! How can I help today?",
                    f"Hey! Let's get things done! What are we working on?",
                ]
            else:  # friendly (default)
                if is_voice:
                    candidates = [
                        f"Hey there! How can I help you today?",
                        f"Hello! Great to hear from you. What's on your mind?",
                        f"Hi! Ready to help whenever you are.",
                    ]
                else:
                    candidates = [
                        f"Hey there! How's your day going? What can I help you with?",
                        f"Hello! Great to see you. How can I help you today?",
                        f"Hi! {name} here, ready to assist. What's on your mind?",
                        f"Hey! Always happy to chat. What are we working on?",
                    ]

        # Prevent exact consecutive duplicate response
        last_resp = cls._last_response_by_personality.get(pers, "")
        available = [c for c in candidates if c != last_resp] or candidates
        chosen = random.choice(available)
        cls._last_response_by_personality[pers] = chosen

        metadata = {
            "salutation": salutation,
            "personality": pers,
            "companion_name": name,
            "is_voice": is_voice,
            "deterministic_greeting": True,
        }
        return chosen, metadata
