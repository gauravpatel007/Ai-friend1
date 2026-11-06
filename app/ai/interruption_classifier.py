"""Context-Aware Interruption Classifier (Phase 4).

Categorizes real-time user interruptions during assistant speech into:
  - Type A: CORRECTION (user corrects misconception / clarifies intent)
  - Type B: FOLLOW_UP (user asks for elaboration / why / what next on active topic)
  - Type C: TOPIC_CHANGE (user discards topic and starts new subject)
  - Type D: ACKNOWLEDGEMENT (brief conversational backchanneling e.g. "hmm", "okay", "yeah")
  - GENERAL: Default conversational statement or query

Supports English, Gujarati (script + Romanized), and Hindi (script + Romanized).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import List, Optional, Set, Tuple
import unicodedata

from app.utils.logger import get_logger

logger = get_logger(__name__)


class InterruptionType(str, Enum):
    """Categorization of user interruptions during AI speech."""

    CORRECTION = "correction"           # Type A: Correction or clarification
    FOLLOW_UP = "follow_up"             # Type B: Follow-up question on current topic
    TOPIC_CHANGE = "topic_change"       # Type C: Discard topic & switch subject
    ACKNOWLEDGEMENT = "acknowledgement" # Type D: Brief backchannel (okay, hmm, right)
    GENERAL = "general"                 # Standard input / unclassified


@dataclass
class InterruptionClassificationResult:
    """Detailed result of interruption analysis."""

    interruption_type: InterruptionType
    confidence: float
    matched_phrase: Optional[str]
    reason: str
    suggested_action: str  # "continue_playback", "apply_correction", "elaborate_topic", "switch_topic", "standard_process"


def _normalize(text: str) -> str:
    """Normalize text preserving Indic scripts while stripping punctuation and excess whitespace."""
    if not text:
        return ""
    chars: List[str] = []
    for ch in text.lower():
        cat = unicodedata.category(ch)
        if cat.startswith("P") or cat.startswith("S"):
            chars.append(" ")
        else:
            chars.append(ch)
    cleaned = "".join(chars)
    return " ".join(cleaned.split())


class InterruptionClassifier:
    """Rule-based and semantic classifier for voice interruptions across EN, GU, HI."""

    # ─────────────────────────────────────────────────────────────────────────
    # TYPE D: Brief Acknowledgements (Backchannels)
    # ─────────────────────────────────────────────────────────────────────────
    _ACKNOWLEDGEMENT_WORDS: Set[str] = {
        # English
        "hmm", "hm", "mmm", "mm", "uh-huh", "uh huh", "mhm", "aha",
        "okay", "ok", "k", "yeah", "yea", "yep", "yes", "right",
        "sure", "i see", "got it", "understood", "all right", "alright",
        # Hindi & Romanized Hindi
        "हाँ", "हूँ", "हम्म", "अच्छा", "ठीक है", "सही है", "हाँ जी", "जी", "बिल्कुल",
        "haan", "ha", "achha", "accha", "acha", "theek hai", "thik hai", "sahi hai", "haan ji", "ji", "bilkul",
        # Gujarati & Romanized Gujarati
        "હા", "હા હા", "બરાબર", "સારું", "સમજાયું", "હા જી", "સાચું",
        "barabar", "saru", "samjayu", "ha ji", "sachu",
    }

    # ─────────────────────────────────────────────────────────────────────────
    # TYPE A: Corrections
    # ─────────────────────────────────────────────────────────────────────────
    _CORRECTION_PATTERNS: List[re.Pattern] = [
        # English
        re.compile(r"\b(wait|hold on|stop)\b.*\b(not what|that'?s not|incorrect|wrong|mistaken|misunderstood)\b"),
        re.compile(r"\b(that'?s not what i (meant|asked|said))\b"),
        re.compile(r"\b(not what i (meant|asked|said))\b"),
        re.compile(r"\b(no (i meant|that'?s not|it'?s not|not that|i said))\b"),
        re.compile(r"\b(let me explain again|i meant something else|you misunderstood me)\b"),
        re.compile(r"\b(that'?s incorrect|that is incorrect|that'?s wrong|that is wrong)\b"),
        re.compile(r"\b(no no|nope|wrong answer|incorrect)\b"),
        re.compile(r"\bwait (a second|a minute|one second)\b"),
        # Hindi & Romanized
        re.compile(r"(मेरा मतलब (यह|ये) नहीं|मेरा वो मतलब नहीं|मैंने (यह|ये) नहीं पूछा)"),
        re.compile(r"(mera matlab (yeh|ye) nahi|maine (yeh|ye) nahi pucha|galat bol rahe ho|yeh galat hai)"),
        re.compile(r"(रुकिए|रुको|अरे नहीं|नहीं नहीं|गलत है|यह सही नहीं है)"),
        re.compile(r"(rukiye|ruko|are nahi|nahi nahi|galat hai|yeh sahi nahi hai)"),
        re.compile(r"(मैं फिर से समझाता|फिर से सुनो|मेरी बात सुनो)"),
        re.compile(r"(main fir se samjhata|fir se suno|meri baat suno)"),
        # Gujarati & Romanized
        re.compile(r"(મારો મતલબ એ નહોતો|હું કંઈક બીજું પૂછી રહ્યો|તમે ખોટું સમજી)"),
        re.compile(r"(maro matlab e nahoto|hu kaik biju puchi rahyo|tame khotu samji)"),
        re.compile(r"(ઊભા રહો|ઊભા રો|ખોટું છે|ના ના|અરે ના)"),
        re.compile(r"(ubha raho|ubha ro|khotu che|na na|are na)"),
        re.compile(r"(હું ફરીથી સમજાવું|મારી વાત સાંભળો)"),
        re.compile(r"(hu farithi samjavu|mari vaat sambhalo)"),
    ]

    # ─────────────────────────────────────────────────────────────────────────
    # TYPE B: Follow-ups (Asking for elaboration / why / what next)
    # ─────────────────────────────────────────────────────────────────────────
    _FOLLOW_UP_PATTERNS: List[re.Pattern] = [
        # English
        re.compile(r"^(why|why so|why is that|how come|and then|what then)\??$"),
        re.compile(r"^(why|how come|what about)\b.*"),
        re.compile(r"\b(why does|why is|why would|why should|why did|why do|how does|what do you mean)\b"),
        re.compile(r"\b(what happened next|tell me more|tell me more about that|can you elaborate)\b"),
        re.compile(r"\b(really|is that true|are you sure|is that so)\??$"),
        re.compile(r"\b(how does that work|what do you mean by that|can you explain further)\b"),
        re.compile(r"\b(go on|continue|and what else)\b"),
        # Hindi & Romanized
        re.compile(r"^(क्यों|क्यों भाई|ऐसा क्यों|फिर क्या|आगे क्या|और क्या)\b.*"),
        re.compile(r"^(kyu|kyun|aisa kyu|fir kya|aage kya|aur kya)\b.*"),
        re.compile(r"(फिर क्या हुआ|और बताओ|इसके बारे में और बताओ|विस्तार से बताओ)"),
        re.compile(r"(fir kya hua|aur batao|iske baare mein aur batao|vistar se batao)"),
        re.compile(r"(सच में|क्या सच में|ऐसा कैसे|ऐसा क्यों होता|ये कैसे होता|इसका क्या मतलब)"),
        re.compile(r"(sach mein|kya sach mein|aisa kaise|aisa kyu hota|ye kaise hota|iska kya matlab)"),
        # Gujarati & Romanized
        re.compile(r"^(કેમ|કેમ ભાઈ|આવું કેમ|પછી શું|આગળ શું)\b.*"),
        re.compile(r"^(kem|kem bhai|aavu kem|pachi shu|aagad shu)\b.*"),
        re.compile(r"(પછી શું થયું|વધુ જણાવો|તેના વિશે વધુ કહો|વિગતવાર જણાવો)"),
        re.compile(r"(pachi shu thayu|vadhu janavo|tena vishe vadhu kaho|vigatvar janavo)"),
        re.compile(r"(સાચે|શું સાચે|કેવી રીતે|આવું કેમ થાય|તેનો શું મતલબ|આ કેવી રીતે)"),
        re.compile(r"(sache|shu sache|kevi rite|aavu kem thay|teno shu matlab|aa kevi rite)"),
    ]

    # ─────────────────────────────────────────────────────────────────────────
    # TYPE C: Topic Changes
    # ─────────────────────────────────────────────────────────────────────────
    _TOPIC_CHANGE_PATTERNS: List[re.Pattern] = [
        # English
        re.compile(r"\b(anyway|anyways|moving on|change the topic|different topic)\b"),
        re.compile(r"\b(forget (that|about that)|leave (that|it)|never mind( that)?)\b"),
        re.compile(r"\b(let'?s talk about something else|i have another question|another question)\b"),
        re.compile(r"\b(different question|switch topic|drop that)\b"),
        # Hindi & Romanized
        re.compile(r"(जाने दो|छोड़ो इसे|छोड़ो ये|इसे छोड़ो|दूसरा सवाल|कोई और बात)"),
        re.compile(r"(jane do|chhodo ise|chhodo ye|ise chhodo|doosra sawal|koi aur baat)"),
        re.compile(r"(विषय बदलो|टॉपिक बदलो|खैर|कुछ और बात करते हैं)"),
        re.compile(r"(topic badlo|khair|kuch aur baat karte hain)"),
        # Gujarati & Romanized
        re.compile(r"(કંઈ વાંધો નહીં|એ ભૂલી જાવ|ભૂલી જાવ એ|બીજો પ્રશ્ન|બીજી વાત)"),
        re.compile(r"(kayi vandho nahi|e bhuli jav|bhuli jav e|bijo prashna|biji vaat)"),
        re.compile(r"(વિષય બદલો|ટોપિક બદલો|છોડો એને|કંઈક બીજું બોલો)"),
        re.compile(r"(topic badlo|chhodo ene|kaik biju bolo)"),
    ]

    @classmethod
    def classify(
        cls,
        interruption_text: str,
        speech_duration_sec: float = 0.0,
        vad_confidence: float = 0.85,
    ) -> InterruptionClassificationResult:
        """Analyze and classify a user interruption utterance.

        Args:
            interruption_text: Transcribed user interruption speech.
            speech_duration_sec: Measured duration of the user speech.
            vad_confidence: VAD confidence probability for the utterance.

        Returns:
            InterruptionClassificationResult with type, confidence, and action.
        """
        raw = interruption_text.strip()
        if not raw:
            return InterruptionClassificationResult(
                interruption_type=InterruptionType.GENERAL,
                confidence=0.5,
                matched_phrase=None,
                reason="Empty utterance",
                suggested_action="standard_process",
            )

        norm = _normalize(raw)
        words = norm.split()
        word_count = len(words)

        # ─────────────────────────────────────────────────────────────────────
        # 1. Check TYPE D: Brief Acknowledgements (Backchannels)
        # ─────────────────────────────────────────────────────────────────────
        # Conditions: Short utterance (<= 3 words), recognized backchannel tokens,
        # and no question/correction triggers.
        if word_count <= 3:
            # Check exact match or token subset
            if norm in cls._ACKNOWLEDGEMENT_WORDS:
                logger.info("[INTERRUPTION_CLASSIFIER] Type D Acknowledgement detected: '%s'", raw)
                return InterruptionClassificationResult(
                    interruption_type=InterruptionType.ACKNOWLEDGEMENT,
                    confidence=0.95,
                    matched_phrase=norm,
                    reason=f"Brief backchannel token ('{norm}') with {word_count} words",
                    suggested_action="continue_playback",
                )
            # Check combined tokens like "ok yeah", "ha barabar", "haan theek hai"
            if all(w in cls._ACKNOWLEDGEMENT_WORDS for w in words):
                logger.info("[INTERRUPTION_CLASSIFIER] Type D Multi-token Acknowledgement: '%s'", raw)
                return InterruptionClassificationResult(
                    interruption_type=InterruptionType.ACKNOWLEDGEMENT,
                    confidence=0.90,
                    matched_phrase=norm,
                    reason=f"Multi-token conversational backchannel ('{norm}')",
                    suggested_action="continue_playback",
                )

        # ─────────────────────────────────────────────────────────────────────
        # 2. Check TYPE A: Corrections
        # ─────────────────────────────────────────────────────────────────────
        for pat in cls._CORRECTION_PATTERNS:
            m = pat.search(norm)
            if m:
                matched = m.group(0)
                logger.info("[INTERRUPTION_CLASSIFIER] Type A Correction detected: '%s' (match: '%s')", raw, matched)
                return InterruptionClassificationResult(
                    interruption_type=InterruptionType.CORRECTION,
                    confidence=0.92,
                    matched_phrase=matched,
                    reason="Matched explicit user correction pattern",
                    suggested_action="apply_correction",
                )

        # ─────────────────────────────────────────────────────────────────────
        # 3. Check TYPE B: Follow-ups
        # ─────────────────────────────────────────────────────────────────────
        for pat in cls._FOLLOW_UP_PATTERNS:
            m = pat.search(norm)
            if m:
                matched = m.group(0)
                logger.info("[INTERRUPTION_CLASSIFIER] Type B Follow-up detected: '%s' (match: '%s')", raw, matched)
                return InterruptionClassificationResult(
                    interruption_type=InterruptionType.FOLLOW_UP,
                    confidence=0.90,
                    matched_phrase=matched,
                    reason="Matched follow-up question/elaboration pattern",
                    suggested_action="elaborate_topic",
                )

        # ─────────────────────────────────────────────────────────────────────
        # 4. Check TYPE C: Topic Changes
        # ─────────────────────────────────────────────────────────────────────
        for pat in cls._TOPIC_CHANGE_PATTERNS:
            m = pat.search(norm)
            if m:
                matched = m.group(0)
                logger.info("[INTERRUPTION_CLASSIFIER] Type C Topic Change detected: '%s' (match: '%s')", raw, matched)
                return InterruptionClassificationResult(
                    interruption_type=InterruptionType.TOPIC_CHANGE,
                    confidence=0.91,
                    matched_phrase=matched,
                    reason="Matched topic change or abandonment pattern",
                    suggested_action="switch_topic",
                )

        # ─────────────────────────────────────────────────────────────────────
        # 5. Default / GENERAL
        # ─────────────────────────────────────────────────────────────────────
        logger.info("[INTERRUPTION_CLASSIFIER] General Interruption: '%s'", raw)
        return InterruptionClassificationResult(
            interruption_type=InterruptionType.GENERAL,
            confidence=0.75,
            matched_phrase=None,
            reason="Uncategorized speech input during assistant turn",
            suggested_action="standard_process",
        )
