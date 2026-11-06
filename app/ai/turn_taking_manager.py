"""Natural Conversational Turn-Taking and Dialogue Flow Manager (Phase 6).

Implements Phase 6 upgrades for natural conversational turn-taking:
6.1 Pause handling & connector detection: Identifies mid-sentence pauses and
    linguistic connectors ("and...", "because...", "aur...", "ane...") across English,
    Gujarati, and Hindi so adaptive VAD does not cut off user speech prematurely.
6.2 Short acknowledgement handling: Detects standalone acknowledgements ("Hmm", "Okay",
    "Yes", "No", "Right", "Interesting", "બરાબર", "ઠીક છે", "अच्छा", "हाँ") and prevents
    the assistant from launching into unwanted long monologues.
6.3 Contextual follow-up coreference resolution: Directs the AI to resolve pronouns
    ("it", "he", "she", "that") to preceding entities without asking the user to repeat.
6.4 Repetition avoidance & robotic canned question suppression: Prevents repeating
    previous answers, detects duplicate speech segments, and eliminates artificial
    customer-service questions ("Would you like to know more?").
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional, Set, Tuple

from app.utils.logger import get_logger

logger = get_logger(__name__)


def _normalize_token(text: str) -> str:
    """Normalize text by stripping unicode accents/punctuation and collapsing spaces."""
    if not text:
        return ""
    chars = []
    for ch in text.lower():
        cat = unicodedata.category(ch)
        if cat.startswith("P") or cat.startswith("S"):
            chars.append(" ")
        else:
            chars.append(ch)
    return " ".join("".join(chars).split())


class TurnTakingManager:
    """Orchestrates natural turn-taking dynamics, connector detection, and conversational continuity."""

    # ─── 6.1 Linguistic Connectors & Hesitation Words ────────────────────────
    # Words at the end of an interim speech segment indicating the user is pausing to think
    CONNECTORS_EN: Set[str] = {
        "and", "because", "but", "so", "or", "also", "then", "like", "if",
        "um", "uh", "well", "that", "to", "since", "although", "though", "meaning",
        "actually", "basically", "which",
    }

    CONNECTORS_HI: Set[str] = {
        "और", "क्योंकि", "लेकिन", "मगर", "तो", "या", "मतलब", "जैसे", "कि",
        "परन्तु", "क्यूंकि", "अर्थात", "यानी",
    }
    CONNECTORS_HI_ROMAN: Set[str] = {
        "aur", "kyunki", "kyonki", "lekin", "magar", "to", "ya", "matlab",
        "jaise", "ki", "parantu", "yaani",
    }

    CONNECTORS_GU: Set[str] = {
        "અને", "કારણ કે", "પણ", "તો", "અથવા", "એટલે", "જેમ કે", "કે", "પરંતુ",
        "મતલબ", "એટલે કે", "નહીંતર",
    }
    CONNECTORS_GU_ROMAN: Set[str] = {
        "ane", "karan ke", "pan", "to", "athva", "etle", "jem ke", "ke",
        "parantu", "matlab", "etle ke", "nahitar",
    }

    ALL_CONNECTORS: Set[str] = (
        CONNECTORS_EN
        | CONNECTORS_HI
        | CONNECTORS_HI_ROMAN
        | CONNECTORS_GU
        | CONNECTORS_GU_ROMAN
    )

    # ─── 6.2 Short Acknowledgements ──────────────────────────────────────────
    # Standalone conversational acknowledgements that should elicit concise check-ins
    ACKNOWLEDGEMENTS_EN: Set[str] = {
        "hmm", "hm", "okay", "ok", "yes", "yeah", "yep", "yup", "no", "nope",
        "right", "alright", "interesting", "sure", "got it", "cool", "understood",
        "i see", "uh-huh", "uh huh", "mhm", "fine", "great", "nice", "true",
        "exactly", "perfect",
    }

    ACKNOWLEDGEMENTS_HI: Set[str] = {
        "हाँ", "ना", "नहीं", "अच्छा", "ठीक है", "हूँ", "सही बात है", "समझ गया",
        "जी", "जी हाँ", "अरे वाह", "बढ़िया", "शुक्रिया", "बिलकुल", "सही है",
        "धन्यवाद", "अच्छा जी", "हाँ जी",
    }
    ACKNOWLEDGEMENTS_HI_ROMAN: Set[str] = {
        "haan", "ha", "na", "nahi", "theek hai", "thik hai", "achha", "accha",
        "sahi", "samajh gaya", "ji haan", "ji", "badhiya", "shukriya", "bilkul",
        "sahi hai", "dhanyavaad", "accha ji", "haan ji",
    }

    ACKNOWLEDGEMENTS_GU: Set[str] = {
        "હા", "ના", "બરાબર", "ઠીક છે", "હંમ", "સારું", "સમજ્યો", "ખરું",
        "જી હા", "વાહ", "સરસ", "આભાર", "ચોક્કસ", "સાચી વાત", "હા જી",
    }
    ACKNOWLEDGEMENTS_GU_ROMAN: Set[str] = {
        "haa", "ha", "na", "barabar", "thik che", "saru", "samjyo", "kharu",
        "ji haa", "saras", "aabhar", "chokkas", "sachi vaat", "haa ji",
    }

    ALL_ACKNOWLEDGEMENTS: Set[str] = (
        ACKNOWLEDGEMENTS_EN
        | ACKNOWLEDGEMENTS_HI
        | ACKNOWLEDGEMENTS_HI_ROMAN
        | ACKNOWLEDGEMENTS_GU
        | ACKNOWLEDGEMENTS_GU_ROMAN
    )

    # ─── 6.4 Robotic Canned Questions to Strip ───────────────────────────────
    CANNED_QUESTIONS_PATTERNS = [
        # English patterns
        re.compile(r"(?i)\s*(is there anything else (i can help (you )?with|you('d| would) like to know|you need help with)[^?.]*\??)$"),
        re.compile(r"(?i)\s*(would you like to know more( about [^?.]+)?\??)$"),
        re.compile(r"(?i)\s*(do you (need|want) (any )?more (help|information|details)[^?.]*\??)$"),
        re.compile(r"(?i)\s*(let me know if you (have any questions|need anything else)[^?.]*\.?)$"),
        re.compile(r"(?i)\s*(feel free to ask if you (have questions|need more details)[^?.]*\.?)$"),
        # Hindi patterns
        re.compile(r"\s*(क्या आप कुछ और जानना चाहते हैं\??|क्या मैं कुछ और मदद करूँ\??|और कुछ जानना है\??|क्या आपको और जानकारी चाहिए\??)$"),
        re.compile(r"(?i)\s*(kya aap kuch aur janna chahte hain\??|aur kuch janna hai\??)$"),
        # Gujarati patterns
        re.compile(r"\s*(શું તમે વધુ જાણવા માંગો છો\??|શું હું તમને બીજું કંઈ મદદ કરી શકું\??|બીજું કંઈ જાણવું છે\??|વધુ માહિતી જોઈએ છે\??)$"),
        re.compile(r"(?i)\s*(shu tame vadhu janva mango cho\??|bijun kai janvu che\??)$"),
    ]

    # ─────────────────────────────────────────────────────────────────────────
    # Public Methods
    # ─────────────────────────────────────────────────────────────────────────

    @classmethod
    def has_trailing_connector(cls, text: str) -> bool:
        """Check if interim transcribed speech ends with a connector/hesitation word.
        
        When True, user is likely pausing mid-sentence to think, so VAD silence threshold
        should be adaptively extended (6.1).
        """
        cleaned = (text or "").strip()
        if not cleaned:
            return False

        # Check multi-word connectors at the tail first (e.g., "karan ke", "jem ke", "etle ke")
        norm = _normalize_token(cleaned)
        words = norm.split()
        if not words:
            return False

        # Two-word tail check
        if len(words) >= 2:
            tail_two = f"{words[-2]} {words[-1]}"
            if tail_two in cls.ALL_CONNECTORS:
                return True

        # Single-word tail check
        tail_one = words[-1]
        if tail_one in cls.ALL_CONNECTORS:
            return True

        # Check raw text for non-ASCII punctuation/script connectors
        raw_words = cleaned.split()
        if raw_words and raw_words[-1] in cls.ALL_CONNECTORS:
            return True

        return False

    @classmethod
    def is_short_acknowledgement(cls, text: str) -> Tuple[bool, str]:
        """Determine if user input is a standalone short acknowledgement (6.2).
        
        Returns:
            Tuple of (is_acknowledgement, matched_term).
        """
        cleaned = (text or "").strip()
        if not cleaned:
            return False, ""

        norm = _normalize_token(cleaned)
        words = norm.split()
        # Acknowledgements are brief (1 to 3 words)
        if not words or len(words) > 3:
            return False, ""

        # Check exact normalized match
        if norm in cls.ALL_ACKNOWLEDGEMENTS:
            return True, norm

        # Check raw string exact match (for devanagari / gujarati)
        raw_clean = re.sub(r"[^\w\s\u0900-\u097F\u0A80-\u0AFF]", "", cleaned).strip()
        if raw_clean in cls.ALL_ACKNOWLEDGEMENTS:
            return True, raw_clean

        return False, ""

    @classmethod
    def build_acknowledgement_instruction(
        cls,
        user_text: str,
        response_language: str = "en",
    ) -> str:
        """Construct context instruction for short acknowledgement turn (6.2).
        
        Directs the LLM to give an attentive, brief conversational check-in instead
        of an unsolicited lecture or monologue.
        """
        lang = str(response_language).lower().strip()
        if lang == "gu":
            lang_prompt = "ગુજરાતીમાં (Gujarati)"
            example_prompt = "'હા, બોલો! આગળ શું કરવું છે?' અથવા 'ઠીક છે, હું સાંભળું છું.'"
        elif lang == "hi":
            lang_prompt = "हिन्दी में (Hindi)"
            example_prompt = "'जी, बताइए! आगे क्या करना है?' अथवा 'हाँ, मैं सुन रहा हूँ।'"
        else:
            lang_prompt = "English"
            example_prompt = "'I'm listening! What's on your mind?' or 'Got it, how would you like to proceed?'"

        return (
            f"[CONVERSATIONAL TURN-TAKING - SHORT ACKNOWLEDGEMENT]\n"
            f"User input: \"{user_text}\"\n"
            f"Constraint: The user gave a short conversational acknowledgement/backchannel. "
            f"DO NOT launch into a long lecture, monologue, or multi-paragraph explanation. "
            f"Respond attentively and warmly in EXACTLY 1 brief spoken sentence in {lang_prompt} "
            f"(e.g., {example_prompt})."
        )

    @classmethod
    def build_turn_taking_directives(cls, response_language: str = "en") -> str:
        """Build system prompt instructions for coreference resolution and anti-repetition (6.3 & 6.4)."""
        lang = str(response_language).lower().strip()
        lang_name = "English"
        if lang == "gu":
            lang_name = "Gujarati"
        elif lang == "hi":
            lang_name = "Hindi"

        return (
            f"[NATURAL CONVERSATIONAL TURN-TAKING & DIALOGUE FLOW]:\n"
            f"1. Coreference Resolution (Follow-ups):\n"
            f"   - When the user asks a follow-up question using pronouns like 'it', 'he', 'she', 'they', 'that', 'this', 'there' "
            f"     (or Hindi: 'उसने', 'उसका', 'वह', 'यह'; or Gujarati: 'તેણે', 'તેનું', 'તે'):\n"
            f"   - Immediately resolve the pronoun to the specific entity, person, movie, book, or concept discussed in the preceding turns.\n"
            f"   - Example: If the previous turn was about 'Interstellar', and the user asks 'Who directed it?', 'it' refers to 'Interstellar'. "
            f"     Answer directly that Christopher Nolan directed it. NEVER ask the user to repeat the movie or entity name.\n"
            f"2. Repetition Avoidance:\n"
            f"   - NEVER repeat your previous answer or re-state what you already communicated in previous turns.\n"
            f"   - Move the conversation forward naturally.\n"
            f"3. Natural Conversational Closings (No Robotic Scripts):\n"
            f"   - NEVER use canned customer-service questions at the end of responses such as:\n"
            f"     * 'Is there anything else I can help you with today?'\n"
            f"     * 'Would you like to know more about this?'\n"
            f"     * 'How else can I assist you?'\n"
            f"     * 'क्या आप कुछ और जानना चाहते हैं?'\n"
            f"     * 'શું તમે વધુ જાણવા માંગો છો?'\n"
            f"   - Conclude naturally and cleanly as a human friend would. When you have answered the question, stop speaking.\n"
            f"4. Language Consistency:\n"
            f"   - Formulate your entire response in {lang_name}."
        )

    @classmethod
    def strip_canned_closing_questions(cls, text: str) -> str:
        """Strip robotic canned closing questions from assistant responses (6.4)."""
        if not text:
            return ""

        cleaned = text.strip()
        for pat in cls.CANNED_QUESTIONS_PATTERNS:
            cleaned = pat.sub("", cleaned).strip()

        # If stripping leaves trailing commas or hyphens, clean them up
        cleaned = re.sub(r"[,;:\-]\s*$", ".", cleaned)
        return cleaned.strip()

    @classmethod
    def is_duplicate_response(
        cls,
        candidate_text: str,
        previous_text: str,
        threshold: float = 0.85,
    ) -> bool:
        """Check if candidate response is an identical or near-duplicate repeat of previous response (6.4)."""
        cand_norm = _normalize_token(candidate_text)
        prev_norm = _normalize_token(previous_text)

        if not cand_norm or not prev_norm:
            return False

        if cand_norm == prev_norm:
            return True

        cand_words = set(cand_norm.split())
        prev_words = set(prev_norm.split())

        if not cand_words or not prev_words:
            return False

        intersection = cand_words.intersection(prev_words)
        union = cand_words.union(prev_words)

        jaccard = len(intersection) / float(len(union))
        return jaccard >= threshold
